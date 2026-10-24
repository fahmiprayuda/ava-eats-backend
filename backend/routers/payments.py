from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query
from datetime import datetime
from sqlalchemy.orm import Session

from database import get_db
from models.order import Order
from models.payment import Payment
from models.admin import Admin
from models.customer import Customer
from models.shipment import Shipment
from schemas.payment import PaymentRequest, PaymentVerifyRequest, GatewayPaymentRequest
from schemas.payment_response import PaymentResponse, GatewayPaymentResponse
from auth.dependencies import get_current_customer, require_admin
from utils.audit import create_audit_log
from services.midtrans import create_snap_transaction, get_transaction_status, sync_payment_status

router = APIRouter(
    prefix="/api/payments",
    tags=["Payments"]
)


@router.get("", response_model=List[PaymentResponse])
def get_payments(
    status: str = Query(None, description="Filter berdasarkan status payment"),
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(require_admin)
):
    query = db.query(Payment)

    if status:
        query = query.filter(Payment.status == status)

    payments = query.order_by(
        Payment.created_at.desc()
    ).all()

    return payments

@router.get(
    "/orders/{order_id}",
    response_model=List[PaymentResponse]
)
def get_order_payments(
    order_id: int,
    db: Session = Depends(get_db),
    current_customer: Customer = Depends(get_current_customer)
):
    order = db.query(Order).filter(
        Order.id == order_id
    ).first()

    if not order:
        raise HTTPException(
            status_code=404,
            detail="Order tidak ditemukan"
        )

    if order.customer_id != current_customer.id:
            raise HTTPException(
                status_code=403,
                detail="Anda tidak memiliki akses untuk melihat payment ini"
            )

    payments = db.query(Payment).filter(
        Payment.order_id == order_id
    ).order_by(
        Payment.created_at.desc()
    ).all()

    for p in payments:
        if p.status == "pending":
            sync_payment_status(db, p, order)

    return payments

@router.post(
    "/orders/{order_id}",
    response_model=PaymentResponse
)
def create_payment(
    order_id: int,
    data: PaymentRequest,
    db: Session = Depends(get_db),
    current_customer: Customer = Depends(get_current_customer)  
):
    # 1. Cari order
    order = db.query(Order).filter(
        Order.id == order_id
    ).first()

    if not order:
        raise HTTPException(
            status_code=404,
            detail="Order tidak ditemukan"
        )

    if order.customer_id != current_customer.id:
        raise HTTPException(
        status_code=403,
        detail="Anda tidak memiliki akses ke order ini"
    )

    # 2. Order harus masih pending
    if order.status != "pending":
        raise HTTPException(
            status_code=400,
            detail=(
                f"Order dengan status '{order.status}' "
                "tidak bisa melakukan pembayaran"
            )
        )

    # 3. Cek apakah sudah ada payment pending
    existing_payment = db.query(Payment).filter(
        Payment.order_id == order.id,
        Payment.status == "pending"
    ).first()

    if existing_payment:
        raise HTTPException(
            status_code=400,
            detail="Order sudah memiliki payment yang menunggu verifikasi"
        )

    # 4. Buat payment
    payment = Payment(
        order_id=order.id,
        payment_method=data.payment_method,
        amount=order.total_amount,
        payment_proof=data.payment_proof,
        status="pending"
    )

    db.add(payment)

    # Supaya payment.id langsung dibuat oleh database
    db.flush()

    create_audit_log(
        db=db,
        user_type="customer",
        user_id=current_customer.id,
        action="PAYMENT_CREATED",
        entity_type="Payment",
        entity_id=payment.id,
        description=f"Payment {order.order_code} "
                    f"has been created by customer {current_customer.name}"
    )

    db.commit()
    db.refresh(payment)

    return payment

@router.get("/{payment_id}", response_model=PaymentResponse)
def get_payment(
    payment_id: int,
    db: Session = Depends(get_db),
    current_customer: Customer = Depends(get_current_customer)
):
    payment = db.query(Payment).filter(
        Payment.id == payment_id
    ).first()

    if not payment:
        raise HTTPException(
            status_code=404,
            detail="Payment tidak ditemukan"
        )

    order = db.query(Order).filter(
        Order.id == payment.order_id
    ).first()

    if order.customer_id != current_customer.id:
        raise HTTPException(
        status_code=403,
        detail="Anda tidak memiliki akses ke payment ini"
    )

    return payment

@router.put(
    "/{payment_id}/verify",
    response_model=PaymentResponse
)
def verify_payment(
    payment_id: int,
    data: PaymentVerifyRequest,
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(require_admin)
    ):
    # 1. Cari payment
    payment = db.query(Payment).filter(
        Payment.id == payment_id
    ).first()

    if not payment:
        raise HTTPException(
            status_code=404,
            detail="Payment tidak ditemukan"
        )

    # 2. Payment harus masih pending
    if payment.status != "pending":
        raise HTTPException(
            status_code=400,
            detail=(
                f"Payment dengan status '{payment.status}' "
                "tidak bisa diverifikasi"
            )
        )

    # 3. Validasi status payment
    if data.status not in ["approved", "rejected"]:
        raise HTTPException(
            status_code=400,
            detail="Status payment harus approved atau rejected"
        )

    # 4. Ambil order
    order = db.query(Order).filter(
        Order.id == payment.order_id
    ).first()

    if not order:
        raise HTTPException(
            status_code=404,
            detail="Order tidak ditemukan"
        )

    # 5. Update payment
    payment.status = data.status

    if data.status == "approved":
        action = "PAYMENT_APPROVED"
        payment.verified_at = datetime.now()
    # Payment approved → order menjadi paid
        order.status = "paid"
    else:
        action = "PAYMENT_REJECTED"

    # Kalau rejected, order tetap pending

    # 6. Simpan semuanya
    create_audit_log(
        db=db,
        user_type="admin",
        user_id=current_admin.id,
        action=action,
        entity_type="Payment",
        entity_id=payment.id,
        description=f"Payment {order.order_code} "
                    f"has been {data.status} by admin {current_admin.username}"
    )

    db.commit()
    db.refresh(payment)

    return payment


@router.post(
    "/orders/{order_id}/gateway",
    response_model=GatewayPaymentResponse
)
def create_gateway_payment(
    order_id: int,
    data: GatewayPaymentRequest,
    db: Session = Depends(get_db),
    current_customer: Customer = Depends(get_current_customer)
):

    # 1. Cari order
    order = db.query(Order).filter(
        Order.id == order_id
    ).first()

    if not order:
        raise HTTPException(
            status_code=404,
            detail="Order tidak ditemukan"
        )

    # 2. Ownership
    if order.customer_id != current_customer.id:
        raise HTTPException(
            status_code=403,
            detail="Anda tidak memiliki akses ke order ini"
        )

    # 3. Order harus pending
    if order.status != "pending":
        raise HTTPException(
            status_code=400,
            detail=(
                f"Order dengan status '{order.status}' "
                "tidak bisa melakukan pembayaran"
            )
        )

    
    # =====================================================
    # 4. VALIDASI FULFILLMENT & SHIPPING
    # =====================================================

    if order.fulfillment_method == "delivery":

        # Delivery wajib punya shipping yang sudah dipilih
        shipment = (
            db.query(Shipment)
            .filter(Shipment.order_id == order.id)
            .first()
        )

        if not shipment or not shipment.courier or not shipment.service:
            raise HTTPException(
                status_code=400,
                detail="Pilih shipping terlebih dahulu sebelum pembayaran"
            )

        if shipment.shipping_cost is None:
            raise HTTPException(
                status_code=400,
                detail="Ongkos kirim belum ditentukan"
            )

        if shipment.shipping_cost != order.shipping_cost:
            raise HTTPException(
                status_code=400,
                detail="Ongkos kirim tidak konsisten dengan order"
            )

        expected_grand_total = max(
            0,
            order.total_amount
            + (order.shipping_cost or 0)
            + (order.packaging_fee or 0)
            - (order.discount_amount or 0)
        )
        if order.grand_total != expected_grand_total:
            raise HTTPException(
                status_code=400,
                detail="Grand total order tidak valid"
            )

    elif order.fulfillment_method == "pickup":

        # Pickup tidak membutuhkan kurir atau shipment
        order.shipping_cost = 0
        order.grand_total = max(
            0,
            order.total_amount
            + (order.packaging_fee or 0)
            - (order.discount_amount or 0)
        )

    else:
        raise HTTPException(
            status_code=400,
            detail="Metode fulfillment tidak valid"
        )



    # =====================================================
    # 5. CEK PAYMENT MIDTRANS YANG MASIH PENDING
    # =====================================================

    existing_payment = db.query(Payment).filter(
        Payment.order_id == order.id,
        Payment.gateway == "midtrans",
        Payment.status == "pending"
    ).order_by(
        Payment.id.desc()
    ).first()

    if existing_payment:

        # Pastikan payment lama punya gateway_order_id
        if not existing_payment.gateway_order_id:
            raise HTTPException(
                status_code=500,
                detail=(
                    "Payment Midtrans lama tidak memiliki "
                    "gateway_order_id"
                )
            )

        # =================================================
        # 6. CEK STATUS AKTUAL KE MIDTRANS
        # =================================================

        try:
            midtrans_status = get_transaction_status(
                existing_payment.gateway_order_id
            )

        except Exception as e:
            raise HTTPException(
                status_code=502,
                detail=(
                    "Gagal mengecek status payment ke Midtrans: "
                    f"{str(e)}"
                )
            )

        transaction_status = midtrans_status.get(
            "transaction_status"
        )
        if not transaction_status or midtrans_status.get("status_code") in ["404", 404]:
            transaction_status = "not_initiated"

        # Cek apakah payment lama masih dalam window berlaku (15 menit)
        is_still_fresh = False
        if existing_payment.created_at:
            age_seconds = (datetime.now() - existing_payment.created_at).total_seconds()
            is_still_fresh = age_seconds < (15 * 60)

        # =================================================
        # 7. MASIH PENDING DI MIDTRANS / BELUM DI-INITIATE
        # =================================================

        if transaction_status in ["pending", "not_initiated"]:

            if is_still_fresh and existing_payment.gateway_token:
                # Return payment lama yang masih aktif agar customer bisa melanjutkan pembayaran
                return {
                    "payment_id": existing_payment.id,
                    "order_id": order.id,
                    "order_code": order.order_code,
                    "payment_method": existing_payment.payment_method,
                    "amount": existing_payment.amount,
                    "status": existing_payment.status,
                    "payment_url": existing_payment.payment_url,
                    "gateway_token": existing_payment.gateway_token,
                    "expires_at": existing_payment.expires_at
                }

            # Jika sudah expired / lewat waktu, tandai expired agar dibuat transaksi baru
            existing_payment.status = "expired"
            create_audit_log(
                db=db,
                user_type="system",
                user_id=0,
                action="PAYMENT_EXPIRED",
                entity_type="payment",
                entity_id=existing_payment.id,
                description=(
                    f"Payment {order.order_code} "
                    f"expired (lewat batas waktu) saat percobaan pembayaran ulang"
                )
            )
            db.flush()

        # =================================================
        # 8. SUDAH BERHASIL DIBAYAR
        # =================================================

        elif transaction_status in [
            "settlement",
            "capture"
        ]:

            existing_payment.status = "approved"

            order.status = "paid"

            create_audit_log(
                db=db,
                user_type="system",
                user_id=0,
                action="PAYMENT_APPROVED",
                entity_type="payment",
                entity_id=existing_payment.id,
                description=(
                    f"Payment {order.order_code} "
                    f"approved saat pengecekan status Midtrans"
                )
            )

            db.commit()

            return {
                "payment_id": existing_payment.id,
                "order_id": order.id,
                "order_code": order.order_code,
                "payment_method": existing_payment.payment_method,
                "amount": existing_payment.amount,
                "status": existing_payment.status,
                "payment_url": existing_payment.payment_url,
                "gateway_token": existing_payment.gateway_token,
                "expires_at": existing_payment.expires_at
            }

        # =================================================
        # 9. EXPIRED
        # =================================================

        elif transaction_status == "expire":

            existing_payment.status = "expired"

            create_audit_log(
                db=db,
                user_type="system",
                user_id=0,
                action="PAYMENT_EXPIRED",
                entity_type="payment",
                entity_id=existing_payment.id,
                description=(
                    f"Payment {order.order_code} "
                    f"expired saat pengecekan status Midtrans"
                )
            )

            db.flush()

        # =================================================
        # 10. REJECTED
        # =================================================

        elif transaction_status in [
            "deny",
            "cancel",
            "failure"
        ]:

            existing_payment.status = "rejected"

            create_audit_log(
                db=db,
                user_type="system",
                user_id=0,
                action="PAYMENT_REJECTED",
                entity_type="payment",
                entity_id=existing_payment.id,
                description=(
                    f"Payment {order.order_code} "
                    f"rejected saat pengecekan status Midtrans "
                    f"dengan status {transaction_status}"
                )
            )

            db.flush()

        else:
            # Jika status tidak dikenali atau None tetapi payment lama masih fresh & punya gateway_token
            if is_still_fresh and existing_payment.gateway_token:
                return {
                    "payment_id": existing_payment.id,
                    "order_id": order.id,
                    "order_code": order.order_code,
                    "payment_method": existing_payment.payment_method,
                    "amount": existing_payment.amount,
                    "status": existing_payment.status,
                    "payment_url": existing_payment.payment_url,
                    "gateway_token": existing_payment.gateway_token,
                    "expires_at": existing_payment.expires_at
                }

            # Jika lewat waktu/tidak fresh, tandai expired agar sistem otomatis membuat transaksi baru
            existing_payment.status = "expired"
            create_audit_log(
                db=db,
                user_type="system",
                user_id=0,
                action="PAYMENT_EXPIRED",
                entity_type="payment",
                entity_id=existing_payment.id,
                description=(
                    f"Payment {order.order_code} "
                    f"expired (lewat batas waktu) dan dibuat transaksi baru"
                )
            )
            db.flush()

    # =====================================================
    # 11. BUAT PAYMENT BARU
    # =====================================================

    payment = Payment(
        order_id=order.id,
        payment_method=data.payment_method,
        gateway="midtrans",
        amount=order.grand_total,
        status="pending"
    )

    db.add(payment)

    # Supaya payment.id tersedia
    db.flush()

    # =====================================================
    # 12. BUAT GATEWAY ORDER ID UNIK
    # =====================================================

    gateway_order_id = (
        f"{order.order_code}-P{payment.id}"
    )

    payment.gateway_order_id = gateway_order_id

    # =====================================================
    # 13. CREATE TRANSACTION DI MIDTRANS
    # =====================================================

    try:

        midtrans_result = create_snap_transaction(
            order_id=gateway_order_id,
            gross_amount=order.grand_total,
            customer_name=current_customer.name,
            customer_phone=current_customer.phone,
            payment_method=data.payment_method
        )

    except Exception as e:

        db.rollback()

        raise HTTPException(
            status_code=502,
            detail=str(e)
        )

    # =====================================================
    # 14. SIMPAN RESPONSE MIDTRANS
    # =====================================================

    payment.gateway_token = midtrans_result["token"]

    payment.payment_url = midtrans_result["redirect_url"]

    # =====================================================
    # 15. AUDIT
    # =====================================================

    create_audit_log(
        db=db,
        user_type="customer",
        user_id=current_customer.id,
        action="PAYMENT_CREATED",
        entity_type="payment",
        entity_id=payment.id,
        description=(
            f"Payment {order.order_code} "
            f"has been created through Midtrans "
            f"with gateway order ID "
            f"{gateway_order_id} "
            f"by customer {current_customer.name}"
        )
    )

    # =====================================================
    # 16. COMMIT
    # =====================================================

    db.commit()

    db.refresh(payment)

    return {
        "payment_id": payment.id,
        "order_id": order.id,
        "order_code": order.order_code,
        "payment_method": payment.payment_method,
        "amount": payment.amount,
        "status": payment.status,
        "payment_url": payment.payment_url,
        "gateway_token": payment.gateway_token,
        "expires_at": payment.expires_at
    }
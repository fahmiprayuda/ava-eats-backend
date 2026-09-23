from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query
from datetime import datetime
from sqlalchemy.orm import Session

from database import get_db
from models.order import Order
from models.payment import Payment
from models.admin import Admin
from models.customer import Customer
from schemas.payment import PaymentRequest, PaymentVerifyRequest
from schemas.payment_response import PaymentResponse
from auth.dependencies import get_current_customer, require_admin
from utils.audit import create_audit_log

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


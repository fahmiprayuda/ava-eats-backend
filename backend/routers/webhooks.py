from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Body, Request
import hmac
from sqlalchemy.orm import Session

from database import get_db
from models.order import Order
from models.payment import Payment

from services.midtrans import verify_midtrans_signature
from utils.audit import create_audit_log
from services.payment_status import is_final_payment_status

from config.biteship import (
    BITESHIP_WEBHOOK_SECRET,
    BITESHIP_WEBHOOK_HEADER,
)
from models.shipment import Shipment
from datetime import datetime

router = APIRouter(
    prefix="/api/webhooks",
    tags=["Webhooks"]
)




@router.post("/biteship")
def biteship_webhook(
    request: Request,
    payload: dict = Body(default={}),
    db: Session = Depends(get_db),
):
    print("=== BITESHIP WEBHOOK RECEIVED ===")
    print("Payload:", payload)

    # 1. Validasi request kosong saat instalasi
    if not payload:
        return {"message": "ok"}

    # 2. Verifikasi secret
    if not BITESHIP_WEBHOOK_SECRET:
        raise HTTPException(
            status_code=503,
            detail="Biteship webhook secret belum dikonfigurasi",
        )

    received_secret = request.headers.get(
        BITESHIP_WEBHOOK_HEADER
    )

    if not received_secret or not hmac.compare_digest(
        received_secret,
        BITESHIP_WEBHOOK_SECRET,
    ):
        raise HTTPException(
            status_code=401,
            detail="Biteship webhook tidak terautentikasi",
        )

    # 3. Validasi event
    event = payload.get("event")
    biteship_order_id = payload.get("order_id")

    if event not in [
        "order.status",
        "order.waybill_id",
        "order.price",
    ]:
        raise HTTPException(
            status_code=400,
            detail="Event Biteship tidak dikenal",
        )

    if not biteship_order_id:
        raise HTTPException(
            status_code=400,
            detail="Biteship order ID tidak tersedia",
        )

    # 4. Cari shipment
    shipment = (
        db.query(Shipment)
        .filter(
            Shipment.biteship_order_id == biteship_order_id
        )
        .first()
    )

    if not shipment:
        raise HTTPException(
            status_code=404,
            detail="Shipment tidak ditemukan",
        )

    order = shipment.order

    if not order:
        raise HTTPException(
            status_code=404,
            detail="Order tidak ditemukan",
        )

    changes = []

    # Urutan status normal pengiriman.
    # Status dengan urutan lebih rendah tidak boleh
    # menimpa status normal yang sudah lebih maju.
    status_priority = {
        "confirmed": 0,
        "allocated": 1,
        "picking_up": 2,
        "picked": 3,
        "in_transit": 4,
        "dropping_off": 5,
        "delivered": 6,
    }

    # Status terminal: perubahan berikutnya memerlukan
    # rekonsiliasi/manual review jika statusnya berbeda.
    terminal_statuses = {
        "delivered",
        "courier_not_found",
        "cancelled",
        "canceled",
        "rejected",
        "returned",
        "failed",
    }

    try:
        # 5. Sinkronisasi nomor resi
        if event in ["order.waybill_id", "order.status"]:
            waybill = (
                payload.get("courier_waybill_id")
                or payload.get("waybill_id")
            )

            if waybill and shipment.tracking_number != waybill:
                shipment.tracking_number = waybill
                changes.append("Nomor resi diperbarui")

        # 6. Proses status pengiriman
        if event == "order.status":
            new_status = payload.get("status")

            if not new_status:
                raise HTTPException(
                    status_code=400,
                    detail="Status pengiriman tidak tersedia",
                )

            new_status = new_status.lower()
            old_status = (shipment.status or "").lower()

            # Abaikan status yang belum kita kenali,
            # tetapi tetap balas 200 agar tidak terjadi
            # retry terus-menerus untuk event tersebut.
            if (
                new_status not in status_priority
                and new_status not in terminal_statuses
            ):
                changes.append(
                    f"Status belum didukung: {new_status}"
                )

            else:
                # Jangan mengubah status terminal ke status
                # lain secara otomatis.
                is_terminal_conflict = (
                    old_status in terminal_statuses
                    and new_status != old_status
                )

                # Jangan mundur dari status normal yang lebih maju.
                is_regression = (
                    old_status in status_priority
                    and new_status in status_priority
                    and status_priority[new_status]
                    < status_priority[old_status]
                )

                if is_terminal_conflict or is_regression:
                    changes.append(
                        f"Status {new_status} diabaikan; "
                        f"status tersimpan tetap {old_status}"
                    )

                elif old_status != new_status:
                    shipment.status = new_status

                    changes.append(
                        f"Status berubah: {old_status} -> {new_status}"
                    )

                    create_audit_log(
                        db=db,
                        user_type="system",
                        user_id=0,
                        action="SHIPMENT_STATUS_UPDATED",
                        entity_type="shipment",
                        entity_id=shipment.id,
                        description=(
                            f"Shipment order {order.order_code} "
                            f"berubah dari {old_status} "
                            f"ke {new_status}"
                        ),
                    )

                # Isi waktu hanya berdasarkan status aktual
                # yang tersimpan, bukan event yang diabaikan.
                current_status = (shipment.status or "").lower()

                if current_status in {
                    "picked",
                    "in_transit",
                    "dropping_off",
                    "delivered",
                } and shipment.shipped_at is None:
                    shipment.shipped_at = datetime.now()

                if current_status == "delivered":
                    if shipment.delivered_at is None:
                        shipment.delivered_at = datetime.now()

                    # Order yang dibatalkan tidak boleh
                    # otomatis diaktifkan kembali.
                    if order.status != "cancelled":
                        order.status = "done"

        # 7. Event harga diterima, tetapi belum mengubah
        # ongkir atau tagihan pelanggan secara otomatis.
        elif event == "order.price":
            changes.append(
                "Event harga diterima; tidak ada perubahan tagihan"
            )

        # 8. Commit
        db.commit()
        db.refresh(shipment)

    except Exception:
        db.rollback()
        raise

    return {
        "message": "Webhook Biteship berhasil diproses",
        "event": event,
        "order_code": order.order_code,
        "shipment": {
            "id": shipment.id,
            "biteship_order_id": shipment.biteship_order_id,
            "tracking_number": shipment.tracking_number,
            "status": shipment.status,
            "shipped_at": (
                shipment.shipped_at.isoformat()
                if shipment.shipped_at else None
            ),
            "delivered_at": (
                shipment.delivered_at.isoformat()
                if shipment.delivered_at else None
            ),
        },
        "changes": changes,
    }



@router.post("/midtrans")
def midtrans_webhook(
    notification: dict,
    db: Session = Depends(get_db)
):

    order_code = notification.get("order_id")
    transaction_id = notification.get("transaction_id")
    transaction_status = notification.get("transaction_status")
    status_code = notification.get("status_code")
    gross_amount = notification.get("gross_amount")
    signature_key = notification.get("signature_key")
    fraud_status = notification.get("fraud_status")

    # =========================
    # 1. VALIDASI PAYLOAD
    # =========================

    if not all([
        order_code,
        transaction_id,
        transaction_status,
        status_code,
        gross_amount,
        signature_key
    ]):
        raise HTTPException(
            status_code=400,
            detail="Notification Midtrans tidak lengkap"
        )

    # =========================
    # 2. VALIDASI SIGNATURE
    # =========================

    is_valid = verify_midtrans_signature(
        order_id=order_code,
        status_code=status_code,
        gross_amount=gross_amount,
        signature_key=signature_key
    )

    if not is_valid:
        raise HTTPException(
            status_code=401,
            detail="Signature Midtrans tidak valid"
        )

    # =========================
    # 3. CARI PAYMENT BERDASARKAN
    #    GATEWAY ORDER ID
    # =========================

    payment = db.query(Payment).filter(
        Payment.gateway == "midtrans",
        Payment.gateway_order_id == order_code
    ).first()

    if not payment:
        raise HTTPException(
            status_code=404,
            detail="Payment Midtrans tidak ditemukan"
        )

    # =========================
    # 4. CARI ORDER DARI PAYMENT
    # =========================

    order = db.query(Order).filter(
        Order.id == payment.order_id
    ).first()

    if not order:
        raise HTTPException(
            status_code=404,
            detail="Order tidak ditemukan"
        )

    # =========================
    # 5. VALIDASI NOMINAL
    # =========================

    if Decimal(gross_amount) != Decimal(payment.amount):

        raise HTTPException(
            status_code=400,
            detail="Nominal payment tidak sesuai"
        )

    # =========================
    # 6. SIMPAN TRANSACTION ID
    # =========================

    payment.gateway_transaction_id = transaction_id

    # =========================
    # 7. HANDLE STATUS MIDTRANS
    # =========================

    
    if transaction_status in ["settlement", "capture"]:

        # 1. Pastikan fraud status aman
        if fraud_status and fraud_status != "accept":
            db.commit()
            return {
                "message": "Transaction belum dapat dianggap sukses"
            }

        # 2. Approval hanya sekali
        newly_approved = payment.status != "approved"

        if newly_approved:
            payment.status = "approved"

            create_audit_log(
                db=db,
                user_type="system",
                user_id=0,
                action="PAYMENT_APPROVED",
                entity_type="payment",
                entity_id=payment.id,
                description=(
                    f"Payment {order.order_code} "
                    "automatically approved by Midtrans"
                )
            )

        # 3. Jangan aktifkan kembali order yang dibatalkan
        if order.status == "cancelled":

            if newly_approved:
                create_audit_log(
                    db=db,
                    user_type="system",
                    user_id=0,
                    action="PAYMENT_APPROVED_ORDER_CANCELLED",
                    entity_type="order",
                    entity_id=order.id,
                    description=(
                        f"Payment {payment.id} berhasil dibayar "
                        f"setelah order {order.order_code} dibatalkan. "
                        "Perlu rekonsiliasi pembayaran."
                    )
                )

        else:
            order.status = "paid"


    elif transaction_status == "pending":

        if not is_final_payment_status(payment.status):
            payment.status = "pending"


    elif transaction_status == "expire":

        if not is_final_payment_status(payment.status):
            payment.status = "expired"

            create_audit_log(
                db=db,
                user_type="system",
                user_id=0,
                action="PAYMENT_EXPIRED",
                entity_type="payment",
                entity_id=payment.id,
                description=(
                    f"Payment {order.order_code} "
                    "expired on Midtrans"
                )
            )


    elif transaction_status in ["deny", "cancel", "failure"]:

        if not is_final_payment_status(payment.status):
            payment.status = "rejected"

            create_audit_log(
                db=db,
                user_type="system",
                user_id=0,
                action="PAYMENT_REJECTED",
                entity_type="payment",
                entity_id=payment.id,
                description=(
                    f"Payment {order.order_code} "
                    "was rejected by Midtrans "
                    f"with status {transaction_status}"
                )
            )

    # =========================
    # 8. COMMIT
    # =========================

    db.commit()

    return {
        "message": "Notification Midtrans berhasil diproses"
    }
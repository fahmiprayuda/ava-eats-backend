import hmac
import requests
import hashlib
from datetime import datetime

from config.midtrans import (
    MIDTRANS_SERVER_KEY,
    MIDTRANS_SNAP_BASE_URL,
    MIDTRANS_API_BASE_URL,
)


def create_snap_transaction(
    order_id: str,
    gross_amount: int,
    customer_name: str,
    customer_phone: str,
    payment_method: str = "other_qris",
    expiry_minutes: int = 15,
):
    url = f"{MIDTRANS_SNAP_BASE_URL}/snap/v1/transactions"

    payload = {
        "transaction_details": {
            "order_id": order_id,
            "gross_amount": gross_amount,
        },
        "customer_details": {
            "first_name": customer_name,
            "phone": customer_phone,
        },
        "expiry": {
            "duration": expiry_minutes,
            "unit": "minutes",
        },
    }

    # Konfigurasi channel pembayaran Midtrans
    if payment_method == "bank_transfer":
        payload["enabled_payments"] = [
            "bca_va",
            "bni_va",
            "bri_va",
            "echannel",
            "permata_va",
            "cimb_va",
            "other_va",
        ]
    elif payment_method in ["qris", "other_qris"]:
        payload["enabled_payments"] = ["other_qris", "gopay", "shopeepay"]
    elif payment_method and payment_method != "all":
        payload["enabled_payments"] = [payment_method]

    response = requests.post(
        url,
        json=payload,
        auth=(MIDTRANS_SERVER_KEY, ""),
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        timeout=30,
    )

    if response.status_code not in [200, 201]:
        raise Exception(
            f"Midtrans error: {response.text}"
        )

    return response.json()


def get_transaction_status(order_id: str):
    url = f"{MIDTRANS_API_BASE_URL}/v2/{order_id}/status"

    response = requests.get(
        url,
        auth=(MIDTRANS_SERVER_KEY, ""),
        headers={
            "Accept": "application/json"
        },
        timeout=10,
    )

    if response.status_code == 404:
        return {
            "status_code": "404",
            "transaction_status": "not_initiated",
            "status_message": "Transaction has not been initiated in Midtrans"
        }

    if response.status_code != 200:
        raise Exception(
            f"Midtrans status error ({response.status_code}): {response.text}"
        )

    return response.json()


def verify_midtrans_signature(
    order_id: str,
    status_code: str,
    gross_amount: str,
    signature_key: str
):
    raw_string = (
        f"{order_id}"
        f"{status_code}"
        f"{gross_amount}"
        f"{MIDTRANS_SERVER_KEY}"
    )

    calculated_signature = hashlib.sha512(
        raw_string.encode("utf-8")
    ).hexdigest()

    return hmac.compare_digest(
        calculated_signature,
        signature_key
    )


def sync_payment_status(db, payment, order=None):
    """
    Sinkronisasi status transaksi dari Midtrans ke database secara real-time.
    Berguna ketika webhook belum diterima (misal di localhost/development)
    atau saat user me-refresh halaman order/checkout.
    """
    if not payment or payment.gateway != "midtrans" or not payment.gateway_order_id:
        return payment

    # Jika sudah status final, tidak perlu query Midtrans lagi
    if payment.status in ["approved", "expired", "rejected"]:
        return payment

    try:
        status_data = get_transaction_status(payment.gateway_order_id)
        tx_status = status_data.get("transaction_status")

        if tx_status in ["settlement", "capture"]:
            fraud = status_data.get("fraud_status")
            if not fraud or fraud == "accept":
                payment.status = "approved"
                payment.verified_at = datetime.now()
                payment.gateway_transaction_id = (
                    status_data.get("transaction_id") or payment.gateway_transaction_id
                )

                # Update order status jika belum paid
                if not order:
                    from models.order import Order
                    order = db.query(Order).filter(Order.id == payment.order_id).first()

                if order and order.status != "cancelled":
                    order.status = "paid"

                db.commit()

        elif tx_status == "expire":
            payment.status = "expired"
            db.commit()

        elif tx_status in ["deny", "cancel", "failure"]:
            payment.status = "rejected"
            db.commit()

        elif tx_status in ["not_initiated", "pending"]:
            # Jika sudah lebih dari 15 menit, tandai expired
            if payment.created_at and (datetime.now() - payment.created_at).total_seconds() > (15 * 60):
                payment.status = "expired"
                db.commit()

    except Exception as e:
        print(f"Warning: gagal sync status Midtrans untuk payment {payment.id}: {e}")

    return payment

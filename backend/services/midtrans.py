import hmac
import requests
import hashlib

from config.midtrans import (
    MIDTRANS_SERVER_KEY,
    MIDTRANS_BASE_URL
)


def create_snap_transaction(
    order_id: str,
    gross_amount: int,
    customer_name: str,
    customer_phone: str,
    payment_method: str = "other_qris"
):
    url = f"{MIDTRANS_BASE_URL}/snap/v1/transactions"

    payload = {
        "transaction_details": {
            "order_id": order_id,
            "gross_amount": gross_amount
        },
        "customer_details": {
            "first_name": customer_name,
            "phone": customer_phone
        },
        "enabled_payments": [
            payment_method
        ]
    }

    response = requests.post(
        url,
        json=payload,
        auth=(MIDTRANS_SERVER_KEY, ""),
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
    )

    if response.status_code not in [200, 201]:
        raise Exception(
            f"Midtrans error: {response.text}"
        )

    return response.json()

def get_transaction_status(order_id: str):
    url = f"{MIDTRANS_BASE_URL}/v2/{order_id}/status"

    response = requests.get(
        url,
        auth=(MIDTRANS_SERVER_KEY, ""),
        headers={
            "Accept": "application/json"
        }
    )

    if response.status_code != 200:
        raise Exception(
            f"Midtrans status error: {response.text}"
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
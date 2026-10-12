import hashlib
import os
import requests
from dotenv import load_dotenv

load_dotenv()

SERVER_KEY = os.getenv("MIDTRANS_SERVER_KEY")

# =========================
# DATA TEST
# =========================

ORDER_CODE = "ORDER-2026-09-25-01"
GROSS_AMOUNT = "30000"

STATUS_CODE = "200"

TRANSACTION_ID = "TEST-MIDTRANS-001"

TRANSACTION_STATUS = "expire"


# =========================
# GENERATE SIGNATURE
# =========================

raw_string = (
    f"{ORDER_CODE}"
    f"{STATUS_CODE}"
    f"{GROSS_AMOUNT}"
    f"{SERVER_KEY}"
)

signature = hashlib.sha512(
    raw_string.encode("utf-8")
).hexdigest()


# =========================
# PAYLOAD
# =========================

payload = {
    "order_id": ORDER_CODE,
    "transaction_id": TRANSACTION_ID,
    "transaction_status": TRANSACTION_STATUS,
    "status_code": STATUS_CODE,
    "gross_amount": GROSS_AMOUNT,
    "signature_key": signature,
    "fraud_status": "accept",
    "payment_type": "qris"
}


# =========================
# SEND WEBHOOK
# =========================

print("ORDER_CODE:", ORDER_CODE)
print("GROSS_AMOUNT:", GROSS_AMOUNT)
print("SIGNATURE:", signature)
print("PAYLOAD:", payload)

response = requests.post(
    "http://127.0.0.1:8000/api/webhooks/midtrans",
    json=payload
)


print("STATUS:", response.status_code)
print("RESPONSE:", response.text)
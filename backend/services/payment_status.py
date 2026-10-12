FINAL_PAYMENT_STATUSES = [
    "approved",
    "expired",
    "rejected"
]


def is_final_payment_status(status: str) -> bool:
    return status in FINAL_PAYMENT_STATUSES
import os

from dotenv import load_dotenv

load_dotenv()

MIDTRANS_SERVER_KEY = os.getenv("MIDTRANS_SERVER_KEY")
MIDTRANS_CLIENT_KEY = os.getenv("MIDTRANS_CLIENT_KEY")
MIDTRANS_IS_PRODUCTION = os.getenv(
    "MIDTRANS_IS_PRODUCTION",
    "false"
).lower() == "true"

if not MIDTRANS_SERVER_KEY:
    raise RuntimeError(
        "MIDTRANS_SERVER_KEY belum diset di environment"
    )

if not MIDTRANS_CLIENT_KEY:
    raise RuntimeError(
        "MIDTRANS_CLIENT_KEY belum diset di environment"
    )

if MIDTRANS_IS_PRODUCTION:
    MIDTRANS_SNAP_BASE_URL = "https://app.midtrans.com"
    MIDTRANS_API_BASE_URL = "https://api.midtrans.com"
    MIDTRANS_BASE_URL = "https://app.midtrans.com"
else:
    MIDTRANS_SNAP_BASE_URL = "https://app.sandbox.midtrans.com"
    MIDTRANS_API_BASE_URL = "https://api.sandbox.midtrans.com"
    MIDTRANS_BASE_URL = "https://app.sandbox.midtrans.com"

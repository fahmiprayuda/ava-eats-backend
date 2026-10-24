import os
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARENT_DIR = os.path.dirname(BASE_DIR)
for env_path in [os.path.join(PARENT_DIR, ".env"), os.path.join(BASE_DIR, ".env"), ".env"]:
    if os.path.exists(env_path):
        load_dotenv(env_path)
        break
else:
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

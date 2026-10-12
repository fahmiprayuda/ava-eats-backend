import os
from dotenv import load_dotenv

load_dotenv()

BITESHIP_API_KEY = os.getenv("BITESHIP_API_KEY")
BITESHIP_BASE_URL = os.getenv(
    "BITESHIP_BASE_URL",
    "https://api.biteship.com"
)

if not BITESHIP_API_KEY:
    raise RuntimeError("BITESHIP_API_KEY belum diset di .env")


STORE_NAME = os.getenv("STORE_NAME")
STORE_PHONE = os.getenv("STORE_PHONE")
STORE_ADDRESS = os.getenv("STORE_ADDRESS")
STORE_POSTAL_CODE = os.getenv("STORE_POSTAL_CODE")
STORE_LATITUDE = float(os.getenv("STORE_LATITUDE", "0"))
STORE_LONGITUDE = float(os.getenv("STORE_LONGITUDE", "0"))


BITESHIP_WEBHOOK_HEADER = os.getenv(
    "BITESHIP_WEBHOOK_HEADER",
    "x-biteship-webhook-secret",
)

BITESHIP_WEBHOOK_SECRET = os.getenv(
    "BITESHIP_WEBHOOK_SECRET",
    "",
)


if not STORE_NAME:
    raise RuntimeError("STORE_NAME belum diset di .env")

if not STORE_PHONE:
    raise RuntimeError("STORE_PHONE belum diset di .env")

if not STORE_ADDRESS:
    raise RuntimeError("STORE_ADDRESS belum diset di .env")

if not STORE_POSTAL_CODE:
    raise RuntimeError("STORE_POSTAL_CODE belum diset di .env")
import os
from dotenv import load_dotenv

load_dotenv()

# WhatsApp Gateway Configurations (Fonnte / Waha / Generic)
WHATSAPP_PROVIDER = os.getenv("WHATSAPP_PROVIDER", "fonnte").lower()
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN") or os.getenv("FONNTE_TOKEN", "")
WHATSAPP_GATEWAY_URL = os.getenv(
    "WHATSAPP_GATEWAY_URL",
    "https://api.fonnte.com/send" if WHATSAPP_PROVIDER == "fonnte" else ""
)

# Admin Phone to receive internal notifications
WHATSAPP_ADMIN_PHONE = os.getenv("WHATSAPP_ADMIN_PHONE") or os.getenv("STORE_PHONE", "082213232456")

# Store details for notifications
STORE_NAME = os.getenv("STORE_NAME", "Ava Eats")
STORE_PHONE = os.getenv("STORE_PHONE", "082213232456")
STORE_ADDRESS = os.getenv(
    "STORE_ADDRESS",
    "Cluster The Awa, Blok B1 No 27, Ciriung, Kec. Cibinong, Kabupaten Bogor, Jawa Barat"
)

# Base URL for tracking links
FRONTEND_BASE_URL = os.getenv("FRONTEND_BASE_URL", "http://localhost:3000")

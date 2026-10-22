import logging
import re
import requests
from typing import Optional

from config.whatsapp import (
    WHATSAPP_PROVIDER,
    WHATSAPP_TOKEN,
    WHATSAPP_GATEWAY_URL,
    WHATSAPP_ADMIN_PHONE,
    STORE_NAME,
    STORE_PHONE,
    STORE_ADDRESS,
    FRONTEND_BASE_URL,
)

logger = logging.getLogger("whatsapp_service")


def normalize_phone_number(phone: str) -> str:
    """
    Normalisasi nomor telepon Indonesia ke format internasional tanpa '+':
    08123456789 -> 628123456789
    +628123456789 -> 628123456789
    628123456789 -> 628123456789
    """
    if not phone:
        return ""
    # Hapus semua karakter non-digit
    cleaned = re.sub(r"\D", "", phone)
    if cleaned.startswith("0"):
        cleaned = "62" + cleaned[1:]
    elif cleaned.startswith("8"):
        cleaned = "62" + cleaned
    return cleaned


def send_whatsapp_message(target_phone: str, message: str) -> bool:
    """
    Kirim pesan WhatsApp melalui Provider Gateway (Fonnte / Waha).
    Jika belum ada token yang diset di .env, pesan akan di-log secara rapi (Mock Mode)
    sehingga sistem tetap berjalan stabil 100% tanpa error.
    """
    normalized = normalize_phone_number(target_phone)
    if not normalized:
        logger.warning(f"[WA] Nomor tujuan tidak valid: {target_phone}")
        return False

    # ── MOCK / DEV MODE JIKA BELUM ADA TOKEN GATEWAY ────────────────────────
    if not WHATSAPP_TOKEN:
        print("\n" + "=" * 60)
        print(f"📲 [WHATSAPP MOCK GATEWAY] To: {normalized} ({target_phone})")
        print("-" * 60)
        print(message.strip())
        print("=" * 60 + "\n")
        return True

    # ── LIVE GATEWAY DISPATCH ────────────────────────────────────────────────
    try:
        if WHATSAPP_PROVIDER == "fonnte":
            url = WHATSAPP_GATEWAY_URL or "https://api.fonnte.com/send"
            response = requests.post(
                url,
                headers={"Authorization": WHATSAPP_TOKEN},
                data={
                    "target": normalized,
                    "message": message.strip(),
                    "countryCode": "62",
                },
                timeout=15,
            )
            res_json = response.json() if response.status_code == 200 else {}
            if response.status_code == 200 and res_json.get("status"):
                print(f"✅ [WA Fonnte] Berhasil terkirim ke {normalized} | Target: {target_phone}")
                logger.info(f"[WA Fonnte] Berhasil terkirim ke {normalized}")
                return True
            else:
                print(f"❌ [WA Fonnte] Gagal kirim ke {normalized}: {response.text}")
                logger.error(f"[WA Fonnte] Gagal kirim ke {normalized}: {response.text}")
                return False

        elif WHATSAPP_PROVIDER == "waha":
            url = f"{WHATSAPP_GATEWAY_URL.rstrip('/')}/api/sendText"
            response = requests.post(
                url,
                json={
                    "chatId": f"{normalized}@c.us",
                    "text": message.strip(),
                },
                timeout=15,
            )
            if response.status_code in [200, 201]:
                logger.info(f"[WA Waha] Berhasil terkirim ke {normalized}")
                return True
            else:
                logger.error(f"[WA Waha] Gagal kirim ke {normalized}: {response.text}")
                return False

        else:
            logger.warning(f"[WA] Provider tidak dikenal: {WHATSAPP_PROVIDER}")
            return False

    except Exception as e:
        logger.error(f"[WA Error] Gagal mengirim pesan ke {normalized}: {str(e)}")
        return False


# =============================================================================
# NOTIFICATION TEMPLATE BUILDERS
# =============================================================================

def notify_order_paid(order, customer=None, items=None):
    """
    Trigger saat pembayaran pesanan terverifikasi lunas:
    1. Kirim notifikasi konfirmasi ke Customer
    2. Kirim alert ke Admin toko
    """
    customer_phone = getattr(order, "phone", None) or getattr(customer, "phone", "")
    customer_name = getattr(order, "customer_name", None) or getattr(customer, "name", "Moms")
    order_code = getattr(order, "order_code", None) or f"ORDER-{order.id}"
    grand_total = getattr(order, "grand_total", None) or getattr(order, "total_amount", 0)
    fulfillment = "🛵 Pengiriman Kurir" if (getattr(order, "fulfillment_method", "delivery") == "delivery") else "🛍️ Ambil di Outlet (Pickup)"
    tracking_url = f"{FRONTEND_BASE_URL}/orders"

    # 1. Pesan ke Customer (Hanya jika customer opt-in WhatsApp)
    customer_opt_in = getattr(order, "notify_whatsapp", True)
    if customer_opt_in:
        customer_msg = (
            f"🍱 *PESANAN DIKONFIRMASI - {STORE_NAME.upper()}*\n\n"
            f"Hai Moms *{customer_name}*, terima kasih sudah memesan di Ava Eats! ❤️\n"
            f"Pembayaran untuk pesanan *#{order_code}* sebesar *Rp {grand_total:,.0f}* telah kami terima dengan sukses.\n\n"
            f"✨ *Status Saat Ini*: Sedang Disiapkan oleh tim Ava Eats (Frozen food & Ice Pack berkualitas prima).\n"
            f"📦 *Metode*: {fulfillment}\n\n"
            f"Moms bisa memantau status pesanan secara real-time di:\n"
            f"👉 {tracking_url}\n\n"
            f"_Homemade with love for your little one_\n"
            f"*{STORE_NAME}*"
        )
        send_whatsapp_message(customer_phone, customer_msg)
    else:
        logger.info(f"[WA] Customer #{order_code} memilih tidak menerima notifikasi WhatsApp (Opt-out).")

    # 2. Pesan Alert ke Admin
    admin_phone = WHATSAPP_ADMIN_PHONE
    if admin_phone:
        # Ringkasan menu
        items_text = ""
        order_items = items or getattr(order, "items", [])
        if order_items:
            lines = []
            for it in order_items:
                name = getattr(it, "product_name", None) or getattr(it, "name", "Menu")
                qty = getattr(it, "quantity", 1)
                lines.append(f"  • {qty}x {name}")
            items_text = "\n".join(lines)
        else:
            items_text = "  • Menu frozen food"

        admin_msg = (
            f"🚨 *ORDER BARU MASUK (LUNAS) - {STORE_NAME.upper()}*\n\n"
            f"Ada pesanan baru yang sudah lunas dan siap disiapkan!\n"
            f"• *Kode Order*: #{order_code}\n"
            f"• *Customer*: {customer_name} ({customer_phone})\n"
            f"• *Total*: Rp {grand_total:,.0f}\n"
            f"• *Metode*: {fulfillment}\n"
            f"• *Menu Pesanan*:\n{items_text}\n\n"
            f"Buka dashboard untuk memproses pesanan:\n"
            f"👉 {FRONTEND_BASE_URL}/admin"
        )
        send_whatsapp_message(admin_phone, admin_msg)


def notify_order_shipped(order, customer=None, tracking_number=None, courier_name=None, tracking_url=None, driver_name=None, driver_phone=None):
    """
    Trigger saat pesanan di-pickup oleh kurir pengiriman (GoSend / Grab / Paxel)
    """
    order_code = getattr(order, "order_code", None) or f"ORDER-{order.id}"
    if not getattr(order, "notify_whatsapp", True):
        logger.info(f"[WA] Customer #{order_code} opt-out notifikasi WhatsApp. Notifikasi pengiriman dilewati.")
        return False

    customer_phone = getattr(order, "phone", None) or getattr(customer, "phone", "")
    customer_name = getattr(order, "customer_name", None) or getattr(customer, "name", "Moms")
    courier = courier_name or getattr(order, "courier", "Kurir Ekspedisi")
    resi = tracking_number or getattr(order, "tracking_number", "-")
    track_link = tracking_url or getattr(order, "tracking_url", f"{FRONTEND_BASE_URL}/orders")

    driver_info = ""
    if driver_name:
        driver_info = f"\n🛵 *Driver*: {driver_name}" + (f" ({driver_phone})" if driver_phone else "")

    customer_msg = (
        f"🛵 *PESANAN SEDANG DIKIRIM - {STORE_NAME.upper()}*\n\n"
        f"Hai Moms *{customer_name}*,\n"
        f"Kabar gembira! Pesanan Moms *#{order_code}* sudah di-pickup oleh kurir *{courier}* dan sedang dalam perjalanan menuju lokasi Moms.{driver_info}\n\n"
        f"📦 *No. Resi*: {resi}\n"
        f"📍 *Lacak Posisi Kurir Real-Time*:\n"
        f"👉 {track_link}\n\n"
        f"❄️ *Penting*: Makanan dikemas beku dengan ice pack. Mohon pastikan ada yang menerima paket ya Moms, dan segera simpan di freezer begitu sampai!\n\n"
        f"Terima kasih,\n"
        f"*{STORE_NAME}*"
    )
    return send_whatsapp_message(customer_phone, customer_msg)


def notify_order_ready_pickup(order, customer=None):
    """
    Trigger saat pesanan pickup mandiri sudah siap diambil di outlet
    """
    order_code = getattr(order, "order_code", None) or f"ORDER-{order.id}"
    if not getattr(order, "notify_whatsapp", True):
        logger.info(f"[WA] Customer #{order_code} opt-out notifikasi WhatsApp. Notifikasi siap pickup dilewati.")
        return False

    customer_phone = getattr(order, "phone", None) or getattr(customer, "phone", "")
    customer_name = getattr(order, "customer_name", None) or getattr(customer, "name", "Moms")

    customer_msg = (
        f"🛍️ *PESANAN SIAP DIAMBIL - {STORE_NAME.upper()}*\n\n"
        f"Hai Moms *{customer_name}*,\n"
        f"Pesanan *#{order_code}* sudah selesai disiapkan dan sudah siap diambil di outlet kami! ✨\n\n"
        f"📍 *Alamat Outlet*:\n"
        f"{STORE_ADDRESS}\n\n"
        f"⏰ *Jam Operasional*: Setiap Hari (08.00 - 20.00 WIB)\n"
        f"📞 *Kontak*: {STORE_PHONE}\n\n"
        f"Tunjukkan pesan ini atau kode order *#{order_code}* ke staf kami saat pengambilan ya Moms.\n\n"
        f"Sampai jumpa di outlet!\n"
        f"*{STORE_NAME}*"
    )
    return send_whatsapp_message(customer_phone, customer_msg)


def notify_order_refunded(order, customer=None):
    """
    Trigger saat proses pengembalian dana (refund) selesai ditransfer admin
    """
    order_code = getattr(order, "order_code", None) or f"ORDER-{order.id}"
    if not getattr(order, "notify_whatsapp", True):
        logger.info(f"[WA] Customer #{order_code} opt-out notifikasi WhatsApp. Notifikasi refund dilewati.")
        return False

    customer_phone = getattr(order, "phone", None) or getattr(customer, "phone", "")
    customer_name = getattr(order, "customer_name", None) or getattr(customer, "name", "Moms")
    grand_total = getattr(order, "grand_total", None) or getattr(order, "total_amount", 0)

    customer_msg = (
        f"💸 *REFUND BERHASIL - {STORE_NAME.upper()}*\n\n"
        f"Hai Moms *{customer_name}*,\n"
        f"Pengembalian dana (refund) untuk pesanan *#{order_code}* sebesar *Rp {grand_total:,.0f}* telah selesai diproses dan ditransfer oleh tim Ava Eats.\n\n"
        f"Bukti transfer refund dapat Moms lihat di halaman status pesanan:\n"
        f"👉 {FRONTEND_BASE_URL}/orders\n\n"
        f"Kami memohon maaf atas ketidaknyamanan yang terjadi. Semoga Ava Eats bisa melayani Moms kembali di lain kesempatan! 🙏\n\n"
        f"Salam hangat,\n"
        f"*{STORE_NAME}*"
    )
    return send_whatsapp_message(customer_phone, customer_msg)

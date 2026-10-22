import math
import requests

from config.biteship import (
    BITESHIP_API_KEY,
    BITESHIP_BASE_URL,
    STORE_POSTAL_CODE,
    STORE_NAME,
    STORE_PHONE,
    STORE_ADDRESS,
    STORE_LATITUDE,
    STORE_LONGITUDE
)


def get_fallback_rates(destination_postal_code: int, items: list):
    """
    Menyediakan opsi ongkir standar (Paxel, Gojek, Grab) ketika API Biteship
    tidak memiliki saldo atau mengalami kendala jaringan.
    """
    total_weight = sum(item.get("weight", 300) * item.get("quantity", 1) for item in items)
    weight_kg = max(1, math.ceil(total_weight / 1000))

    pricing = [
        {
            "available_for_cash_on_delivery": False,
            "available_for_proof_of_delivery": False,
            "available_for_instant_waybill_id": True,
            "courier_name": "Paxel",
            "courier_code": "paxel",
            "courier_service_name": "Same Day (Cold)",
            "courier_service_code": "small",
            "description": "Layanan Paxel Same Day dengan fasilitas pendingin (8 - 12 jam)",
            "duration": "8 - 12 jam",
            "shipment_duration_range": "8 - 12",
            "shipment_duration_unit": "hours",
            "price": 18000 * weight_kg,
            "type": "same_day",
        },
        {
            "available_for_cash_on_delivery": False,
            "available_for_proof_of_delivery": False,
            "available_for_instant_waybill_id": True,
            "courier_name": "Gojek",
            "courier_code": "gojek",
            "courier_service_name": "Instant",
            "courier_service_code": "instant",
            "description": "GoSend Instant - Tiba cepat dalam 1 - 2 jam",
            "duration": "1 - 2 jam",
            "shipment_duration_range": "1 - 2",
            "shipment_duration_unit": "hours",
            "price": 25000,
            "type": "instant",
        },
        {
            "available_for_cash_on_delivery": False,
            "available_for_proof_of_delivery": False,
            "available_for_instant_waybill_id": True,
            "courier_name": "Gojek",
            "courier_code": "gojek",
            "courier_service_name": "Same Day",
            "courier_service_code": "same_day",
            "description": "GoSend Same Day - Pengiriman hemat dalam 6 - 8 jam",
            "duration": "6 - 8 jam",
            "shipment_duration_range": "6 - 8",
            "shipment_duration_unit": "hours",
            "price": 16000,
            "type": "same_day",
        },
        {
            "available_for_cash_on_delivery": False,
            "available_for_proof_of_delivery": False,
            "available_for_instant_waybill_id": True,
            "courier_name": "Grab",
            "courier_code": "grab",
            "courier_service_name": "Instant",
            "courier_service_code": "instant",
            "description": "GrabExpress Instant - Tiba cepat dalam 1 - 2 jam",
            "duration": "1 - 2 jam",
            "shipment_duration_range": "1 - 2",
            "shipment_duration_unit": "hours",
            "price": 24000,
            "type": "instant",
        },
        {
            "available_for_cash_on_delivery": False,
            "available_for_proof_of_delivery": False,
            "available_for_instant_waybill_id": True,
            "courier_name": "Grab",
            "courier_code": "grab",
            "courier_service_name": "Same Day",
            "courier_service_code": "same_day",
            "description": "GrabExpress Same Day - Pengiriman hemat dalam 6 - 8 jam",
            "duration": "6 - 8 jam",
            "shipment_duration_range": "6 - 8",
            "shipment_duration_unit": "hours",
            "price": 15000,
            "type": "same_day",
        },
        {
            "available_for_cash_on_delivery": False,
            "available_for_proof_of_delivery": False,
            "available_for_instant_waybill_id": True,
            "courier_name": "Lalamove",
            "courier_code": "lalamove",
            "courier_service_name": "Instant Motor",
            "courier_service_code": "motorcycle",
            "description": "Lalamove Instant - Pengiriman cepat roda dua (1 - 2 jam)",
            "duration": "1 - 2 jam",
            "shipment_duration_range": "1 - 2",
            "shipment_duration_unit": "hours",
            "price": 22000,
            "type": "instant",
        },
    ]

    return {
        "success": True,
        "message": "Tarif pengiriman standar makanan (Paxel, Gojek, Grab, Lalamove)",
        "pricing": pricing,
        "is_fallback": True,
    }


def get_biteship_areas(query: str):
    url = f"{BITESHIP_BASE_URL}/v1/maps/areas"

    response = requests.get(
        url,
        params={
            "countries": "ID",
            "input": query
        },
        headers={
            "Authorization": BITESHIP_API_KEY,
            "Content-Type": "application/json"
        }
    )

    if response.status_code != 200:
        raise Exception(
            f"Biteship error: {response.text}"
        )

    return response.json()


def get_courier_rates(
    destination_postal_code: int,
    items: list,
    couriers: str = "paxel,gojek,grab,lalamove",
    destination_latitude: float = None,
    destination_longitude: float = None,
):
    url = f"{BITESHIP_BASE_URL}/v1/rates/couriers"

    payload = {
        "origin_postal_code": int(STORE_POSTAL_CODE),
        "destination_postal_code": destination_postal_code,
        "couriers": couriers,
        "items": items
    }

    if STORE_LATITUDE and STORE_LONGITUDE:
        payload["origin_latitude"] = STORE_LATITUDE
        payload["origin_longitude"] = STORE_LONGITUDE

    if destination_latitude and destination_longitude:
        payload["destination_latitude"] = destination_latitude
        payload["destination_longitude"] = destination_longitude

    try:
        response = requests.post(
            url,
            json=payload,
            headers={
                "Authorization": BITESHIP_API_KEY,
                "Content-Type": "application/json"
            },
            timeout=10,
        )

        if response.status_code == 200:
            result = response.json()
            if result.get("success") is not False and result.get("pricing"):
                return result
            print(f"[Biteship Warning] Rates returned non-success: {response.text}")
        else:
            print(f"[Biteship Warning] Rates API status {response.status_code}: {response.text}")

    except Exception as e:
        print(f"[Biteship Warning] Exception connecting to Biteship: {e}")

    # Fallback jika saldo Biteship 0 atau terjadi error API
    return get_fallback_rates(destination_postal_code, items)



def create_biteship_order(
    order_id: str,
    courier_company: str,
    courier_type: str,
    destination: dict,
    items: list,
):
    url = f"{BITESHIP_BASE_URL}/v1/orders"

    payload = {
        "reference_id": order_id,
        "courier_company": courier_company.lower(),
        "courier_type": courier_type.lower(),
        "delivery_type": "now",

        "origin_contact_name": STORE_NAME,
        "origin_contact_phone": STORE_PHONE,
        "origin_address": STORE_ADDRESS,
        "origin_postal_code": int(STORE_POSTAL_CODE),

        "origin_coordinate": {
        "latitude": STORE_LATITUDE,
        "longitude": STORE_LONGITUDE,
        },

        "destination_contact_name": destination["name"],
        "destination_contact_phone": destination["phone"],
        "destination_address": destination["address"],
        "destination_postal_code": int(destination["postal_code"]),

        "destination_coordinate": {
        "latitude": destination["latitude"],
        "longitude": destination["longitude"],
        },

        "items": items,
    }

    try:
        response = requests.post(
            url,
            json=payload,
            headers={
                "Authorization": BITESHIP_API_KEY,
                "Content-Type": "application/json",
            },
            timeout=30,
        )
        response.raise_for_status()
        result = response.json()

        if result.get("success") is False:
            raise Exception(
                f"Biteship gagal membuat order: "
                f"{result.get('error', result.get('message'))}"
            )

        if not result.get("id"):
            raise Exception(
                "Respons Biteship tidak memiliki order ID."
            )

        return result

    except requests.RequestException as e:
        detail = (
            e.response.text
            if e.response is not None
            else str(e)
        )
        raise Exception(f"Biteship API error: {detail}") from e

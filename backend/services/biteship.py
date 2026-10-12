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
    couriers: str = "jne,sicepat,jnt"
):
    url = f"{BITESHIP_BASE_URL}/v1/rates/couriers"

    payload = {
        "origin_postal_code": int(STORE_POSTAL_CODE),
        "destination_postal_code": destination_postal_code,
        "couriers": couriers,
        "items": items
    }

    response = requests.post(
        url,
        json=payload,
        headers={
            "Authorization": BITESHIP_API_KEY,
            "Content-Type": "application/json"
        }
    )

    if response.status_code != 200:
        raise Exception(
            f"Biteship rates error: {response.text}"
        )

    return response.json()



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

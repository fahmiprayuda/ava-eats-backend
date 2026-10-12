
import requests


class GeocodingError(Exception):
    pass


def geocode_address(
    address: str,
    district: str,
    city: str,
    province: str,
    postal_code: str,
) -> dict:
    full_address = (
        f"{address}, {district}, {city}, "
        f"{province}, {postal_code}, Indonesia"
    )

    url = "https://nominatim.openstreetmap.org/search"

    headers = {
        # Ganti email ini dengan email kontak project kamu.
        "User-Agent": "AvaEats/1.0 (contact: prayuda.fahmi@gmail.com)",
    }

    params = {
        "q": full_address,
        "format": "jsonv2",
        "limit": 1,
        "countrycodes": "id",
    }

    try:
        response = requests.get(
            url,
            params=params,
            headers=headers,
            timeout=15,
        )
        response.raise_for_status()
        results = response.json()

    except requests.RequestException as exc:
        raise GeocodingError(
            "Layanan pencarian alamat sedang bermasalah. "
            "Silakan coba lagi."
        ) from exc

    if not results:
        raise GeocodingError(
            "Alamat tidak ditemukan. Periksa alamat dan kode pos."
        )

    try:
        latitude = float(results[0]["lat"])
        longitude = float(results[0]["lon"])
    except (KeyError, TypeError, ValueError) as exc:
        raise GeocodingError(
            "Koordinat alamat tidak valid."
        ) from exc

    if not (-90 <= latitude <= 90):
        raise GeocodingError("Latitude tidak valid.")

    if not (-180 <= longitude <= 180):
        raise GeocodingError("Longitude tidak valid.")

    if latitude == 0 and longitude == 0:
        raise GeocodingError(
            "Lokasi alamat tidak valid. Silakan periksa kembali."
        )

    return {
        "latitude": latitude,
        "longitude": longitude,
    }

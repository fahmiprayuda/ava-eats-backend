import logging
import requests

logger = logging.getLogger("ava_eats.geocoding")

class GeocodingError(Exception):
    pass

# Titik koordinat acuan kota-kota utama (khususnya Jabodetabek & sekitarnya)
DEFAULT_CITY_COORDINATES = {
    "jakarta pusat": (-6.1805, 106.8284),
    "jakarta selatan": (-6.2615, 106.8106),
    "jakarta timur": (-6.2250, 106.9004),
    "jakarta barat": (-6.1683, 106.7588),
    "jakarta utara": (-6.1384, 106.8640),
    "dki jakarta": (-6.2088, 106.8456),
    "jakarta": (-6.2088, 106.8456),
    "tangerang": (-6.1783, 106.6319),
    "tangerang selatan": (-6.2888, 106.7179),
    "tangsel": (-6.2888, 106.7179),
    "depok": (-6.4025, 106.7942),
    "bekasi": (-6.2383, 106.9756),
    "kota bekasi": (-6.2383, 106.9756),
    "kabupaten bekasi": (-6.2500, 107.1500),
    "bogor": (-6.5971, 106.8060),
    "kota bogor": (-6.5971, 106.8060),
    "kabupaten bogor": (-6.4797, 106.8247),
    "bandung": (-6.9175, 107.6191),
    "kota bandung": (-6.9175, 107.6191),
    "surabaya": (-7.2575, 112.7521),
    "semarang": (-6.9667, 110.4167),
    "yogyakarta": (-7.7956, 110.3695),
}

FALLBACK_COORDINATE = (-6.2088, 106.8456)  # Default: Jakarta Pusat

def _lookup_city_fallback(city: str, province: str) -> dict:
    """Mencari koordinat fallback berdasarkan nama kota / provinsi."""
    city_clean = (city or "").strip().lower()
    prov_clean = (province or "").strip().lower()

    for key, (lat, lon) in DEFAULT_CITY_COORDINATES.items():
        if key in city_clean or key in prov_clean:
            return {"latitude": lat, "longitude": lon}

    return {"latitude": FALLBACK_COORDINATE[0], "longitude": FALLBACK_COORDINATE[1]}

def geocode_address(
    address: str,
    district: str,
    city: str,
    province: str,
    postal_code: str,
) -> dict:
    """
    Mencari koordinat (latitude, longitude) dengan sistem berjenjang (cascading fallback):
    1. Query lengkap (Alamat + Kecamatan + Kota + Provinsi)
    2. Query Kecamatan + Kota + Provinsi
    3. Query Kode Pos + Kota
    4. Query Kota + Provinsi
    5. Fallback ke daftar koordinat kota bawaan (Anti-Gagal)
    """
    url = "https://nominatim.openstreetmap.org/search"
    headers = {
        "User-Agent": "AvaEats/1.0 (contact: support@avaeats.com)",
        "Accept-Language": "id,en",
    }

    # Urutan query dari yang paling spesifik ke yang paling umum
    candidate_queries = [
        f"{address}, {district}, {city}, {province}, Indonesia",
        f"{district}, {city}, {province}, Indonesia",
        f"{postal_code}, {city}, Indonesia" if postal_code else "",
        f"{city}, {province}, Indonesia",
        f"{city}, Indonesia",
    ]

    for q in candidate_queries:
        if not q or not q.strip():
            continue

        params = {
            "q": q.strip(),
            "format": "jsonv2",
            "limit": 1,
            "countrycodes": "id",
        }

        try:
            response = requests.get(
                url,
                params=params,
                headers=headers,
                timeout=5,
            )
            if response.status_code == 200:
                results = response.json()
                if results and len(results) > 0:
                    lat = float(results[0]["lat"])
                    lon = float(results[0]["lon"])
                    if -90 <= lat <= 90 and -180 <= lon <= 180 and not (lat == 0 and lon == 0):
                        logger.info(f"Geocoding berhasil untuk query '{q}': ({lat}, {lon})")
                        return {"latitude": lat, "longitude": lon}
        except Exception as err:
            logger.warning(f"Nominatim query '{q}' gagal: {err}")
            continue

    # Jika semua query Nominatim gagal / tidak ada hasil / timeout:
    # Jangan melempar error HTTP 422! Gunakan fallback cerdas berdasarkan kota.
    fallback = _lookup_city_fallback(city, province)
    logger.warning(
        f"Semua query Nominatim tidak menemukan hasil untuk '{address}, {city}'. "
        f"Menggunakan fallback koordinat kota ({fallback['latitude']}, {fallback['longitude']})."
    )
    return fallback

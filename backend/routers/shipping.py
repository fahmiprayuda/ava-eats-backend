from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models.order import Order
from models.customer_address import CustomerAddress
from models.shipment import Shipment
from models.payment import Payment
from models.product import Product

from schemas.shipping import ShippingSelectRequest, CalculateShippingRatesRequest

from services.biteship import get_courier_rates, create_biteship_order
from utils.audit import create_audit_log


router = APIRouter(
    prefix="/shipping",
    tags=["Shipping"],
)


@router.post("/rates")
def calculate_shipping_rates(
    data: CalculateShippingRatesRequest,
    db: Session = Depends(get_db),
):
    destination_postal_code = None
    address_info = None

    if data.address_id:
        address = (
            db.query(CustomerAddress)
            .filter(CustomerAddress.id == data.address_id)
            .first()
        )
        if not address:
            raise HTTPException(
                status_code=404,
                detail="Alamat tidak ditemukan",
            )
        if not address.postal_code:
            raise HTTPException(
                status_code=400,
                detail="Kode pos alamat belum diisi",
            )
        try:
            destination_postal_code = int(address.postal_code)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="Format kode pos alamat tidak valid",
            )
        address_info = {
            "id": address.id,
            "label": address.label,
            "city": address.city,
            "postal_code": address.postal_code,
        }
    elif data.postal_code:
        try:
            destination_postal_code = int(data.postal_code)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="Format kode pos tidak valid",
            )
    else:
        raise HTTPException(
            status_code=400,
            detail="Pilih alamat pengiriman terlebih dahulu",
        )

    if not data.items:
        raise HTTPException(
            status_code=400,
            detail="Daftar item tidak boleh kosong",
        )

    items = []
    product_ids = [item.product_id for item in data.items]
    products = db.query(Product).filter(Product.id.in_(product_ids)).all()
    product_map = {p.id: p for p in products}

    for item in data.items:
        product = product_map.get(item.product_id)
        if not product:
            continue
        weight = product.weight_grams or 300
        items.append({
            "name": product.name,
            "description": product.name,
            "value": product.price,
            "weight": weight,
            "quantity": item.quantity,
        })

    if not items:
        raise HTTPException(
            status_code=400,
            detail="Produk dalam keranjang tidak ditemukan",
        )

    dest_lat = address.latitude if address else None
    dest_lng = address.longitude if address else None

    rates = get_courier_rates(
        destination_postal_code=destination_postal_code,
        items=items,
        couriers="paxel,gojek,grab,lalamove",
        destination_latitude=dest_lat,
        destination_longitude=dest_lng,
    )

    total_weight_grams = sum(it["weight"] * it["quantity"] for it in items)

    return {
        "destination_postal_code": destination_postal_code,
        "address": address_info,
        "total_weight_grams": total_weight_grams,
        "pricing": rates.get("pricing", []),
        "is_fallback": rates.get("is_fallback", False),
    }


@router.get("/rates/{order_id}")
def get_shipping_rates(
    order_id: int,
    db: Session = Depends(get_db),
):
    # 1. Cari order
    order = (
        db.query(Order)
        .filter(Order.id == order_id)
        .first()
    )

    if not order:
        raise HTTPException(
            status_code=404,
            detail="Order tidak ditemukan",
        )

    # 2. Pastikan order punya address
    address = (
        db.query(CustomerAddress)
        .filter(CustomerAddress.id == order.address_id)
        .first()
    )

    if not address:
        raise HTTPException(
            status_code=404,
            detail="Alamat order tidak ditemukan",
        )

    # 3. Pastikan postal code tersedia
    if not address.postal_code:
        raise HTTPException(
            status_code=400,
            detail="Postal code alamat belum tersedia",
        )

    # 4. Pastikan order tidak pickup
    if order.fulfillment_method == "pickup":
        raise HTTPException(
            status_code=400,
            detail="Pesanan pickup tidak membutuhkan ongkos kirim",
        )

    # 5. Siapkan item untuk Biteship
    items = []

    for order_item in order.items:
        weight = order_item.product.weight_grams

        items.append({
            "name": order_item.product_name,
            "description": order_item.product_name,
            "value": order_item.price,
            "weight": weight,
            "quantity": order_item.quantity,
        })

    # 6. Request shipping rates ke Biteship
    try:
        rates = get_courier_rates(
            destination_postal_code=int(address.postal_code),
            items=items,
        )
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=str(e),
        )

    # 7. Return response Biteship
    return {
        "order_id": order.id,
        "order_code": order.order_code,
        "destination": {
            "postal_code": address.postal_code,
            "latitude": address.latitude,
            "longitude": address.longitude,
        },
        "items": items,
        "rates": rates,
    }

@router.post("/select")
def select_shipping(
    data: ShippingSelectRequest,
    db: Session = Depends(get_db),
):
    # 1. Cari order
    order = (
        db.query(Order)
        .filter(Order.id == data.order_id)
        .first()
    )

    if not order:
        raise HTTPException(
            status_code=404,
            detail="Order tidak ditemukan",
        )

    
    if order.fulfillment_method == "pickup":
        raise HTTPException(
            status_code=400,
            detail="Pesanan pickup tidak membutuhkan ongkos kirim",
        )

    # 2. Shipping hanya boleh dipilih sebelum pembayaran
    if order.status != "pending":
        raise HTTPException(
            status_code=400,
            detail="Shipping hanya dapat dipilih saat order masih pending",
        )

    # 3. Validasi shipping cost
    if data.shipping_cost < 0:
        raise HTTPException(
            status_code=400,
            detail="Shipping cost tidak valid",
        )

    # 4. Cek apakah shipment sudah ada
    shipment = (
        db.query(Shipment)
        .filter(Shipment.order_id == order.id)
        .first()
    )

    if shipment:
        # Update pilihan shipping
        shipment.courier = data.courier_code
        shipment.service = data.service_code
        shipment.shipping_cost = data.shipping_cost

    else:
        # Buat shipment baru
        shipment = Shipment(
            order_id=order.id,
            courier=data.courier_code,
            service=data.service_code,
            shipping_cost=data.shipping_cost,
            status="pending",
        )

        db.add(shipment)

    # 5. Update total order
    order.shipping_cost = data.shipping_cost
    order.grand_total = (
        order.total_amount + data.shipping_cost
    )

    db.commit()
    db.refresh(order)
    db.refresh(shipment)

    return {
        "message": "Shipping berhasil dipilih",
        "order": {
            "id": order.id,
            "order_code": order.order_code,
            "total_amount": order.total_amount,
            "shipping_cost": order.shipping_cost,
            "grand_total": order.grand_total,
        },
        "shipment": {
            "id": shipment.id,
            "courier": shipment.courier,
            "service": shipment.service,
            "shipping_cost": shipment.shipping_cost,
            "status": shipment.status,
        },
    }


@router.post("/create/{order_id}")

def create_shipping_order(
    order_id: int,
    db: Session = Depends(get_db),
):
    # 1. Cari order
    order = (
        db.query(Order)
        .filter(Order.id == order_id)
        .first()
    )

    if not order:
        raise HTTPException(
            status_code=404,
            detail="Order tidak ditemukan",
        )

    # 2. Order harus sudah dibayar
    if order.status != "paid":
        raise HTTPException(
            status_code=400,
            detail="Order harus sudah dibayar sebelum proses ini",
        )

    # 3. Pastikan pembayaran approved
    payment = (
        db.query(Payment)
        .filter(
            Payment.order_id == order.id,
            Payment.status == "approved",
        )
        .first()
    )

    if not payment:
        raise HTTPException(
            status_code=400,
            detail="Pembayaran approved tidak ditemukan",
        )

    # 4. Pickup tidak perlu booking Biteship
    if order.fulfillment_method == "pickup":
        order.shipping_cost = 0
        order.grand_total = order.total_amount

        db.commit()
        db.refresh(order)

        return {
            "message": "Pickup dikonfirmasi. Tidak perlu booking pengiriman.",
            "order_code": order.order_code,
            "fulfillment_method": "pickup",
            "shipping_cost": 0,
            "grand_total": order.grand_total,
        }

    # 5. Lanjutkan proses Biteship hanya untuk delivery
    if order.fulfillment_method != "delivery":
        raise HTTPException(
            status_code=400,
            detail="Metode pemenuhan order tidak valid",
        )

    shipment = (
        db.query(Shipment)
        .filter(Shipment.order_id == order.id)
        .first()
    )

    if not shipment or not shipment.courier or not shipment.service:
        raise HTTPException(
            status_code=400,
            detail="Pilih layanan pengiriman terlebih dahulu",
        )

    if shipment.shipping_cost != order.shipping_cost:
        raise HTTPException(
            status_code=400,
            detail="Shipping cost tidak sesuai dengan order",
        )

    if order.grand_total != order.total_amount + order.shipping_cost:
        raise HTTPException(
            status_code=400,
            detail="Grand total order tidak valid",
        )

    # Cegah booking duplikat
    if shipment.biteship_order_id:
        raise HTTPException(
            status_code=409,
            detail="Pengiriman untuk order ini sudah dibuat",
        )

    # Validasi alamat tujuan
    if not all([
        order.recipient_name,
        order.phone,
        order.address,
        order.postal_code,
    ]):
        raise HTTPException(
            status_code=400,
            detail="Data alamat penerima belum lengkap",
        )

    # Siapkan alamat dari snapshot order
    destination = {
        "name": order.recipient_name,
        "phone": order.phone,
        "address": order.address,
        "postal_code": order.postal_code,
        "latitude": order.latitude,
        "longitude": order.longitude,
    }

    latitude = destination["latitude"]
    longitude = destination["longitude"]

    if latitude is None or longitude is None:
        raise HTTPException(
            status_code=400,
            detail="Koordinat alamat penerima belum tersedia",
        )

    try:
        latitude = float(latitude)
        longitude = float(longitude)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=400,
            detail="Koordinat alamat penerima tidak valid",
        )

    if not (
        -90 <= latitude <= 90
        and -180 <= longitude <= 180
    ):
        raise HTTPException(
            status_code=400,
            detail="Latitude atau longitude di luar rentang yang valid",
        )

    destination["latitude"] = latitude
    destination["longitude"] = longitude

    # Siapkan item untuk Biteship
    items = []

    for order_item in order.items:
        product = order_item.product

        if not product or not product.weight_grams:
            raise HTTPException(
                status_code=400,
                detail=f"Berat produk {order_item.product_name} belum tersedia",
            )

        if product.weight_grams <= 0 or order_item.quantity <= 0:
            raise HTTPException(
                status_code=400,
                detail="Berat atau jumlah produk tidak valid",
            )

        items.append({
            "name": order_item.product_name,
            "description": order_item.product_name,
            "value": order_item.price,
            "weight": product.weight_grams,
            "quantity": order_item.quantity,
        })

    if not items:
        raise HTTPException(
            status_code=400,
            detail="Order tidak memiliki item",
        )

    # Buat booking Biteship
    try:
        result = create_biteship_order(
            order_id=order.order_code,
            courier_company=shipment.courier,
            courier_type=shipment.service,
            destination=destination,
            items=items,
        )
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=str(e),
        )

    # Simpan hasil booking
    shipment.biteship_order_id = result.get("id")
    courier_data = result.get("courier") if isinstance(result.get("courier"), dict) else {}
    shipment.tracking_number = (
        result.get("waybill_id")
        or courier_data.get("waybill_id")
        or courier_data.get("tracking_id")
    )
    shipment.tracking_url = (
        result.get("tracking_url")
        or courier_data.get("link")
        or (f"https://biteship.com/track/{result['id']}" if result.get("id") else None)
    )
    shipment.driver_name = courier_data.get("driver_name")
    shipment.driver_phone = courier_data.get("driver_phone")
    shipment.driver_plate_number = courier_data.get("driver_plate_number")
    shipment.driver_photo_url = courier_data.get("driver_photo_url")

    if result.get("status"):
        shipment.status = result["status"]

    db.commit()
    db.refresh(shipment)

    return {
        "message": "Booking pengiriman berhasil dibuat",
        "order_code": order.order_code,
        "fulfillment_method": "delivery",
        "shipment": {
            "id": shipment.id,
            "biteship_order_id": shipment.biteship_order_id,
            "courier": shipment.courier,
            "service": shipment.service,
            "tracking_number": shipment.tracking_number,
            "status": shipment.status,
        },
    }


@router.post("/simulate/{order_id}")
def simulate_shipping_assignment(
    order_id: int,
    db: Session = Depends(get_db),
):
    """
    Endpoint simulasi untuk pengujian UI:
    Menghasilkan nomor resi (Paxel) atau data driver live (Gojek / Grab / Lalamove).
    Otomatis memperbarui status pesanan menjadi 'delivered' (Dalam Pengiriman).
    """
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order tidak ditemukan")

    shipment = db.query(Shipment).filter(Shipment.order_id == order_id).first()
    if not shipment:
        shipment = Shipment(
            order_id=order.id,
            courier="paxel",
            service="small",
            shipping_cost=18000,
            status="pending",
        )
        db.add(shipment)
        db.flush()

    courier = (shipment.courier or "paxel").lower()

    if courier == "paxel":
        shipment.tracking_number = f"PXL-{datetime.now().strftime('%Y%m%d')}-{order.id:04d}"
        shipment.tracking_url = f"https://paxel.co/track?waybill={shipment.tracking_number}"
        shipment.status = "in_transit"
    else:
        shipment.driver_name = "Budi Santoso"
        shipment.driver_phone = "0812-3456-7890"
        shipment.driver_plate_number = "B 1234 XYZ (Honda Vario)"
        shipment.tracking_url = (
            f"https://maps.google.com/?q={order.latitude or -6.459818},{order.longitude or 106.873844}"
        )
        shipment.status = "in_transit"

    if shipment.shipped_at is None:
        shipment.shipped_at = datetime.now()

    # Otomatis update status pesanan menjadi 'delivered' jika masih paid atau processing
    if order.status in ["paid", "processing"]:
        old_status = order.status
        order.status = "delivered"
        create_audit_log(
            db=db,
            user_type="system",
            user_id=0,
            action="ORDER_STATUS_UPDATED",
            entity_type="order",
            entity_id=order.id,
            description=(
                f"Kurir telah menjemput paket (Simulasi) untuk order {order.order_code}. "
                f"Status pesanan otomatis berubah dari '{old_status}' ke 'delivered' (Dalam Pengiriman)."
            ),
        )

    db.commit()
    db.refresh(shipment)
    db.refresh(order)

    return {
        "message": "Simulasi kurir berhasil diaktifkan",
        "order_id": order.id,
        "order_status": order.status,
        "courier": shipment.courier,
        "tracking_number": shipment.tracking_number,
        "driver_name": shipment.driver_name,
        "driver_phone": shipment.driver_phone,
        "driver_plate_number": shipment.driver_plate_number,
        "tracking_url": shipment.tracking_url,
        "status": shipment.status,
    }


@router.post("/simulate-delivered/{order_id}")
def simulate_shipping_delivered(
    order_id: int,
    db: Session = Depends(get_db),
):
    """
    Endpoint simulasi untuk pengujian UI:
    Menyimulasikan paket telah tiba di tangan penerima (status 'delivered' dari kurir).
    Otomatis memperbarui status pesanan menjadi 'completed' (Selesai).
    """
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order tidak ditemukan")

    shipment = db.query(Shipment).filter(Shipment.order_id == order_id).first()
    if not shipment:
        raise HTTPException(status_code=404, detail="Shipment belum dibuat untuk order ini")

    shipment.status = "delivered"
    if shipment.delivered_at is None:
        shipment.delivered_at = datetime.now()

    if order.status != "cancelled":
        old_status = order.status
        order.status = "completed"
        create_audit_log(
            db=db,
            user_type="system",
            user_id=0,
            action="ORDER_STATUS_UPDATED",
            entity_type="order",
            entity_id=order.id,
            description=(
                f"Paket telah diterima pemesan (Simulasi) untuk order {order.order_code}. "
                f"Status pesanan otomatis berubah dari '{old_status}' ke 'completed' (Selesai)."
            ),
        )

    db.commit()
    db.refresh(shipment)
    db.refresh(order)

    return {
        "message": "Simulasi paket tiba di tujuan berhasil",
        "order_id": order.id,
        "order_status": order.status,
        "shipment_status": shipment.status,
        "delivered_at": shipment.delivered_at.isoformat() if shipment.delivered_at else None,
    }

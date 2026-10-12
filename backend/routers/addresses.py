from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models.order import Order
from models.customer import Customer
from models.customer_address import CustomerAddress
from schemas.customer_address import CustomerAddressRequest
from schemas.customer_address_update import CustomerAddressUpdate
from auth.dependencies import get_current_customer

from services.geocoding import geocode_address, GeocodingError



router = APIRouter(
    prefix="/api/customers",
    tags=["Customers"]
)



@router.post("/{customer_id}/addresses")
def add_customer_address(
    customer_id: int,
    address_request: CustomerAddressRequest,
    db: Session = Depends(get_db),
    current_customer: Customer = Depends(get_current_customer),
):
    # 1. Cek customer
    customer = (
        db.query(Customer)
        .filter(Customer.id == customer_id)
        .first()
    )

    if not customer:
        raise HTTPException(
            status_code=404,
            detail="Customer tidak ditemukan",
        )

    # 2. Pastikan alamat milik customer yang login
    if customer.id != current_customer.id:
        raise HTTPException(
            status_code=403,
            detail="Anda tidak memiliki akses untuk menambahkan alamat ini",
        )

    # 3. Cari koordinat otomatis menggunakan Nominatim
    try:
        coordinates = geocode_address(
            address=address_request.address,
            district=address_request.district,
            city=address_request.city,
            province=address_request.province,
            postal_code=address_request.postal_code,
        )
    except GeocodingError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc



    # 4. Tentukan apakah alamat baru menjadi alamat utama
    active_addresses = (
        db.query(CustomerAddress)
        .filter(
            CustomerAddress.customer_id == customer_id,
            CustomerAddress.is_active.is_(True),
        )
        .all()
    )

    # Jika alamat pertama, otomatis jadikan default.
    # Jika customer memilih is_default=True, gunakan alamat baru.
    should_be_default = (
        address_request.is_default or len(active_addresses) == 0
    )

    if should_be_default:
        for item in active_addresses:
            item.is_default = False


    # 5. Simpan alamat dan koordinat hasil geocoding
    new_address = CustomerAddress(
        customer_id=customer_id,
        label=address_request.label,
        recipient_name=address_request.recipient_name,
        phone=address_request.phone,
        address=address_request.address,
        province=address_request.province,
        city=address_request.city,
        district=address_request.district,
        postal_code=address_request.postal_code,
        latitude=coordinates["latitude"],
        longitude=coordinates["longitude"],
        is_default=should_be_default,
        is_active=True,
    )

    try:
        db.add(new_address)
        db.commit()
        db.refresh(new_address)
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Gagal menyimpan alamat pelanggan",
        )

    return {
        "message": "Alamat berhasil ditambahkan",
        "address": {
            "id": new_address.id,
            "label": new_address.label,
            "recipient_name": new_address.recipient_name,
            "phone": new_address.phone,
            "address": new_address.address,
            "province": new_address.province,
            "city": new_address.city,
            "district": new_address.district,
            "postal_code": new_address.postal_code,
            "latitude": new_address.latitude,
            "longitude": new_address.longitude,
            "is_default": new_address.is_default,
        },
    }

@router.get("/{customer_id}/addresses")
def get_customer_addresses(
    customer_id: int,
    db: Session = Depends(get_db),
    current_customer: Customer = Depends(get_current_customer)
):
    customer = db.query(Customer).filter(
        Customer.id == customer_id
    ).first()

    if not customer:
        raise HTTPException(
            status_code=404,
            detail="Customer tidak ditemukan"
        )

    if customer.id != current_customer.id:
        raise HTTPException(
            status_code=403,
            detail="Anda tidak memiliki akses untuk melihat alamat ini"
        )

    addresses = (
        db.query(CustomerAddress)
        .filter(
            CustomerAddress.customer_id == customer_id,
            CustomerAddress.is_active.is_(True),
        )
        .all()
    )

    return {
        "message": "Alamat berhasil diambil",
        "addresses": [
            {
                "id": address.id,
                "label": address.label,
                "recipient_name": address.recipient_name,
                "phone": address.phone,
                "address": address.address,
                "province": address.province,
                "city": address.city,
                "district": address.district,
                "postal_code": address.postal_code,
                "latitude": address.latitude,
                "longitude": address.longitude,
                "is_default": address.is_default
            }
            for address in addresses
        ]
    }

@router.put("/{customer_id}/addresses/{address_id}")
def update_address(
    customer_id: int,
    address_id: int,
    address: CustomerAddressUpdate,
    db: Session = Depends(get_db),
    current_customer: Customer = Depends(get_current_customer)
):

    if customer_id != current_customer.id:
        raise HTTPException(
            status_code=403,
            detail="Anda tidak memiliki akses untuk memperbarui alamat ini"
        )

    # 1. Cek customer
    customer = db.query(Customer).filter(
        Customer.id == customer_id
    ).first()

    if not customer:
        raise HTTPException(
            status_code=404,
            detail="Customer tidak ditemukan"
        )

    # 2. Cek address milik customer tersebut
    existing_address = (
        db.query(CustomerAddress)
            .filter(
                CustomerAddress.id == address_id,
                CustomerAddress.customer_id == customer_id,
                CustomerAddress.is_active.is_(True),
            )
            .first()
    )

    if not existing_address:
        raise HTTPException(
            status_code=404,
            detail="Alamat tidak ditemukan"
        )

    # 3. Kalau address ini dijadikan default
    if address.is_default:

        old_default = db.query(CustomerAddress).filter(
            CustomerAddress.customer_id == customer_id,
            CustomerAddress.is_default == True,
            CustomerAddress.id != address_id
        ).all()

        for item in old_default:
            item.is_default = False

    try:
        coordinates = geocode_address(
            address=address.address,
            district=address.district,
            city=address.city,
            province=address.province,
            postal_code=address.postal_code,
        )
    except GeocodingError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc

    # 4. Update data
    existing_address.label = address.label
    existing_address.recipient_name = address.recipient_name
    existing_address.phone = address.phone
    existing_address.address = address.address
    existing_address.province = address.province
    existing_address.city = address.city
    existing_address.district = address.district
    existing_address.postal_code = address.postal_code
    existing_address.latitude = coordinates["latitude"]
    existing_address.longitude = coordinates["longitude"]
    existing_address.is_default = address.is_default

    # 5. Simpan
    db.commit()
    db.refresh(existing_address)

    return {
        "message": "Alamat berhasil diperbarui",
        "address": {
            "id": existing_address.id,
            "customer_id": existing_address.customer_id,
            "label": existing_address.label,
            "recipient_name": existing_address.recipient_name,
            "phone": existing_address.phone,
            "address": existing_address.address,
            "province": existing_address.province,
            "city": existing_address.city,
            "district": existing_address.district,
            "postal_code": existing_address.postal_code,
            "latitude": existing_address.latitude,
            "longitude": existing_address.longitude,
            "is_default": existing_address.is_default
        }
    }

@router.put("/{customer_id}/addresses/{address_id}/default")
def set_default_address(
    customer_id: int,
    address_id: int,
    db: Session = Depends(get_db),
    current_customer: Customer = Depends(get_current_customer)
):
    if customer_id != current_customer.id:
        raise HTTPException(
            status_code=403,
            detail="Anda tidak memiliki akses untuk mengatur alamat ini sebagai default"
        )

    # 1. Pastikan customer ada
    customer = db.query(Customer).filter(
        Customer.id == customer_id
    ).first()

    if not customer:
        raise HTTPException(
            status_code=404,
            detail="Customer tidak ditemukan"
        )

    # 2. Cari alamat yang mau dijadikan utama
    #    sekaligus pastikan alamat tersebut milik customer
    selected_address = (
    db.query(CustomerAddress)
        .filter(
            CustomerAddress.id == address_id,
            CustomerAddress.customer_id == customer_id,
            CustomerAddress.is_active.is_(True),
        )
        .first()
    )

    if not selected_address:
        raise HTTPException(
            status_code=404,
            detail="Alamat tidak ditemukan"
        )

    # 3. Jadikan semua alamat customer bukan default
    addresses = (
        db.query(CustomerAddress)
        .filter(
            CustomerAddress.customer_id == customer_id,
            CustomerAddress.is_active.is_(True),
        )
        .all()
    )

    for item in addresses:
        item.is_default = False

    # 4. Jadikan alamat yang dipilih sebagai default
    selected_address.is_default = True

    # 5. Simpan perubahan
    db.commit()
    db.refresh(selected_address)

    return {
        "message": "Alamat utama berhasil diubah",
        "address": {
            "id": selected_address.id,
            "customer_id": selected_address.customer_id,
            "label": selected_address.label,
            "recipient_name": selected_address.recipient_name,
            "phone": selected_address.phone,
            "address": selected_address.address,
            "province": selected_address.province,
            "city": selected_address.city,
            "district": selected_address.district,
            "postal_code": selected_address.postal_code,
            "latitude": selected_address.latitude,
            "longitude": selected_address.longitude,
            "is_default": selected_address.is_default
        }
    }




@router.delete("/{customer_id}/addresses/{address_id}")
def delete_address(
    customer_id: int,
    address_id: int,
    db: Session = Depends(get_db),
    current_customer: Customer = Depends(get_current_customer),
):
    # 1. Validasi kepemilikan
    if customer_id != current_customer.id:
        raise HTTPException(
            status_code=403,
            detail="Anda tidak memiliki akses untuk menghapus alamat ini",
        )

    # 2. Pastikan customer ada
    customer = (
        db.query(Customer)
        .filter(Customer.id == customer_id)
        .first()
    )

    if not customer:
        raise HTTPException(
            status_code=404,
            detail="Customer tidak ditemukan",
        )

    # 3. Cari alamat aktif milik customer
    existing_address = (
        db.query(CustomerAddress)
        .filter(
            CustomerAddress.id == address_id,
            CustomerAddress.customer_id == customer_id,
            CustomerAddress.is_active.is_(True),
        )
        .first()
    )

    if not existing_address:
        raise HTTPException(
            status_code=404,
            detail="Alamat aktif tidak ditemukan",
        )

    # 4. Alamat utama tidak boleh dihapus
    if existing_address.is_default:
        raise HTTPException(
            status_code=400,
            detail=(
                "Alamat utama tidak dapat dihapus. "
                "Jadikan alamat lain sebagai alamat utama terlebih dahulu."
            ),
        )

    # 5. Cek apakah alamat pernah digunakan order
    has_order = (
        db.query(Order.id)
        .filter(Order.address_id == address_id)
        .first()
        is not None
    )

    try:
        if has_order:
            # Arsipkan jika sudah digunakan order
            existing_address.is_active = False
            message = "Alamat berhasil diarsipkan."
        else:
            # Hapus permanen jika belum digunakan order
            db.delete(existing_address)
            message = "Alamat berhasil dihapus."

        db.commit()

    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Gagal memproses penghapusan alamat.",
        )

    return {
        "message": message,
        "address_id": address_id,
        "archived": has_order,
    }

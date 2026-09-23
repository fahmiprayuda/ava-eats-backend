from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models.customer import Customer
from models.customer_address import CustomerAddress
from schemas.customer_address import CustomerAddressRequest
from schemas.customer_address_update import CustomerAddressUpdate
from auth.dependencies import get_current_customer



router = APIRouter(
    prefix="/api/customers",
    tags=["Customers"]
)


@router.post("/{customer_id}/addresses")
def add_customer_address(
    customer_id: int,
    address_request: CustomerAddressRequest,
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
            detail="Anda tidak memiliki akses untuk menambahkan alamat ini"
        )

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
        is_default=address_request.is_default
    )

    db.add(new_address)
    db.commit()
    db.refresh(new_address)

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
            "is_default": new_address.is_default
        }
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

    addresses = customer.addresses

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
    existing_address = db.query(CustomerAddress).filter(
        CustomerAddress.id == address_id,
        CustomerAddress.customer_id == customer_id
    ).first()

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

    # 4. Update data
    existing_address.label = address.label
    existing_address.recipient_name = address.recipient_name
    existing_address.phone = address.phone
    existing_address.address = address.address
    existing_address.province = address.province
    existing_address.city = address.city
    existing_address.district = address.district
    existing_address.postal_code = address.postal_code
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
    selected_address = db.query(CustomerAddress).filter(
        CustomerAddress.id == address_id,
        CustomerAddress.customer_id == customer_id
    ).first()

    if not selected_address:
        raise HTTPException(
            status_code=404,
            detail="Alamat tidak ditemukan"
        )

    # 3. Jadikan semua alamat customer bukan default
    addresses = db.query(CustomerAddress).filter(
        CustomerAddress.customer_id == customer_id
    ).all()

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
            "is_default": selected_address.is_default
        }
    }

@router.delete("/{customer_id}/addresses/{address_id}")
def delete_address(
    customer_id: int,
    address_id: int,
    db: Session = Depends(get_db),
    current_customer: Customer = Depends(get_current_customer)
):
    if customer_id != current_customer.id:
        raise HTTPException(
            status_code=403,
            detail="Anda tidak memiliki akses untuk menghapus alamat ini"
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

    # 2. Cari alamat milik customer
    existing_address = db.query(CustomerAddress).filter(
        CustomerAddress.id == address_id,
        CustomerAddress.customer_id == customer_id
    ).first()

    if not existing_address:
        raise HTTPException(
            status_code=404,
            detail="Alamat tidak ditemukan"
        )

    # 3. Cek apakah alamat adalah alamat utama
    if existing_address.is_default:
        raise HTTPException(
            status_code=400,
            detail="Alamat utama tidak dapat dihapus. Jadikan alamat lain sebagai alamat utama terlebih dahulu."
        )

    # 4. Hapus alamat
    db.delete(existing_address)
    db.commit()

    return {
        "message": "Alamat berhasil dihapus"
    }
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models.customer import Customer
from models.order import Order
from models.payment import Payment
from models.shipment import Shipment
from schemas.customer import CustomerRequest, CustomerLoginRequest, CustomerUpdateRequest
from schemas.order_response import MyOrderResponse
from auth.jwt import create_access_token
from utils.password import hash_password, verify_password
from auth.dependencies import get_current_customer
from services.midtrans import sync_payment_status


router = APIRouter(
    prefix="/api/customers",
    tags=["Customers"]
)

@router.post("/register")
def register_customer(
    customer: CustomerRequest,
    db: Session = Depends(get_db)
):

    existing_customer = db.query(Customer).filter(
        Customer.phone == customer.phone.strip()
    ).first()

    if existing_customer:
        raise HTTPException(
            status_code=400,
            detail="Nomor WhatsApp sudah terdaftar"
        )

    new_customer = Customer(
        phone=customer.phone.strip(),
        password=hash_password(customer.password),
        name=customer.name.strip()
    )

    db.add(new_customer)
    db.commit()
    db.refresh(new_customer)

    access_token = create_access_token({
        "sub": str(new_customer.id),
        "phone": new_customer.phone,
        "role": "customer"
    })

    return {
        "message": "Customer berhasil dibuat",
        "access_token": access_token,
        "token_type": "bearer",
        "customer": {
            "id": new_customer.id,
            "phone": new_customer.phone,
            "name": new_customer.name
        }
    }

@router.post("/login")
def login_customer(
    data: CustomerLoginRequest,
    db: Session = Depends(get_db)
):
    customer = db.query(Customer).filter(
        Customer.phone == data.phone
    ).first()

    if not customer:
        raise HTTPException(
            status_code=401,
            detail="Nomor WhatsApp atau password salah"
        )

    password_valid = verify_password(
        data.password,
        customer.password
    )

    if not password_valid:
        raise HTTPException(
            status_code=401,
            detail="Nomor WhatsApp atau password salah"
        )

    access_token = create_access_token({
        "sub": str(customer.id),
        "phone": customer.phone,
        "role": "customer"
    })

    return {
        "access_token": access_token,
        "token_type": "bearer"
    }

@router.get("/me")
def get_my_profile(
    current_customer: Customer = Depends(get_current_customer)
):
    return {
        "id": current_customer.id,
        "phone": current_customer.phone,
        "name": current_customer.name
    }

@router.put("/me")
def update_my_profile(
    data: CustomerUpdateRequest,
    current_customer: Customer = Depends(get_current_customer),
    db: Session = Depends(get_db)
):
    # 1. Update nama jika diberikan
    if data.name and data.name.strip():
        current_customer.name = data.name.strip()

    # 2. Update nomor WhatsApp jika diubah
    if data.phone and data.phone.strip() != current_customer.phone:
        clean_phone = data.phone.strip()
        existing = db.query(Customer).filter(
            Customer.phone == clean_phone,
            Customer.id != current_customer.id
        ).first()

        if existing:
            raise HTTPException(
                status_code=400,
                detail="Nomor WhatsApp sudah digunakan oleh akun lain"
            )
        current_customer.phone = clean_phone

    # 3. Update password jika diberikan
    if data.new_password:
        if not data.current_password:
            raise HTTPException(
                status_code=400,
                detail="Password saat ini wajib diisi untuk mengganti password"
            )
        if not verify_password(data.current_password, current_customer.password):
            raise HTTPException(
                status_code=400,
                detail="Password saat ini tidak sesuai"
            )
        current_customer.password = hash_password(data.new_password)

    db.commit()
    db.refresh(current_customer)

    # Buat token baru dengan data nomor hp terbaru
    access_token = create_access_token({
        "sub": str(current_customer.id),
        "phone": current_customer.phone,
        "role": "customer"
    })

    return {
        "message": "Profil berhasil diperbarui",
        "customer": {
            "id": current_customer.id,
            "phone": current_customer.phone,
            "name": current_customer.name
        },
        "access_token": access_token
    }

@router.get("/me/orders", response_model=List[MyOrderResponse])
def get_my_orders(
    current_customer: Customer = Depends(get_current_customer),
    db: Session = Depends(get_db)
):
    orders = (
        db.query(Order)
        .filter(Order.customer_id == current_customer.id)
        .order_by(Order.created_at.desc())
        .all()
    )

    for order in orders:
        latest_payment = (
            db.query(Payment)
            .filter(Payment.order_id == order.id)
            .order_by(Payment.id.desc())
            .first()
        )

        if latest_payment and latest_payment.status == "pending":
            latest_payment = sync_payment_status(db, latest_payment, order)

        order.payment_id = (
            latest_payment.id if latest_payment else None
        )
        order.payment_status = (
            latest_payment.status if latest_payment else None
        )

        shipment = (
            db.query(Shipment)
            .filter(Shipment.order_id == order.id)
            .first()
        )
        if shipment:
            order.courier = shipment.courier
            order.courier_service = shipment.service
            order.shipment_status = shipment.status
            order.tracking_number = shipment.tracking_number
            order.tracking_url = shipment.tracking_url
            order.driver_name = shipment.driver_name
            order.driver_phone = shipment.driver_phone
            order.driver_plate_number = shipment.driver_plate_number
            order.driver_photo_url = shipment.driver_photo_url

            # Default tracking URL jika belum diset
            if not order.tracking_url and shipment.tracking_number:
                if (shipment.courier or "").lower() == "paxel":
                    order.tracking_url = f"https://paxel.co/track?waybill={shipment.tracking_number}"
                elif shipment.biteship_order_id:
                    order.tracking_url = f"https://biteship.com/track/{shipment.biteship_order_id}"
        else:
            order.courier = None
            order.courier_service = None
            order.shipment_status = None
            order.tracking_number = None
            order.tracking_url = None
            order.driver_name = None
            order.driver_phone = None
            order.driver_plate_number = None
            order.driver_photo_url = None

    return orders
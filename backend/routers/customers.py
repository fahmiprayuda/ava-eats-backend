from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, or_

from database import get_db
from models.customer import Customer
from models.customer_address import CustomerAddress
from models.admin import Admin
from models.order import Order
from models.payment import Payment
from models.shipment import Shipment
from schemas.customer import (
    CustomerRequest,
    CustomerLoginRequest,
    CustomerUpdateRequest,
    AdminCustomerCreateRequest,
    AdminCustomerUpdateRequest,
    AdminCustomerResponse,
)
from schemas.order_response import MyOrderResponse
from auth.jwt import create_access_token
from utils.password import hash_password, verify_password
from auth.dependencies import get_current_customer, require_admin, require_super_admin
from utils.audit import create_audit_log
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


# =========================================================================
# ADMIN CUSTOMER MANAGEMENT (CRUD)
# =========================================================================

@router.get("", response_model=List[AdminCustomerResponse])
def get_all_customers_admin(
    search: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(require_admin)
):
    query = db.query(Customer)
    if search and search.strip():
        term = f"%{search.strip()}%"
        query = query.filter(
            or_(
                Customer.name.ilike(term),
                Customer.phone.ilike(term)
            )
        )

    customers = query.order_by(Customer.id.desc()).offset(offset).limit(limit).all()

    result = []
    VALID_SPENT_STATUSES = {"paid", "processing", "shipped", "delivered", "completed", "done"}

    for c in customers:
        # Hitung total pesanan dan total belanja akumulatif yang valid (lunas / selesai)
        orders = db.query(Order).filter(Order.customer_id == c.id).all()
        orders_count = len(orders)
        total_spent = sum(
            o.grand_total or o.total_amount or 0
            for o in orders
            if str(o.status or "").lower() in VALID_SPENT_STATUSES
        )

        result.append(
            AdminCustomerResponse(
                id=c.id,
                name=c.name,
                phone=c.phone,
                orders_count=orders_count,
                total_spent=int(total_spent)
            )
        )

    return result


@router.post("/admin", response_model=AdminCustomerResponse)
def create_customer_by_admin(
    data: AdminCustomerCreateRequest,
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(require_super_admin)
):
    existing = db.query(Customer).filter(Customer.phone == data.phone.strip()).first()
    if existing:
        raise HTTPException(status_code=400, detail="Nomor WhatsApp sudah digunakan oleh customer lain.")

    customer = Customer(
        phone=data.phone.strip(),
        name=data.name.strip(),
        password=hash_password(data.password.strip())
    )
    db.add(customer)
    db.commit()
    db.refresh(customer)

    create_audit_log(
        db=db,
        user_type="admin",
        user_id=current_admin.id,
        action="CREATE",
        entity_type="customer",
        entity_id=customer.id,
        description=f"Pelanggan baru ditambahkan oleh admin: {customer.name} ({customer.phone})"
    )
    db.commit()

    return AdminCustomerResponse(
        id=customer.id,
        name=customer.name,
        phone=customer.phone,
        orders_count=0,
        total_spent=0
    )


@router.put("/admin/{customer_id}", response_model=AdminCustomerResponse)
def update_customer_by_admin(
    customer_id: int,
    data: AdminCustomerUpdateRequest,
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(require_super_admin)
):
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Pelanggan tidak ditemukan")

    changes = []
    if data.name and data.name.strip() != customer.name:
        changes.append(f"nama: {customer.name} -> {data.name.strip()}")
        customer.name = data.name.strip()

    if data.phone and data.phone.strip() != customer.phone:
        duplicate = db.query(Customer).filter(
            Customer.phone == data.phone.strip(),
            Customer.id != customer_id
        ).first()
        if duplicate:
            raise HTTPException(status_code=400, detail="Nomor WhatsApp sudah digunakan pelanggan lain")
        changes.append(f"no hp: {customer.phone} -> {data.phone.strip()}")
        customer.phone = data.phone.strip()

    if data.password and data.password.strip():
        customer.password = hash_password(data.password.strip())
        changes.append("password di-reset")

    db.commit()
    db.refresh(customer)

    if changes:
        create_audit_log(
            db=db,
            user_type="admin",
            user_id=current_admin.id,
            action="UPDATE",
            entity_type="customer",
            entity_id=customer.id,
            description=f"Data pelanggan {customer.name} ({customer.phone}) diperbarui: {', '.join(changes)}"
        )
        db.commit()

    orders = db.query(Order).filter(Order.customer_id == customer.id).all()
    orders_count = len(orders)
    VALID_SPENT_STATUSES = {"paid", "processing", "shipped", "delivered", "completed", "done"}
    total_spent = sum(
        o.grand_total or o.total_amount or 0
        for o in orders
        if str(o.status or "").lower() in VALID_SPENT_STATUSES
    )

    return AdminCustomerResponse(
        id=customer.id,
        name=customer.name,
        phone=customer.phone,
        orders_count=orders_count,
        total_spent=int(total_spent)
    )


@router.delete("/admin/{customer_id}")
def delete_customer_by_admin(
    customer_id: int,
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(require_super_admin)
):
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Pelanggan tidak ditemukan")

    order_count = db.query(Order).filter(Order.customer_id == customer_id).count()
    if order_count > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Pelanggan tidak dapat dihapus karena memiliki {order_count} riwayat pesanan (menjaga integritas data finansial)."
        )

    # Hapus alamat terkait
    db.query(CustomerAddress).filter(CustomerAddress.customer_id == customer_id).delete()

    deleted_name = customer.name
    deleted_phone = customer.phone

    db.delete(customer)
    db.commit()

    create_audit_log(
        db=db,
        user_type="admin",
        user_id=current_admin.id,
        action="DELETE",
        entity_type="customer",
        entity_id=customer_id,
        description=f"Pelanggan {deleted_name} ({deleted_phone}) dihapus dari sistem."
    )
    db.commit()

    return {"message": f"Pelanggan {deleted_name} berhasil dihapus"}

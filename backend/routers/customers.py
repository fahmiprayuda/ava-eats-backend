from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models.customer import Customer
from models.order import Order
from schemas.customer import CustomerRequest, CustomerLoginRequest
from schemas.order_response import OrderResponse
from auth.jwt import create_access_token
from utils.password import hash_password, verify_password
from auth.dependencies import get_current_customer


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
        Customer.phone == customer.phone
    ).first()

    if existing_customer:
        raise HTTPException(
            status_code=400,
            detail="Nomor WhatsApp sudah terdaftar"
        )

    new_customer = Customer(
        phone=customer.phone,
        password=hash_password(customer.password),
        name=customer.name
    )

    db.add(new_customer)
    db.commit()
    db.refresh(new_customer)

    return {
        "message": "Customer berhasil dibuat",
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

@router.get("/me/orders", response_model=List[OrderResponse])
def get_my_orders(
    current_customer: Customer = Depends(get_current_customer),
    db: Session = Depends(get_db)
):
    orders = db.query(Order).filter(
        Order.customer_id == current_customer.id
    ).order_by(
        Order.created_at.desc()
    ).all()

    return orders
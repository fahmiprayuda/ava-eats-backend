from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import get_db
from models.admin import Admin
from models.customer import Customer
from models.customer_address import CustomerAddress
from models.product import Product
from models.order import Order
from models.order_item import OrderItem

from schemas.order import OrderRequest
from schemas.order_response import OrderResponse
from schemas.order_status import OrderStatusRequest

from auth.dependencies import get_current_customer, require_admin

from utils.audit import create_audit_log


router = APIRouter(
    prefix="/api/orders",
    tags=["Orders"]
)

@router.post("", response_model=OrderResponse)
def create_order(
    data: OrderRequest,
    current_customer: Customer = Depends(get_current_customer),
    db: Session = Depends(get_db)
):

    # 2. Cek address
    address = db.query(CustomerAddress).filter(
        CustomerAddress.id == data.address_id
    ).first()

    if not address:
        raise HTTPException(
            status_code=404,
            detail="Address tidak ditemukan"
        )

    # 3. Pastikan address milik customer
    if address.customer_id != current_customer.id:
        raise HTTPException(
            status_code=403,
            detail="Anda tidak memiliki akses ke alamat ini"
    )

    # 4. Cek product + stock
    order_items_data = []

    total_amount = 0

    for item in data.items:

        product = db.query(Product).filter(
            Product.id == item.product_id
        ).first()

        if not product:
            raise HTTPException(
                status_code=404,
                detail=f"Product ID {item.product_id} tidak ditemukan"
            )

        if not product.is_available:
            raise HTTPException(
                status_code=400,
                detail=f"Product '{product.name}' sedang tidak tersedia"
            )

        if product.stock < item.quantity:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Stock '{product.name}' tidak cukup. "
                    f"Stock tersedia: {product.stock}"
                )
            )

        subtotal = product.price * item.quantity

        total_amount += subtotal

        order_items_data.append({
            "product": product,
            "quantity": item.quantity,
            "subtotal": subtotal
        })

    # 5. Generate order code
    today = datetime.now().strftime("%Y-%m-%d")

    last_order = db.query(Order).filter(
        Order.order_code.like(f"ORDER-{today}-%")
    ).order_by(
        Order.id.desc()
    ).first()

    if last_order:
        last_number = int(last_order.order_code.split("-")[-1])
        next_number = last_number + 1
    else:
        next_number = 1

    order_code = f"ORDER-{today}-{next_number:02d}"


    # 6. Create order
    order = Order(
        order_code=order_code,

        customer_id=current_customer.id,
        address_id=address.id,

        recipient_name=address.recipient_name,
        phone=address.phone,
        address=address.address,
        province=address.province,
        city=address.city,
        district=address.district,
        postal_code=address.postal_code,

        notes=data.notes,

        total_amount=total_amount,

        payment_method=data.payment_method,

        status="pending"
    )

    db.add(order)

    # Supaya order.id tersedia
    db.flush()

    # 7. Create order items + kurangi stock
    for item_data in order_items_data:

        product = item_data["product"]
        quantity = item_data["quantity"]
        subtotal = item_data["subtotal"]

        order_item = OrderItem(
            order_id=order.id,
            product_id=product.id,
            product_name=product.name,
            price=product.price,
            quantity=quantity,
            subtotal=subtotal
        )

        db.add(order_item)

        product.stock -= quantity

        if product.stock == 0:
            product.is_available = False

    create_audit_log(
        db=db,
        user_type="customer",
        user_id=current_customer.id,
        action="ORDER_CREATED",
        entity_type="Order",
        entity_id=order.id,
        description=f"Order {order.order_code} "
                    f"has been created by customer {current_customer.name}"
    )

    # 8. Simpan semuanya
    db.commit()
    db.refresh(order)

    return order

@router.get("", response_model=List[OrderResponse])
def get_orders(
    status: str = Query(
        None,
        description="Filter berdasarkan status order"
    ),
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(require_admin)
):
    query = db.query(Order)

    if status:
        query = query.filter(
            Order.status == status
        )

    orders = query.order_by(
        Order.created_at.desc()
    ).all()

    return orders

@router.get("/{order_id}", response_model=OrderResponse)
def get_order(
    order_id: int,
    db: Session = Depends(get_db),
    current_customer: Customer = Depends(get_current_customer)
):
    order = db.query(Order).filter(
        Order.id == order_id
    ).first()

    if not order:
        raise HTTPException(
            status_code=404,
            detail="Order tidak ditemukan"
        )

    if order.customer_id != current_customer.id:
        raise HTTPException(
            status_code=403,
            detail="Anda tidak memiliki akses untuk melihat order ini"
        )

    return order


@router.put("/{order_id}/status", response_model=OrderResponse)
def update_order_status(
    order_id: int,
    data: OrderStatusRequest,
    db: Session = Depends(get_db),
    current_customer: Customer = Depends(get_current_customer)
):
    # 1. Cek order
    order = db.query(Order).filter(
        Order.id == order_id
    ).first()

    if not order:
        raise HTTPException(
            status_code=404,
            detail="Order tidak ditemukan"
        )

    # 2. Cek perpindahan status
    allowed_transitions = {
        "pending": ["paid"],
        "paid": ["done"],
        "done": []
    }

    if data.status not in allowed_transitions[order.status]:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Order dengan status '{order.status}' "
                f"tidak bisa diubah menjadi '{data.status}'"
            )
        )

    # 3. Update status
    order.status = data.status

    db.commit()
    db.refresh(order)

    return order
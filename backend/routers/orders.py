import os
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
from models.payment import Payment

from schemas.order import OrderRequest
from schemas.order_response import OrderResponse
from schemas.order_status import OrderStatusRequest

from auth.dependencies import get_current_customer, require_admin

from utils.audit import create_audit_log
from services.midtrans import get_transaction_status


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

    fulfillment_method = data.fulfillment_method
    address = None

    if fulfillment_method == "delivery":
        if not data.address_id:
            raise HTTPException(
                status_code=400,
                detail="Pilih alamat pengiriman terlebih dahulu",
            )

        address = (
            db.query(CustomerAddress)
            .filter(
                CustomerAddress.id == data.address_id,
                CustomerAddress.customer_id == current_customer.id,
                CustomerAddress.is_active.is_(True),
            )
            .first()
        )

        if not address:
            raise HTTPException(
                status_code=404,
                detail="Alamat aktif tidak ditemukan",
            )

    elif fulfillment_method == "pickup":
        address = None

    else:
        raise HTTPException(
            status_code=400,
            detail="Metode pemenuhan pesanan tidak valid"
        )

    # 3. Pastikan address milik customer untuk delivery
    if fulfillment_method == "delivery":
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


    print("=== CHECK ADDRESS COORDINATES ===")
    if fulfillment_method == "delivery":
        print("Address ID:", address.id)
        print("Address latitude:", repr(address.latitude))
        print("Address longitude:", repr(address.longitude))
    else:
        print("Pickup order: menggunakan lokasi toko")
    
    # 6. Create order
    if fulfillment_method == "delivery":
        order_address_id = address.id
        recipient_name = address.recipient_name
        phone = address.phone
        order_address = address.address
        province = address.province
        city = address.city
        district = address.district
        postal_code = address.postal_code
        latitude = address.latitude
        longitude = address.longitude

    else:
        order_address_id = None
        recipient_name = current_customer.name
        phone = current_customer.phone
        order_address = os.getenv(
            "STORE_ADDRESS",
            "Cluster The Awa, Blok B1 No 27, Ciriung, "
            "Kec. Cibinong, Kabupaten Bogor, Jawa Barat",
        )
        province = "Jawa Barat"
        city = "Kabupaten Bogor"
        district = "Cibinong"
        postal_code = os.getenv("STORE_POSTAL_CODE", "16918")
        latitude = float(
            os.getenv("STORE_LATITUDE", "-6.459818049304167")
        )
        longitude = float(
            os.getenv("STORE_LONGITUDE", "106.87384403716149")
        )

    order = Order(
        order_code=order_code,
        customer_id=current_customer.id,
        address_id=order_address_id,
        fulfillment_method=fulfillment_method,
        recipient_name=recipient_name,
        phone=phone,
        address=order_address,
        province=province,
        city=city,
        district=district,
        postal_code=postal_code,
        latitude=latitude,
        longitude=longitude,
        notes=data.notes,
        total_amount=total_amount,
        shipping_cost=0,
        grand_total=total_amount,
        status="pending",
    )

    db.add(order)

    # Supaya order.id tersedia
    db.flush()
    print("=== CHECK CREATED ORDER ===")
    print("Order ID:", order.id)
    print("Order latitude:", repr(order.latitude))
    print("Order longitude:", repr(order.longitude))

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

@router.post("/{order_id}/cancel", response_model=OrderResponse)
def cancel_order(
    order_id: int,
    db: Session = Depends(get_db),
    current_customer: Customer = Depends(get_current_customer)
):
    # 1. Cari order
    order = db.query(Order).filter(
        Order.id == order_id
    ).first()

    if not order:
        raise HTTPException(
            status_code=404,
            detail="Order tidak ditemukan"
        )

    # 2. Pastikan order milik customer
    if order.customer_id != current_customer.id:
        raise HTTPException(
            status_code=403,
            detail="Anda tidak memiliki akses ke order ini"
        )

    # 3. Hanya order pending yang boleh dibatalkan
    if order.status != "pending":
        raise HTTPException(
            status_code=400,
            detail=(
                f"Order dengan status '{order.status}' "
                "tidak bisa dibatalkan"
            )
        )

    # 4. Cari payment Midtrans yang masih pending
    payment = db.query(Payment).filter(
        Payment.order_id == order.id,
        Payment.gateway == "midtrans",
        Payment.status == "pending"
    ).order_by(
        Payment.id.desc()
    ).first()

    # 5. Kalau ada payment pending, cek status ke Midtrans
    if payment:
        if not payment.gateway_order_id:
            raise HTTPException(
                status_code=500,
                detail="Payment Midtrans tidak memiliki gateway_order_id"
            )

        try:
            midtrans_status = get_transaction_status(
                payment.gateway_order_id
            )
        except Exception as e:
            raise HTTPException(
                status_code=502,
                detail=(
                    "Gagal mengecek status payment ke Midtrans: "
                    f"{str(e)}"
                )
            )

        transaction_status = midtrans_status.get(
            "transaction_status"
        )

        # Payment masih pending di Midtrans
        if transaction_status == "pending":
            raise HTTPException(
                status_code=400,
                detail=(
                    "Order memiliki payment yang masih menunggu "
                    "pembayaran. Batalkan payment terlebih dahulu."
                )
            )

        # Payment sudah berhasil
        if transaction_status in ["settlement", "capture"]:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Payment sudah berhasil. "
                    "Order tidak dapat dibatalkan melalui endpoint ini."
                )
            )

        # Payment expired / gagal
        if transaction_status == "expire":
            payment.status = "expired"

        elif transaction_status in [
            "deny",
            "cancel",
            "failure"
        ]:
            payment.status = "rejected"

    # 6. Kembalikan stock
    for item in order.items:
        product = db.query(Product).filter(
            Product.id == item.product_id
        ).first()

        if product:
            product.stock += item.quantity

    # 7. Ubah status order
    order.status = "cancelled"

    # 8. Audit trail
    create_audit_log(
        db=db,
        user_type="customer",
        user_id=current_customer.id,
        action="ORDER_CANCELLED",
        entity_type="Order",
        entity_id=order.id,
        description=(
            f"Order {order.order_code} "
            f"has been cancelled by customer "
            f"{current_customer.name}"
        )
    )

    # 9. Simpan semua perubahan
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
    current_admin: Admin = Depends(require_admin)
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
        "done": [],
        "cancelled": []
    }

    if data.status not in allowed_transitions.get(
        order.status,
        []
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                f"Order dengan status '{order.status}' "
                f"tidak bisa diubah menjadi '{data.status}'"
            )
        )

    # 3. Update status
    order.status = data.status

    # 4. Audit trail
    create_audit_log(
        db=db,
        user_type="admin",
        user_id=current_admin.id,
        action="ORDER_STATUS_UPDATED",
        entity_type="Order",
        entity_id=order.id,
        description=(
            f"Order {order.order_code} "
            f"status changed to {data.status} "
            f"by admin {current_admin.name}"
        )
    )

    # 5. Simpan
    db.commit()
    db.refresh(order)

    return order
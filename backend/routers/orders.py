import os
import shutil
import uuid
from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, File, UploadFile
from sqlalchemy.orm import Session

from database import get_db

from models.admin import Admin
from models.customer import Customer
from models.customer_address import CustomerAddress
from models.product import Product
from models.order import Order
from models.order_item import OrderItem
from models.payment import Payment
from models.shipment import Shipment
from models.promo_code import PromoCode, PromoCodeUsage

from schemas.order import OrderRequest
from schemas.order_response import OrderResponse
from schemas.order_status import OrderStatusRequest, OrderRefundRequest

from auth.dependencies import get_current_customer, require_admin

from utils.audit import create_audit_log
from services.midtrans import get_transaction_status
from services.whatsapp import notify_order_ready_pickup, notify_order_refunded
from routers.promos import calculate_discount


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

    shipping_cost = 0
    if fulfillment_method == "delivery" and data.shipping_cost:
        shipping_cost = max(0, int(data.shipping_cost))

    packaging_fee = 0
    if data.packaging_fee is not None:
        packaging_fee = max(0, int(data.packaging_fee))

    # Validasi & Aplikasikan Kupon Promo jika ada
    promo_code_id = None
    applied_promo_code = None
    discount_amount = 0

    if data.promo_code and data.promo_code.strip():
        clean_code = data.promo_code.strip().upper()
        now = datetime.now()
        promo = db.query(PromoCode).filter(PromoCode.code == clean_code).first()

        if not promo or not promo.is_active:
            raise HTTPException(
                status_code=400,
                detail=f"Kupon promo '{clean_code}' tidak valid atau sedang tidak aktif."
            )

        if promo.start_date and now < promo.start_date:
            raise HTTPException(
                status_code=400,
                detail=f"Kupon promo '{clean_code}' baru dapat digunakan mulai {promo.start_date.strftime('%d %b %Y %H:%M')}."
            )

        if promo.end_date and now > promo.end_date:
            raise HTTPException(
                status_code=400,
                detail=f"Kupon promo '{clean_code}' sudah kedaluwarsa."
            )

        if promo.usage_limit and promo.used_count >= promo.usage_limit:
            raise HTTPException(
                status_code=400,
                detail=f"Kuota kupon promo '{clean_code}' sudah habis."
            )

        user_usage_count = db.query(PromoCodeUsage).filter(
            PromoCodeUsage.promo_code_id == promo.id,
            PromoCodeUsage.customer_id == current_customer.id
        ).count()

        if user_usage_count >= promo.usage_limit_per_user:
            raise HTTPException(
                status_code=400,
                detail=f"Anda sudah mencapai batas penggunaan kupon '{clean_code}'."
            )

        if total_amount < promo.min_order_amount:
            raise HTTPException(
                status_code=400,
                detail=f"Kupon promo '{clean_code}' membutuhkan minimum belanja Rp {promo.min_order_amount:,.0f}."
            )

        if promo.discount_type == "shipping_discount" and shipping_cost <= 0:
            raise HTTPException(
                status_code=400,
                detail=f"Kupon '{clean_code}' adalah voucher potongan ongkir, namun pesanan Anda tidak memiliki biaya ongkir."
            )

        discount_amount = calculate_discount(promo, total_amount, shipping_cost)
        promo_code_id = promo.id
        applied_promo_code = promo.code
        promo.used_count += 1

    grand_total = max(0, total_amount + shipping_cost + packaging_fee - discount_amount)

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
        shipping_cost=shipping_cost,
        packaging_fee=packaging_fee,
        promo_code_id=promo_code_id,
        promo_code=applied_promo_code,
        discount_amount=discount_amount,
        grand_total=grand_total,
        notify_whatsapp=data.notify_whatsapp if data.notify_whatsapp is not None else True,
        status="pending",
    )

    db.add(order)

    # Supaya order.id tersedia
    db.flush()

    if promo_code_id:
        usage = PromoCodeUsage(
            promo_code_id=promo_code_id,
            customer_id=current_customer.id,
            order_id=order.id,
            discount_amount=discount_amount,
        )
        db.add(usage)
    print("=== CHECK CREATED ORDER ===")
    print("Order ID:", order.id)
    print("Order latitude:", repr(order.latitude))
    print("Order longitude:", repr(order.longitude))

    # Jika delivery dan kurir sudah dipilih di checkout, otomatis buat record Shipment
    if fulfillment_method == "delivery" and data.courier_code and data.service_code:
        shipment = Shipment(
            order_id=order.id,
            courier=data.courier_code,
            service=data.service_code,
            shipping_cost=shipping_cost,
            status="pending",
        )
        db.add(shipment)
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

    # 7b. Kembalikan kuota promo jika order ini memakai kupon promo
    if order.promo_code_id:
        promo = db.query(PromoCode).filter(PromoCode.id == order.promo_code_id).first()
        if promo and promo.used_count > 0:
            promo.used_count -= 1
        db.query(PromoCodeUsage).filter(
            PromoCodeUsage.order_id == order.id
        ).delete()

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
    status_val = data.status.value if hasattr(data.status, "value") else str(data.status)

    allowed_transitions = {
        "pending": ["paid", "cancelled"],
        "paid": ["processing", "delivered", "completed", "done", "cancelled"],
        "processing": ["delivered", "completed", "done", "cancelled"],
        "delivered": ["completed", "done", "cancelled"],
        "completed": [],
        "done": [],
        "cancelled": []
    }

    if status_val not in allowed_transitions.get(order.status, []):
        raise HTTPException(
            status_code=400,
            detail=(
                f"Order dengan status '{order.status}' "
                f"tidak bisa diubah menjadi '{status_val}'"
            )
        )

    old_status = order.status
    # 3. Update status
    order.status = status_val

    # Sinkronisasi status shipment jika ada
    if order.shipment:
        if status_val == "delivered":
            order.shipment.status = "delivering"
        elif status_val in ["completed", "done"]:
            order.shipment.status = "delivered"
        elif status_val == "cancelled":
            order.shipment.status = "cancelled"

    if status_val == "delivered" and (order.fulfillment_method or order.order_type) == "pickup":
        try:
            notify_order_ready_pickup(order, order.customer)
        except Exception as wa_err:
            print(f"[WA Error notify_order_ready_pickup] {wa_err}")

    admin_display = getattr(current_admin, "name", None) or getattr(current_admin, "username", "Admin")

    # Penanganan khusus jika order dibatalkan (cancelled)
    if status_val == "cancelled":
        order.cancellation_reason = (
            data.cancellation_reason
            or "Dibatalkan oleh Admin"
        )
        # Kembalikan stok produk
        for item in order.items:
            product = db.query(Product).filter(Product.id == item.product_id).first()
            if product:
                product.stock += item.quantity

        # Kembalikan kuota promo jika order ini memakai kupon promo
        if order.promo_code_id:
            promo = db.query(PromoCode).filter(PromoCode.id == order.promo_code_id).first()
            if promo and promo.used_count > 0:
                promo.used_count -= 1
            db.query(PromoCodeUsage).filter(
                PromoCodeUsage.order_id == order.id
            ).delete()

        was_paid = old_status in ["paid", "processing", "delivered"]
        if was_paid:
            order.refund_status = "refund_pending"
            order.refund_note = data.refund_note or "Menunggu transfer pengembalian dana dari Admin"
            audit_description = (
                f"Admin {admin_display} membatalkan pesanan {order.order_code} "
                f"dari status '{old_status}'. Alasan: '{order.cancellation_reason}'. "
                f"Stok produk dikembalikan. Status refund: REFUND_PENDING (Rp {order.grand_total:,})."
            )
        else:
            order.refund_status = "not_applicable"
            audit_description = (
                f"Admin {admin_display} membatalkan pesanan {order.order_code} "
                f"dari status '{old_status}'. Alasan: '{order.cancellation_reason}'. "
                f"Stok produk dikembalikan."
            )
    else:
        audit_description = (
            f"Admin {admin_display} mengubah status pesanan {order.order_code} "
            f"dari '{old_status}' menjadi '{status_val}'"
        )

    # 4. Audit trail
    create_audit_log(
        db=db,
        user_type="admin",
        user_id=current_admin.id,
        action="ORDER_STATUS_UPDATED",
        entity_type="Order",
        entity_id=order.id,
        description=audit_description,
    )

    # 5. Simpan
    db.commit()
    db.refresh(order)

    return order


UPLOAD_REFUNDS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "uploads",
    "refunds"
)


@router.post("/upload-refund-proof")
def upload_refund_proof(
    file: UploadFile = File(...),
    current_admin: Admin = Depends(require_admin)
):
    """
    Endpoint bagi Admin untuk mengunggah foto / screenshot bukti transfer refund.
    File disimpan di folder backend/uploads/refunds.
    """
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(
            status_code=400,
            detail="File harus berformat gambar (JPG, PNG, WEBP, GIF)."
        )

    os.makedirs(UPLOAD_REFUNDS_DIR, exist_ok=True)

    ext = os.path.splitext(file.filename)[1].lower() if file.filename else ".jpg"
    if not ext or ext not in [".jpg", ".jpeg", ".png", ".webp", ".gif"]:
        ext = ".jpg"

    unique_filename = f"refund_{uuid.uuid4().hex[:12]}_{int(datetime.now().timestamp())}{ext}"
    destination_path = os.path.join(UPLOAD_REFUNDS_DIR, unique_filename)

    with open(destination_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    return {
        "message": "Bukti transfer refund berhasil diunggah",
        "proof_url": f"/uploads/refunds/{unique_filename}"
    }


@router.put("/{order_id}/refund", response_model=OrderResponse)
def confirm_order_refund(
    order_id: int,
    data: OrderRefundRequest,
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(require_admin),
):
    """
    Endpoint bagi Admin untuk mengonfirmasi bahwa dana (refund)
    telah berhasil ditransfer kembali ke rekening/e-wallet pelanggan.
    """
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(
            status_code=404,
            detail="Order tidak ditemukan",
        )

    if order.status != "cancelled":
        raise HTTPException(
            status_code=400,
            detail="Hanya pesanan yang dibatalkan yang dapat diproses refund",
        )

    if order.refund_status == "refunded":
        raise HTTPException(
            status_code=400,
            detail="Pesanan ini sudah ditandai selesai refund",
        )

    order.refund_status = "refunded"
    order.refund_note = (
        data.refund_note
        or "Dana berhasil ditransfer kembali ke pelanggan"
    )
    if data.refund_proof_url:
        order.refund_proof_url = data.refund_proof_url

    order.refunded_at = datetime.now()

    admin_display = getattr(current_admin, "name", None) or getattr(current_admin, "username", "Admin")

    create_audit_log(
        db=db,
        user_type="admin",
        user_id=current_admin.id,
        action="ORDER_REFUND_COMPLETED",
        entity_type="Order",
        entity_id=order.id,
        description=(
            f"Admin {admin_display} mengonfirmasi pengembalian dana (refund) sebesar Rp {order.grand_total:,} "
            f"untuk pesanan {order.order_code} telah selesai. Catatan: '{order.refund_note}'"
            + (f" (Bukti transfer: {order.refund_proof_url})" if order.refund_proof_url else "")
        ),
    )

    db.commit()
    db.refresh(order)

    try:
        notify_order_refunded(order, order.customer)
    except Exception as wa_err:
        print(f"[WA Error notify_order_refunded] {wa_err}")

    return order
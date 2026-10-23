from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db
from models.promo_code import PromoCode, PromoCodeUsage, PromoCodeCustomer
from models.customer import Customer
from models.admin import Admin
from schemas.promo_code import (
    PromoCodeCreate,
    PromoCodeUpdate,
    PromoCodeResponse,
    PromoValidateRequest,
    PromoValidateResponse,
)
from auth.dependencies import get_current_customer, get_optional_customer, require_admin
from utils.audit import create_audit_log


router = APIRouter(
    prefix="/api/promos",
    tags=["Promotions & Vouchers"]
)


# =============================================================================
# HELPER: CALCULATE DISCOUNT
# =============================================================================
def calculate_discount(promo: PromoCode, subtotal: int, shipping_cost: int = 0) -> int:
    """
    Hitung nominal rupiah potongan diskon berdasarkan tipe kupon.
    """
    if promo.discount_type == "percentage":
        discount = (subtotal * promo.discount_value) // 100
        if promo.max_discount and promo.max_discount > 0:
            discount = min(discount, promo.max_discount)
        return max(0, min(subtotal, discount))

    elif promo.discount_type == "fixed_amount":
        return max(0, min(subtotal, promo.discount_value))

    elif promo.discount_type == "shipping_discount":
        return max(0, min(shipping_cost, promo.discount_value))

    return 0


# =============================================================================
# CUSTOMER ENDPOINTS
# =============================================================================

@router.post("/validate", response_model=PromoValidateResponse)
def validate_promo_code(
    data: PromoValidateRequest,
    current_customer: Optional[Customer] = Depends(get_optional_customer),
    db: Session = Depends(get_db)
):
    """
    Validasi kode promo secara real-time saat customer memasukkan kode di checkout.
    """
    clean_code = data.code.strip().upper()
    now = datetime.now()
    subtotal = data.effective_subtotal

    promo = db.query(PromoCode).filter(PromoCode.code == clean_code).first()
    if not promo:
        raise HTTPException(
            status_code=404,
            detail=f"Kode promo '{clean_code}' tidak ditemukan."
        )

    if not promo.is_active:
        raise HTTPException(
            status_code=400,
            detail=f"Kupon promo '{clean_code}' sedang tidak aktif."
        )

    if promo.start_date and now < promo.start_date:
        raise HTTPException(
            status_code=400,
            detail=f"Kupon promo '{clean_code}' baru dapat digunakan mulai {promo.start_date.strftime('%d %b %Y %H:%M')}."
        )

    if promo.end_date and now > promo.end_date:
        raise HTTPException(
            status_code=400,
            detail=f"Kupon promo '{clean_code}' sudah kedaluwarsa pada {promo.end_date.strftime('%d %b %Y %H:%M')}."
        )

    if promo.usage_limit and promo.used_count >= promo.usage_limit:
        raise HTTPException(
            status_code=400,
            detail=f"Kuota kupon promo '{clean_code}' sudah habis."
        )

    # Cek sasaran khusus pelanggan (targeted promo)
    if promo.target_type == "specific":
        if not current_customer:
            raise HTTPException(
                status_code=400,
                detail=f"Kupon promo '{clean_code}' khusus untuk pelanggan tertentu. Silakan masuk (login) ke akun Anda terlebih dahulu."
            )
        allowed_ids = {tc.customer_id for tc in promo.target_customers}
        if current_customer.id not in allowed_ids:
            raise HTTPException(
                status_code=400,
                detail=f"Maaf Moms, kupon promo '{clean_code}' hanya berlaku untuk pelanggan terpilih."
            )

    # Cek batas pemakaian per customer (jika customer login)
    if current_customer:
        user_usage_count = db.query(PromoCodeUsage).filter(
            PromoCodeUsage.promo_code_id == promo.id,
            PromoCodeUsage.customer_id == current_customer.id
        ).count()

        if user_usage_count >= promo.usage_limit_per_user:
            raise HTTPException(
                status_code=400,
                detail=f"Anda sudah mencapai batas penggunaan kupon '{clean_code}' (maksimal {promo.usage_limit_per_user}x per akun)."
            )

    # Cek minimum belanja
    if subtotal < promo.min_order_amount:
        raise HTTPException(
            status_code=400,
            detail=f"Kupon promo '{clean_code}' membutuhkan minimum belanja Rp {promo.min_order_amount:,.0f} (Subtotal Anda: Rp {subtotal:,.0f})."
        )

    # Khusus tipe subsidi ongkir, jika ongkir 0 (misal pickup) beri tahu customer
    if promo.discount_type == "shipping_discount" and data.shipping_cost <= 0:
        raise HTTPException(
            status_code=400,
            detail=f"Kupon '{clean_code}' adalah voucher potongan ongkir, namun pesanan Anda tidak memiliki biaya pengiriman."
        )

    discount_amount = calculate_discount(promo, subtotal, data.shipping_cost)

    promo_dict = {
        "id": promo.id,
        "code": promo.code,
        "name": promo.description or promo.code,
        "description": promo.description,
        "discount_type": promo.discount_type,
        "discount_value": promo.discount_value,
        "max_discount": promo.max_discount,
        "min_order_amount": promo.min_order_amount,
    }

    return PromoValidateResponse(
        valid=True,
        promo_code=promo.code,
        code=promo.code,
        name=promo.description or promo.code,
        description=promo.description,
        discount_type=promo.discount_type,
        discount_value=promo.discount_value,
        discount_amount=discount_amount,
        max_discount=promo.max_discount,
        min_order_amount=promo.min_order_amount,
        message=f"Kupon '{promo.code}' berhasil digunakan! Hemat Rp {discount_amount:,.0f}.",
        promo=promo_dict,
    )


@router.get("/active", response_model=List[PromoCodeResponse])
def get_active_promos(
    current_customer: Optional[Customer] = Depends(get_optional_customer),
    db: Session = Depends(get_db)
):
    """
    Daftar kupon promo yang sedang aktif.
    Jika pelanggan login, menampilkan promo publik dan promo khusus miliknya.
    Jika tidak login, hanya menampilkan promo publik.
    """
    now = datetime.now()
    promos = db.query(PromoCode).filter(
        PromoCode.is_active.is_(True),
        (PromoCode.start_date.is_(None) | (PromoCode.start_date <= now)),
        (PromoCode.end_date.is_(None) | (PromoCode.end_date >= now)),
    ).order_by(PromoCode.created_at.desc()).all()

    available_promos = []
    for p in promos:
        # Cek kuota habis
        if p.usage_limit is not None and p.used_count >= p.usage_limit:
            continue

        # Cek sasaran khusus pelanggan
        if p.target_type == "specific":
            if not current_customer:
                continue
            target_ids = {tc.customer_id for tc in p.target_customers}
            if current_customer.id not in target_ids:
                continue

        available_promos.append(p)

    return available_promos


# =============================================================================
# ADMIN ENDPOINTS (CRUD & MONITORING)
# =============================================================================

@router.get("", response_model=List[PromoCodeResponse])
def get_all_promos_admin(
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(require_admin)
):
    """
    Admin: Dapatkan seluruh daftar promo code (aktif maupun nonaktif).
    """
    return db.query(PromoCode).order_by(PromoCode.created_at.desc()).all()


@router.post("", response_model=PromoCodeResponse, status_code=status.HTTP_201_CREATED)
def create_promo_code(
    data: PromoCodeCreate,
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(require_admin)
):
    """
    Admin: Buat kupon promo baru.
    """
    clean_code = data.code.strip().upper()

    existing = db.query(PromoCode).filter(PromoCode.code == clean_code).first()
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Kode promo '{clean_code}' sudah terdaftar. Gunakan kode lain."
        )

    # Validasi diskon persen tidak boleh > 100
    if data.discount_type == "percentage" and data.discount_value > 100:
        raise HTTPException(
            status_code=400,
            detail="Diskon persentase tidak boleh lebih dari 100%."
        )

    # Validasi target pelanggan pilihan
    if data.target_type == "specific":
        if not data.customer_ids or len(data.customer_ids) == 0:
            raise HTTPException(
                status_code=400,
                detail="Silakan pilih minimal 1 pelanggan untuk kupon bertarget khusus."
            )

    promo = PromoCode(
        code=clean_code,
        name=data.name or clean_code,
        description=data.description,
        discount_type=data.discount_type,
        discount_value=data.discount_value,
        max_discount=data.max_discount,
        min_order_amount=data.min_order_amount,
        usage_limit=data.usage_limit,
        usage_limit_per_user=data.usage_limit_per_user,
        start_date=data.start_date,
        end_date=data.end_date,
        is_active=data.is_active,
        target_type=data.target_type or "all",
    )
    db.add(promo)
    db.flush()

    if promo.target_type == "specific" and data.customer_ids:
        for cid in set(data.customer_ids):
            db.add(PromoCodeCustomer(promo_code_id=promo.id, customer_id=cid))

    db.commit()
    db.refresh(promo)

    admin_display = getattr(current_admin, "name", None) or getattr(current_admin, "username", "Admin")
    target_info_str = f"khusus {len(data.customer_ids)} customer" if promo.target_type == "specific" else "semua customer"
    create_audit_log(
        db=db,
        user_type="admin",
        user_id=current_admin.id,
        action="PROMO_CREATED",
        entity_type="promo_code",
        entity_id=promo.id,
        description=f"Admin {admin_display} membuat kupon promo baru '{promo.code}' ({promo.discount_type} {promo.discount_value}, target: {target_info_str})."
    )

    return promo


@router.put("/{promo_id}", response_model=PromoCodeResponse)
def update_promo_code(
    promo_id: int,
    data: PromoCodeUpdate,
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(require_admin)
):
    """
    Admin: Edit pengaturan kupon promo.
    """
    promo = db.query(PromoCode).filter(PromoCode.id == promo_id).first()
    if not promo:
        raise HTTPException(
            status_code=404,
            detail="Kupon promo tidak ditemukan."
        )

    update_dict = data.dict(exclude_unset=True)
    customer_ids_to_update = update_dict.pop("customer_ids", None)

    if "discount_type" in update_dict and update_dict["discount_type"] == "percentage":
        val = update_dict.get("discount_value", promo.discount_value)
        if val > 100:
            raise HTTPException(
                status_code=400,
                detail="Diskon persentase tidak boleh lebih dari 100%."
            )

    for field, val in update_dict.items():
        setattr(promo, field, val)

    # Sinkronisasi target pelanggan
    if promo.target_type == "specific":
        if customer_ids_to_update is not None:
            if len(customer_ids_to_update) == 0:
                raise HTTPException(
                    status_code=400,
                    detail="Silakan pilih minimal 1 pelanggan untuk kupon bertarget khusus."
                )
            db.query(PromoCodeCustomer).filter(PromoCodeCustomer.promo_code_id == promo.id).delete()
            for cid in set(customer_ids_to_update):
                db.add(PromoCodeCustomer(promo_code_id=promo.id, customer_id=cid))
        else:
            existing_count = db.query(PromoCodeCustomer).filter(PromoCodeCustomer.promo_code_id == promo.id).count()
            if existing_count == 0:
                raise HTTPException(
                    status_code=400,
                    detail="Silakan pilih minimal 1 pelanggan untuk kupon bertarget khusus."
                )
    elif promo.target_type == "all":
        db.query(PromoCodeCustomer).filter(PromoCodeCustomer.promo_code_id == promo.id).delete()

    db.commit()
    db.refresh(promo)

    admin_display = getattr(current_admin, "name", None) or getattr(current_admin, "username", "Admin")
    create_audit_log(
        db=db,
        user_type="admin",
        user_id=current_admin.id,
        action="PROMO_UPDATED",
        entity_type="promo_code",
        entity_id=promo.id,
        description=f"Admin {admin_display} memperbarui kupon promo '{promo.code}'."
    )

    return promo


@router.patch("/{promo_id}/toggle", response_model=PromoCodeResponse)
def toggle_promo_status(
    promo_id: int,
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(require_admin)
):
    """
    Admin: 1-klik aktifkan / nonaktifkan kupon promo.
    """
    promo = db.query(PromoCode).filter(PromoCode.id == promo_id).first()
    if not promo:
        raise HTTPException(
            status_code=404,
            detail="Kupon promo tidak ditemukan."
        )

    promo.is_active = not promo.is_active
    db.commit()
    db.refresh(promo)

    status_str = "diaktifkan" if promo.is_active else "dinonaktifkan"
    admin_display = getattr(current_admin, "name", None) or getattr(current_admin, "username", "Admin")
    create_audit_log(
        db=db,
        user_type="admin",
        user_id=current_admin.id,
        action="PROMO_STATUS_TOGGLED",
        entity_type="promo_code",
        entity_id=promo.id,
        description=f"Admin {admin_display} mengubah status promo '{promo.code}' menjadi {status_str}."
    )

    return promo


@router.delete("/{promo_id}")
def delete_promo_code(
    promo_id: int,
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(require_admin)
):
    """
    Admin: Hapus kupon promo.
    """
    promo = db.query(PromoCode).filter(PromoCode.id == promo_id).first()
    if not promo:
        raise HTTPException(
            status_code=404,
            detail="Kupon promo tidak ditemukan."
        )

    code = promo.code
    db.delete(promo)
    db.commit()

    admin_display = getattr(current_admin, "name", None) or getattr(current_admin, "username", "Admin")
    create_audit_log(
        db=db,
        user_type="admin",
        user_id=current_admin.id,
        action="PROMO_DELETED",
        entity_type="promo_code",
        entity_id=promo_id,
        description=f"Admin {admin_display} menghapus kupon promo '{code}'."
    )

    return {"message": f"Kupon promo '{code}' berhasil dihapus."}

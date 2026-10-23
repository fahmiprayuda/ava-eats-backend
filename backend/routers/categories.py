from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db
from models.category import Category
from models.product import Product
from models.admin import Admin
from schemas.category import (
    CategoryCreate,
    CategoryUpdate,
    CategoryResponse,
    CategoryAssignProducts,
)
from auth.dependencies import require_admin
from utils.audit import create_audit_log

router = APIRouter(
    prefix="/api/categories",
    tags=["Menu Categories"]
)


def _build_category_response(cat: Category, db: Session) -> dict:
    products = db.query(Product).filter(Product.category_id == cat.id).all()
    return {
        "id": cat.id,
        "name": cat.name,
        "description": cat.description,
        "icon": cat.icon or "🍽️",
        "display_order": cat.display_order,
        "is_active": cat.is_active,
        "product_count": len(products),
        "product_ids": [p.id for p in products],
        "created_at": cat.created_at,
        "updated_at": cat.updated_at,
    }


# =============================================================================
# PUBLIC ENDPOINTS
# =============================================================================

@router.get("", response_model=List[CategoryResponse])
def get_active_categories(
    db: Session = Depends(get_db)
):
    """
    Daftar kategori menu aktif yang ditampilkan ke pelanggan (urut berdasarkan display_order).
    """
    categories = db.query(Category).filter(
        Category.is_active.is_(True)
    ).order_by(Category.display_order.asc(), Category.name.asc()).all()

    return [_build_category_response(cat, db) for cat in categories]


# =============================================================================
# ADMIN ENDPOINTS
# =============================================================================

@router.get("/admin", response_model=List[CategoryResponse])
def get_all_categories_admin(
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(require_admin)
):
    """
    Admin: Dapatkan seluruh daftar kategori menu (aktif & nonaktif).
    """
    categories = db.query(Category).order_by(
        Category.display_order.asc(), Category.name.asc()
    ).all()

    return [_build_category_response(cat, db) for cat in categories]


@router.post("", response_model=CategoryResponse, status_code=status.HTTP_201_CREATED)
def create_category(
    data: CategoryCreate,
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(require_admin)
):
    """
    Admin: Buat kategori menu baru.
    """
    clean_name = data.name.strip()
    existing = db.query(Category).filter(Category.name.ilike(clean_name)).first()
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Kategori '{clean_name}' sudah ada."
        )

    cat = Category(
        name=clean_name,
        description=data.description.strip() if data.description else None,
        icon=data.icon.strip() if data.icon else "🍽️",
        display_order=data.display_order or 0,
        is_active=data.is_active,
    )
    db.add(cat)
    db.commit()
    db.refresh(cat)

    # Jika admin langsung memilih produk untuk dimasukkan ke kategori ini
    if data.product_ids:
        for pid in data.product_ids:
            prod = db.query(Product).filter(Product.id == pid).first()
            if prod:
                prod.category_id = cat.id
        db.commit()

    admin_display = getattr(current_admin, "name", None) or getattr(current_admin, "username", "Admin")
    create_audit_log(
        db=db,
        user_type="admin",
        user_id=current_admin.id,
        action="CATEGORY_CREATED",
        entity_type="category",
        entity_id=cat.id,
        description=f"Admin {admin_display} membuat kategori menu baru '{cat.name}'."
    )
    db.commit()

    return _build_category_response(cat, db)


@router.put("/{category_id}", response_model=CategoryResponse)
def update_category(
    category_id: int,
    data: CategoryUpdate,
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(require_admin)
):
    """
    Admin: Edit nama, icon, status, atau daftar menu dalam kategori.
    """
    cat = db.query(Category).filter(Category.id == category_id).first()
    if not cat:
        raise HTTPException(status_code=404, detail="Kategori tidak ditemukan.")

    if data.name is not None:
        clean_name = data.name.strip()
        existing = db.query(Category).filter(
            Category.name.ilike(clean_name),
            Category.id != cat.id
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail=f"Nama kategori '{clean_name}' sudah digunakan.")
        cat.name = clean_name

    if data.description is not None:
        cat.description = data.description.strip() if data.description else None
    if data.icon is not None:
        cat.icon = data.icon.strip() if data.icon else "🍽️"
    if data.display_order is not None:
        cat.display_order = data.display_order
    if data.is_active is not None:
        cat.is_active = data.is_active

    # Sinkronisasi menu terpilih jika product_ids disertakan
    if data.product_ids is not None:
        # Lepas menu yang sebelumnya ada di kategori ini tapi tidak ada di product_ids baru
        db.query(Product).filter(
            Product.category_id == cat.id,
            ~Product.id.in_(data.product_ids)
        ).update({"category_id": None}, synchronize_session=False)

        # Tetapkan menu yang dipilih ke kategori ini
        if data.product_ids:
            db.query(Product).filter(
                Product.id.in_(data.product_ids)
            ).update({"category_id": cat.id}, synchronize_session=False)

    db.commit()
    db.refresh(cat)

    admin_display = getattr(current_admin, "name", None) or getattr(current_admin, "username", "Admin")
    create_audit_log(
        db=db,
        user_type="admin",
        user_id=current_admin.id,
        action="CATEGORY_UPDATED",
        entity_type="category",
        entity_id=cat.id,
        description=f"Admin {admin_display} memperbarui kategori '{cat.name}'."
    )
    db.commit()

    return _build_category_response(cat, db)


@router.delete("/{category_id}")
def delete_category(
    category_id: int,
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(require_admin)
):
    """
    Admin: Hapus kategori. Produk yang ada di dalamnya akan diubah menjadi tanpa kategori (Lainnya).
    """
    cat = db.query(Category).filter(Category.id == category_id).first()
    if not cat:
        raise HTTPException(status_code=404, detail="Kategori tidak ditemukan.")

    # Lepas produk
    db.query(Product).filter(Product.category_id == cat.id).update(
        {"category_id": None}, synchronize_session=False
    )

    name = cat.name
    db.delete(cat)
    db.commit()

    admin_display = getattr(current_admin, "name", None) or getattr(current_admin, "username", "Admin")
    create_audit_log(
        db=db,
        user_type="admin",
        user_id=current_admin.id,
        action="CATEGORY_DELETED",
        entity_type="category",
        entity_id=category_id,
        description=f"Admin {admin_display} menghapus kategori '{name}'."
    )
    db.commit()

    return {"message": f"Kategori '{name}' berhasil dihapus."}


@router.post("/{category_id}/assign-products", response_model=CategoryResponse)
def assign_products_to_category(
    category_id: int,
    data: CategoryAssignProducts,
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(require_admin)
):
    """
    Admin: Tetapkan daftar produk ke dalam kategori ini.
    """
    cat = db.query(Category).filter(Category.id == category_id).first()
    if not cat:
        raise HTTPException(status_code=404, detail="Kategori tidak ditemukan.")

    # Lepaskan produk yang ada di kategori ini yang tidak terpilih lagi
    db.query(Product).filter(
        Product.category_id == cat.id,
        ~Product.id.in_(data.product_ids)
    ).update({"category_id": None}, synchronize_session=False)

    # Tetapkan produk terpilih
    if data.product_ids:
        db.query(Product).filter(
            Product.id.in_(data.product_ids)
        ).update({"category_id": cat.id}, synchronize_session=False)

    db.commit()
    db.refresh(cat)

    return _build_category_response(cat, db)

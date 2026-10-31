import os
import uuid
import shutil
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session

from database import get_db
from models.product import Product
from models.admin import Admin
from models.order_item import OrderItem
from schemas.product import ProductRequest
from schemas.product_availability import ProductAvailabilityRequest
from auth.dependencies import require_admin
from utils.audit import create_audit_log

router = APIRouter(
    prefix="/api/products",
    tags=["Products"]
)

UPLOAD_PRODUCTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "uploads",
    "products"
)

@router.post("/upload-image")
def upload_product_image(
    file: UploadFile = File(...),
    current_admin: Admin = Depends(require_admin)
):
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(
            status_code=400,
            detail="File harus berformat gambar (JPG, PNG, WEBP, GIF)."
        )

    os.makedirs(UPLOAD_PRODUCTS_DIR, exist_ok=True)

    ext = os.path.splitext(file.filename)[1].lower() if file.filename else ".jpg"
    if not ext or ext not in [".jpg", ".jpeg", ".png", ".webp", ".gif"]:
        ext = ".jpg"

    unique_filename = f"{uuid.uuid4().hex}{ext}"
    filepath = os.path.join(UPLOAD_PRODUCTS_DIR, unique_filename)

    with open(filepath, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    image_url = f"/uploads/products/{unique_filename}"
    return {
        "message": "Gambar berhasil diunggah dari perangkat",
        "image_url": image_url,
        "filename": unique_filename
    }


@router.post("")
def create_product(
    data: ProductRequest,
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(require_admin)
):
    # Kalau stock 0, otomatis tidak tersedia
    if data.stock == 0:
        data.is_available = False

    new_product = Product(
        name=data.name,
        description=data.description,
        price=data.price,
        image=data.image,
        weight_grams=data.weight_grams,
        stock=data.stock,
        is_available=data.is_available,
        category_id=data.category_id,
    )

    db.add(new_product)
    db.commit()
    db.refresh(new_product)

    create_audit_log(
        db=db,
        user_type="admin",
        user_id=current_admin.id,
        action="PRODUCT_CREATED",
        entity_type="product",
        entity_id=new_product.id,
        description=f"Admin {current_admin.username} membuat produk '{new_product.name}' (stok: {new_product.stock}, harga: Rp{new_product.price:,})"
    )
    db.commit()

    return {
        "message": "Product berhasil dibuat",
        "product": {
            "id": new_product.id,
            "name": new_product.name,
            "description": new_product.description,
            "price": new_product.price,
            "image": new_product.image,
            "weight_grams": new_product.weight_grams,
            "stock": new_product.stock,
            "is_available": new_product.is_available,
            "category_id": new_product.category_id,
            "category": new_product.category_name,
        }
    }

@router.get("")
def get_products(
    db: Session = Depends(get_db)
):
    products = db.query(Product).all()

    return {
        "products": [
            {
                "id": item.id,
                "name": item.name,
                "description": item.description,
                "price": item.price,
                "image": item.image,
                "weight_grams": item.weight_grams,
                "stock": item.stock,
                "is_available": item.is_available,
                "category_id": item.category_id,
                "category": item.category_name,
            }
            for item in products
        ]
    }

@router.get("/{product_id}")
def get_product(
    product_id: int,
    db: Session = Depends(get_db)
):
    product = db.query(Product).filter(
        Product.id == product_id
    ).first()

    if not product:
        raise HTTPException(
            status_code=404,
            detail="Product tidak ditemukan"
        )

    return {
        "product": {
            "id": product.id,
            "name": product.name,
            "description": product.description,
            "price": product.price,
            "image": product.image,
            "weight_grams": product.weight_grams,
            "stock": product.stock,
            "is_available": product.is_available,
            "category_id": product.category_id,
            "category": product.category_name,
        }
    }

@router.put("/{product_id}")
def update_product(
    product_id: int,
    product: ProductRequest,
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(require_admin)
):
    existing_product = db.query(Product).filter(
        Product.id == product_id
    ).first()

    if not existing_product:
        raise HTTPException(
            status_code=404,
            detail="Product tidak ditemukan"
        )

    old_stock = existing_product.stock
    old_price = existing_product.price

    existing_product.name = product.name
    existing_product.description = product.description
    existing_product.price = product.price
    existing_product.image = product.image
    existing_product.weight_grams = product.weight_grams
    existing_product.stock = product.stock
    existing_product.is_available = product.is_available
    if product.category_id is not None:
        existing_product.category_id = product.category_id

    desc_parts = []
    if old_stock != existing_product.stock:
        desc_parts.append(f"stok: {old_stock} ➔ {existing_product.stock}")
    if old_price != existing_product.price:
        desc_parts.append(f"harga: Rp{old_price:,} ➔ Rp{existing_product.price:,}")

    change_str = ", ".join(desc_parts) if desc_parts else f"stok: {existing_product.stock}, harga: Rp{existing_product.price:,}"

    create_audit_log(
        db=db,
        user_type="admin",
        user_id=current_admin.id,
        action="PRODUCT_UPDATED",
        entity_type="product",
        entity_id=existing_product.id,
        description=f"Admin {current_admin.username} memperbarui '{existing_product.name}' ({change_str})"
    )

    db.commit()
    db.refresh(existing_product)

    return {
        "message": "Product berhasil diperbarui",
        "product": {
            "id": existing_product.id,
            "name": existing_product.name,
            "description": existing_product.description,
            "price": existing_product.price,
            "image": existing_product.image,
            "weight_grams": existing_product.weight_grams,
            "stock": existing_product.stock,
            "is_available": existing_product.is_available,
            "category_id": existing_product.category_id,
            "category": existing_product.category_name,
        }
    }

@router.delete("/{product_id}")
def delete_product(
    product_id: int,
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(require_admin)
):
    existing_product = db.query(Product).filter(
        Product.id == product_id
    ).first()

    if not existing_product:
        raise HTTPException(
            status_code=404,
            detail="Product tidak ditemukan"
        )

    product_name = existing_product.name

    try:
        # Putuskan keterkaitan foreign key di order_items agar riwayat pesanan (snapshot nama & harga)
        # tetap tersimpan di riwayat transaksi, tetapi produk dapat dihapus dari katalog
        db.query(OrderItem).filter(OrderItem.product_id == product_id).update(
            {"product_id": None},
            synchronize_session=False
        )
        db.flush()

        create_audit_log(
            db=db,
            user_type="admin",
            user_id=current_admin.id,
            action="PRODUCT_DELETED",
            entity_type="product",
            entity_id=existing_product.id,
            description=f"Admin {current_admin.username} menghapus produk '{product_name}' (ID: {product_id})"
        )

        db.delete(existing_product)
        db.commit()

        return {
            "message": f"Produk '{product_name}' berhasil dihapus"
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail=f"Gagal menghapus produk: {str(e)}"
        )

@router.put("/{product_id}/availability")
def update_product_availability(
    product_id: int,
    data: ProductAvailabilityRequest,
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(require_admin)
):
    product = db.query(Product).filter(
        Product.id == product_id
    ).first()

    if not product:
        raise HTTPException(
            status_code=404,
            detail="Product tidak ditemukan"
        )

    # Tidak boleh mengaktifkan produk yang stoknya 0
    if data.is_available and product.stock == 0:
        raise HTTPException(
            status_code=400,
            detail="Product tidak bisa diaktifkan karena stock 0"
        )

    product.is_available = data.is_available

    create_audit_log(
        db=db,
        user_type="admin",
        user_id=current_admin.id,
        action="PRODUCT_AVAILABILITY_CHANGED",
        entity_type="product",
        entity_id=product.id,
        description=f"Admin {current_admin.username} mengubah status ketersediaan produk '{product.name}' menjadi {'Tersedia (Ready)' if product.is_available else 'Habis'}"
    )

    db.commit()
    db.refresh(product)

    return product
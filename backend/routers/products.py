from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models.product import Product
from models.admin import Admin
from schemas.product import ProductRequest
from schemas.product_availability import ProductAvailabilityRequest
from auth.dependencies import require_admin

router = APIRouter(
    prefix="/api/products",
    tags=["Products"]
)

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
        is_available=data.is_available
    )

    db.add(new_product)
    db.commit()
    db.refresh(new_product)

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
            "is_available": new_product.is_available
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
                "is_available": item.is_available
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
            "is_available": product.is_available
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

    existing_product.name = product.name
    existing_product.description = product.description
    existing_product.price = product.price
    existing_product.image = product.image
    existing_product.weight_grams = product.weight_grams
    existing_product.stock = product.stock
    existing_product.is_available = product.is_available

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
            "is_available": existing_product.is_available
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

    db.delete(existing_product)
    db.commit()

    return {
        "message": "Product berhasil dihapus"
    }

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

    db.commit()
    db.refresh(product)

    return product
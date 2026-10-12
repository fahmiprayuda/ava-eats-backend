from database import SessionLocal
from models.product import Product

db = SessionLocal()

products = [
    {
        "name": "Otak Sapi Ungkep Kuning",
        "description": "Otak Sapi dengan bumbu khas ungkep kuning",
        "price": 50000,
        "image": "https://example.com/otaksapi.jpg",
        "weight_grams": 500,
        "stock": 10,
        "is_available": True
    },
    {
        "name": "Ayam Ungkep Bumbu Kuning",
        "description": "Ayam goreng gurih dan renyah",
        "price": 80000,
        "image": "https://example.com/ayam-goreng.jpg",
        "weight_grams": 800,
        "stock": 20,
        "is_available": True
    },
    {
        "name": "Nasi Goreng Bebek",
        "description": "Nasi goreng dengan bebek khas",
        "price": 35000,
        "image": "https://example.com/nasibebek.jpg",
        "weight_grams": 400,
        "stock": 10,
        "is_available": True
    },
    {
        "name": "Potato Creamy Soup",
        "description": "Kentang creamy dengan topping daging sapi",
        "price": 40000,
        "image": "https://example.com/potato.jpg",
        "weight_grams": 400,
        "stock": 20,
        "is_available": True
    }
]

for data in products:
    print("Menambahkan:", data["name"])

    product = Product(**data)

    db.add(product)

db.commit()

print("Semua produk sudah di-commit")
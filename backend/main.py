import os
import sys
from dotenv import load_dotenv

# Tambahkan direktori backend ke sys.path agar impor modular berjalan lancar baik dari root maupun folder backend
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# Muat file .env dari root repository atau folder backend
PARENT_DIR = os.path.dirname(BASE_DIR)
for env_path in [os.path.join(PARENT_DIR, ".env"), os.path.join(BASE_DIR, ".env"), ".env"]:
    if os.path.exists(env_path):
        load_dotenv(env_path)
        break
else:
    load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from database import engine, Base
from sqlalchemy import text
from models import (
    Customer,
    CustomerAddress,
    Product,
    Order,
    OrderItem,
    Payment,
    Admin,
    AuditTrail,
    Shipment,
    PromoCode,
    PromoCodeUsage,
    PromoCodeCustomer,
    Category,
)

# Migrasi otomatis kolom target_type & name pada promo_codes jika belum ada
try:
    with engine.connect() as conn:
        res = conn.execute(text("SHOW COLUMNS FROM promo_codes LIKE 'target_type';")).fetchone()
        if not res:
            conn.execute(text("ALTER TABLE promo_codes ADD COLUMN target_type VARCHAR(20) NOT NULL DEFAULT 'all';"))
            conn.commit()

        res_name = conn.execute(text("SHOW COLUMNS FROM promo_codes LIKE 'name';")).fetchone()
        if not res_name:
            conn.execute(text("ALTER TABLE promo_codes ADD COLUMN name VARCHAR(100) NULL AFTER code;"))
            conn.execute(text("UPDATE promo_codes SET name = COALESCE(description, code) WHERE name IS NULL;"))
            conn.commit()

        # Migrasi otomatis: ubah order_items.product_id agar nullable dan ON DELETE SET NULL
        # sehingga produk dapat dihapus tanpa merusak riwayat transaksi pemesanan
        col_res = conn.execute(text("SHOW COLUMNS FROM order_items LIKE 'product_id';")).fetchone()
        if col_res and col_res[2] == "NO":  # col_res[2] adalah kolom 'Null' ('YES' atau 'NO')
            # 1. Modifikasi kolom menjadi NULL
            conn.execute(text("ALTER TABLE order_items MODIFY product_id INT NULL;"))
            conn.commit()

            # 2. Update foreign key constraint agar ON DELETE SET NULL
            fk_query = text("""
                SELECT CONSTRAINT_NAME 
                FROM information_schema.key_column_usage 
                WHERE TABLE_SCHEMA = DATABASE() 
                  AND TABLE_NAME = 'order_items' 
                  AND COLUMN_NAME = 'product_id' 
                  AND REFERENCED_TABLE_NAME = 'products';
            """)
            fk_rows = conn.execute(fk_query).fetchall()
            for row in fk_rows:
                fk_name = row[0]
                conn.execute(text(f"ALTER TABLE order_items DROP FOREIGN KEY `{fk_name}`;"))
            
            conn.execute(text("""
                ALTER TABLE order_items 
                ADD CONSTRAINT fk_order_items_product 
                FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE SET NULL;
            """))
            conn.commit()
except Exception as e:
    print(f"Warning auto-migration database: {e}")

Base.metadata.create_all(bind=engine)

from routers import customers, addresses, products, orders, payments, admins, auth, webhooks, shipping, promos, categories

app = FastAPI(title="Ava Eats API")

# Mount direktori uploads agar gambar produk bisa diakses langsung via browser
UPLOADS_DIR = os.path.join(BASE_DIR, "uploads")
os.makedirs(os.path.join(UPLOADS_DIR, "products"), exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOADS_DIR), name="uploads")

# Konfigurasi CORS: izinkan localhost, domain Vercel, dan custom domain via environment variable
allowed_origins_env = os.getenv("CORS_ALLOWED_ORIGINS", "")
allowed_origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:8000",
]
if allowed_origins_env:
    for origin in allowed_origins_env.split(","):
        cleaned = origin.strip()
        if cleaned and cleaned not in allowed_origins:
            allowed_origins.append(cleaned)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=r"https://.*\.vercel\.app",  # Mengizinkan semua preview & production branch deployment Vercel
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def home():
    return {
        "message": "Hello dari FastAPI!"
    }

app.include_router(customers.router)
app.include_router(addresses.router)
app.include_router(products.router)
app.include_router(orders.router)
app.include_router(payments.router)
app.include_router(admins.router)
app.include_router(auth.router)
app.include_router(webhooks.router)
app.include_router(shipping.router)
app.include_router(shipping.router, prefix="/api")
app.include_router(promos.router)
app.include_router(categories.router)
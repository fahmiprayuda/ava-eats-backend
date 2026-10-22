import os
import sys

# Tambahkan path folder backend ke sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env"))

from sqlalchemy import text
from database import engine, Base, SessionLocal
from models import (
    Admin,
    Customer,
    CustomerAddress,
    Product,
    Order,
    OrderItem,
    Payment,
    Shipment,
    AuditTrail,
)
from utils.password import hash_password

def run_fresh_migration():
    print("==================================================")
    print("🚀 MEMULAI FRESH MIGRATION AVA EATS DATABASE...")
    print("==================================================")

    db = SessionLocal()

    try:
        # 1. Nonaktifkan foreign key checks dan bersihkan tabel
        print("\n[1/4] Menghapus (DROP) semua tabel lama...")
        with engine.connect() as conn:
            conn.execute(text("SET FOREIGN_KEY_CHECKS = 0;"))
            tables_to_drop = [
                "shipments",
                "payments",
                "order_items",
                "orders",
                "customer_addresses",
                "audit_trails",
                "customers",
                "products",
                "admins",
            ]
            for table in tables_to_drop:
                conn.execute(text(f"DROP TABLE IF EXISTS {table};"))
            conn.execute(text("SET FOREIGN_KEY_CHECKS = 1;"))
            conn.commit()
        print("✓ Semua tabel lama berhasil dibersihkan.")

        # 2. Buat ulang semua tabel baru sesuai skema model SQLAlchemy
        print("\n[2/4] Membuat ulang semua struktur tabel baru...")
        Base.metadata.create_all(bind=engine)
        print("✓ 9 Tabel berhasil dibuat: admins, products, customers, customer_addresses, orders, order_items, payments, shipments, audit_trails.")

        # 3. Seed akun Admin utama
        print("\n[3/4] Menyiapkan kredensial Admin Ava Eats...")
        default_admin = Admin(
            username="admin_fahmi",
            name="Admin Fahmi",
            password=hash_password("admin123"),
            role="admin",
        )
        db.add(default_admin)
        db.commit()
        db.refresh(default_admin)
        print(f"✓ Akun Admin berhasil dibuat:")
        print(f"   • Username: admin_fahmi")
        print(f"   • Password: admin123")

        # 4. Seed Katalog Menu Makanan Awal Ava Eats
        print("\n[4/4] Memasukkan menu makanan Ava Eats yang siap dipesan...")
        seed_products = [
            Product(
                name="Otak Sapi Ungkep Kuning",
                description="Olahan otak sapi bernutrisi tinggi dengan bumbu ungkep rempah kuning gurih, empuk, kaya DHA & cocok untuk balita.",
                price=50000,
                weight_grams=500,
                stock=20,
                is_available=True,
                image="https://images.unsplash.com/photo-1546069901-ba9599a7e63c?w=500&auto=format&fit=crop&q=80",
            ),
            Product(
                name="Ayam Ungkep Bumbu Kuning",
                description="Ayam kampung ungkep bumbu rempah kuning gurih alami, tekstur juicy, praktis siap digoreng atau diairfryer.",
                price=80000,
                weight_grams=800,
                stock=15,
                is_available=True,
                image="https://images.unsplash.com/photo-1626082927389-6cd097cdc6ec?w=500&auto=format&fit=crop&q=80",
            ),
            Product(
                name="Beef Teriyaki Kids Rice",
                description="Irisan daging sapi empuk saus teriyaki manis gurih tanpa MSG berlebih, dilengkapi potongan wortel & brokoli manis.",
                price=45000,
                weight_grams=350,
                stock=25,
                is_available=True,
                image="https://images.unsplash.com/photo-1512058564366-18510be2db19?w=500&auto=format&fit=crop&q=80",
            ),
            Product(
                name="Salmon Creamy Soup",
                description="Sup krim lembut dengan potongan daging salmon segar, kentang, dan jagung manis kaya Omega-3 untuk si kecil.",
                price=45000,
                weight_grams=400,
                stock=15,
                is_available=True,
                image="https://images.unsplash.com/photo-1547592166-23ac45744acd?w=500&auto=format&fit=crop&q=80",
            ),
            Product(
                name="Potato Macaroni Schotel",
                description="Macaroni panggang creamy dengan keju cheddar leleh, potongan daging sapi cincang, dan susu murni bergizi.",
                price=38000,
                weight_grams=300,
                stock=20,
                is_available=True,
                image="https://images.unsplash.com/photo-1551183053-bf91a1d81141?w=500&auto=format&fit=crop&q=80",
            ),
        ]

        for p in seed_products:
            db.add(p)
        db.commit()
        print(f"✓ {len(seed_products)} Menu makanan favorit berhasil dimasukkan.")

        # Catat inisialisasi ke audit trail
        init_log = AuditTrail(
            user_type="admin",
            user_id=default_admin.id,
            action="SYSTEM_INIT",
            entity_type="system",
            entity_id=1,
            description="Database fresh migration & baseline seeding berhasil dijalankan.",
        )
        db.add(init_log)
        db.commit()

        print("\n==================================================")
        print("🎉 FRESH MIGRATION BERHASIL 100%!")
        print("Database bersih & siap untuk test flow dari awal:")
        print(" 1. Register Customer baru")
        print(" 2. Tambah Alamat Pengiriman")
        print(" 3. Pesan Menu & Pilih Ekspedisi Paxel/Gojek/Grab/Lalamove")
        print(" 4. Bayar & Pantau Tracking Resi/Driver")
        print(" 5. Cek Order & Update Status di Dashboard Admin")
        print("==================================================")

    except Exception as exc:
        db.rollback()
        print(f"\n❌ Terjadi kesalahan saat migrasi: {exc}")
        raise exc
    finally:
        db.close()

if __name__ == "__main__":
    run_fresh_migration()

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# Ambil DATABASE_URL dari environment (Production / Cloud), atau fallback ke database lokal
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "mysql+pymysql://root:Fahmi290919@localhost:3306/ava_eats"
)

# Kompatibilitas URL cloud provider (Railway/Heroku/Render) yang memberi awalan mysql://
if DATABASE_URL.startswith("mysql://"):
    DATABASE_URL = DATABASE_URL.replace("mysql://", "mysql+pymysql://", 1)

connect_args = {}
if "mysql" in DATABASE_URL:
    # Memaksa setiap sesi koneksi MySQL memakai zona waktu Asia/Jakarta (WIB / GMT+7)
    # sehingga fungsi SQL func.now() / NOW() konsisten di WIB baik di lokal maupun Railway/Cloud
    connect_args["init_command"] = "SET time_zone='+07:00'"
elif "postgres" in DATABASE_URL:
    connect_args["options"] = "-c timezone=Asia/Jakarta"

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,  # Otomatis cek & pulihkan koneksi (mencegah error "MySQL server has gone away")
    pool_recycle=300,    # Re-cycle koneksi tiap 5 menit agar tidak di-drop oleh firewall cloud/VPS
    pool_size=10,
    max_overflow=20,
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
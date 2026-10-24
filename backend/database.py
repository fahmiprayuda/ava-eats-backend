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

engine = create_engine(
    DATABASE_URL,
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
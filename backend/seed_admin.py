from database import SessionLocal
from models.admin import Admin
from utils.password import hash_password


db = SessionLocal()

admin = Admin(
    username="admin_fahmi",
    name="Fahmi",
    password=hash_password("AdminFahmi123"),
    role="admin"
)

db.add(admin)
db.commit()
db.refresh(admin)

print("Admin berhasil dibuat")
print("ID:", admin.id)
print("Username:", admin.username)

db.close()
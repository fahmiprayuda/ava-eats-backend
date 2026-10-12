from database import SessionLocal
from models.customer import Customer
from utils.password import hash_password


db = SessionLocal()

customer = Customer(
    phone="085282314006",
    name="Aulia",
    password=hash_password("Aulia123"),
)

db.add(customer)
db.commit()
db.refresh(customer)

print("Customer berhasil dibuat")
print("ID:", customer.id)
print("Name:", customer.name)

db.close()
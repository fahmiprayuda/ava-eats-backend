from fastapi import FastAPI

from database import engine, Base
from models import Customer, CustomerAddress, Product, Order, OrderItem, Payment, Admin

from routers import customers, addresses, products, orders, payments, admins, auth

Base.metadata.create_all(bind=engine)

app = FastAPI()

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
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import engine, Base
from models import Customer, CustomerAddress, Product, Order, OrderItem, Payment, Admin, AuditTrail, Shipment

from routers import customers, addresses, products, orders, payments, admins, auth, webhooks, shipping


Base.metadata.create_all(bind=engine)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
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
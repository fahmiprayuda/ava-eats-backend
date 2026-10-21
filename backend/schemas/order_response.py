from pydantic import BaseModel

from typing import List, Optional
from datetime import datetime


class OrderItemResponse(BaseModel):
    id: int
    product_id: int
    product_name: str
    price: int
    quantity: int
    subtotal: int


class OrderResponse(BaseModel):
    id: int
    order_code: str

    customer_id: int
    address_id: Optional[int] = None

    recipient_name: str
    phone: str
    address: str
    province: str
    city: str
    district: str
    postal_code: str

    notes: Optional[str]
    total_amount: int
    status: str

    fulfillment_method: str
    shipping_cost: int
    grand_total: int

    items: List[OrderItemResponse]


class MyOrderResponse(OrderResponse):
    payment_id: Optional[int] = None
    payment_status: Optional[str] = None
    created_at: Optional[datetime] = None
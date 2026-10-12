from typing import List, Optional

from pydantic import BaseModel


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
    address_id: int

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

    items: List[OrderItemResponse]
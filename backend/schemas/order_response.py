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
    packaging_fee: Optional[int] = 0
    promo_code: Optional[str] = None
    discount_amount: int = 0
    grand_total: int

    cancellation_reason: Optional[str] = None
    refund_status: Optional[str] = None
    refund_note: Optional[str] = None
    refund_proof_url: Optional[str] = None
    refunded_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

    items: List[OrderItemResponse]

    class Config:
        from_attributes = True
        orm_mode = True


class MyOrderResponse(OrderResponse):
    payment_id: Optional[int] = None
    payment_status: Optional[str] = None
    created_at: Optional[datetime] = None
    courier: Optional[str] = None
    courier_service: Optional[str] = None
    shipment_status: Optional[str] = None
    tracking_number: Optional[str] = None
    tracking_url: Optional[str] = None
    driver_name: Optional[str] = None
    driver_phone: Optional[str] = None
    driver_plate_number: Optional[str] = None
    driver_photo_url: Optional[str] = None
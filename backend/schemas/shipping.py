from pydantic import BaseModel
from typing import List, Optional


class ShippingSelectRequest(BaseModel):
    order_id: Optional[int] = None
    courier_code: Optional[str] = None
    service_code: Optional[str] = None
    shipping_cost: Optional[int] = None


class ShippingItemRateRequest(BaseModel):
    product_id: int
    quantity: int = 1


class CalculateShippingRatesRequest(BaseModel):
    address_id: Optional[int] = None
    postal_code: Optional[str] = None
    items: List[ShippingItemRateRequest]


class ManualTrackingRequest(BaseModel):
    tracking_number: str
    courier: Optional[str] = None
    tracking_url: Optional[str] = None
    update_order_status: bool = False


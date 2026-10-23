from typing import Literal, Optional

from pydantic import BaseModel, Field


class OrderItemRequest(BaseModel):
    product_id: int = Field(..., gt=0)
    quantity: int = Field(..., gt=0)


class OrderRequest(BaseModel):
    fulfillment_method: Literal["delivery", "pickup"] = "delivery"
    address_id: Optional[int] = None
    items: list[OrderItemRequest]
    notes: Optional[str] = None
    payment_method: Optional[str] = None
    courier_code: Optional[str] = None
    service_code: Optional[str] = None
    shipping_cost: Optional[int] = 0
    packaging_fee: Optional[int] = 0
    promo_code: Optional[str] = None
    notify_whatsapp: Optional[bool] = True
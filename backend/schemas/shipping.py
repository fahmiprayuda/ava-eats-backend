from pydantic import BaseModel
from typing import Optional


class ShippingSelectRequest(BaseModel):
    order_id: Optional[int] = None
    courier_code: Optional[str] = None
    service_code: Optional[str] = None
    shipping_cost: Optional[int] = None

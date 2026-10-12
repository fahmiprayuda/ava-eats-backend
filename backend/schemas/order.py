from typing import List, Optional

from pydantic import BaseModel, Field


class OrderItemRequest(BaseModel):
    product_id: int = Field(..., gt=0)
    quantity: int = Field(..., gt=0)


class OrderRequest(BaseModel):
    address_id: int = Field(..., gt=0)
    items: List[OrderItemRequest] = Field(..., min_items=1)
    notes: Optional[str] = Field(None, max_length=500)
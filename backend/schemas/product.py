from typing import Optional
from pydantic import BaseModel, Field


class ProductRequest(BaseModel):
    name: str = Field(..., min_length=3, max_length=150)
    
    description: Optional[str] = Field(None, max_length=1000)

    price: int = Field(..., gt=0)

    image: Optional[str] = Field(None, max_length=500)

    weight_grams: int = Field(..., gt=0)

    stock: int = Field(..., ge=0)

    is_available: bool = True
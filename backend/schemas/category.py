from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


class CategoryBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    description: Optional[str] = None
    icon: Optional[str] = "🍽️"
    display_order: int = 0
    is_active: bool = True


class CategoryCreate(CategoryBase):
    product_ids: Optional[List[int]] = None


class CategoryUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=100)
    description: Optional[str] = None
    icon: Optional[str] = None
    display_order: Optional[int] = None
    is_active: Optional[bool] = None
    product_ids: Optional[List[int]] = None


class CategoryResponse(CategoryBase):
    id: int
    product_count: int = 0
    product_ids: List[int] = []
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class CategoryAssignProducts(BaseModel):
    product_ids: List[int] = []

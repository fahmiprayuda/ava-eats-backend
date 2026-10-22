from typing import Optional
from pydantic import BaseModel, Field


class CustomerRequest(BaseModel):
    phone: str = Field(..., min_length=10, max_length=20)
    name: str = Field(..., min_length=2, max_length=100)
    password: str = Field(..., min_length=6, max_length=100)


class CustomerLoginRequest(BaseModel):
    phone: str = Field(..., min_length=10, max_length=20)
    password: str = Field(..., min_length=6, max_length=100)


class CustomerUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=100)
    phone: Optional[str] = Field(None, min_length=10, max_length=20)
    current_password: Optional[str] = None
    new_password: Optional[str] = Field(None, min_length=6, max_length=100)


class AdminCustomerCreateRequest(BaseModel):
    phone: str = Field(..., min_length=10, max_length=20)
    name: str = Field(..., min_length=2, max_length=100)
    password: str = Field(..., min_length=6, max_length=100)


class AdminCustomerUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=100)
    phone: Optional[str] = Field(None, min_length=10, max_length=20)
    password: Optional[str] = Field(None, min_length=6, max_length=100)


class AdminCustomerResponse(BaseModel):
    id: int
    name: str
    phone: str
    orders_count: int = 0
    total_spent: int = 0

    class Config:
        from_attributes = True


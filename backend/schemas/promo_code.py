from datetime import datetime
from typing import List, Literal, Optional
from pydantic import BaseModel, Field, field_validator


class PromoCodeBase(BaseModel):
    code: str = Field(..., min_length=3, max_length=50)
    name: Optional[str] = None
    description: Optional[str] = None
    discount_type: Literal["percentage", "fixed_amount", "shipping_discount"] = "percentage"
    discount_value: int = Field(..., gt=0)
    max_discount: Optional[int] = Field(None, ge=0)
    min_order_amount: int = Field(0, ge=0)
    usage_limit: Optional[int] = Field(None, ge=1)
    usage_limit_per_user: int = Field(1, ge=1)
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    is_active: bool = True
    target_type: Literal["all", "specific"] = "all"
    customer_ids: Optional[List[int]] = None

    @field_validator("start_date", "end_date", mode="before")
    @classmethod
    def clean_local_datetime(cls, v):
        if not v:
            return None
        if isinstance(v, str):
            s = v.replace("Z", "")
            if "+" in s:
                s = s.split("+")[0]
            try:
                return datetime.fromisoformat(s)
            except Exception:
                pass
        elif isinstance(v, datetime) and v.tzinfo is not None:
            return v.replace(tzinfo=None)
        return v


class PromoCodeCreate(PromoCodeBase):
    pass


class PromoCodeUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    discount_type: Optional[Literal["percentage", "fixed_amount", "shipping_discount"]] = None
    discount_value: Optional[int] = Field(None, gt=0)
    max_discount: Optional[int] = Field(None, ge=0)
    min_order_amount: Optional[int] = Field(None, ge=0)
    usage_limit: Optional[int] = Field(None, ge=1)
    usage_limit_per_user: Optional[int] = Field(None, ge=1)
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    is_active: Optional[bool] = None
    target_type: Optional[Literal["all", "specific"]] = None
    customer_ids: Optional[List[int]] = None

    @field_validator("start_date", "end_date", mode="before")
    @classmethod
    def clean_local_datetime_update(cls, v):
        if not v:
            return None
        if isinstance(v, str):
            s = v.replace("Z", "")
            if "+" in s:
                s = s.split("+")[0]
            try:
                return datetime.fromisoformat(s)
            except Exception:
                pass
        elif isinstance(v, datetime) and v.tzinfo is not None:
            return v.replace(tzinfo=None)
        return v


class TargetCustomerInfo(BaseModel):
    id: int
    name: str
    phone: str

    class Config:
        from_attributes = True


class PromoCodeResponse(PromoCodeBase):
    id: int
    used_count: int
    target_type: str = "all"
    target_customer_ids: List[int] = Field(default_factory=list)
    target_customers: List[TargetCustomerInfo] = Field(default_factory=list, validation_alias="target_customers_info")
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
        populate_by_name = True


class PromoValidateRequest(BaseModel):
    code: str = Field(..., min_length=1)
    subtotal: Optional[int] = Field(None, ge=0)
    order_amount: Optional[int] = Field(None, ge=0)
    shipping_cost: int = Field(0, ge=0)

    @property
    def effective_subtotal(self) -> int:
        if self.subtotal is not None:
            return self.subtotal
        if self.order_amount is not None:
            return self.order_amount
        return 0


class PromoValidateResponse(BaseModel):
    valid: bool
    promo_code: str
    code: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    discount_type: str
    discount_value: int
    discount_amount: int
    max_discount: Optional[int] = None
    min_order_amount: int
    message: str
    promo: Optional[dict] = None

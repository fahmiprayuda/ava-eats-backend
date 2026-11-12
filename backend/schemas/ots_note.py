from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel, Field


class OtsNoteBase(BaseModel):
    note_date: date
    day_label: Optional[str] = Field(None, max_length=100)
    customer_name: str = Field(..., min_length=1, max_length=150)
    items_text: str = Field(..., min_length=1)
    amount: Optional[int] = Field(None, ge=0)
    is_paid: bool = False
    is_done: bool = False


class OtsNoteCreate(OtsNoteBase):
    pass


class OtsNoteBulkCreate(BaseModel):
    note_date: date
    day_label: Optional[str] = Field(None, max_length=100)
    raw_text: str = Field(..., min_length=1)


class OtsNoteUpdate(BaseModel):
    note_date: Optional[date] = None
    day_label: Optional[str] = Field(None, max_length=100)
    customer_name: Optional[str] = Field(None, min_length=1, max_length=150)
    items_text: Optional[str] = Field(None, min_length=1)
    amount: Optional[int] = Field(None, ge=0)
    is_paid: Optional[bool] = None
    is_done: Optional[bool] = None


class OtsNoteResponse(OtsNoteBase):
    id: int
    created_by: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class OtsMenuBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=150)
    price: int = Field(0, ge=0)
    is_active: bool = True


class OtsMenuCreate(OtsMenuBase):
    pass


class OtsMenuUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=150)
    price: Optional[int] = Field(None, ge=0)
    is_active: Optional[bool] = None


class OtsMenuResponse(OtsMenuBase):
    id: int
    created_by: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

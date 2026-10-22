from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field


class AdminCreate(BaseModel):
    username: str = Field(
        ...,
        min_length=3,
        max_length=50
    )
    password: str = Field(
        ...,
        min_length=6,
        max_length=100
    )
    name: str = Field(
        ...,
        min_length=2,
        max_length=100
    )
    role: str = Field(
        default="admin",
        max_length=30
    )


class AdminUpdate(BaseModel):
    username: Optional[str] = Field(None, min_length=3, max_length=50)
    name: Optional[str] = Field(None, min_length=2, max_length=100)
    role: Optional[str] = Field(None, max_length=30)
    password: Optional[str] = Field(None, min_length=6, max_length=100)


class AdminResponse(BaseModel):
    id: int
    username: str
    name: str
    role: str
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True

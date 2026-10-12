from typing import Optional
from pydantic import BaseModel

class CustomerAddressRequest(BaseModel):
    label: str
    recipient_name: str
    phone: str
    address: str
    province: str
    city: str
    district: str
    postal_code: str
    is_default: bool = False
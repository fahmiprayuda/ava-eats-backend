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
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    is_default: bool = False

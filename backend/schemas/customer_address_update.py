from pydantic import BaseModel


class CustomerAddressUpdate(BaseModel):
    label: str
    recipient_name: str
    phone: str
    address: str
    province: str
    city: str
    district: str
    postal_code: str
    is_default: bool = False
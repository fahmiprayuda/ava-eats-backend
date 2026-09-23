from pydantic import BaseModel

class ProductAvailabilityRequest(BaseModel):
    is_available: bool
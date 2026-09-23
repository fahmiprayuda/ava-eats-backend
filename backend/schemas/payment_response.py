from typing import Optional
from datetime import datetime
from pydantic import BaseModel


class PaymentResponse(BaseModel):
    id: int
    order_id: int
    payment_method: str
    amount: int
    payment_proof: Optional[str]
    status: str
    verified_at: Optional[datetime]
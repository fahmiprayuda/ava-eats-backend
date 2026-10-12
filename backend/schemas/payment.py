from typing import Optional

from pydantic import BaseModel, Field


class PaymentRequest(BaseModel):
    payment_method: str = Field(
        ...,
        min_length=1,
        max_length=30
    )

    payment_proof: Optional[str] = Field(
        None,
        max_length=500
    )


class PaymentVerifyRequest(BaseModel):
    status: str


class GatewayPaymentRequest(BaseModel):
    payment_method: str = Field(
        default="other_qris",
        max_length=30
    )
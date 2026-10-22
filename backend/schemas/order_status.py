from enum import Enum
from typing import Optional
from pydantic import BaseModel


class OrderStatus(str, Enum):
    PENDING = "pending"
    PAID = "paid"
    PROCESSING = "processing"
    DELIVERED = "delivered"
    COMPLETED = "completed"
    DONE = "done"
    CANCELLED = "cancelled"


class OrderStatusRequest(BaseModel):
    status: OrderStatus
    cancellation_reason: Optional[str] = None
    refund_note: Optional[str] = None


class OrderRefundRequest(BaseModel):
    refund_note: Optional[str] = None
    refund_proof_url: Optional[str] = None

from enum import Enum
from pydantic import BaseModel


class OrderStatus(str, Enum):
    PENDING = "pending"
    PAID = "paid"
    DONE = "done"


class OrderStatusRequest(BaseModel):
    status: OrderStatus
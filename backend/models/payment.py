from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    ForeignKey
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from database import Base


class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    payment_method = Column(String(30), nullable=False)
    gateway = Column(String(30), nullable=True)
    gateway_order_id = Column(String(100), nullable=True)
    gateway_transaction_id = Column(String(100), nullable=True)
    gateway_token = Column(String(255), nullable=True)
    payment_url = Column(String(500), nullable=True)
    expires_at = Column(DateTime, nullable=True)
    amount = Column(Integer, nullable=False)
    payment_proof = Column(String(500), nullable=True)
    status = Column(String(30), nullable=False, default="pending")
    verified_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    order = relationship("Order", back_populates="payments")
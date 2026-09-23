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


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)

    order_code = Column(
        String(30),
        unique=True,
        nullable=False
    )

    customer_id = Column(
        Integer,
        ForeignKey("customers.id"),
        nullable=False
    )

    address_id = Column(
        Integer,
        ForeignKey("customer_addresses.id"),
        nullable=False
    )

    # Snapshot alamat saat order dibuat
    recipient_name = Column(String(100), nullable=False)
    phone = Column(String(20), nullable=False)
    address = Column(String(255), nullable=False)
    province = Column(String(100), nullable=False)
    city = Column(String(100), nullable=False)
    district = Column(String(100), nullable=False)
    postal_code = Column(String(10), nullable=False)

    notes = Column(String(500), nullable=True)

    total_amount = Column(Integer, nullable=False)

    payment_method = Column(String(30), nullable=False)

    payment_proof = Column(String(500), nullable=True)

    status = Column(
        String(30),
        nullable=False,
        default="pending"
    )

    created_at = Column(
        DateTime,
        server_default=func.now()
    )

    updated_at = Column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now()
    )

    # Relationship
    customer = relationship(
        "Customer",
        back_populates="orders"
    )

    items = relationship(
        "OrderItem",
        back_populates="order",
        cascade="all, delete-orphan"
    )

    payments = relationship(
        "Payment",
        back_populates="order",
        cascade="all, delete-orphan"
)
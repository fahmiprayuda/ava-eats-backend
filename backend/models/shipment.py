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


class Shipment(Base):
    __tablename__ = "shipments"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), unique=True, nullable=False)
    biteship_order_id = Column(String(100), unique=True, nullable=True)
    courier = Column(String(50), nullable=True)
    service = Column(String(100), nullable=True)
    tracking_number = Column(String(100), nullable=True)
    status = Column(String(30), nullable=False, default="pending")
    shipping_cost = Column(Integer, nullable=True)

    tracking_url = Column(String(500), nullable=True)
    driver_name = Column(String(100), nullable=True)
    driver_phone = Column(String(50), nullable=True)
    driver_plate_number = Column(String(50), nullable=True)
    driver_photo_url = Column(String(500), nullable=True)

    shipped_at = Column(DateTime, nullable=True)
    delivered_at = Column( DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    order = relationship(
        "Order",
        back_populates="shipment"
    )
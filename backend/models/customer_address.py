from sqlalchemy import Column, Integer, String, ForeignKey, Boolean
from sqlalchemy.orm import relationship

from database import Base

class CustomerAddress(Base):
    __tablename__ = "customer_addresses"

    id = Column(
        Integer,
        primary_key=True,
        index=True
        )

    customer_id = Column(
        Integer,
        ForeignKey("customers.id"),
        nullable=False
        )

    label = Column(String(50), nullable=False)
    recipient_name = Column(String(100), nullable=False)
    phone = Column(String(20), nullable=False)

    address = Column(String(255), nullable=False)
    province = Column(String(100), nullable=False)
    city = Column(String(100), nullable=False)
    district = Column(String(100), nullable=False)
    postal_code = Column(String(10), nullable=False)

    is_default = Column(Boolean, default=False)

    customer = relationship(
        "Customer",
        back_populates="addresses"
    )
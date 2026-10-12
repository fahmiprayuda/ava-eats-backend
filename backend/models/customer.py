from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import relationship

from database import Base


class Customer(Base):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, index=True)
    phone = Column(String(20), unique=True, nullable=False)
    password = Column(String(255), nullable=False)
    name = Column(String(100), nullable=False)

    addresses = relationship(
        "CustomerAddress",
        back_populates="customer"
    )

    orders = relationship(
        "Order",
        back_populates="customer"
    )
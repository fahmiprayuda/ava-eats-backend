from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    ForeignKey,
    Boolean,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from database import Base


class PromoCode(Base):
    __tablename__ = "promo_codes"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(50), unique=True, nullable=False, index=True)
    description = Column(String(255), nullable=True)
    
    # "percentage" | "fixed_amount" | "shipping_discount"
    discount_type = Column(String(30), nullable=False, default="percentage")
    discount_value = Column(Integer, nullable=False, default=0)
    max_discount = Column(Integer, nullable=True) # Maksimal potongan untuk tipe persen
    min_order_amount = Column(Integer, nullable=False, default=0) # Minimal subtotal
    
    usage_limit = Column(Integer, nullable=True) # Kuota total (None = unlimited)
    used_count = Column(Integer, nullable=False, default=0)
    usage_limit_per_user = Column(Integer, nullable=False, default=1)
    
    start_date = Column(DateTime, nullable=True)
    end_date = Column(DateTime, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relationships
    usages = relationship("PromoCodeUsage", back_populates="promo_code", cascade="all, delete-orphan")
    orders = relationship("Order", back_populates="promo")


class PromoCodeUsage(Base):
    __tablename__ = "promo_code_usages"

    id = Column(Integer, primary_key=True, index=True)
    promo_code_id = Column(Integer, ForeignKey("promo_codes.id", ondelete="CASCADE"), nullable=False)
    customer_id = Column(Integer, ForeignKey("customers.id", ondelete="CASCADE"), nullable=False)
    order_id = Column(Integer, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False)
    discount_amount = Column(Integer, nullable=False, default=0)
    used_at = Column(DateTime, server_default=func.now())

    # Relationships
    promo_code = relationship("PromoCode", back_populates="usages")
    customer = relationship("Customer")
    order = relationship("Order", back_populates="promo_usage")

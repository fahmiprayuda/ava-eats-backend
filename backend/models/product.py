from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from database import Base


class Product(Base):    
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(150), nullable=False)
    description = Column(Text, nullable=True)
    price = Column(Integer, nullable=False)
    image = Column(String(500), nullable=True)
    weight_grams = Column(Integer, nullable=False)
    stock = Column(Integer, nullable=False, default=0)
    is_available = Column(Boolean, default=True, nullable=False)
    is_preorder = Column(Boolean, default=False, nullable=False)
    preorder_days = Column(Integer, default=7, nullable=False)
    preorder_pickup_date = Column(String(50), nullable=True)
    category_id = Column(Integer, ForeignKey("categories.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relationships
    category_rel = relationship("Category", back_populates="products")

    @property
    def category_name(self):
        return self.category_rel.name if self.category_rel else "Lainnya"

    @property
    def category_icon(self):
        return self.category_rel.icon if (self.category_rel and self.category_rel.icon) else "🍽️"

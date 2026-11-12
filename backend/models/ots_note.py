from sqlalchemy import Column, Integer, String, Text, Boolean, Date, DateTime
from sqlalchemy.sql import func

from database import Base


class OtsNote(Base):
    __tablename__ = "ots_notes"

    id = Column(Integer, primary_key=True, index=True)
    note_date = Column(Date, nullable=False, index=True)
    day_label = Column(String(100), nullable=True)
    customer_name = Column(String(150), nullable=False)
    items_text = Column(Text, nullable=False)
    amount = Column(Integer, nullable=True)
    is_paid = Column(Boolean, nullable=False, default=False)
    is_done = Column(Boolean, nullable=False, default=False)
    created_by = Column(String(100), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class OtsMenu(Base):
    __tablename__ = "ots_menus"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(150), nullable=False)
    price = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    created_by = Column(String(100), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

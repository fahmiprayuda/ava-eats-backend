from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func

from database import Base


class AuditTrail(Base):
    __tablename__ = "audit_trails"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    user_type = Column(
        String(30),
        nullable=False
    )

    user_id = Column(
        Integer,
        nullable=False
    )

    action = Column(
        String(100),
        nullable=False
    )

    entity_type = Column(
        String(50),
        nullable=False
    )

    entity_id = Column(
        Integer,
        nullable=False
    )

    description = Column(
        String(500),
        nullable=True
    )

    created_at = Column(
        DateTime,
        server_default=func.now()
    )
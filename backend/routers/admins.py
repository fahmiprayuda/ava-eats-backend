from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_

from database import get_db
from models.admin import Admin
from models.audit_trail import AuditTrail
from schemas.admin import AdminCreate
from utils.password import hash_password
from auth.dependencies import require_admin


router = APIRouter(
    prefix="/api/admins",
    tags=["Admins"]
)


@router.post("")
def create_admin(
    data: AdminCreate,
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(require_admin)
):
    existing_admin = db.query(Admin).filter(
        Admin.username == data.username
    ).first()

    if existing_admin:
        raise HTTPException(
            status_code=400,
            detail="Username sudah digunakan"
        )

    admin = Admin(
        username=data.username,
        password=hash_password(data.password)
    )

    db.add(admin)
    db.commit()
    db.refresh(admin)

    return {
        "id": admin.id,
        "username": admin.username
    }


@router.get("/audit-trails")
def get_audit_trails(
    search: Optional[str] = None,
    entity_type: Optional[str] = None,
    action: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(require_admin)
):
    query = db.query(AuditTrail)

    if search and search.strip():
        term = f"%{search.strip()}%"
        query = query.filter(
            or_(
                AuditTrail.description.ilike(term),
                AuditTrail.action.ilike(term),
                AuditTrail.user_type.ilike(term),
                AuditTrail.entity_type.ilike(term)
            )
        )

    if entity_type:
        query = query.filter(AuditTrail.entity_type == entity_type)

    if action:
        query = query.filter(AuditTrail.action == action)

    total = query.count()
    records = query.order_by(AuditTrail.created_at.desc()).offset(offset).limit(limit).all()

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "audit_trails": [
            {
                "id": r.id,
                "user_type": r.user_type,
                "user_id": r.user_id,
                "action": r.action,
                "entity_type": r.entity_type,
                "entity_id": r.entity_id,
                "description": r.description,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in records
        ]
    }

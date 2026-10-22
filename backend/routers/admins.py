from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_

from database import get_db
from models.admin import Admin
from models.audit_trail import AuditTrail
from schemas.admin import AdminCreate, AdminUpdate, AdminResponse
from utils.password import hash_password
from auth.dependencies import require_admin, require_super_admin
from utils.audit import create_audit_log


router = APIRouter(
    prefix="/api/admins",
    tags=["Admins"]
)


@router.get("/me", response_model=AdminResponse)
def get_current_admin_profile(
    current_admin: Admin = Depends(require_admin)
):
    return current_admin


@router.get("", response_model=List[AdminResponse])
def get_all_admins(
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(require_super_admin)
):
    admins = db.query(Admin).order_by(Admin.id.asc()).all()
    return admins


@router.post("", response_model=AdminResponse)
def create_admin(
    data: AdminCreate,
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(require_super_admin)
):
    existing_admin = db.query(Admin).filter(
        Admin.username == data.username.strip()
    ).first()

    if existing_admin:
        raise HTTPException(
            status_code=400,
            detail="Username sudah digunakan"
        )

    admin = Admin(
        username=data.username.strip(),
        name=data.name.strip(),
        role=data.role.strip() if data.role else "admin",
        password=hash_password(data.password)
    )

    db.add(admin)
    db.commit()
    db.refresh(admin)

    create_audit_log(
        db=db,
        user_type="admin",
        user_id=current_admin.id,
        action="CREATE",
        entity_type="admin",
        entity_id=admin.id,
        description=f"Admin baru dibuat: {admin.username} ({admin.name}, role: {admin.role})"
    )
    db.commit()

    return admin


@router.put("/{admin_id}", response_model=AdminResponse)
def update_admin(
    admin_id: int,
    data: AdminUpdate,
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(require_super_admin)
):
    admin = db.query(Admin).filter(Admin.id == admin_id).first()
    if not admin:
        raise HTTPException(status_code=404, detail="Admin tidak ditemukan")

    changes = []
    if data.username and data.username.strip() != admin.username:
        # Check uniqueness
        duplicate = db.query(Admin).filter(
            Admin.username == data.username.strip(),
            Admin.id != admin_id
        ).first()
        if duplicate:
            raise HTTPException(status_code=400, detail="Username sudah digunakan oleh admin lain")
        changes.append(f"username: {admin.username} -> {data.username.strip()}")
        admin.username = data.username.strip()

    if data.name and data.name.strip() != admin.name:
        changes.append(f"nama: {admin.name} -> {data.name.strip()}")
        admin.name = data.name.strip()

    if data.role and data.role.strip() != admin.role:
        changes.append(f"role: {admin.role} -> {data.role.strip()}")
        admin.role = data.role.strip()

    if data.password and data.password.strip():
        admin.password = hash_password(data.password.strip())
        changes.append("password diubah")

    db.commit()
    db.refresh(admin)

    if changes:
        create_audit_log(
            db=db,
            user_type="admin",
            user_id=current_admin.id,
            action="UPDATE",
            entity_type="admin",
            entity_id=admin.id,
            description=f"Admin {admin.username} diperbarui: {', '.join(changes)}"
        )
        db.commit()

    return admin


@router.delete("/{admin_id}")
def delete_admin(
    admin_id: int,
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(require_super_admin)
):
    if admin_id == current_admin.id:
        raise HTTPException(
            status_code=400,
            detail="Tidak dapat menghapus akun Anda sendiri yang sedang aktif."
        )

    admin = db.query(Admin).filter(Admin.id == admin_id).first()
    if not admin:
        raise HTTPException(status_code=404, detail="Admin tidak ditemukan")

    total_admins = db.query(Admin).count()
    if total_admins <= 1:
        raise HTTPException(
            status_code=400,
            detail="Tidak dapat menghapus admin terakhir pada sistem."
        )

    deleted_username = admin.username
    deleted_name = admin.name

    db.delete(admin)
    db.commit()

    create_audit_log(
        db=db,
        user_type="admin",
        user_id=current_admin.id,
        action="DELETE",
        entity_type="admin",
        entity_id=admin_id,
        description=f"Admin {deleted_username} ({deleted_name}) dihapus dari sistem."
    )
    db.commit()

    return {"message": f"Admin {deleted_username} berhasil dihapus"}



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

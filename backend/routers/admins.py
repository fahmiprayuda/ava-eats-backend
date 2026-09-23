from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models.admin import Admin
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
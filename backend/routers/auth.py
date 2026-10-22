from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models.admin import Admin
from schemas.auth import LoginRequest
from utils.password import verify_password
from auth.jwt import create_access_token


router = APIRouter(
    prefix="/api/auth",
    tags=["Authentication"]
)


@router.post("/login")
def login(
    data: LoginRequest,
    db: Session = Depends(get_db)
):
    admin = db.query(Admin).filter(
        Admin.username == data.username
    ).first()

    if not admin:
        raise HTTPException(
            status_code=401,
            detail="Username atau password salah"
        )

    password_valid = verify_password(
        data.password,
        admin.password
    )

    if not password_valid:
        raise HTTPException(
            status_code=401,
            detail="Username atau password salah"
        )

    access_token = create_access_token({
        "sub": str(admin.id),
        "username": admin.username,
        "role": admin.role
    })

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "admin": {
            "id": admin.id,
            "username": admin.username,
            "name": admin.name,
            "role": admin.role,
        }
    }
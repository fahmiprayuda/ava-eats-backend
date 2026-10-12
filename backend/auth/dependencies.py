from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from database import get_db
from models.admin import Admin
from models.customer import Customer
from auth.jwt import SECRET_KEY, ALGORITHM


security = HTTPBearer()


def get_current_admin(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    token = credentials.credentials

    try:
        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM]
        )

        admin_id = payload.get("sub")
        role = payload.get("role")

        if role != "admin":
            raise HTTPException(
                status_code=403,
                detail="Token bukan milik admin"
            )


        if admin_id is None:
            raise HTTPException(
                status_code=401,
                detail="Token tidak valid"
            )

    except JWTError:
        raise HTTPException(
            status_code=401,
            detail="Token tidak valid atau sudah expired"
        )

    admin = db.query(Admin).filter(
        Admin.id == int(admin_id)
    ).first()

    if not admin:
        raise HTTPException(
            status_code=401,
            detail="Admin tidak ditemukan"
        )

    return admin

def require_admin(
    current_admin: Admin = Depends(get_current_admin)
):
    if current_admin.role != "admin":
        raise HTTPException(
            status_code=403,
            detail="Anda tidak memiliki izin untuk melakukan tindakan ini"
        )

    return current_admin

def get_current_customer(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    token = credentials.credentials

    try:
        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM]
        )

        customer_id = payload.get("sub")
        role = payload.get("role")

        if customer_id is None:
            raise HTTPException(
                status_code=401,
                detail="Token tidak valid"
            )

        if role != "customer":
            raise HTTPException(
                status_code=403,
                detail="Token bukan milik customer"
            )

    except JWTError:
        raise HTTPException(
            status_code=401,
            detail="Token tidak valid atau sudah expired"
        )

    customer = db.query(Customer).filter(
        Customer.id == int(customer_id)
    ).first()

    if not customer:
        raise HTTPException(
            status_code=401,
            detail="Customer tidak ditemukan"
        )

    return customer
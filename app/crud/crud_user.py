from sqlalchemy.orm import Session
from typing import Optional
from app.models.user import User
from app.schemas.user import UserCreate
from app.core.security import get_password_hash

def get_user_by_email(db: Session, email: str):
    return db.query(User).filter(User.email == email).first()

def get_user_by_id(db: Session, user_id: int):
    return db.query(User).filter(User.id == user_id).first()

def get_users(db: Session, skip: int = 0, limit: int = 100, business_id: Optional[int] = None):
    query = db.query(User)
    if business_id is not None:
        query = query.filter(User.business_id == business_id)
    return query.offset(skip).limit(limit).all()

def create_user(db: Session, user: UserCreate, business_id: Optional[int] = None, branch_id: Optional[int] = None):
    hashed_password = get_password_hash(user.password)
    db_user = User(
        email=user.email,
        name=user.name,
        password=hashed_password,
        role_id=user.role_id,
        is_active=user.is_active,
        business_id=business_id,
        branch_id=branch_id
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

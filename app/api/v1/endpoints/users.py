from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.user import UserCreate, UserResponse
from app.crud import crud_user
from app.api.deps import get_current_active_user
from app.models.user import User

router = APIRouter()

@router.get("/", response_model=List[UserResponse])
def read_users(
    skip: int = 0,
    limit: int = 100,
    business_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Retrieve users. Super Admin gets Super Admin system users by default unless business_id is specified.
    """
    if current_user.role and current_user.role.name == "Super Admin":
        if business_id is not None:
            return crud_user.get_users(db, skip=skip, limit=limit, business_id=business_id)
        return db.query(User).filter(User.business_id == None).offset(skip).limit(limit).all()
    
    return crud_user.get_users(db, skip=skip, limit=limit, business_id=current_user.business_id)

@router.post("/", response_model=UserResponse)
def create_user(
    *,
    db: Session = Depends(get_db),
    user_in: UserCreate,
    current_user: User = Depends(get_current_active_user)
):
    """
    Create a new user under current business tenant.
    """
    user = crud_user.get_user_by_email(db, email=user_in.email)
    if user:
        raise HTTPException(status_code=400, detail="User with this email already exists")
    
    business_id = current_user.business_id or 1
    branch_id = user_in.branch_id
    return crud_user.create_user(db=db, user=user_in, business_id=business_id, branch_id=branch_id)

@router.put("/{user_id}", response_model=UserResponse)
def update_user(
    *,
    db: Session = Depends(get_db),
    user_id: int,
    user_in: dict,
    current_user: User = Depends(get_current_active_user)
):
    query = db.query(User).filter(User.id == user_id)
    if current_user.role and current_user.role.name != "Super Admin":
        query = query.filter(User.business_id == current_user.business_id)
    
    user = query.first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if "name" in user_in:
        user.name = user_in["name"]
    if "is_active" in user_in:
        user.is_active = user_in["is_active"]
    if "role_id" in user_in:
        user.role_id = user_in["role_id"]
    if "branch_id" in user_in:
        user.branch_id = user_in["branch_id"]
        
    db.commit()
    db.refresh(user)
    return user

@router.delete("/{user_id}")
def delete_user(
    *,
    db: Session = Depends(get_db),
    user_id: int,
    current_user: User = Depends(get_current_active_user)
):
    query = db.query(User).filter(User.id == user_id)
    if current_user.role and current_user.role.name != "Super Admin":
        query = query.filter(User.business_id == current_user.business_id)
        
    user = query.first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="You cannot delete yourself")
        
    db.delete(user)
    db.commit()
    return {"message": "User deleted successfully"}

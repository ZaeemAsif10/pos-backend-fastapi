from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.business import BusinessCreate, BusinessResponse, BusinessUpdate
from app.crud import crud_business
from app.api.deps import get_current_active_user
from app.models.user import User

router = APIRouter()

@router.get("/", response_model=List[BusinessResponse])
def read_businesses(skip: int = 0, limit: int = 100, db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    """
    Retrieve businesses. Super Admin sees all businesses; Business Users see only their own.
    """
    if current_user.role and current_user.role.name == "Super Admin":
        return crud_business.get_businesses(db, skip=skip, limit=limit)
    
    # Non-Super Admin only gets their assigned business
    if current_user.business_id:
        b = crud_business.get_business(db, business_id=current_user.business_id)
        return [b] if b else []
    return []

@router.post("/", response_model=BusinessResponse)
def create_business(
    business_in: BusinessCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Create a new business and auto-provision its main branch and admin user.
    """
    return crud_business.create_business(db=db, business_in=business_in)

@router.get("/{business_id}", response_model=BusinessResponse)
def read_business(
    business_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    business = crud_business.get_business(db, business_id=business_id)
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")
    return business

@router.put("/{business_id}", response_model=BusinessResponse)
def update_business(
    business_id: int,
    business_in: BusinessUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    return crud_business.update_business(db=db, business_id=business_id, business_in=business_in)

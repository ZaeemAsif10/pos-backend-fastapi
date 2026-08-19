from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.payment_method import PaymentMethodCreate, PaymentMethodResponse, PaymentMethodUpdate
from app.crud import crud_payment_method
from app.api.deps import get_current_active_user
from app.models.user import User

router = APIRouter()

@router.get("/", response_model=List[PaymentMethodResponse])
def read_payment_methods(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Retrieve payment methods scoped by user's business tenant.
    """
    business_id = None if (current_user.role and current_user.role.name == "Super Admin") else current_user.business_id
    pms = crud_payment_method.get_payment_methods(db, skip=skip, limit=limit, business_id=business_id)
    return pms

@router.post("/", response_model=PaymentMethodResponse)
def create_payment_method(
    *,
    db: Session = Depends(get_db),
    pm_in: PaymentMethodCreate,
    current_user: User = Depends(get_current_active_user)
):
    """
    Create new payment method for current business tenant.
    """
    business_id = current_user.business_id or 1
    pm = crud_payment_method.create_payment_method(db=db, pm=pm_in, business_id=business_id)
    return pm

@router.put("/{pm_id}", response_model=PaymentMethodResponse)
def update_payment_method(
    *,
    db: Session = Depends(get_db),
    pm_id: int,
    pm_in: PaymentMethodUpdate,
    current_user: User = Depends(get_current_active_user)
):
    """
    Update a payment method.
    """
    business_id = None if (current_user.role and current_user.role.name == "Super Admin") else current_user.business_id
    pm = crud_payment_method.get_payment_method(db=db, payment_method_id=pm_id, business_id=business_id)
    if not pm:
        raise HTTPException(status_code=404, detail="Payment Method not found")
    pm = crud_payment_method.update_payment_method(db=db, db_pm=pm, pm_in=pm_in)
    return pm

@router.delete("/{pm_id}")
def delete_payment_method(
    *,
    db: Session = Depends(get_db),
    pm_id: int,
    current_user: User = Depends(get_current_active_user)
):
    """
    Delete a payment method.
    """
    business_id = None if (current_user.role and current_user.role.name == "Super Admin") else current_user.business_id
    pm = crud_payment_method.get_payment_method(db=db, payment_method_id=pm_id, business_id=business_id)
    if not pm:
        raise HTTPException(status_code=404, detail="Payment Method not found")
    crud_payment_method.delete_payment_method(db=db, db_pm=pm)
    return {"message": "Payment method deleted successfully"}

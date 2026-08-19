from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.customer import CustomerCreate, CustomerUpdate, CustomerResponse
from app.crud import crud_customer
from app.api.deps import get_current_active_user
from app.models.user import User

router = APIRouter()

@router.get("/", response_model=List[CustomerResponse])
def read_customers(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Retrieve customers scoped by user's business tenant.
    """
    business_id = None if (current_user.role and current_user.role.name == "Super Admin") else current_user.business_id
    return crud_customer.get_customers(db, skip=skip, limit=limit, business_id=business_id)

@router.post("/", response_model=CustomerResponse)
def create_customer(
    *,
    db: Session = Depends(get_db),
    customer_in: CustomerCreate,
    current_user: User = Depends(get_current_active_user)
):
    """
    Register a new customer.
    """
    business_id = current_user.business_id or 1
    if customer_in.phone:
        customer = crud_customer.get_customer_by_phone(db, phone=customer_in.phone, business_id=business_id)
        if customer:
            raise HTTPException(status_code=400, detail="Customer with this phone number already exists")
    
    return crud_customer.create_customer(db=db, customer=customer_in, business_id=business_id)

@router.put("/{customer_id}", response_model=CustomerResponse)
def update_customer(
    *,
    db: Session = Depends(get_db),
    customer_id: int,
    customer_in: CustomerUpdate,
    current_user: User = Depends(get_current_active_user)
):
    business_id = None if (current_user.role and current_user.role.name == "Super Admin") else current_user.business_id
    customer = crud_customer.get_customer(db=db, customer_id=customer_id, business_id=business_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    if customer_in.phone and customer_in.phone != customer.phone:
        existing = crud_customer.get_customer_by_phone(db, phone=customer_in.phone, business_id=business_id)
        if existing:
            raise HTTPException(status_code=400, detail="Phone number already in use by another customer")

    return crud_customer.update_customer(db=db, db_customer=customer, customer_in=customer_in)

@router.delete("/{customer_id}")
def delete_customer(
    *,
    db: Session = Depends(get_db),
    customer_id: int,
    current_user: User = Depends(get_current_active_user)
):
    business_id = None if (current_user.role and current_user.role.name == "Super Admin") else current_user.business_id
    customer = crud_customer.get_customer(db=db, customer_id=customer_id, business_id=business_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    crud_customer.delete_customer(db=db, db_customer=customer)
    return {"message": "Customer deleted successfully"}

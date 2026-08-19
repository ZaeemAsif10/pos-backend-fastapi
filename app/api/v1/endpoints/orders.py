from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.order import OrderCreate, OrderResponse, OrderPaymentCreate, OrderPaymentResponse
from app.crud import crud_order
from app.api.deps import get_current_active_user
from app.models.user import User

router = APIRouter()

@router.get("/", response_model=List[OrderResponse])
def read_orders(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Retrieve orders scoped by user's business tenant.
    """
    business_id = None if (current_user.role and current_user.role.name == "Super Admin") else current_user.business_id
    branch_id = current_user.branch_id if (current_user.role and current_user.role.name in ["Branch Manager", "Cashier"]) else None
    orders = crud_order.get_orders(db, skip=skip, limit=limit, business_id=business_id, branch_id=branch_id)
    return orders

@router.post("/", response_model=OrderResponse)
def create_order(
    *,
    db: Session = Depends(get_db),
    order_in: OrderCreate,
    current_user: User = Depends(get_current_active_user)
):
    """
    Create new order for current tenant business and branch.
    """
    business_id = current_user.business_id or 1
    branch_id = current_user.branch_id
    order = crud_order.create_order(
        db=db,
        order_in=order_in,
        user_id=current_user.id,
        business_id=business_id,
        branch_id=branch_id
    )
    return order

@router.get("/{order_id}", response_model=OrderResponse)
def read_order(
    order_id: int, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Get a specific order by ID.
    """
    business_id = None if (current_user.role and current_user.role.name == "Super Admin") else current_user.business_id
    order = crud_order.get_order(db=db, order_id=order_id, business_id=business_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order

@router.post("/{order_id}/payments", response_model=OrderResponse)
def add_payment_to_order(
    order_id: int,
    payment_in: OrderPaymentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Add a payment to an existing order.
    """
    business_id = None if (current_user.role and current_user.role.name == "Super Admin") else current_user.business_id
    return crud_order.add_order_payment(db=db, order_id=order_id, payment_in=payment_in, business_id=business_id)

@router.get("/{order_id}/payments", response_model=List[OrderPaymentResponse])
def get_payments_for_order(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Get payment history/breakdown for a specific order.
    """
    business_id = None if (current_user.role and current_user.role.name == "Super Admin") else current_user.business_id
    return crud_order.get_order_payments(db=db, order_id=order_id, business_id=business_id)

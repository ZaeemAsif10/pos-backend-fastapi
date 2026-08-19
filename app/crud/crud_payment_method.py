from sqlalchemy.orm import Session
from typing import Optional
from app.models.payment_method import PaymentMethod
from app.schemas.payment_method import PaymentMethodCreate, PaymentMethodUpdate

def get_payment_method(db: Session, payment_method_id: int, business_id: Optional[int] = None):
    query = db.query(PaymentMethod).filter(PaymentMethod.id == payment_method_id)
    if business_id is not None:
        query = query.filter(PaymentMethod.business_id == business_id)
    return query.first()

def get_payment_methods(db: Session, skip: int = 0, limit: int = 100, business_id: Optional[int] = None):
    query = db.query(PaymentMethod)
    if business_id is not None:
        query = query.filter(PaymentMethod.business_id == business_id)
    return query.offset(skip).limit(limit).all()

def create_payment_method(db: Session, pm: PaymentMethodCreate, business_id: Optional[int] = None):
    db_pm = PaymentMethod(
        name=pm.name,
        description=pm.description,
        is_active=pm.is_active,
        business_id=business_id
    )
    db.add(db_pm)
    db.commit()
    db.refresh(db_pm)
    return db_pm

def update_payment_method(db: Session, db_pm: PaymentMethod, pm_in: PaymentMethodUpdate):
    update_data = pm_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_pm, field, value)
    db.commit()
    db.refresh(db_pm)
    return db_pm

def delete_payment_method(db: Session, db_pm: PaymentMethod):
    db.delete(db_pm)
    db.commit()
    return db_pm

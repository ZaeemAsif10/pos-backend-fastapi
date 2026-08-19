from sqlalchemy.orm import Session
from typing import Optional
from app.models.customer import Customer
from app.schemas.customer import CustomerCreate, CustomerUpdate

def get_customer(db: Session, customer_id: int, business_id: Optional[int] = None):
    query = db.query(Customer).filter(Customer.id == customer_id)
    if business_id is not None:
        query = query.filter(Customer.business_id == business_id)
    return query.first()

def get_customer_by_phone(db: Session, phone: str, business_id: Optional[int] = None):
    query = db.query(Customer).filter(Customer.phone == phone)
    if business_id is not None:
        query = query.filter(Customer.business_id == business_id)
    return query.first()

def get_customers(db: Session, skip: int = 0, limit: int = 100, business_id: Optional[int] = None):
    query = db.query(Customer)
    if business_id is not None:
        query = query.filter(Customer.business_id == business_id)
    return query.offset(skip).limit(limit).all()

def create_customer(db: Session, customer: CustomerCreate, business_id: Optional[int] = None):
    import uuid
    final_phone = customer.phone.strip() if customer.phone else ""
    if not final_phone:
        final_phone = f"N/A-{uuid.uuid4().hex[:8]}"
        
    db_customer = Customer(
        name=customer.name,
        phone=final_phone,
        email=customer.email,
        address=customer.address,
        business_id=business_id
    )
    db.add(db_customer)
    try:
        db.commit()
        db.refresh(db_customer)
    except Exception as e:
        db.rollback()
        raise e
    return db_customer

def update_customer(db: Session, db_customer: Customer, customer_in: CustomerUpdate):
    update_data = customer_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_customer, field, value)
    db.commit()
    db.refresh(db_customer)
    return db_customer

def delete_customer(db: Session, db_customer: Customer):
    db.delete(db_customer)
    db.commit()
    return db_customer

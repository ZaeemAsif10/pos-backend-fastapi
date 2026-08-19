from sqlalchemy.orm import Session
from typing import Optional
from app.models.product import Brand
from app.schemas.brand import BrandCreate, BrandUpdate

def get_brand(db: Session, brand_id: int, business_id: Optional[int] = None):
    query = db.query(Brand).filter(Brand.id == brand_id)
    if business_id is not None:
        query = query.filter(Brand.business_id == business_id)
    return query.first()

def get_brands(db: Session, skip: int = 0, limit: int = 100, business_id: Optional[int] = None):
    query = db.query(Brand)
    if business_id is not None:
        query = query.filter(Brand.business_id == business_id)
    return query.offset(skip).limit(limit).all()

def create_brand(db: Session, brand: BrandCreate, business_id: Optional[int] = None):
    db_brand = Brand(
        name=brand.name,
        description=brand.description,
        business_id=business_id
    )
    db.add(db_brand)
    db.commit()
    db.refresh(db_brand)
    return db_brand

def update_brand(db: Session, db_brand: Brand, brand_in: BrandUpdate):
    update_data = brand_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_brand, field, value)
    db.commit()
    db.refresh(db_brand)
    return db_brand

def delete_brand(db: Session, db_brand: Brand):
    db.delete(db_brand)
    db.commit()
    return db_brand

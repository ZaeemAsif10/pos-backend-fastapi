from sqlalchemy.orm import Session
from typing import Optional
from app.models.product import Category
from app.schemas.category import CategoryCreate, CategoryUpdate

def get_category(db: Session, category_id: int, business_id: Optional[int] = None):
    query = db.query(Category).filter(Category.id == category_id)
    if business_id is not None:
        query = query.filter(Category.business_id == business_id)
    return query.first()

def get_categories(db: Session, skip: int = 0, limit: int = 100, business_id: Optional[int] = None):
    query = db.query(Category)
    if business_id is not None:
        query = query.filter(Category.business_id == business_id)
    return query.offset(skip).limit(limit).all()

def create_category(db: Session, category: CategoryCreate, business_id: Optional[int] = None):
    db_category = Category(
        name=category.name,
        description=category.description,
        business_id=business_id
    )
    db.add(db_category)
    db.commit()
    db.refresh(db_category)
    return db_category

def update_category(db: Session, db_category: Category, category_in: CategoryUpdate):
    update_data = category_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_category, field, value)
    db.commit()
    db.refresh(db_category)
    return db_category

def delete_category(db: Session, db_category: Category):
    db.delete(db_category)
    db.commit()
    return db_category

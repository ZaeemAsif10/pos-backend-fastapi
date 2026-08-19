from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.category import CategoryCreate, CategoryResponse, CategoryUpdate
from app.crud import crud_category
from app.api.deps import get_current_active_user
from app.models.user import User

router = APIRouter()

@router.get("/", response_model=List[CategoryResponse])
def read_categories(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Retrieve product categories scoped by user's business tenant.
    """
    business_id = None if (current_user.role and current_user.role.name == "Super Admin") else current_user.business_id
    categories = crud_category.get_categories(db, skip=skip, limit=limit, business_id=business_id)
    return categories

@router.post("/", response_model=CategoryResponse)
def create_category(
    *,
    db: Session = Depends(get_db),
    category_in: CategoryCreate,
    current_user: User = Depends(get_current_active_user)
):
    """
    Create new product category for current business tenant.
    """
    business_id = current_user.business_id or 1
    category = crud_category.create_category(db=db, category=category_in, business_id=business_id)
    return category

@router.put("/{category_id}", response_model=CategoryResponse)
def update_category(
    *,
    db: Session = Depends(get_db),
    category_id: int,
    category_in: CategoryUpdate,
    current_user: User = Depends(get_current_active_user)
):
    """
    Update a product category.
    """
    business_id = None if (current_user.role and current_user.role.name == "Super Admin") else current_user.business_id
    category = crud_category.get_category(db=db, category_id=category_id, business_id=business_id)
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
    category = crud_category.update_category(db=db, db_category=category, category_in=category_in)
    return category

@router.delete("/{category_id}")
def delete_category(
    *,
    db: Session = Depends(get_db),
    category_id: int,
    current_user: User = Depends(get_current_active_user)
):
    """
    Delete a product category.
    """
    business_id = None if (current_user.role and current_user.role.name == "Super Admin") else current_user.business_id
    category = crud_category.get_category(db=db, category_id=category_id, business_id=business_id)
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
    crud_category.delete_category(db=db, db_category=category)
    return {"message": "Category deleted successfully"}

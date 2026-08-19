from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.brand import BrandCreate, BrandResponse, BrandUpdate
from app.crud import crud_brand
from app.api.deps import get_current_active_user
from app.models.user import User

router = APIRouter()

@router.get("/", response_model=List[BrandResponse])
def read_brands(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Retrieve product brands scoped by user's business tenant.
    """
    business_id = None if (current_user.role and current_user.role.name == "Super Admin") else current_user.business_id
    brands = crud_brand.get_brands(db, skip=skip, limit=limit, business_id=business_id)
    return brands

@router.post("/", response_model=BrandResponse)
def create_brand(
    *,
    db: Session = Depends(get_db),
    brand_in: BrandCreate,
    current_user: User = Depends(get_current_active_user)
):
    """
    Create new product brand for current business tenant.
    """
    business_id = current_user.business_id or 1
    brand = crud_brand.create_brand(db=db, brand=brand_in, business_id=business_id)
    return brand

@router.put("/{brand_id}", response_model=BrandResponse)
def update_brand(
    *,
    db: Session = Depends(get_db),
    brand_id: int,
    brand_in: BrandUpdate,
    current_user: User = Depends(get_current_active_user)
):
    """
    Update a product brand.
    """
    business_id = None if (current_user.role and current_user.role.name == "Super Admin") else current_user.business_id
    brand = crud_brand.get_brand(db=db, brand_id=brand_id, business_id=business_id)
    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found")
    brand = crud_brand.update_brand(db=db, db_brand=brand, brand_in=brand_in)
    return brand

@router.delete("/{brand_id}")
def delete_brand(
    *,
    db: Session = Depends(get_db),
    brand_id: int,
    current_user: User = Depends(get_current_active_user)
):
    """
    Delete a product brand.
    """
    business_id = None if (current_user.role and current_user.role.name == "Super Admin") else current_user.business_id
    brand = crud_brand.get_brand(db=db, brand_id=brand_id, business_id=business_id)
    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found")
    crud_brand.delete_brand(db=db, db_brand=brand)
    return {"message": "Brand deleted successfully"}

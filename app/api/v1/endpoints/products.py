from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.product import ProductCreate, ProductResponse
from app.crud import crud_product, crud_category
from app.api.deps import get_current_active_user
from app.models.user import User

router = APIRouter()

@router.get("/", response_model=List[ProductResponse])
def read_products(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Retrieve products scoped by user's business tenant.
    """
    business_id = None if (current_user.role and current_user.role.name == "Super Admin") else current_user.business_id
    products = crud_product.get_products(db, skip=skip, limit=limit, business_id=business_id)
    return products

@router.post("/", response_model=ProductResponse)
def create_product(
    *,
    db: Session = Depends(get_db),
    product_in: ProductCreate,
    current_user: User = Depends(get_current_active_user)
):
    """
    Create new product with its variants for current business tenant.
    """
    business_id = current_user.business_id or 1
    # Verify category exists
    category = crud_category.get_category(db=db, category_id=product_in.category_id, business_id=business_id)
    if not category:
        raise HTTPException(status_code=400, detail="Invalid Category ID provided.")
        
    product = crud_product.create_product(db=db, product_in=product_in, business_id=business_id)
    return product

@router.get("/{product_id}", response_model=ProductResponse)
def read_product(
    product_id: int, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Get a specific product by ID.
    """
    business_id = None if (current_user.role and current_user.role.name == "Super Admin") else current_user.business_id
    product = crud_product.get_product(db=db, product_id=product_id, business_id=business_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product

@router.put("/{product_id}", response_model=ProductResponse)
def update_product(
    *,
    db: Session = Depends(get_db),
    product_id: int,
    product_in: ProductCreate,
    current_user: User = Depends(get_current_active_user)
):
    business_id = None if (current_user.role and current_user.role.name == "Super Admin") else current_user.business_id
    product = crud_product.get_product(db=db, product_id=product_id, business_id=business_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    product = crud_product.update_product(db=db, db_product=product, product_in=product_in)
    return product

@router.delete("/{product_id}")
def delete_product(
    *,
    db: Session = Depends(get_db),
    product_id: int,
    current_user: User = Depends(get_current_active_user)
):
    business_id = None if (current_user.role and current_user.role.name == "Super Admin") else current_user.business_id
    product = crud_product.get_product(db=db, product_id=product_id, business_id=business_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    crud_product.delete_product(db=db, db_product=product)
    return {"message": "Product deleted successfully"}

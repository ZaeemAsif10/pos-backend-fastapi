from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime, timezone

from app.db.database import get_db
from app.api.deps import get_current_active_user
from app.models.user import User

router = APIRouter()

class PurchaseItemCreate(BaseModel):
    product_id: int
    quantity: int
    unit_cost: float

class PurchaseCreate(BaseModel):
    supplier_name: str
    total_amount: float
    items: List[PurchaseItemCreate]

@router.get("/")
def get_purchases(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """
    Mock endpoint to retrieve purchases.
    To be fully implemented with DB models later.
    """
    return []

@router.post("/")
def create_purchase(
    *,
    db: Session = Depends(get_db),
    purchase_in: PurchaseCreate,
    current_user: User = Depends(get_current_active_user)
):
    """
    Mock endpoint to create a purchase (Inventory intake).
    In a full system, this would update Product Variant stocks.
    """
    # Find the default variant for each product and update its stock
    for item in purchase_in.items:
        from app.models.product import ProductVariant
        # We assume the first variant is the default one for this simplified POS
        variant = db.query(ProductVariant).filter(ProductVariant.product_id == item.product_id).first()
        if variant:
            variant.stock_quantity += item.quantity
        else:
            # If a product doesn't have a variant, we create one to hold stock
            new_variant = ProductVariant(
                product_id=item.product_id,
                size="Standard",
                color="Standard",
                sku=f"SKU-{item.product_id}-{int(datetime.now().timestamp())}",
                stock_quantity=item.quantity,
                price_adjustment=0
            )
            db.add(new_variant)
            
        # Also update the product's cost_price to reflect the latest purchase cost
        from app.models.product import Product
        product = db.query(Product).filter(Product.id == item.product_id).first()
        if product and item.unit_cost > 0:
            product.cost_price = item.unit_cost
            
    db.commit()

    return {
        "id": int(datetime.now().timestamp() % 100000),
        "supplier_name": purchase_in.supplier_name,
        "total_amount": purchase_in.total_amount,
        "status": "Completed",
        "created_at": datetime.now(timezone.utc).isoformat()
    }

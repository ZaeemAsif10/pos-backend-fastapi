from pydantic import BaseModel
from typing import List, Optional
from app.schemas.category import CategoryResponse
from app.schemas.brand import BrandResponse

# Shared properties
class ProductVariantBase(BaseModel):
    size: str
    color: str
    sku: str
    barcode: Optional[str] = None
    stock_quantity: int = 0
    price_adjustment: float = 0.0

class ProductBase(BaseModel):
    name: str
    description: Optional[str] = None
    image_url: Optional[str] = None
    base_price: float
    cost_price: float = 0.0
    category_id: Optional[int] = None
    brand_id: Optional[int] = None

# Properties to receive on item creation
class ProductVariantCreate(ProductVariantBase):
    pass

class ProductCreate(ProductBase):
    variants: List[ProductVariantCreate] = []

# Properties to return to client
class ProductVariantResponse(ProductVariantBase):
    id: int
    product_id: int

    class Config:
        from_attributes = True

class ProductResponse(ProductBase):
    id: int
    category: Optional[CategoryResponse] = None
    brand: Optional[BrandResponse] = None
    variants: List[ProductVariantResponse] = []

    class Config:
        from_attributes = True

from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field


# ==========================================
# CATEGORY SCHEMAS
# ==========================================
class CategoryBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=100, description="Category name")
    code: str = Field(..., min_length=2, max_length=30, description="Unique category code")
    parent_id: Optional[int] = Field(None, description="Parent category ID for sub-categories")
    description: Optional[str] = Field(None, description="Category description")
    is_active: bool = Field(default=True)


class CategoryCreate(CategoryBase):
    pass


class CategoryUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=100)
    code: Optional[str] = Field(None, min_length=2, max_length=30)
    parent_id: Optional[int] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


class CategoryResponse(CategoryBase):
    id: int
    tenant_id: int
    product_count: Optional[int] = 0
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ==========================================
# BRAND SCHEMAS
# ==========================================
class BrandBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=100, description="Brand name")
    code: str = Field(..., min_length=2, max_length=30, description="Unique brand code")
    origin: Optional[str] = Field(default="Pakistan", max_length=50)
    description: Optional[str] = None
    is_active: bool = Field(default=True)


class BrandCreate(BrandBase):
    pass


class BrandUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=100)
    code: Optional[str] = Field(None, min_length=2, max_length=30)
    origin: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


class BrandResponse(BrandBase):
    id: int
    tenant_id: int
    product_count: Optional[int] = 0
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ==========================================
# PRODUCT UOM CONVERSION SCHEMAS
# ==========================================
class ProductUOMConversionBase(BaseModel):
    unit_name: str = Field(..., min_length=1, max_length=50, description="Packaging unit name e.g. Carton, Box")
    conversion_factor: float = Field(..., gt=0, description="Number of base units e.g. 24")
    carton_barcode: Optional[str] = Field(None, max_length=100)
    carton_wholesale_price: Optional[float] = Field(None, ge=0)
    carton_retail_price: Optional[float] = Field(None, ge=0)


class ProductUOMConversionCreate(ProductUOMConversionBase):
    pass


class ProductUOMConversionResponse(ProductUOMConversionBase):
    id: int
    product_id: int
    created_at: datetime

    class Config:
        from_attributes = True


# ==========================================
# BRANCH STOCK SCHEMAS
# ==========================================
class BranchStockResponse(BaseModel):
    id: int
    branch_id: int
    branch_name: str
    branch_code: str
    branch_type: str
    quantity: float
    reserved_quantity: float
    reorder_point: Optional[int] = None
    updated_at: datetime

    class Config:
        from_attributes = True


class InitialStockItem(BaseModel):
    branch_id: int
    quantity: float = Field(default=0.0, ge=0)
    reorder_point: Optional[int] = None


# ==========================================
# PRODUCT SCHEMAS
# ==========================================
class ProductBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=150, description="Product title")
    sku: str = Field(..., min_length=2, max_length=50, description="Stock keeping unit")
    barcode: Optional[str] = Field(None, max_length=100, description="Barcode for scanning")
    category_id: int = Field(..., description="Category ID")
    brand_id: Optional[int] = Field(None, description="Brand ID")
    base_unit: str = Field(default="Piece", max_length=30, description="Base UOM e.g. Piece, Kg, Packet")
    cost_price: float = Field(default=0.0, ge=0, description="Purchase cost in PKR")
    retail_price: float = Field(default=0.0, ge=0, description="Retail MRP in PKR")
    wholesale_price: float = Field(default=0.0, ge=0, description="Wholesale price in PKR")
    min_price: Optional[float] = Field(None, ge=0, description="Minimum floor price threshold")
    tax_rate: float = Field(default=0.0, ge=0, le=100, description="Sales tax percentage")
    is_fbr_third_schedule: bool = Field(default=False)
    has_batches: bool = Field(default=False)
    reorder_level: int = Field(default=5, ge=0)
    image_url: Optional[str] = None
    description: Optional[str] = None
    is_active: bool = Field(default=True)


class ProductCreate(ProductBase):
    uom_conversions: Optional[List[ProductUOMConversionCreate]] = Field(default_factory=list)
    initial_stocks: Optional[List[InitialStockItem]] = Field(default_factory=list)


class ProductUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=150)
    sku: Optional[str] = Field(None, min_length=2, max_length=50)
    barcode: Optional[str] = None
    category_id: Optional[int] = None
    brand_id: Optional[int] = None
    base_unit: Optional[str] = None
    cost_price: Optional[float] = Field(None, ge=0)
    retail_price: Optional[float] = Field(None, ge=0)
    wholesale_price: Optional[float] = Field(None, ge=0)
    min_price: Optional[float] = None
    tax_rate: Optional[float] = Field(None, ge=0, le=100)
    is_fbr_third_schedule: Optional[bool] = None
    has_batches: Optional[bool] = None
    reorder_level: Optional[int] = Field(None, ge=0)
    image_url: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None
    uom_conversions: Optional[List[ProductUOMConversionCreate]] = None


class ProductListItem(BaseModel):
    id: int
    name: str
    sku: str
    barcode: Optional[str] = None
    category_id: int
    category_name: str
    brand_id: Optional[int] = None
    brand_name: Optional[str] = None
    base_unit: str
    cost_price: float
    retail_price: float
    wholesale_price: float
    tax_rate: float
    is_fbr_third_schedule: bool
    has_batches: bool
    reorder_level: int
    image_url: Optional[str] = None
    is_active: bool
    total_stock: float
    stock_status: str  # "in_stock", "low_stock", "out_of_stock"
    created_at: datetime

    class Config:
        from_attributes = True


class ProductDetailResponse(ProductBase):
    id: int
    tenant_id: int
    category_name: str
    brand_name: Optional[str] = None
    total_stock: float
    stock_status: str
    uom_conversions: List[ProductUOMConversionResponse] = []
    branch_stocks: List[BranchStockResponse] = []
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ProductStats(BaseModel):
    total_products: int
    total_inventory_value: float
    low_stock_count: int
    out_of_stock_count: int


class ProductListResponse(BaseModel):
    items: List[ProductListItem]
    total: int
    page: int
    size: int
    stats: ProductStats

from typing import Optional, List
from datetime import datetime, date
from pydantic import BaseModel, Field


# ==========================================
# PURCHASE ITEMS SCHEMAS
# ==========================================
class PurchaseItemBase(BaseModel):
    product_id: int = Field(..., description="Product ID")
    uom_conversion_id: Optional[int] = Field(None, description="Packaging conversion unit ID")
    unit_name: str = Field(default="Piece", max_length=50, description="e.g. Carton, Box, Piece")
    quantity: float = Field(..., gt=0, description="Quantity in selected unit")
    conversion_factor: float = Field(default=1.0, gt=0, description="Multiplier to base unit")
    unit_cost: float = Field(..., ge=0, description="Price per selected unit")
    batch_number: Optional[str] = Field(None, max_length=50)
    expiry_date: Optional[date] = None


class PurchaseItemCreate(PurchaseItemBase):
    pass


class PurchaseItemResponse(PurchaseItemBase):
    id: int
    purchase_id: int
    product_name: Optional[str] = None
    product_sku: Optional[str] = None
    total_base_quantity: float
    total_cost: float

    class Config:
        from_attributes = True


# ==========================================
# PURCHASE INVOICE SCHEMAS
# ==========================================
class PurchaseCreate(BaseModel):
    branch_id: int = Field(..., description="Receiving branch / warehouse ID")
    supplier_id: int = Field(..., description="Vendor ID")
    supplier_bill_no: Optional[str] = Field(None, max_length=50, description="Supplier's physical invoice #")
    purchase_date: Optional[date] = None
    discount_amount: float = Field(default=0.00, ge=0)
    tax_amount: float = Field(default=0.00, ge=0)
    shipping_cost: float = Field(default=0.00, ge=0)
    paid_amount: float = Field(default=0.00, ge=0, description="Cash/bank paid immediately")
    notes: Optional[str] = None
    items: List[PurchaseItemCreate] = Field(..., min_length=1, description="Purchase line items")


class PurchaseUpdate(BaseModel):
    notes: Optional[str] = None
    status: Optional[str] = None  # draft, received, cancelled, returned


class PurchaseReturnRequest(BaseModel):
    reason: Optional[str] = "Goods Returned to Supplier / Debit Note"
    refund_payment_method: Optional[str] = "cash"  # cash, bank, credit


class PurchaseResponse(BaseModel):
    id: int
    tenant_id: int
    invoice_number: str
    supplier_bill_no: Optional[str] = None
    purchase_date: date
    status: str
    payment_status: str
    branch_id: int
    branch_name: Optional[str] = None
    supplier_id: int
    supplier_name: Optional[str] = None
    items_count: int = 0
    subtotal: float
    discount_amount: float
    tax_amount: float
    shipping_cost: float
    total_amount: float
    paid_amount: float
    balance_due: float
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PurchaseDetailResponse(PurchaseResponse):
    items: List[PurchaseItemResponse] = []


class PurchaseStatsResponse(BaseModel):
    total_purchases_count: int = 0
    total_purchases_amount: float = 0.00
    total_unpaid_payables: float = 0.00
    monthly_purchases_amount: float = 0.00


# ==========================================
# LIVE INVENTORY & BIN CARD SCHEMAS
# ==========================================
class LiveInventoryItem(BaseModel):
    product_id: int
    product_name: str
    sku: str
    barcode: Optional[str] = None
    category_name: Optional[str] = None
    brand_name: Optional[str] = None
    base_unit: str
    branch_id: int
    branch_name: str
    current_stock: float
    reorder_point: float
    cost_price: float
    retail_price: float
    stock_status: str  # "In Stock", "Low Stock", "Out of Stock"


class StockMovementResponse(BaseModel):
    id: int
    branch_id: int
    branch_name: Optional[str] = None
    product_id: int
    product_name: Optional[str] = None
    movement_type: str
    quantity: float
    balance_after: float
    unit_cost: float
    reference_type: str
    reference_id: int
    notes: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


# ==========================================
# STOCK TRANSFER SCHEMAS
# ==========================================
class StockTransferItemCreate(BaseModel):
    product_id: int
    quantity: float = Field(..., gt=0)


class StockTransferCreate(BaseModel):
    from_branch_id: int = Field(..., description="Source branch / warehouse")
    to_branch_id: int = Field(..., description="Destination branch / store")
    transfer_date: Optional[date] = None
    notes: Optional[str] = None
    items: List[StockTransferItemCreate] = Field(..., min_length=1)


class StockTransferResponse(BaseModel):
    id: int
    tenant_id: int
    transfer_number: str
    from_branch_id: int
    from_branch_name: Optional[str] = None
    to_branch_id: int
    to_branch_name: Optional[str] = None
    transfer_date: date
    status: str
    items_count: int = 0
    notes: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


# ==========================================
# STOCK ADJUSTMENT SCHEMAS
# ==========================================
class StockAdjustmentItemCreate(BaseModel):
    product_id: int
    adjustment_type: str = Field(default="SUBTRACT", description="ADD or SUBTRACT")
    quantity: float = Field(..., gt=0)


class StockAdjustmentCreate(BaseModel):
    branch_id: int
    reason: str = Field(default="damage", description="damage, expiry, audit_correction, sample")
    adjustment_date: Optional[date] = None
    notes: Optional[str] = None
    items: List[StockAdjustmentItemCreate] = Field(..., min_length=1)


class StockAdjustmentResponse(BaseModel):
    id: int
    tenant_id: int
    adjustment_number: str
    branch_id: int
    branch_name: Optional[str] = None
    reason: str
    adjustment_date: date
    items_count: int = 0
    notes: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True

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
    unit_cost: float = Field(..., ge=0, description="Purchase price per selected unit")
    retail_price: float = Field(default=0.0, ge=0, description="Sale / Retail price per selected unit")
    tax_rate: float = Field(default=0.0, ge=0, le=100, description="Tax percentage on this item")
    tax_amount: float = Field(default=0.0, ge=0, description="Calculated tax amount for this row")
    batch_number: Optional[str] = Field(None, max_length=50)
    expiry_date: Optional[date] = None


class PurchaseItemCreate(PurchaseItemBase):
    pass


class PurchaseItemResponse(PurchaseItemBase):
    id: int
    purchase_id: int
    product_name: Optional[str] = None
    product_sku: Optional[str] = None
    returned_quantity: float = 0.0
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
    payment_status: Optional[str] = Field(default="unpaid", max_length=50, description="Selected payment status code (e.g. paid, unpaid)")
    discount_amount: float = Field(default=0.00, ge=0)
    tax_amount: float = Field(default=0.00, ge=0)
    shipping_cost: float = Field(default=0.00, ge=0)
    paid_amount: float = Field(default=0.00, ge=0, description="Cash/bank paid immediately")
    paid_from_account_id: Optional[int] = Field(None, description="Chart of Accounts ID from which payment was made")
    notes: Optional[str] = None
    items: List[PurchaseItemCreate] = Field(..., min_length=1, description="Purchase line items")


class PurchaseUpdate(BaseModel):
    payment_status: Optional[str] = Field(None, max_length=50, description="Updated payment status code (e.g. paid, unpaid)")
    paid_amount: Optional[float] = Field(None, ge=0)
    paid_from_account_id: Optional[int] = Field(None, description="Chart of Accounts ID from which payment was made")
    supplier_bill_no: Optional[str] = Field(None, max_length=50)
    notes: Optional[str] = None
    status: Optional[str] = None  # draft, received, cancelled, returned


class PurchaseReturnItemInput(BaseModel):
    purchase_item_id: Optional[int] = Field(None, description="Original purchase_items.id if returning from an invoice")
    product_id: int = Field(..., description="Product ID being returned")
    unit_name: str = Field(default="Piece", max_length=50)
    quantity: float = Field(..., gt=0, description="Quantity being returned")
    conversion_factor: float = Field(default=1.0, gt=0)
    unit_cost: float = Field(..., ge=0, description="Return rate per unit")


class PurchaseReturnRequest(BaseModel):
    reason: Optional[str] = "Goods Returned to Supplier / Debit Note"
    refund_payment_method: Optional[str] = "credit"  # credit, cash, bank
    refund_account_id: Optional[int] = Field(None, description="Cash / Bank account ID if refund received in cash/bank")
    notes: Optional[str] = None
    items: Optional[List[PurchaseReturnItemInput]] = Field(None, description="Partial or full item quantities to return")


class StandalonePurchaseReturnCreate(BaseModel):
    branch_id: int = Field(..., description="Warehouse / Branch from which stock is being returned")
    supplier_id: int = Field(..., description="Supplier / Vendor to whom stock is returned")
    purchase_id: Optional[int] = Field(None, description="Optional linked purchase invoice ID")
    return_date: Optional[date] = None
    refund_method: str = Field(default="credit", description="credit (reduce Supplier Khata payable), cash, or bank")
    refund_account_id: Optional[int] = Field(None, description="Cash / Bank account ID if cash/bank refund received")
    reason: Optional[str] = "Damaged / Excess Goods Returned to Supplier"
    notes: Optional[str] = None
    items: List[PurchaseReturnItemInput] = Field(..., min_length=1)


class PurchaseReturnItemResponse(BaseModel):
    id: int
    purchase_return_id: int
    purchase_item_id: Optional[int] = None
    product_id: int
    product_name: Optional[str] = None
    product_sku: Optional[str] = None
    unit_name: str
    quantity: float
    conversion_factor: float
    total_base_quantity: float
    unit_cost: float
    total_cost: float

    class Config:
        from_attributes = True


class PurchaseReturnResponse(BaseModel):
    id: int
    tenant_id: int
    purchase_id: Optional[int] = None
    purchase_invoice_number: Optional[str] = None
    branch_id: int
    branch_name: Optional[str] = None
    supplier_id: int
    supplier_name: Optional[str] = None
    return_number: str
    return_date: date
    total_qty: float
    total_amount: float
    refund_method: str
    refund_account_id: Optional[int] = None
    refund_account_name: Optional[str] = None
    refund_account_code: Optional[str] = None
    journal_entry_number: Optional[str] = None
    reason: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime
    items: List[PurchaseReturnItemResponse] = []

    class Config:
        from_attributes = True


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
    total_qty: float = 0.0
    returned_qty: float = 0.0
    returned_amount: float = 0.0
    subtotal: float
    discount_amount: float
    tax_amount: float
    shipping_cost: float
    total_amount: float
    paid_amount: float
    balance_due: float
    paid_from_account_id: Optional[int] = None
    paid_from_account_name: Optional[str] = None
    paid_from_account_code: Optional[str] = None
    journal_entry_number: Optional[str] = None
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
    category_id: Optional[int] = None
    category_name: Optional[str] = None
    brand_id: Optional[int] = None
    brand_name: Optional[str] = None
    base_unit: str
    branch_id: int
    branch_name: str
    current_stock: float
    reorder_point: float
    cost_price: float
    retail_price: float
    wholesale_price: float = 0.0
    tax_rate: float = 0.0
    is_fbr_third_schedule: bool = False
    image_url: Optional[str] = None
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


# ==========================================
# PAYMENT STATUS OPTIONS SCHEMAS (CRUD)
# ==========================================
class PaymentStatusOptionCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=50, description="Display label e.g. Paid, Unpaid")
    code: Optional[str] = Field(None, max_length=50, description="Unique slug e.g. paid, unpaid")
    accounting_type: str = Field(default="unpaid", description="'paid' (Cash/Bank), 'unpaid' (Accounts Payable), or 'partial'")
    color: str = Field(default="emerald", max_length=20)
    description: Optional[str] = Field(None, max_length=255)
    is_active: bool = True


class PaymentStatusOptionUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=50)
    accounting_type: Optional[str] = None
    color: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


class PaymentStatusOptionResponse(BaseModel):
    id: int
    tenant_id: int
    name: str
    code: str
    accounting_type: str
    color: str
    description: Optional[str] = None
    is_system: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


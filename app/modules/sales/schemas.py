from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


# ================= POS Shift / Cash Drawer Schemas =================
class POSShiftOpenRequest(BaseModel):
    branch_id: int
    opening_cash: float = Field(default=0.0, ge=0.0)
    notes: Optional[str] = None


class POSShiftCloseRequest(BaseModel):
    closing_cash: float = Field(..., ge=0.0)
    notes: Optional[str] = None


class POSShiftResponse(BaseModel):
    id: int
    tenant_id: int
    branch_id: int
    cashier_id: int
    cashier_name: Optional[str] = None
    branch_name: Optional[str] = None
    opened_at: datetime
    closed_at: Optional[datetime] = None
    opening_cash: float
    closing_cash: Optional[float] = None
    expected_cash: Optional[float] = None
    cash_difference: Optional[float] = None
    status: str
    notes: Optional[str] = None

    class Config:
        from_attributes = True


# ================= Sales Invoice Item Schemas =================
class SalesInvoiceItemCreate(BaseModel):
    product_id: int
    uom_id: Optional[int] = None
    quantity: float = Field(..., gt=0)
    unit_price: float = Field(..., ge=0.0)
    discount_amount: float = Field(default=0.0, ge=0.0)
    tax_rate: float = Field(default=0.0, ge=0.0)


class SalesInvoiceItemResponse(BaseModel):
    id: int
    product_id: int
    product_name: Optional[str] = None
    sku: Optional[str] = None
    barcode: Optional[str] = None
    uom_id: Optional[int] = None
    uom_name: str
    quantity: float
    unit_price: float
    cost_price: float
    discount_amount: float
    tax_rate: float
    tax_amount: float
    pct_code: Optional[str] = None
    total_amount: float

    class Config:
        from_attributes = True


# ================= Sales Payment Schemas =================
class SalesPaymentCreate(BaseModel):
    payment_method: str = Field(default="cash")  # cash, card, bank_transfer, credit, cheque
    amount: float = Field(..., gt=0.0)
    reference_no: Optional[str] = None


class SalesPaymentResponse(BaseModel):
    id: int
    payment_method: str
    amount: float
    reference_no: Optional[str] = None
    payment_date: datetime

    class Config:
        from_attributes = True


# ================= Sales Checkout & Invoice Schemas =================
class SalesCheckoutRequest(BaseModel):
    branch_id: int
    customer_id: Optional[int] = None
    customer_name: Optional[str] = "Walk-in Retail Buyer"
    customer_phone: Optional[str] = None
    customer_ntn_cnic: Optional[str] = None
    sale_type: str = Field(default="pos_retail")  # pos_retail, wholesale_invoice
    pos_shift_id: Optional[int] = None

    discount_amount: float = Field(default=0.0, ge=0.0)
    paid_amount: float = Field(default=0.0, ge=0.0)
    payment_method: str = Field(default="cash")  # cash, card, split, credit
    payments: Optional[List[SalesPaymentCreate]] = None
    notes: Optional[str] = None

    items: List[SalesInvoiceItemCreate] = Field(..., min_length=1)


class SalesRefundRequest(BaseModel):
    reason: Optional[str] = "Customer Return / Credit Note"



class SalesInvoiceResponse(BaseModel):
    id: int
    tenant_id: int
    branch_id: int
    branch_name: Optional[str] = None
    customer_id: Optional[int] = None
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    customer_ntn_cnic: Optional[str] = None

    invoice_number: str
    sale_type: str
    invoice_date: datetime

    payment_method: str
    payment_status: str

    subtotal: float
    discount_amount: float
    tax_amount: float
    total_amount: float
    paid_amount: float
    change_amount: float
    balance_due: float

    # FBR Fiscal Fields
    fbr_pos_id: Optional[str] = None
    fbr_invoice_number: Optional[str] = None
    fbr_qr_code: Optional[str] = None
    fbr_status: str
    fbr_response_message: Optional[str] = None
    fbr_synced_at: Optional[datetime] = None

    status: str
    notes: Optional[str] = None
    cashier_name: Optional[str] = None

    items: List[SalesInvoiceItemResponse] = Field(default_factory=list)
    payments: List[SalesPaymentResponse] = Field(default_factory=list)

    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class SalesSummaryStats(BaseModel):
    today_sales: float
    today_invoices_count: int
    today_cash_collected: float
    pending_fbr_sync_count: int


class PaginatedSalesInvoiceResponse(BaseModel):
    items: List[SalesInvoiceResponse]
    total: int
    page: int
    size: int
    total_pages: int

    class Config:
        from_attributes = True


# ==========================================
# DAY BOOK (ROZNAMCHA / CASH BOOK) SCHEMAS
# ==========================================
class DayBookEntry(BaseModel):
    id: str
    entry_type: str  # "sale", "customer_payment", "supplier_payment"
    timestamp: datetime
    voucher_no: str
    party_name: str
    payment_method: str
    cash_in: float
    cash_out: float
    running_balance: float
    user_name: Optional[str] = None
    branch_name: Optional[str] = None
    notes: Optional[str] = None


class DayBookSummary(BaseModel):
    opening_cash: float
    total_cash_in: float
    total_cash_out: float
    closing_cash: float
    cash_sales: float
    customer_wasooli: float
    supplier_payments: float
    cash_expenses: float = 0.0
    non_cash_inflow: float
    total_turnover: float
    total_entries_count: int


class DayBookPaymentMethodsSummary(BaseModel):
    cash: float
    bank_transfer: float
    card: float
    raast: float
    cheque: float
    other: float


class DayBookResponse(BaseModel):
    date: str
    branch_id: Optional[int] = None
    branch_name: Optional[str] = None
    summary: DayBookSummary
    payment_methods: DayBookPaymentMethodsSummary
    entries: List[DayBookEntry]


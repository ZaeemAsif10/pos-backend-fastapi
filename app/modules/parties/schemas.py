from typing import Optional, List
from datetime import datetime, date
from decimal import Decimal
from pydantic import BaseModel, Field


# ==========================================
# DELIVERY AREA SCHEMAS
# ==========================================
class DeliveryAreaBase(BaseModel):
    code: str = Field(..., min_length=2, max_length=30, description="Route or beat code e.g. R-01")
    name: str = Field(..., min_length=2, max_length=100, description="Route/Area name e.g. Shah Alam Market")
    city: str = Field(default="Lahore", max_length=50)
    description: Optional[str] = None
    delivery_days: Optional[str] = Field(None, max_length=100, description="e.g. Mon, Wed, Fri")
    assigned_salesman_id: Optional[int] = Field(None, description="Assigned salesman user ID")
    is_active: bool = Field(default=True)


class DeliveryAreaCreate(DeliveryAreaBase):
    pass


class DeliveryAreaUpdate(BaseModel):
    code: Optional[str] = Field(None, min_length=2, max_length=30)
    name: Optional[str] = Field(None, min_length=2, max_length=100)
    city: Optional[str] = Field(None, max_length=50)
    description: Optional[str] = None
    delivery_days: Optional[str] = Field(None, max_length=100)
    assigned_salesman_id: Optional[int] = None
    is_active: Optional[bool] = None


class DeliveryAreaResponse(DeliveryAreaBase):
    id: int
    tenant_id: int
    assigned_salesman_name: Optional[str] = None
    customer_count: Optional[int] = 0
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ==========================================
# CUSTOMER SCHEMAS
# ==========================================
class CustomerBase(BaseModel):
    code: str = Field(..., min_length=2, max_length=30, description="Customer account code e.g. CUST-001")
    business_name: str = Field(..., min_length=2, max_length=150, description="Shop or company name")
    owner_name: Optional[str] = Field(None, max_length=100, description="Proprietor / Contact name")
    phone: str = Field(..., min_length=7, max_length=30, description="Contact number")
    whatsapp_number: Optional[str] = Field(None, max_length=30)
    email: Optional[str] = Field(None, max_length=100)
    cnic: Optional[str] = Field(None, max_length=25, description="13-digit CNIC")
    ntn: Optional[str] = Field(None, max_length=30)
    strn: Optional[str] = Field(None, max_length=30)
    customer_type: str = Field(default="retailer", max_length=30, description="retailer, wholesaler, corporate")
    
    credit_limit: float = Field(default=0.00, ge=0, description="Maximum udhaar allowed")
    credit_days: int = Field(default=0, ge=0, description="Payment credit period in days")
    opening_balance: float = Field(default=0.00, description="Opening balance (+ for receivable, - for payable)")
    
    area_id: Optional[int] = Field(None, description="Delivery route / beat ID")
    branch_id: Optional[int] = Field(None, description="Assigned branch / store ID")
    city: str = Field(default="Lahore", max_length=50)
    address: Optional[str] = None
    kyc_status: str = Field(default="verified", max_length=20, description="pending, verified, rejected")
    is_active: bool = Field(default=True)


class CustomerCreate(CustomerBase):
    pass


class CustomerUpdate(BaseModel):
    code: Optional[str] = Field(None, min_length=2, max_length=30)
    business_name: Optional[str] = Field(None, min_length=2, max_length=150)
    owner_name: Optional[str] = Field(None, max_length=100)
    phone: Optional[str] = Field(None, min_length=7, max_length=30)
    whatsapp_number: Optional[str] = None
    email: Optional[str] = None
    cnic: Optional[str] = None
    ntn: Optional[str] = None
    strn: Optional[str] = None
    customer_type: Optional[str] = None
    credit_limit: Optional[float] = Field(None, ge=0)
    credit_days: Optional[int] = Field(None, ge=0)
    opening_balance: Optional[float] = None
    is_credit_blocked: Optional[bool] = None
    area_id: Optional[int] = None
    branch_id: Optional[int] = None
    city: Optional[str] = None
    address: Optional[str] = None
    kyc_status: Optional[str] = None
    is_active: Optional[bool] = None


class CustomerResponse(CustomerBase):
    id: int
    tenant_id: int
    current_balance: float = 0.00
    is_credit_blocked: bool = False
    area_name: Optional[str] = None
    branch_name: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class CustomerStatsResponse(BaseModel):
    total_customers: int = 0
    total_receivables: float = 0.00
    overdue_accounts: int = 0
    credit_blocked_count: int = 0


# ==========================================
# SUPPLIER SCHEMAS
# ==========================================
class SupplierBase(BaseModel):
    code: str = Field(..., min_length=2, max_length=30, description="Supplier code e.g. SUP-001")
    company_name: str = Field(..., min_length=2, max_length=150, description="Company / Mill name")
    contact_person: Optional[str] = Field(None, max_length=100)
    phone: str = Field(..., min_length=7, max_length=30)
    email: Optional[str] = Field(None, max_length=100)
    ntn: Optional[str] = Field(None, max_length=30)
    strn: Optional[str] = Field(None, max_length=30)
    
    payment_terms_days: int = Field(default=30, ge=0, description="Agreed payment terms in days")
    opening_balance: float = Field(default=0.00, description="Initial balance owed to supplier")
    
    bank_name: Optional[str] = Field(None, max_length=100)
    bank_account_number: Optional[str] = Field(None, max_length=50)
    bank_iban: Optional[str] = Field(None, max_length=40)
    bank_branch: Optional[str] = Field(None, max_length=100)
    
    city: str = Field(default="Lahore", max_length=50)
    address: Optional[str] = None
    is_active: bool = Field(default=True)


class SupplierCreate(SupplierBase):
    pass


class SupplierUpdate(BaseModel):
    code: Optional[str] = Field(None, min_length=2, max_length=30)
    company_name: Optional[str] = Field(None, min_length=2, max_length=150)
    contact_person: Optional[str] = None
    phone: Optional[str] = Field(None, min_length=7, max_length=30)
    email: Optional[str] = None
    ntn: Optional[str] = None
    strn: Optional[str] = None
    payment_terms_days: Optional[int] = Field(None, ge=0)
    opening_balance: Optional[float] = None
    bank_name: Optional[str] = None
    bank_account_number: Optional[str] = None
    bank_iban: Optional[str] = None
    bank_branch: Optional[str] = None
    city: Optional[str] = None
    address: Optional[str] = None
    is_active: Optional[bool] = None


class SupplierResponse(SupplierBase):
    id: int
    tenant_id: int
    current_balance: float = 0.00
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class SupplierStatsResponse(BaseModel):
    total_suppliers: int = 0
    total_payables: float = 0.00
    active_mills: int = 0
    bank_accounts_count: int = 0


class PaginatedCustomersResponse(BaseModel):
    items: List[CustomerResponse]
    total: int
    page: int
    size: int
    total_pages: int

    class Config:
        from_attributes = True


class PaginatedSuppliersResponse(BaseModel):
    items: List[SupplierResponse]
    total: int
    page: int
    size: int
    total_pages: int

    class Config:
        from_attributes = True


# ==========================================
# CUSTOMER PAYMENT (KHATA WASOOLI) SCHEMAS
# ==========================================
class CustomerPaymentCreate(BaseModel):
    amount: float = Field(..., gt=0, description="Amount received against khata")
    payment_method: str = Field(default="cash", description="cash, bank_transfer, cheque, raast, easypaisa")
    branch_id: Optional[int] = None
    reference_number: Optional[str] = Field(None, max_length=100, description="Cheque/Txn reference")
    notes: Optional[str] = None


class CustomerPaymentResponse(BaseModel):
    id: int
    tenant_id: int
    customer_id: int
    branch_id: Optional[int] = None
    voucher_number: str
    amount: float
    payment_method: str
    reference_number: Optional[str] = None
    notes: Optional[str] = None
    previous_balance: float
    new_balance: float
    received_by_id: Optional[int] = None
    received_by_name: Optional[str] = None
    customer_business_name: Optional[str] = None
    customer_phone: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PaginatedCustomerPaymentsResponse(BaseModel):
    items: List[CustomerPaymentResponse]
    total: int
    page: int
    size: int
    total_pages: int

    class Config:
        from_attributes = True


# ==========================================
# CUSTOMER LEDGER STATEMENT SCHEMAS
# ==========================================
class CustomerLedgerEntry(BaseModel):
    id: int
    entry_type: str  # "opening_balance", "invoice", "payment"
    date: datetime
    reference: str
    description: str
    debit: float
    credit: float
    balance: float
    payment_method: Optional[str] = None
    notes: Optional[str] = None


class CustomerLedgerSummary(BaseModel):
    opening_balance: float
    total_debit: float
    total_credit: float
    closing_balance: float
    credit_limit: float
    is_credit_blocked: bool


class CustomerLedgerResponse(BaseModel):
    customer_id: int
    customer_name: str
    customer_code: str
    customer_phone: Optional[str] = None
    from_date: Optional[datetime] = None
    to_date: Optional[datetime] = None
    summary: CustomerLedgerSummary
    entries: List[CustomerLedgerEntry]


# ==========================================
# SUPPLIER PAYMENT (CPV) SCHEMAS
# ==========================================
class SupplierPaymentCreate(BaseModel):
    amount: float = Field(..., gt=0, description="Amount paid to vendor/mill")
    payment_method: str = Field(default="cash", description="cash, bank_transfer, cheque, raast")
    branch_id: Optional[int] = None
    reference_number: Optional[str] = Field(None, max_length=100, description="Cheque/Txn reference")
    notes: Optional[str] = None


class SupplierPaymentResponse(BaseModel):
    id: int
    tenant_id: int
    supplier_id: int
    branch_id: Optional[int] = None
    voucher_number: str
    amount: float
    payment_method: str
    reference_number: Optional[str] = None
    notes: Optional[str] = None
    previous_balance: float
    new_balance: float
    paid_by_id: Optional[int] = None
    paid_by_name: Optional[str] = None
    supplier_company_name: Optional[str] = None
    supplier_phone: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PaginatedSupplierPaymentsResponse(BaseModel):
    items: List[SupplierPaymentResponse]
    total: int
    page: int
    size: int
    total_pages: int

    class Config:
        from_attributes = True


# ==========================================
# SUPPLIER LEDGER STATEMENT SCHEMAS
# ==========================================
class SupplierLedgerEntry(BaseModel):
    id: int
    entry_type: str  # "purchase", "payment"
    date: datetime
    reference: str
    description: str
    debit: float   # Paid to supplier (reduces payable)
    credit: float  # Purchase / Bill added (increases payable)
    balance: float # Running payable balance after entry
    payment_method: Optional[str] = None
    notes: Optional[str] = None


class SupplierLedgerSummary(BaseModel):
    opening_balance: float
    total_purchases: float
    total_paid: float
    closing_balance: float
    payment_terms_days: int


class SupplierLedgerResponse(BaseModel):
    supplier_id: int
    supplier_name: str
    supplier_code: str
    supplier_phone: Optional[str] = None
    from_date: Optional[datetime] = None
    to_date: Optional[datetime] = None
    summary: SupplierLedgerSummary
    entries: List[SupplierLedgerEntry]


# ==========================================
# KHATA & AGING ANALYSIS (AR / AP) SCHEMAS
# ==========================================
class AgingBucketBreakdown(BaseModel):
    current: float = Field(0.0, description="0 - 30 days")
    days_31_60: float = Field(0.0, description="31 - 60 days overdue")
    days_61_90: float = Field(0.0, description="61 - 90 days overdue")
    days_91_120: float = Field(0.0, description="91 - 120 days overdue")
    over_120: float = Field(0.0, description="> 120 days overdue (High risk)")
    total: float = Field(0.0, description="Total outstanding across all buckets")


class CustomerAgingItem(BaseModel):
    customer_id: int
    code: str
    business_name: str
    owner_name: Optional[str] = None
    phone: str
    whatsapp_number: Optional[str] = None
    area_name: Optional[str] = None
    credit_limit: float = 0.0
    credit_days: int = 0
    is_credit_blocked: bool = False
    current_balance: float = 0.0
    total_receivable: float = 0.0
    aging: AgingBucketBreakdown
    overdue_amount: float = 0.0
    oldest_unpaid_days: int = 0
    last_payment_date: Optional[datetime] = None
    last_payment_amount: Optional[float] = None


class CustomerAgingSummaryKPI(BaseModel):
    total_receivables: float = 0.0
    total_current: float = 0.0
    total_overdue: float = 0.0
    total_overdue_30_plus: float = 0.0
    total_overdue_60_plus: float = 0.0
    total_overdue_90_plus: float = 0.0
    days_sales_outstanding: float = 0.0
    total_customers_count: int = 0
    overdue_customers_count: int = 0
    high_risk_customers_count: int = 0


class CustomerAgingReportResponse(BaseModel):
    as_of_date: date
    branch_id: Optional[int] = None
    summary: CustomerAgingSummaryKPI
    customers: List[CustomerAgingItem]


class SupplierAgingItem(BaseModel):
    supplier_id: int
    code: str
    company_name: str
    contact_person: Optional[str] = None
    phone: str
    payment_terms_days: int = 30
    current_balance: float = 0.0
    total_payable: float = 0.0
    aging: AgingBucketBreakdown
    overdue_amount: float = 0.0
    oldest_unpaid_days: int = 0
    last_payment_date: Optional[datetime] = None
    last_payment_amount: Optional[float] = None


class SupplierAgingSummaryKPI(BaseModel):
    total_payables: float = 0.0
    total_current: float = 0.0
    total_overdue: float = 0.0
    days_payable_outstanding: float = 0.0
    total_suppliers_count: int = 0
    overdue_suppliers_count: int = 0


class SupplierAgingReportResponse(BaseModel):
    as_of_date: date
    branch_id: Optional[int] = None
    summary: SupplierAgingSummaryKPI
    suppliers: List[SupplierAgingItem]




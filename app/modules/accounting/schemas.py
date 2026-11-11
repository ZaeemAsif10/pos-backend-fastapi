from datetime import datetime, date
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


# ================= Chart of Accounts (COA) Schemas =================
class AccountCreate(BaseModel):
    code: str = Field(..., min_length=2, max_length=50, description="Unique account code (e.g. 1010)")
    name: str = Field(..., min_length=2, max_length=255, description="Account name")
    account_type: str = Field(..., description="asset, liability, equity, revenue, expense")
    sub_type: Optional[str] = Field(None, description="cash, bank, receivable, payable, cogs, operating_expense, tax, equity, etc.")
    parent_id: Optional[int] = Field(None, description="Parent account ID for hierarchy")
    currency: str = Field(default="PKR", max_length=10)
    description: Optional[str] = None


class AccountUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=255)
    account_type: Optional[str] = None
    sub_type: Optional[str] = None
    parent_id: Optional[int] = None
    currency: Optional[str] = None
    is_active: Optional[bool] = None
    description: Optional[str] = None


class AccountItem(BaseModel):
    id: int
    tenant_id: int
    code: str
    name: str
    account_type: str
    sub_type: Optional[str] = None
    parent_id: Optional[int] = None
    parent_name: Optional[str] = None
    currency: str
    is_system: bool
    is_active: bool
    description: Optional[str] = None
    current_balance: float = 0.0
    created_at: datetime

    class Config:
        from_attributes = True


class AccountTreeNode(BaseModel):
    id: int
    code: str
    name: str
    account_type: str
    sub_type: Optional[str] = None
    parent_id: Optional[int] = None
    currency: str
    is_system: bool
    is_active: bool
    current_balance: float = 0.0
    children: List["AccountTreeNode"] = []


# ================= Account Mapping & Settings (The 1 Screen) =================
class TenantAccountingSettingsUpdate(BaseModel):
    base_currency: Optional[str] = Field(None, max_length=10)
    financial_year_start_month: Optional[int] = Field(None, ge=1, le=12)
    default_sales_income_account_id: Optional[int] = None
    default_ar_account_id: Optional[int] = None
    default_ap_account_id: Optional[int] = None
    default_cash_account_id: Optional[int] = None
    default_bank_account_id: Optional[int] = None
    default_sales_tax_account_id: Optional[int] = None
    default_discount_account_id: Optional[int] = None
    default_cogs_account_id: Optional[int] = None
    default_inventory_asset_account_id: Optional[int] = None
    payment_method_mappings: Optional[Dict[str, Optional[int]]] = None
    auto_posting_enabled: Optional[bool] = None


class AccountBrief(BaseModel):
    id: int
    code: str
    name: str
    account_type: str

    class Config:
        from_attributes = True


class TenantAccountingSettingsResponse(BaseModel):
    id: int
    tenant_id: int
    base_currency: str
    financial_year_start_month: int
    auto_posting_enabled: bool

    default_sales_income_account_id: Optional[int] = None
    default_sales_income_account: Optional[AccountBrief] = None

    default_ar_account_id: Optional[int] = None
    default_ar_account: Optional[AccountBrief] = None

    default_ap_account_id: Optional[int] = None
    default_ap_account: Optional[AccountBrief] = None

    default_cash_account_id: Optional[int] = None
    default_cash_account: Optional[AccountBrief] = None

    default_bank_account_id: Optional[int] = None
    default_bank_account: Optional[AccountBrief] = None

    default_sales_tax_account_id: Optional[int] = None
    default_sales_tax_account: Optional[AccountBrief] = None

    default_discount_account_id: Optional[int] = None
    default_discount_account: Optional[AccountBrief] = None

    default_cogs_account_id: Optional[int] = None
    default_cogs_account: Optional[AccountBrief] = None

    default_inventory_asset_account_id: Optional[int] = None
    default_inventory_asset_account: Optional[AccountBrief] = None

    payment_method_mappings: Dict[str, Any] = {}
    updated_at: datetime

    class Config:
        from_attributes = True


# ================= General Journal Entry (JV) Schemas =================
class JournalEntryLineCreate(BaseModel):
    account_id: int
    branch_id: Optional[int] = None
    debit: float = Field(default=0.0, ge=0.0)
    credit: float = Field(default=0.0, ge=0.0)
    foreign_amount: Optional[float] = None
    foreign_currency: Optional[str] = None
    narration: Optional[str] = None
    customer_id: Optional[int] = None
    supplier_id: Optional[int] = None


class JournalEntryCreate(BaseModel):
    branch_id: Optional[int] = None
    entry_date: Optional[datetime] = None
    reference_no: Optional[str] = None
    narration: Optional[str] = None
    currency: str = Field(default="PKR", max_length=10)
    exchange_rate: float = Field(default=1.0, gt=0.0)
    lines: List[JournalEntryLineCreate] = Field(..., min_length=2)


class JournalEntryLineItem(BaseModel):
    id: int
    account_id: int
    account_code: Optional[str] = None
    account_name: Optional[str] = None
    branch_id: Optional[int] = None
    branch_name: Optional[str] = None
    debit: float
    credit: float
    foreign_amount: Optional[float] = None
    foreign_currency: Optional[str] = None
    narration: Optional[str] = None
    customer_id: Optional[int] = None
    customer_name: Optional[str] = None
    supplier_id: Optional[int] = None
    supplier_name: Optional[str] = None

    class Config:
        from_attributes = True


class JournalEntryItem(BaseModel):
    id: int
    tenant_id: int
    branch_id: Optional[int] = None
    branch_name: Optional[str] = None
    entry_number: str
    entry_date: datetime
    source_type: str
    source_id: Optional[int] = None
    reference_no: Optional[str] = None
    narration: Optional[str] = None
    currency: str
    exchange_rate: float
    status: str
    total_debit: float
    total_credit: float
    created_by_id: Optional[int] = None
    created_by_name: Optional[str] = None
    created_at: datetime
    lines: List[JournalEntryLineItem] = []

    class Config:
        from_attributes = True


class PaginatedJournalEntriesResponse(BaseModel):
    items: List[JournalEntryItem]
    total: int
    page: int
    page_size: int
    pages: int


# ================= Financial Statements & Ledger Schemas =================
class GeneralLedgerLine(BaseModel):
    id: int
    entry_date: datetime
    entry_number: str
    source_type: str
    reference_no: Optional[str] = None
    narration: Optional[str] = None
    branch_name: Optional[str] = None
    debit: float
    credit: float
    running_balance: float


class GeneralLedgerAccountReport(BaseModel):
    account_id: int
    account_code: str
    account_name: str
    account_type: str
    sub_type: Optional[str] = None
    currency: str
    opening_balance: float
    total_debit: float
    total_credit: float
    closing_balance: float
    lines: List[GeneralLedgerLine]


class TrialBalanceItem(BaseModel):
    account_id: int
    account_code: str
    account_name: str
    account_type: str
    sub_type: Optional[str] = None
    debit_balance: float
    credit_balance: float


class TrialBalanceResponse(BaseModel):
    as_of_date: str
    branch_id: Optional[int] = None
    branch_name: Optional[str] = None
    items: List[TrialBalanceItem]
    total_debits: float
    total_credits: float
    is_balanced: bool


# ================= Direct Expense Voucher Schemas =================
class ExpenseVoucherCreate(BaseModel):
    branch_id: Optional[int] = Field(None, description="Branch ID (optional)")
    expense_account_id: int = Field(..., description="Operating Expense COA Account ID (e.g. 6010-6090)")
    paid_from_account_id: Optional[int] = Field(None, description="Cash or Bank Account ID. Defaults to default cash account")
    amount: float = Field(..., gt=0, description="Expense amount in PKR")
    payment_method: str = Field(default="cash", description="cash, bank_transfer, card, cheque, raast, etc.")
    payee_name: str = Field(..., min_length=2, max_length=255, description="Who was paid (e.g. LESCO, Landlord, Chai Wala, Staff)")
    expense_date: Optional[datetime] = Field(None, description="Date & time of expense")
    reference_no: Optional[str] = Field(None, max_length=100, description="Bill/Receipt # or Cheque #")
    narration: Optional[str] = Field(None, description="Description or note")
    attachment_url: Optional[str] = None


class ExpenseVoucherItem(BaseModel):
    id: int
    tenant_id: int
    branch_id: Optional[int] = None
    branch_name: Optional[str] = None
    voucher_number: str
    expense_date: datetime
    expense_account_id: int
    expense_account_code: str
    expense_account_name: str
    paid_from_account_id: int
    paid_from_account_code: str
    paid_from_account_name: str
    amount: float
    payment_method: str
    payee_name: str
    reference_no: Optional[str] = None
    narration: Optional[str] = None
    attachment_url: Optional[str] = None
    status: str
    journal_entry_id: Optional[int] = None
    journal_entry_number: Optional[str] = None
    created_by_name: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class PaginatedExpenseVouchersResponse(BaseModel):
    items: List[ExpenseVoucherItem]
    total: int
    page: int
    page_size: int
    pages: int


class ExpenseSummaryResponse(BaseModel):
    today_total: float
    month_total: float
    cash_total: float
    bank_total: float
    category_breakdown: List[Dict[str, Any]]


# ================= Financial Statements (P&L and Balance Sheet) Schemas =================
class ProfitAndLossAccountLine(BaseModel):
    account_id: int
    account_code: str
    account_name: str
    amount: float
    percentage_of_revenue: float = 0.0


class ProfitAndLossResponse(BaseModel):
    from_date: str
    to_date: str
    branch_id: Optional[int] = None
    branch_name: Optional[str] = None
    currency: str = "PKR"

    # 1. Turnover & Revenue
    gross_sales: float
    sales_discounts: float
    net_revenue: float
    revenue_lines: List[ProfitAndLossAccountLine] = []

    # 2. Cost of Goods Sold
    total_cogs: float
    cogs_lines: List[ProfitAndLossAccountLine] = []

    # 3. Gross Profit
    gross_profit: float
    gross_profit_margin_pct: float

    # 4. Operating Expenses
    total_operating_expenses: float
    expense_lines: List[ProfitAndLossAccountLine] = []

    # 5. Net Profit
    net_profit: float
    net_profit_margin_pct: float
    is_profitable: bool


class BalanceSheetAccountLine(BaseModel):
    account_id: int
    account_code: str
    account_name: str
    sub_type: Optional[str] = None
    balance: float


class BalanceSheetResponse(BaseModel):
    as_of_date: str
    branch_id: Optional[int] = None
    branch_name: Optional[str] = None
    currency: str = "PKR"

    # Assets
    current_assets: List[BalanceSheetAccountLine] = []
    total_current_assets: float
    non_current_assets: List[BalanceSheetAccountLine] = []
    total_non_current_assets: float
    total_assets: float

    # Liabilities
    current_liabilities: List[BalanceSheetAccountLine] = []
    total_current_liabilities: float
    long_term_liabilities: List[BalanceSheetAccountLine] = []
    total_long_term_liabilities: float
    total_liabilities: float

    # Equity & Accumulated Profits
    equity_lines: List[BalanceSheetAccountLine] = []
    total_equity_capital: float
    retained_earnings: float
    current_period_net_profit: float
    total_equity: float

    # Golden Equation Verification
    total_liabilities_and_equity: float
    is_balanced: bool
    discrepancy: float


# ================= Year-End Fiscal Closing Schemas =================
class YearEndClosingAccountLine(BaseModel):
    account_id: int
    account_code: str
    account_name: str
    account_type: str  # revenue, expense
    current_balance: float
    closing_action: str  # e.g. "Debit 12,000" or "Credit 8,000"
    amount: float


class YearEndClosingPreviewResponse(BaseModel):
    closing_date: str
    financial_year_start: str
    financial_year_end: str
    branch_id: Optional[int] = None
    branch_name: Optional[str] = None
    total_revenue_to_close: float
    total_expenses_to_close: float
    net_profit: float
    is_profitable: bool
    retained_earnings_account_id: int
    retained_earnings_account_code: str
    retained_earnings_account_name: str
    retained_earnings_before: float
    retained_earnings_after: float
    lines: List[YearEndClosingAccountLine] = []
    can_close: bool
    already_closed: bool = False
    existing_jv_number: Optional[str] = None
    message: Optional[str] = None


class YearEndClosingExecuteRequest(BaseModel):
    closing_date: date
    branch_id: Optional[int] = None
    notes: Optional[str] = None


class YearEndClosingExecuteResponse(BaseModel):
    message: str
    journal_entry_id: int
    journal_entry_number: str
    closing_date: str
    net_profit_transferred: float
    total_revenue_closed: float
    total_expenses_closed: float
    retained_earnings_new_balance: float


# ================= 7. Bank Reconciliation (BRS) Schemas =================
class BankReconcilableAccountItem(BaseModel):
    id: int
    code: str
    name: str
    currency: str
    current_balance: float
    unreconciled_count: int


class BankReconciliationCreateRequest(BaseModel):
    account_id: int = Field(..., description="Bank G/L Account ID (e.g., 1020)")
    statement_date: date = Field(..., description="As of date of official bank statement")
    statement_start_date: Optional[date] = Field(None, description="Optional start date of statement cycle")
    statement_ending_balance: float = Field(..., description="Ending balance shown on official bank statement")
    branch_id: Optional[int] = Field(None, description="Optional branch scope")
    notes: Optional[str] = None


class BankReconciliationTransactionItem(BaseModel):
    journal_entry_line_id: int
    journal_entry_id: int
    entry_number: str
    entry_date: str
    source_type: str
    reference_no: Optional[str] = None
    narration: Optional[str] = None
    debit: float   # Deposit / Inflow to Bank
    credit: float  # Payment / Outflow from Bank
    is_matched: bool
    matched_at: Optional[str] = None


class BankReconciliationSummary(BaseModel):
    id: int
    reconciliation_number: str
    account_id: int
    account_code: str
    account_name: str
    branch_id: Optional[int] = None
    statement_date: str
    statement_start_date: Optional[str] = None
    statement_ending_balance: float
    book_balance: float
    cleared_deposits: float
    cleared_payments: float
    reconciled_balance: float
    difference: float
    status: str
    notes: Optional[str] = None
    reconciled_by_name: Optional[str] = None
    reconciled_at: Optional[str] = None
    created_at: str


class BankReconciliationDetailResponse(BaseModel):
    reconciliation: BankReconciliationSummary
    deposits_in_transit: float
    outstanding_payments: float
    adjusted_book_balance: float
    is_balanced: bool
    transactions: List[BankReconciliationTransactionItem] = []


class BankReconciliationMatchRequest(BaseModel):
    matched_line_ids: List[int] = Field(default=[], description="JournalEntryLine IDs to mark as cleared/matched")
    unmatched_line_ids: List[int] = Field(default=[], description="JournalEntryLine IDs to unmark / keep in transit")


class BankReconciliationCompleteRequest(BaseModel):
    notes: Optional[str] = None





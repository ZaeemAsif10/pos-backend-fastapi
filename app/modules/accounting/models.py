from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy import (
    BigInteger,
    Integer,
    String,
    Boolean,
    DateTime,
    Text,
    Numeric,
    ForeignKey,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base_class import Base


class Account(Base):
    """
    Chart of Accounts (COA) master table.
    Multi-tenant isolated, hierarchical (parent-child tree), supports system defaults and custom user accounts.
    """
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    account_type: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )  # asset, liability, equity, revenue, expense
    sub_type: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True
    )  # cash, bank, receivable, payable, current_asset, fixed_asset, cogs, operating_expense, tax, equity

    parent_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    currency: Mapped[str] = mapped_column(String(10), default="PKR", nullable=False)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_tenant_account_code"),
    )

    parent = relationship("Account", remote_side=[id], backref="children")
    tenant = relationship("Tenant")
    journal_lines = relationship("JournalEntryLine", back_populates="account")


class TenantAccountingSettings(Base):
    """
    Business-level account mapping configuration (The 1 Mapping Screen).
    Determines which COA heads are impacted by POS checkouts, invoices, payments, and expenses.
    """
    __tablename__ = "tenant_accounting_settings"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenants.id", ondelete="CASCADE"), unique=True, nullable=False, index=True
    )

    base_currency: Mapped[str] = mapped_column(String(10), default="PKR", nullable=False)
    financial_year_start_month: Mapped[int] = mapped_column(Integer, default=7, nullable=False)  # July (PK) or Jan

    default_sales_income_account_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=True
    )
    default_ar_account_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=True
    )  # Accounts Receivable (Customer Khata)
    default_ap_account_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=True
    )  # Accounts Payable (Supplier Khata)
    default_cash_account_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=True
    )  # Cash Drawer / Counter Cash
    default_bank_account_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=True
    )  # Default Bank Account
    default_sales_tax_account_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=True
    )  # FBR / Provincial Sales Tax Output
    default_discount_account_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=True
    )  # Sales Discounts Allowed
    default_cogs_account_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=True
    )  # Cost of Goods Sold
    default_inventory_asset_account_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=True
    )  # Merchandise Inventory Stock

    # Dynamic JSON mapping for tender types: e.g. {"cash": 1010, "bank_transfer": 1020, "raast": 1021, "card": 1022}
    payment_method_mappings: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    auto_posting_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    tenant = relationship("Tenant")
    default_sales_income_account = relationship("Account", foreign_keys=[default_sales_income_account_id])
    default_ar_account = relationship("Account", foreign_keys=[default_ar_account_id])
    default_ap_account = relationship("Account", foreign_keys=[default_ap_account_id])
    default_cash_account = relationship("Account", foreign_keys=[default_cash_account_id])
    default_bank_account = relationship("Account", foreign_keys=[default_bank_account_id])
    default_sales_tax_account = relationship("Account", foreign_keys=[default_sales_tax_account_id])
    default_discount_account = relationship("Account", foreign_keys=[default_discount_account_id])
    default_cogs_account = relationship("Account", foreign_keys=[default_cogs_account_id])
    default_inventory_asset_account = relationship("Account", foreign_keys=[default_inventory_asset_account_id])


class JournalEntry(Base):
    """
    Master General Journal Voucher (JV).
    Double-entry accounting header record. Enforces sum(debit) == sum(credit).
    Multi-branch and multi-currency enabled.
    """
    __tablename__ = "journal_entries"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    branch_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("branches.id", ondelete="SET NULL"), nullable=True, index=True
    )
    entry_number: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    entry_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False, index=True
    )
    source_type: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )  # sales_invoice, customer_payment, supplier_payment, purchase_invoice, expense_voucher, manual_jv, opening_balance, stock_adjustment
    source_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, index=True)
    reference_no: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # Invoice #, Cheque #, B/L #, LC #
    narration: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    currency: Mapped[str] = mapped_column(String(10), default="PKR", nullable=False)
    exchange_rate: Mapped[float] = mapped_column(Numeric(12, 6), default=1.0, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default="posted", nullable=False
    )  # draft, posted, void, reversed

    total_debit: Mapped[float] = mapped_column(Numeric(15, 2), default=0.00, nullable=False)
    total_credit: Mapped[float] = mapped_column(Numeric(15, 2), default=0.00, nullable=False)

    created_by_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "entry_number", name="uq_tenant_journal_entry_number"),
    )

    tenant = relationship("Tenant")
    branch = relationship("Branch")
    created_by = relationship("User")
    lines: Mapped[List["JournalEntryLine"]] = relationship(
        "JournalEntryLine", back_populates="journal_entry", cascade="all, delete-orphan"
    )


class JournalEntryLine(Base):
    """
    Debit and credit breakdown lines for a Journal Entry.
    Supports sub-ledger linking to customers/suppliers, branch tagging, and foreign currency.
    """
    __tablename__ = "journal_entry_lines"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    journal_entry_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("journal_entries.id", ondelete="CASCADE"), nullable=False, index=True
    )
    account_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    branch_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("branches.id", ondelete="SET NULL"), nullable=True, index=True
    )

    debit: Mapped[float] = mapped_column(Numeric(15, 2), default=0.00, nullable=False)
    credit: Mapped[float] = mapped_column(Numeric(15, 2), default=0.00, nullable=False)

    # Multi-currency support (e.g. for import/export consignments)
    foreign_amount: Mapped[Optional[float]] = mapped_column(Numeric(15, 2), nullable=True)
    foreign_currency: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)

    narration: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Sub-ledger references for customer/supplier party reconciliation
    customer_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("customers.id", ondelete="SET NULL"), nullable=True, index=True
    )
    supplier_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("suppliers.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Bank Reconciliation status
    is_reconciled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    reconciled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    journal_entry = relationship("JournalEntry", back_populates="lines")
    account = relationship("Account", back_populates="journal_lines")
    customer = relationship("Customer")
    supplier = relationship("Supplier")
    branch = relationship("Branch")


class ExpenseVoucher(Base):
    """
    Direct Expense Voucher (Daily Shop & Office Kharchay).
    Allows counter staff & cashiers to record operational expenses without knowing debits/credits.
    Automatically posts a balanced double-entry Journal Voucher (Dr Expense, Cr Cash/Bank).
    """
    __tablename__ = "expense_vouchers"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    branch_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("branches.id", ondelete="SET NULL"), nullable=True, index=True
    )
    voucher_number: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    expense_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False, index=True
    )

    expense_account_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    paid_from_account_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    amount: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False)
    payment_method: Mapped[str] = mapped_column(String(50), default="cash", nullable=False)  # cash, bank_transfer, card, cheque, etc.
    payee_name: Mapped[str] = mapped_column(String(255), nullable=False)  # LESCO, Landlord, Chai Wala, etc.
    reference_no: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # Bill/Receipt #
    narration: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    attachment_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    status: Mapped[str] = mapped_column(String(20), default="posted", nullable=False)  # posted, cancelled

    journal_entry_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("journal_entries.id", ondelete="SET NULL"), nullable=True, index=True
    )

    created_by_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "voucher_number", name="uq_tenant_expense_voucher_number"),
    )

    tenant = relationship("Tenant")
    branch = relationship("Branch")
    expense_account = relationship("Account", foreign_keys=[expense_account_id])
    paid_from_account = relationship("Account", foreign_keys=[paid_from_account_id])
    journal_entry = relationship("JournalEntry", foreign_keys=[journal_entry_id])
    created_by = relationship("User", foreign_keys=[created_by_id])


class BankReconciliation(Base):
    """
    Bank Reconciliation Statement (BRS) session.
    Reconciles General Ledger Bank Head balance against official Bank Statement.
    """
    __tablename__ = "bank_reconciliations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    account_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    branch_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("branches.id", ondelete="SET NULL"), nullable=True, index=True
    )

    reconciliation_number: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    statement_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    statement_start_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Financial Balances
    statement_ending_balance: Mapped[float] = mapped_column(Numeric(15, 2), default=0.00, nullable=False)
    book_balance: Mapped[float] = mapped_column(Numeric(15, 2), default=0.00, nullable=False)
    cleared_deposits: Mapped[float] = mapped_column(Numeric(15, 2), default=0.00, nullable=False)
    cleared_payments: Mapped[float] = mapped_column(Numeric(15, 2), default=0.00, nullable=False)
    reconciled_balance: Mapped[float] = mapped_column(Numeric(15, 2), default=0.00, nullable=False)
    difference: Mapped[float] = mapped_column(Numeric(15, 2), default=0.00, nullable=False)

    status: Mapped[str] = mapped_column(String(20), default="in_progress", nullable=False, index=True)  # in_progress, completed, cancelled
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    reconciled_by_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reconciled_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "reconciliation_number", name="uq_tenant_bank_reconciliation_number"),
    )

    tenant = relationship("Tenant")
    account = relationship("Account")
    branch = relationship("Branch")
    reconciled_by = relationship("User", foreign_keys=[reconciled_by_id])
    items = relationship("BankReconciliationItem", back_populates="reconciliation", cascade="all, delete-orphan")


class BankReconciliationItem(Base):
    """
    Matched / Cleared Journal Entry Line item within a BRS session.
    """
    __tablename__ = "bank_reconciliation_items"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    reconciliation_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("bank_reconciliations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    journal_entry_line_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("journal_entry_lines.id", ondelete="CASCADE"), nullable=False, index=True
    )

    is_matched: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    matched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    notes: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    __table_args__ = (
        UniqueConstraint("reconciliation_id", "journal_entry_line_id", name="uq_reconciliation_line"),
    )

    reconciliation = relationship("BankReconciliation", back_populates="items")
    journal_entry_line = relationship("JournalEntryLine")



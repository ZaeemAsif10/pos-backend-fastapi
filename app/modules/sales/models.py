from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy import (
    BigInteger,
    String,
    Boolean,
    DateTime,
    Text,
    Numeric,
    ForeignKey,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base_class import Base


class POSShift(Base):
    """POS Cash Register / Counter shifts for cash tracking."""
    __tablename__ = "pos_shifts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    branch_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    cashier_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    opening_cash: Mapped[float] = mapped_column(Numeric(14, 2), default=0.00, nullable=False)
    closing_cash: Mapped[Optional[float]] = mapped_column(Numeric(14, 2), nullable=True)
    expected_cash: Mapped[Optional[float]] = mapped_column(Numeric(14, 2), nullable=True)
    cash_difference: Mapped[Optional[float]] = mapped_column(Numeric(14, 2), nullable=True)

    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="open", nullable=False)  # open, closed

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    tenant = relationship("Tenant", backref="pos_shifts")
    branch = relationship("Branch", backref="pos_shifts")
    cashier = relationship("User", foreign_keys=[cashier_id])
    invoices = relationship("SalesInvoice", back_populates="shift")


class SalesInvoice(Base):
    """POS Counter Sales and Wholesale/B2B Sales Invoices with FBR Integration."""
    __tablename__ = "sales_invoices"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    branch_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    customer_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("customers.id", ondelete="SET NULL"), nullable=True, index=True
    )
    pos_shift_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("pos_shifts.id", ondelete="SET NULL"), nullable=True, index=True
    )

    customer_name: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    customer_phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    customer_ntn_cnic: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)

    invoice_number: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    sale_type: Mapped[str] = mapped_column(String(30), default="pos_retail", nullable=False)  # pos_retail, wholesale_invoice, return_credit_note
    invoice_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    payment_method: Mapped[str] = mapped_column(String(30), default="cash", nullable=False)  # cash, card, bank_transfer, credit, split
    payment_status: Mapped[str] = mapped_column(String(20), default="paid", nullable=False)  # paid, partial, unpaid

    subtotal: Mapped[float] = mapped_column(Numeric(14, 2), default=0.00, nullable=False)
    discount_amount: Mapped[float] = mapped_column(Numeric(14, 2), default=0.00, nullable=False)
    tax_amount: Mapped[float] = mapped_column(Numeric(14, 2), default=0.00, nullable=False)
    total_amount: Mapped[float] = mapped_column(Numeric(14, 2), default=0.00, nullable=False)
    paid_amount: Mapped[float] = mapped_column(Numeric(14, 2), default=0.00, nullable=False)
    change_amount: Mapped[float] = mapped_column(Numeric(14, 2), default=0.00, nullable=False)
    balance_due: Mapped[float] = mapped_column(Numeric(14, 2), default=0.00, nullable=False)

    # FBR & Fiscal Data
    fbr_pos_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    fbr_invoice_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    fbr_qr_code: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    fbr_status: Mapped[str] = mapped_column(String(20), default="mocked", nullable=False)  # mocked, synced, pending, failed, exempt
    fbr_response_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    fbr_synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    salesman_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_by_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="completed", nullable=False)  # completed, draft, cancelled, refunded

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    tenant = relationship("Tenant", backref="sales_invoices")
    branch = relationship("Branch", backref="sales_invoices")
    customer = relationship("Customer", backref="sales_invoices")
    shift = relationship("POSShift", back_populates="invoices")
    salesman = relationship("User", foreign_keys=[salesman_id])
    created_by = relationship("User", foreign_keys=[created_by_id])
    items = relationship("SalesInvoiceItem", back_populates="sales_invoice", cascade="all, delete-orphan")
    payments = relationship("SalesPayment", back_populates="sales_invoice", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("tenant_id", "invoice_number", name="uq_tenant_sales_invoice_number"),
    )


class SalesInvoiceItem(Base):
    """Line items sold in POS / sales invoices with FBR PCT code and cost snapshot."""
    __tablename__ = "sales_invoice_items"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sales_invoice_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("sales_invoices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("products.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    uom_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("product_uom_conversions.id", ondelete="SET NULL"), nullable=True
    )

    uom_name: Mapped[str] = mapped_column(String(50), default="Piece", nullable=False)
    quantity: Mapped[float] = mapped_column(Numeric(14, 3), default=1.000, nullable=False)
    unit_price: Mapped[float] = mapped_column(Numeric(14, 2), default=0.00, nullable=False)
    cost_price: Mapped[float] = mapped_column(Numeric(14, 2), default=0.00, nullable=False)
    discount_amount: Mapped[float] = mapped_column(Numeric(14, 2), default=0.00, nullable=False)
    tax_rate: Mapped[float] = mapped_column(Numeric(5, 2), default=0.00, nullable=False)
    tax_amount: Mapped[float] = mapped_column(Numeric(14, 2), default=0.00, nullable=False)
    pct_code: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)  # FBR HS/PCT code
    total_amount: Mapped[float] = mapped_column(Numeric(14, 2), default=0.00, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    # Relationships
    sales_invoice = relationship("SalesInvoice", back_populates="items")
    product = relationship("Product")
    uom = relationship("ProductUOMConversion")


class SalesPayment(Base):
    """Payment records for invoices (supports split payments e.g. cash + card)."""
    __tablename__ = "sales_payments"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sales_invoice_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("sales_invoices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    payment_method: Mapped[str] = mapped_column(String(30), default="cash", nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(14, 2), default=0.00, nullable=False)
    reference_no: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    payment_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    received_by_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    # Relationships
    sales_invoice = relationship("SalesInvoice", back_populates="payments")
    received_by = relationship("User")

from datetime import datetime, date, timezone
from typing import Optional, List
from sqlalchemy import (
    BigInteger,
    String,
    Boolean,
    DateTime,
    Date,
    Text,
    Numeric,
    ForeignKey,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base_class import Base


class Purchase(Base):
    """Purchase invoices and Goods Received Notes (GRN) from suppliers."""
    __tablename__ = "purchases"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    branch_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    supplier_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("suppliers.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    invoice_number: Mapped[str] = mapped_column(String(50), nullable=False)
    supplier_bill_no: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    purchase_date: Mapped[date] = mapped_column(Date, default=lambda: datetime.now(timezone.utc).date(), nullable=False)
    
    status: Mapped[str] = mapped_column(String(20), default="received", nullable=False)  # draft, received, cancelled
    payment_status: Mapped[str] = mapped_column(String(20), default="unpaid", nullable=False)  # unpaid, partial, paid

    subtotal: Mapped[float] = mapped_column(Numeric(14, 2), default=0.00, nullable=False)
    discount_amount: Mapped[float] = mapped_column(Numeric(14, 2), default=0.00, nullable=False)
    tax_amount: Mapped[float] = mapped_column(Numeric(14, 2), default=0.00, nullable=False)
    shipping_cost: Mapped[float] = mapped_column(Numeric(14, 2), default=0.00, nullable=False)
    total_amount: Mapped[float] = mapped_column(Numeric(14, 2), default=0.00, nullable=False)
    paid_amount: Mapped[float] = mapped_column(Numeric(14, 2), default=0.00, nullable=False)
    balance_due: Mapped[float] = mapped_column(Numeric(14, 2), default=0.00, nullable=False)

    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
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

    # Relationships
    tenant = relationship("Tenant", backref="purchases")
    branch = relationship("Branch", foreign_keys=[branch_id])
    supplier = relationship("Supplier", foreign_keys=[supplier_id])
    created_by = relationship("User", foreign_keys=[created_by_id])
    items = relationship("PurchaseItem", back_populates="purchase", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("tenant_id", "invoice_number", name="uq_tenant_purchase_invoice_no"),
    )


class PurchaseItem(Base):
    """Line items for each purchase bill."""
    __tablename__ = "purchase_items"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    purchase_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("purchases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("products.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    uom_conversion_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("product_uom_conversions.id", ondelete="SET NULL"), nullable=True
    )

    unit_name: Mapped[str] = mapped_column(String(50), nullable=False)  # Piece, Carton, Box
    quantity: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    conversion_factor: Mapped[float] = mapped_column(Numeric(10, 2), default=1.00, nullable=False)
    total_base_quantity: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    unit_cost: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    total_cost: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)

    batch_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    expiry_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    # Relationships
    purchase = relationship("Purchase", back_populates="items")
    product = relationship("Product")
    uom_conversion = relationship("ProductUOMConversion")


class StockMovement(Base):
    """Immutable stock ledger / bin card audit trail for every stock change."""
    __tablename__ = "stock_movements"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    branch_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("branches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )

    movement_type: Mapped[str] = mapped_column(String(30), nullable=False)  # PURCHASE, SALE, TRANSFER_IN, TRANSFER_OUT, ADJUSTMENT_ADD, ADJUSTMENT_SUB
    quantity: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)  # + for increase, - for decrease
    balance_after: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)  # running balance after transaction
    unit_cost: Mapped[float] = mapped_column(Numeric(14, 2), default=0.00, nullable=False)
    
    reference_type: Mapped[str] = mapped_column(String(30), nullable=False)  # purchase, sale, transfer, adjustment
    reference_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False, index=True
    )

    # Relationships
    tenant = relationship("Tenant")
    branch = relationship("Branch")
    product = relationship("Product")


class StockTransfer(Base):
    """Inter-branch stock transfers (Warehouse to Shop/Van)."""
    __tablename__ = "stock_transfers"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    transfer_number: Mapped[str] = mapped_column(String(50), nullable=False)
    from_branch_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    to_branch_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    transfer_date: Mapped[date] = mapped_column(Date, default=lambda: datetime.now(timezone.utc).date(), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="completed", nullable=False)  # pending, completed, cancelled
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
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

    # Relationships
    from_branch = relationship("Branch", foreign_keys=[from_branch_id])
    to_branch = relationship("Branch", foreign_keys=[to_branch_id])
    created_by = relationship("User", foreign_keys=[created_by_id])
    items = relationship("StockTransferItem", back_populates="transfer", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("tenant_id", "transfer_number", name="uq_tenant_stock_transfer_no"),
    )


class StockTransferItem(Base):
    """Line items for stock transfer."""
    __tablename__ = "stock_transfer_items"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    transfer_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("stock_transfers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("products.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    quantity: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    unit_cost: Mapped[float] = mapped_column(Numeric(14, 2), default=0.00, nullable=False)

    # Relationships
    transfer = relationship("StockTransfer", back_populates="items")
    product = relationship("Product")


class StockAdjustment(Base):
    """Stock shrinkage, damage, expiry, or audit corrections."""
    __tablename__ = "stock_adjustments"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    branch_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    adjustment_number: Mapped[str] = mapped_column(String(50), nullable=False)
    adjustment_date: Mapped[date] = mapped_column(Date, default=lambda: datetime.now(timezone.utc).date(), nullable=False)
    reason: Mapped[str] = mapped_column(String(50), default="audit_correction", nullable=False)  # damage, expiry, audit_correction, sample
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
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

    # Relationships
    branch = relationship("Branch", foreign_keys=[branch_id])
    created_by = relationship("User", foreign_keys=[created_by_id])
    items = relationship("StockAdjustmentItem", back_populates="adjustment", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("tenant_id", "adjustment_number", name="uq_tenant_stock_adj_no"),
    )


class StockAdjustmentItem(Base):
    """Line items for stock adjustment."""
    __tablename__ = "stock_adjustment_items"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    adjustment_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("stock_adjustments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("products.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    adjustment_type: Mapped[str] = mapped_column(String(10), default="SUBTRACT", nullable=False)  # ADD, SUBTRACT
    quantity: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    unit_cost: Mapped[float] = mapped_column(Numeric(14, 2), default=0.00, nullable=False)

    # Relationships
    adjustment = relationship("StockAdjustment", back_populates="items")
    product = relationship("Product")

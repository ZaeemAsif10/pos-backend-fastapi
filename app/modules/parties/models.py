from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy import (
    BigInteger,
    String,
    Boolean,
    DateTime,
    Text,
    Numeric,
    Integer,
    ForeignKey,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base_class import Base


class DeliveryArea(Base):
    """Geographic delivery routes, areas, and market beats for salesmen and distribution."""
    __tablename__ = "delivery_areas"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    city: Mapped[str] = mapped_column(String(50), default="Lahore", nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    delivery_days: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    assigned_salesman_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

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
    tenant = relationship("Tenant", backref="delivery_areas")
    assigned_salesman = relationship("User", foreign_keys=[assigned_salesman_id])
    customers = relationship("Customer", back_populates="area")

    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_tenant_delivery_area_code"),
    )


class Customer(Base):
    """Customers, retail shops, wholesale accounts, and corporate buyers."""
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(30), nullable=False)
    business_name: Mapped[str] = mapped_column(String(150), nullable=False)
    owner_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    phone: Mapped[str] = mapped_column(String(30), nullable=False)
    whatsapp_number: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    cnic: Mapped[Optional[str]] = mapped_column(String(25), nullable=True)
    ntn: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    strn: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    customer_type: Mapped[str] = mapped_column(String(30), default="retailer", nullable=False)
    
    # Financial & Udhaar Controls
    credit_limit: Mapped[float] = mapped_column(Numeric(14, 2), default=0.00, nullable=False)
    credit_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    current_balance: Mapped[float] = mapped_column(Numeric(14, 2), default=0.00, nullable=False)
    opening_balance: Mapped[float] = mapped_column(Numeric(14, 2), default=0.00, nullable=False)
    is_credit_blocked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Location & Assignment
    area_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("delivery_areas.id", ondelete="SET NULL"), nullable=True, index=True
    )
    branch_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("branches.id", ondelete="SET NULL"), nullable=True, index=True
    )
    city: Mapped[str] = mapped_column(String(50), default="Lahore", nullable=False)
    address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    kyc_status: Mapped[str] = mapped_column(String(20), default="verified", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

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
    tenant = relationship("Tenant", backref="customers")
    area = relationship("DeliveryArea", back_populates="customers")
    branch = relationship("Branch", foreign_keys=[branch_id])
    payments = relationship("CustomerPayment", back_populates="customer", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_tenant_customer_code"),
    )


class Supplier(Base):
    """Principals, manufacturers, mills, and wholesale vendors."""
    __tablename__ = "suppliers"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(30), nullable=False)
    company_name: Mapped[str] = mapped_column(String(150), nullable=False)
    contact_person: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    phone: Mapped[str] = mapped_column(String(30), nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    ntn: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    strn: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    
    # Commercial Terms & Balances
    payment_terms_days: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    current_balance: Mapped[float] = mapped_column(Numeric(14, 2), default=0.00, nullable=False)
    opening_balance: Mapped[float] = mapped_column(Numeric(14, 2), default=0.00, nullable=False)

    # Banking Details
    bank_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    bank_account_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    bank_iban: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    bank_branch: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    city: Mapped[str] = mapped_column(String(50), default="Lahore", nullable=False)
    address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

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
    tenant = relationship("Tenant", backref="suppliers")
    payments = relationship("SupplierPayment", back_populates="supplier", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_tenant_supplier_code"),
    )


class SalesmanTarget(Base):
    """Monthly order booking and udhaar recovery targets by salesman."""
    __tablename__ = "salesman_targets"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    salesman_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    area_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("delivery_areas.id", ondelete="SET NULL"), nullable=True, index=True
    )
    period_month: Mapped[str] = mapped_column(String(7), nullable=False)  # Format: YYYY-MM
    target_sales_amount: Mapped[float] = mapped_column(Numeric(14, 2), default=0.00, nullable=False)
    target_recovery_amount: Mapped[float] = mapped_column(Numeric(14, 2), default=0.00, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

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
    tenant = relationship("Tenant", backref="salesman_targets")
    salesman = relationship("User", foreign_keys=[salesman_id])
    area = relationship("DeliveryArea")

    __table_args__ = (
        UniqueConstraint("tenant_id", "salesman_id", "period_month", name="uq_tenant_salesman_target_month"),
    )


class CustomerPayment(Base):
    """Customer Khata recovery / Cash receipt voucher (CRV)."""
    __tablename__ = "customer_payments"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    customer_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    branch_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("branches.id", ondelete="SET NULL"), nullable=True, index=True
    )
    voucher_number: Mapped[str] = mapped_column(String(40), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(14, 2), default=0.00, nullable=False)
    payment_method: Mapped[str] = mapped_column(String(30), default="cash", nullable=False)
    reference_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    previous_balance: Mapped[float] = mapped_column(Numeric(14, 2), default=0.00, nullable=False)
    new_balance: Mapped[float] = mapped_column(Numeric(14, 2), default=0.00, nullable=False)
    received_by_id: Mapped[Optional[int]] = mapped_column(
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
    tenant = relationship("Tenant")
    customer = relationship("Customer", back_populates="payments")
    branch = relationship("Branch")
    received_by = relationship("User")

    __table_args__ = (
        UniqueConstraint("tenant_id", "voucher_number", name="uq_tenant_customer_payment_voucher"),
    )


class SupplierPayment(Base):
    """Supplier payment / Cash Payment Voucher (CPV)."""
    __tablename__ = "supplier_payments"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    supplier_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    branch_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("branches.id", ondelete="SET NULL"), nullable=True, index=True
    )
    voucher_number: Mapped[str] = mapped_column(String(40), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(14, 2), default=0.00, nullable=False)
    payment_method: Mapped[str] = mapped_column(String(30), default="cash", nullable=False)
    reference_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    previous_balance: Mapped[float] = mapped_column(Numeric(14, 2), default=0.00, nullable=False)
    new_balance: Mapped[float] = mapped_column(Numeric(14, 2), default=0.00, nullable=False)
    paid_by_id: Mapped[Optional[int]] = mapped_column(
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
    tenant = relationship("Tenant")
    supplier = relationship("Supplier", back_populates="payments")
    branch = relationship("Branch")
    paid_by = relationship("User")

    __table_args__ = (
        UniqueConstraint("tenant_id", "voucher_number", name="uq_tenant_supplier_payment_voucher"),
    )



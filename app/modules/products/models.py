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


class Category(Base):
    """Product classification hierarchy (Categories and Sub-categories)."""
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    parent_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("categories.id", ondelete="SET NULL"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    code: Mapped[str] = mapped_column(String(30), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
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
    tenant = relationship("Tenant", backref="categories")
    parent = relationship("Category", remote_side=[id], backref="subcategories")
    products = relationship("Product", back_populates="category")

    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_tenant_category_name"),
        UniqueConstraint("tenant_id", "code", name="uq_tenant_category_code"),
    )


class Brand(Base):
    """Manufacturer / Principal Company Brand Master."""
    __tablename__ = "brands"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    code: Mapped[str] = mapped_column(String(30), nullable=False)
    origin: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, default="Pakistan")
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
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
    tenant = relationship("Tenant", backref="brands")
    products = relationship("Product", back_populates="brand")

    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_tenant_brand_name"),
        UniqueConstraint("tenant_id", "code", name="uq_tenant_brand_code"),
    )


class Product(Base):
    """Master Products & Inventory Item Master."""
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    sku: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    barcode: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)

    category_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("categories.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    brand_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("brands.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Unit of Measure
    base_unit: Mapped[str] = mapped_column(String(30), default="Piece", nullable=False)

    # Pricing Engine (in PKR)
    cost_price: Mapped[float] = mapped_column(Numeric(12, 2), default=0.00, nullable=False)
    retail_price: Mapped[float] = mapped_column(Numeric(12, 2), default=0.00, nullable=False)  # POS MRP
    wholesale_price: Mapped[float] = mapped_column(Numeric(12, 2), default=0.00, nullable=False)  # Bulk Trade
    min_price: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), nullable=True)  # Floor price threshold

    # FBR & Tax Details
    tax_rate: Mapped[float] = mapped_column(Numeric(5, 2), default=0.00, nullable=False)  # Default 0 or 18%
    is_fbr_third_schedule: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Operations & Tracking
    has_batches: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    reorder_level: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    image_url: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
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
    tenant = relationship("Tenant", backref="products")
    category = relationship("Category", back_populates="products")
    brand = relationship("Brand", back_populates="products")
    uom_conversions = relationship("ProductUOMConversion", back_populates="product", cascade="all, delete-orphan")
    branch_stocks = relationship("BranchStock", back_populates="product", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("tenant_id", "sku", name="uq_tenant_product_sku"),
    )


class ProductUOMConversion(Base):
    """Packaging unit conversions for wholesale distribution (e.g. 1 Carton = 24 Pieces)."""
    __tablename__ = "product_uom_conversions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    unit_name: Mapped[str] = mapped_column(String(50), nullable=False)  # e.g. "Carton", "Box", "Pack of 12"
    conversion_factor: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)  # Quantity of base units (e.g. 24)
    carton_barcode: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    carton_wholesale_price: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), nullable=True)
    carton_retail_price: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    # Relationships
    product = relationship("Product", back_populates="uom_conversions")


class BranchStock(Base):
    """Multi-branch & warehouse physical stock levels."""
    __tablename__ = "branch_stocks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    branch_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("branches.id", ondelete="CASCADE"), nullable=False, index=True
    )

    quantity: Mapped[float] = mapped_column(Numeric(12, 2), default=0.00, nullable=False)
    reserved_quantity: Mapped[float] = mapped_column(Numeric(12, 2), default=0.00, nullable=False)
    reorder_point: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    product = relationship("Product", back_populates="branch_stocks")
    branch = relationship("Branch", backref="branch_stocks")

    @property
    def current_stock(self) -> float:
        return float(self.quantity)

    @current_stock.setter
    def current_stock(self, val: float) -> None:
        self.quantity = val


    __table_args__ = (
        UniqueConstraint("branch_id", "product_id", name="uq_branch_product_stock"),
    )

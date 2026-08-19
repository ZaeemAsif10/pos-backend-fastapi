from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from app.db.base import Base

class Branch(Base):
    __tablename__ = "branches"

    id = Column(Integer, primary_key=True, index=True)
    business_id = Column(Integer, ForeignKey("businesses.id"), nullable=False)
    name = Column(String(255), index=True, nullable=False) # e.g. "Gulberg Branch"
    code = Column(String(50), nullable=True) # e.g. "LHR-01"
    address = Column(String(500), nullable=True)
    phone = Column(String(50), nullable=True)
    is_main_branch = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    business = relationship("Business", back_populates="branches")
    variant_stocks = relationship("BranchVariantStock", back_populates="branch", cascade="all, delete-orphan")

class BranchVariantStock(Base):
    __tablename__ = "branch_variant_stock"

    id = Column(Integer, primary_key=True, index=True)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=False)
    product_variant_id = Column(Integer, ForeignKey("product_variants.id"), nullable=False)
    stock_quantity = Column(Integer, default=0)
    min_alert_quantity = Column(Integer, default=5)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    branch = relationship("Branch", back_populates="variant_stocks")
    variant = relationship("ProductVariant")

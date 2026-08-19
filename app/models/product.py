from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from app.db.base import Base

class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, index=True)
    business_id = Column(Integer, ForeignKey("businesses.id"), nullable=True)
    name = Column(String(100), index=True, nullable=False)
    description = Column(String(255), nullable=True)
    
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    products = relationship("Product", back_populates="category")

class Brand(Base):
    __tablename__ = "brands"

    id = Column(Integer, primary_key=True, index=True)
    business_id = Column(Integer, ForeignKey("businesses.id"), nullable=True)
    name = Column(String(100), index=True, nullable=False)
    description = Column(String(255), nullable=True)
    
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    products = relationship("Product", back_populates="brand")

class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    business_id = Column(Integer, ForeignKey("businesses.id"), nullable=True)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    brand_id = Column(Integer, ForeignKey("brands.id"), nullable=True)
    name = Column(String(255), index=True, nullable=False)
    description = Column(String(500), nullable=True)
    image_url = Column(String(500), nullable=True)
    base_price = Column(Float, nullable=False)
    cost_price = Column(Float, nullable=False, default=0.0)
    
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    category = relationship("Category", back_populates="products")
    brand = relationship("Brand", back_populates="products")
    variants = relationship("ProductVariant", back_populates="product", cascade="all, delete-orphan")

class ProductVariant(Base):
    __tablename__ = "product_variants"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"))
    
    size = Column(String(50), nullable=True)
    color = Column(String(50), nullable=True)
    sku = Column(String(100), unique=True, index=True, nullable=False)
    barcode = Column(String(100), unique=True, index=True, nullable=True)
    
    stock_quantity = Column(Integer, default=0)
    price_adjustment = Column(Float, default=0.0)
    
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    product = relationship("Product", back_populates="variants")

from sqlalchemy import Column, Integer, Float, String, ForeignKey, DateTime # pyrefly: ignore [missing-import]
from sqlalchemy.orm import relationship # pyrefly: ignore [missing-import]
from datetime import datetime, timezone # pyrefly: ignore [missing-import]
from app.db.base import Base # pyrefly: ignore [missing-import]
from app.models.user import User # pyrefly: ignore [missing-import]
from app.models.customer import Customer # pyrefly: ignore [missing-import]
from app.models.payment_method import PaymentMethod # pyrefly: ignore [missing-import]
from app.models.product import ProductVariant # pyrefly: ignore [missing-import]

class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    business_id = Column(Integer, ForeignKey("businesses.id"), nullable=True)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)
    payment_method_id = Column(Integer, ForeignKey("payment_methods.id"), nullable=True)
    
    total_amount = Column(Float, nullable=False, default=0.0)
    discount = Column(Float, default=0.0)
    tax = Column(Float, default=0.0)
    final_amount = Column(Float, nullable=False, default=0.0)
    paid_amount = Column(Float, nullable=False, default=0.0)
    due_amount = Column(Float, nullable=False, default=0.0)
    
    status = Column(String(50), default="Paid") # Paid, Partial, Due, Returned
    
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    user = relationship("User")
    customer = relationship("Customer", back_populates="orders")
    payment_method = relationship("PaymentMethod")
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")
    payments = relationship("OrderPayment", back_populates="order", cascade="all, delete-orphan")

class OrderItem(Base):
    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"))
    product_variant_id = Column(Integer, ForeignKey("product_variants.id"))
    
    quantity = Column(Integer, nullable=False)
    unit_price = Column(Float, nullable=False) # Price at the time of sale
    subtotal = Column(Float, nullable=False)
    
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    order = relationship("Order", back_populates="items")
    variant = relationship("ProductVariant")

class OrderPayment(Base):
    __tablename__ = "order_payments"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    payment_method_id = Column(Integer, ForeignKey("payment_methods.id"), nullable=True)
    amount = Column(Float, nullable=False, default=0.0)
    note = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    order = relationship("Order", back_populates="payments")
    payment_method = relationship("PaymentMethod")

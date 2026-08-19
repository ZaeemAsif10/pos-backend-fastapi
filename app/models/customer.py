from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime # pyrefly: ignore [missing-import]
from sqlalchemy.orm import relationship # pyrefly: ignore [missing-import]
from datetime import datetime, timezone
from app.db.base import Base # pyrefly: ignore [missing-import]

class Customer(Base):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, index=True)
    business_id = Column(Integer, ForeignKey("businesses.id"), nullable=True)
    name = Column(String(100), index=True, nullable=False)
    phone = Column(String(20), index=True, nullable=False)
    email = Column(String(100), nullable=True)
    address = Column(String(255), nullable=True)
    
    total_spent = Column(Float, default=0.0)
    loyalty_points = Column(Integer, default=0)
    
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    orders = relationship("Order", back_populates="customer")

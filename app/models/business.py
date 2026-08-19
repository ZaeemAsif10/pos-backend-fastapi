from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from app.db.base import Base

class Business(Base):
    __tablename__ = "businesses"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), index=True, nullable=False)
    slug = Column(String(255), unique=True, index=True, nullable=True)
    phone = Column(String(50), nullable=True)
    email = Column(String(255), nullable=True)
    address = Column(String(500), nullable=True)
    logo_url = Column(String(500), nullable=True)
    currency = Column(String(20), default="PKR")
    status = Column(String(50), default="Active") # Active, Suspended, Expired
    
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    branches = relationship("Branch", back_populates="business", cascade="all, delete-orphan")

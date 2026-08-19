from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class BusinessBase(BaseModel):
    name: str
    slug: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    logo_url: Optional[str] = None
    currency: Optional[str] = "PKR"
    status: Optional[str] = "Active"

class BusinessCreate(BusinessBase):
    admin_name: Optional[str] = "Business Admin"
    admin_email: str
    admin_password: str

class BusinessUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    logo_url: Optional[str] = None
    currency: Optional[str] = None
    status: Optional[str] = None

class BusinessResponse(BusinessBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

from pydantic import BaseModel # pyrefly: ignore [missing-import]
from typing import Optional # pyrefly: ignore [missing-import]

class CustomerBase(BaseModel):
    name: str
    phone: str
    email: Optional[str] = None
    address: Optional[str] = None

class CustomerCreate(CustomerBase):
    pass

class CustomerUpdate(CustomerBase):
    name: Optional[str] = None
    phone: Optional[str] = None

class CustomerResponse(CustomerBase):
    id: int
    total_spent: float
    loyalty_points: int
    
    class Config:
        from_attributes = True

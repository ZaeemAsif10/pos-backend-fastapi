from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class BranchBase(BaseModel):
    business_id: Optional[int] = None
    name: str
    code: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    is_main_branch: Optional[bool] = False
    is_active: Optional[bool] = True

class BranchCreate(BranchBase):
    pass

class BranchUpdate(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    is_main_branch: Optional[bool] = None
    is_active: Optional[bool] = None

class BranchResponse(BranchBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

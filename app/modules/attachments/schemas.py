from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


class AttachmentBase(BaseModel):
    attachable_type: str = Field(..., description="Entity type e.g. Product, Customer, SalesInvoice")
    attachable_id: int = Field(..., description="Target entity ID")
    file_name: str = Field(..., description="Original filename")
    file_path: str = Field(..., description="Accessible URL or path")
    file_type: Optional[str] = None
    file_size: int = 0
    is_primary: bool = False
    title: Optional[str] = None
    description: Optional[str] = None


class AttachmentCreate(AttachmentBase):
    pass


class AttachmentResponse(AttachmentBase):
    id: int
    tenant_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class AttachmentListResponse(BaseModel):
    items: List[AttachmentResponse]
    total: int

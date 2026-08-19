from pydantic import BaseModel, EmailStr # pyrefly: ignore [missing-import]
from typing import Optional, List # pyrefly: ignore [missing-import]
from datetime import datetime

class PermissionBase(BaseModel):
    name: str
    description: Optional[str] = None

class PermissionResponse(PermissionBase):
    id: int
    class Config:
        from_attributes = True

class RoleBase(BaseModel):
    name: str
    description: Optional[str] = None

class RoleCreate(RoleBase):
    permission_ids: Optional[List[int]] = []

class RoleResponse(RoleBase):
    id: int
    permissions: List[PermissionResponse] = []
    class Config:
        from_attributes = True

class UserBase(BaseModel):
    email: EmailStr
    name: Optional[str] = None
    is_active: Optional[bool] = True
    role_id: int
    branch_id: Optional[int] = None

class UserCreate(UserBase):
    password: str

class UserResponse(UserBase):
    id: int
    business_id: Optional[int] = None
    branch_id: Optional[int] = None
    business_name: Optional[str] = None
    branch_name: Optional[str] = None
    role: RoleResponse
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str

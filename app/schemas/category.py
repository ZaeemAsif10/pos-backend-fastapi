from pydantic import BaseModel # pyrefly: ignore [missing-import]
from typing import Optional # pyrefly: ignore [missing-import]

class CategoryBase(BaseModel):
    name: str
    description: Optional[str] = None

class CategoryCreate(CategoryBase):
    pass

class CategoryUpdate(CategoryBase):
    name: Optional[str] = None

class CategoryResponse(CategoryBase):
    id: int
    class Config:
        from_attributes = True

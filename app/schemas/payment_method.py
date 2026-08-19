from pydantic import BaseModel
from typing import Optional

class PaymentMethodBase(BaseModel):
    name: str
    description: Optional[str] = None
    is_active: bool = True

class PaymentMethodCreate(PaymentMethodBase):
    pass

class PaymentMethodUpdate(PaymentMethodBase):
    name: Optional[str] = None
    is_active: Optional[bool] = None

class PaymentMethodResponse(PaymentMethodBase):
    id: int
    class Config:
        from_attributes = True

from pydantic import BaseModel # pyrefly: ignore [missing-import]
from typing import List, Optional # pyrefly: ignore [missing-import]
from datetime import datetime # pyrefly: ignore [missing-import]
from app.schemas.customer import CustomerResponse # pyrefly: ignore [missing-import]
from app.schemas.payment_method import PaymentMethodResponse # pyrefly: ignore [missing-import]

class OrderItemBase(BaseModel):
    product_variant_id: int
    quantity: int

class OrderItemCreate(OrderItemBase):
    pass

class OrderItemResponse(OrderItemBase):
    id: int
    order_id: int
    unit_price: float
    subtotal: float
    
    class Config:
        from_attributes = True

class OrderPaymentBase(BaseModel):
    payment_method_id: Optional[int] = None
    amount: float
    note: Optional[str] = None

class OrderPaymentCreate(OrderPaymentBase):
    pass

class OrderPaymentResponse(OrderPaymentBase):
    id: int
    order_id: int
    created_at: datetime
    payment_method: Optional[PaymentMethodResponse] = None

    class Config:
        from_attributes = True

class OrderBase(BaseModel):
    customer_id: Optional[int] = None
    payment_method_id: Optional[int] = None
    discount: float = 0.0
    tax: float = 0.0
    paid_amount: Optional[float] = None

class OrderCreate(OrderBase):
    items: List[OrderItemCreate]

class OrderResponse(OrderBase):
    id: int
    created_at: datetime
    total_amount: float
    final_amount: float
    paid_amount: float = 0.0
    due_amount: float = 0.0
    status: str
    user_id: int
    payment_method_id: Optional[int] = None
    customer: Optional[CustomerResponse] = None
    payment_method: Optional[PaymentMethodResponse] = None
    items: List[OrderItemResponse] = []
    payments: List[OrderPaymentResponse] = []
    
    class Config:
        from_attributes = True

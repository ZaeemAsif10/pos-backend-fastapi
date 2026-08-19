from sqlalchemy.orm import Session
from typing import Optional
from fastapi import HTTPException
from app.models.order import Order, OrderItem, OrderPayment
from app.models.product import ProductVariant
from app.schemas.order import OrderCreate, OrderPaymentCreate

def get_order(db: Session, order_id: int, business_id: Optional[int] = None):
    query = db.query(Order).filter(Order.id == order_id)
    if business_id is not None:
        query = query.filter(Order.business_id == business_id)
    return query.first()

def get_orders(db: Session, skip: int = 0, limit: int = 100, business_id: Optional[int] = None, branch_id: Optional[int] = None):
    query = db.query(Order)
    if business_id is not None:
        query = query.filter(Order.business_id == business_id)
    if branch_id is not None:
        query = query.filter(Order.branch_id == branch_id)
    return query.order_by(Order.created_at.desc()).offset(skip).limit(limit).all()

def create_order(db: Session, order_in: OrderCreate, user_id: int, business_id: Optional[int] = None, branch_id: Optional[int] = None):
    # 1. Calculate totals and check inventory
    total_amount = 0.0
    order_items_to_create = []
    
    for item_in in order_in.items:
        variant_query = db.query(ProductVariant).filter(ProductVariant.id == item_in.product_variant_id)
        variant = variant_query.first()
        if not variant:
            raise HTTPException(status_code=400, detail="Product variant not found")
            
        if variant.stock_quantity < item_in.quantity:
            product_name = variant.product.name if variant.product else f"Variant {variant.id}"
            raise HTTPException(
                status_code=400, 
                detail=f"Not enough stock for '{product_name}'. Available: {variant.stock_quantity}, Requested: {item_in.quantity}."
            )
            
        # Deduct stock
        variant.stock_quantity -= item_in.quantity
        
        # Calculate price
        unit_price = variant.product.base_price + variant.price_adjustment
        subtotal = unit_price * item_in.quantity
        total_amount += subtotal
        
        order_items_to_create.append({
            "product_variant_id": variant.id,
            "quantity": item_in.quantity,
            "unit_price": unit_price,
            "subtotal": subtotal
        })
        
    final_amount = max(0.0, total_amount - order_in.discount + order_in.tax)
    
    # Determine paid_amount, due_amount, and payment status
    if order_in.paid_amount is None:
        paid_amount = final_amount
    else:
        paid_amount = max(0.0, float(order_in.paid_amount))

    due_amount = max(0.0, final_amount - paid_amount)

    if due_amount <= 0.01:
        status = "Paid"
        due_amount = 0.0
    elif paid_amount > 0:
        status = "Partial"
    else:
        status = "Due"

    # 2. Create Order with business_id and branch_id
    db_order = Order(
        user_id=user_id,
        customer_id=order_in.customer_id,
        payment_method_id=order_in.payment_method_id,
        total_amount=total_amount,
        discount=order_in.discount,
        tax=order_in.tax,
        final_amount=final_amount,
        paid_amount=paid_amount,
        due_amount=due_amount,
        status=status,
        business_id=business_id,
        branch_id=branch_id
    )
    db.add(db_order)
    db.flush() # Get the order ID
    
    # 3. Create Order Items
    for item_data in order_items_to_create:
        db_item = OrderItem(
            order_id=db_order.id,
            **item_data
        )
        db.add(db_item)

    # 4. Create Initial Payment record if paid_amount > 0
    if paid_amount > 0:
        initial_payment = OrderPayment(
            order_id=db_order.id,
            payment_method_id=order_in.payment_method_id,
            amount=paid_amount,
            note="Initial Payment",
            created_at=db_order.created_at
        )
        db.add(initial_payment)
        
    db.commit()
    db.refresh(db_order)
    return db_order

def add_order_payment(db: Session, order_id: int, payment_in: OrderPaymentCreate, business_id: Optional[int] = None):
    order = get_order(db, order_id=order_id, business_id=business_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
        
    if order.due_amount <= 0:
        raise HTTPException(status_code=400, detail="This order is already fully paid.")
        
    pay_amount = min(payment_in.amount, order.due_amount)
    if pay_amount <= 0:
        raise HTTPException(status_code=400, detail="Payment amount must be greater than 0.")
        
    order.paid_amount += pay_amount
    order.due_amount = max(0.0, order.final_amount - order.paid_amount)
    
    if order.due_amount <= 0.01:
        order.due_amount = 0.0
        order.status = "Paid"
    else:
        order.status = "Partial"
        
    db_payment = OrderPayment(
        order_id=order.id,
        payment_method_id=payment_in.payment_method_id or order.payment_method_id,
        amount=pay_amount,
        note=payment_in.note or "Due Payment Collected"
    )
    db.add(db_payment)
    db.commit()
    db.refresh(order)
    return order

def get_order_payments(db: Session, order_id: int, business_id: Optional[int] = None):
    order = get_order(db, order_id=order_id, business_id=business_id)
    if not order:
        return []

    payments = db.query(OrderPayment).filter(OrderPayment.order_id == order_id).order_by(OrderPayment.created_at.asc()).all()
    recorded_sum = sum(p.amount for p in payments)

    if order.paid_amount > recorded_sum:
        missing_initial = order.paid_amount - recorded_sum
        initial_payment = OrderPayment(
            order_id=order.id,
            payment_method_id=order.payment_method_id,
            amount=missing_initial,
            note="Initial Payment",
            created_at=order.created_at
        )
        db.add(initial_payment)
        db.commit()
        payments = db.query(OrderPayment).filter(OrderPayment.order_id == order_id).order_by(OrderPayment.created_at.desc()).all()
    else:
        payments = sorted(payments, key=lambda p: p.created_at, reverse=True)

    return payments

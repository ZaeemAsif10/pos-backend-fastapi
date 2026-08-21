from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, or_
from datetime import datetime, date, timedelta, timezone

from app.db.database import get_db
from app.api.deps import get_current_active_user
from app.models.user import User, Role
from app.models.order import Order, OrderItem, OrderPayment
from app.models.product import Product, ProductVariant, Category, Brand
from app.models.customer import Customer
from app.models.branch import Branch
from app.models.business import Business
from app.models.payment_method import PaymentMethod

router = APIRouter()

def apply_tenant_filter(query, model, current_user: User, branch_id: Optional[int] = None):
    """
    Apply role-based multi-tenancy and branch filters.
    - Scopes to current_user.business_id when set.
    - If user is Branch Manager / Cashier or branch_id is specified, filter by branch_id.
    """
    user_role = current_user.role.name if current_user.role else ""
    
    if current_user.business_id:
        query = query.filter(model.business_id == current_user.business_id)
        
    if user_role in ["Branch Manager", "Cashier"] and current_user.branch_id:
        query = query.filter(model.branch_id == current_user.branch_id)
    elif branch_id:
        query = query.filter(model.branch_id == branch_id)
            
    return query


@router.get("/summary")
def get_report_summary(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    branch_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Get top-level KPI metrics (Total Sales, Net Profit, Orders Count, Customers, Inventory Value).
    """
    # 1. Base Orders Query
    orders_query = db.query(Order)
    orders_query = apply_tenant_filter(orders_query, Order, current_user, branch_id)

    if start_date:
        s_date = datetime.strptime(start_date, "%Y-%m-%d")
        orders_query = orders_query.filter(Order.created_at >= s_date)
    if end_date:
        e_date = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
        orders_query = orders_query.filter(Order.created_at < e_date)

    orders = orders_query.all()

    total_orders = len(orders)
    total_sales = sum(o.final_amount for o in orders)
    total_paid = sum(o.paid_amount for o in orders)
    total_due = sum(o.due_amount for o in orders)
    total_discount = sum(o.discount for o in orders)
    total_tax = sum(o.tax for o in orders)

    # Calculate COGS (Cost of Goods Sold) & Net Profit
    order_ids = [o.id for o in orders]
    cogs = 0.0
    if order_ids:
        items = db.query(OrderItem).filter(OrderItem.order_id.in_(order_ids)).all()
        for item in items:
            cost = 0.0
            if item.variant and item.variant.product:
                cost = item.variant.product.cost_price or 0.0
            cogs += (cost * item.quantity)

    net_profit = total_sales - cogs - total_discount

    # 2. Customers Count & Due Receivables
    cust_query = db.query(Customer)
    if current_user.business_id:
        cust_query = cust_query.filter(Customer.business_id == current_user.business_id)

    total_customers = cust_query.count()

    # 3. Inventory Valuation & Total Stock
    stock_query = db.query(ProductVariant)
    if current_user.business_id:
        stock_query = stock_query.join(Product).filter(Product.business_id == current_user.business_id)

    variants = stock_query.all()
    total_stock_qty = sum(v.stock_quantity for v in variants)
    total_inventory_value = sum((v.stock_quantity or 0) * (v.product.cost_price if v.product else 0.0) for v in variants)

    return {
        "total_sales": round(total_sales, 2),
        "total_orders": total_orders,
        "total_paid": round(total_paid, 2),
        "total_due": round(total_due, 2),
        "total_discount": round(total_discount, 2),
        "total_tax": round(total_tax, 2),
        "cogs": round(cogs, 2),
        "net_profit": round(net_profit, 2),
        "total_customers": total_customers,
        "total_stock_qty": total_stock_qty,
        "total_inventory_value": round(total_inventory_value, 2)
    }


@router.get("/sales")
def get_sales_report(
    period: str = Query("daily", pattern="^(daily|weekly|monthly)$"),
    branch_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Get sales breakdown over time and payment method distribution.
    """
    orders_query = db.query(Order)
    orders_query = apply_tenant_filter(orders_query, Order, current_user, branch_id)
    orders = orders_query.all()

    # 1. Timeline grouping
    timeline = {}
    for o in orders:
        if period == "daily":
            key = o.created_at.strftime("%Y-%m-%d") if o.created_at else "Unknown"
        elif period == "weekly":
            key = o.created_at.strftime("%Y-W%W") if o.created_at else "Unknown"
        else:
            key = o.created_at.strftime("%Y-%m") if o.created_at else "Unknown"
        
        if key not in timeline:
            timeline[key] = {"date": key, "sales": 0.0, "orders": 0, "due": 0.0}
        timeline[key]["sales"] += o.final_amount
        timeline[key]["orders"] += 1
        timeline[key]["due"] += o.due_amount

    sorted_timeline = sorted(timeline.values(), key=lambda x: x["date"])

    # 2. Payment Method Breakdown
    pm_summary = {}
    for o in orders:
        pm_name = o.payment_method.name if o.payment_method else "Cash"
        if pm_name not in pm_summary:
            pm_summary[pm_name] = 0.0
        pm_summary[pm_name] += o.final_amount

    payment_breakdown = [{"method": k, "amount": round(v, 2)} for k, v in pm_summary.items()]

    return {
        "period": period,
        "timeline": sorted_timeline,
        "payment_breakdown": payment_breakdown
    }


@router.get("/products")
def get_product_reports(
    limit: int = 10,
    branch_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Get Top Selling Products, Category Performance, and Low Stock Alerts.
    """
    # 1. Top Selling Products
    items_query = db.query(
        OrderItem.product_variant_id,
        func.sum(OrderItem.quantity).label("total_sold"),
        func.sum(OrderItem.subtotal).label("total_revenue")
    ).join(Order).filter(Order.status != "Cancelled")
    
    items_query = apply_tenant_filter(items_query, Order, current_user, branch_id)
    top_items = items_query.group_by(OrderItem.product_variant_id).order_by(desc("total_sold")).limit(limit).all()

    top_products = []
    for variant_id, qty_sold, rev in top_items:
        variant = db.query(ProductVariant).filter(ProductVariant.id == variant_id).first()
        if variant and variant.product:
            top_products.append({
                "product_name": variant.product.name,
                "sku": variant.sku,
                "variant_info": f"{variant.size or ''} {variant.color or ''}".strip(),
                "quantity_sold": qty_sold,
                "total_revenue": round(rev or 0.0, 2),
                "current_stock": variant.stock_quantity
            })

    # 2. Low Stock Alerts
    stock_query = db.query(ProductVariant).join(Product)
    if current_user.business_id:
        stock_query = stock_query.filter(Product.business_id == current_user.business_id)

    low_stock = stock_query.filter(ProductVariant.stock_quantity <= 5).order_by(ProductVariant.stock_quantity).limit(15).all()
    low_stock_list = [{
        "product_name": v.product.name if v.product else "Unknown",
        "sku": v.sku,
        "stock_quantity": v.stock_quantity,
        "category": v.product.category.name if v.product and v.product.category else "N/A"
    } for v in low_stock]

    return {
        "top_selling_products": top_products,
        "low_stock_alerts": low_stock_list
    }


@router.get("/branches")
def get_branch_performance(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Get Branch performance report for current user's business.
    """
    branch_query = db.query(Branch)
    if current_user.business_id:
        branch_query = branch_query.filter(Branch.business_id == current_user.business_id)

    branches = branch_query.all()

    branch_data = []
    for b in branches:
        orders = db.query(Order).filter(Order.branch_id == b.id).all()
        sales = sum(o.final_amount for o in orders)
        order_count = len(orders)
        
        branch_data.append({
            "branch_id": b.id,
            "branch_name": b.name,
            "business_name": b.business.name if b.business else "N/A",
            "total_sales": round(sales, 2),
            "total_orders": order_count
        })

    return branch_data

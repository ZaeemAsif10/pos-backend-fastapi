from fastapi import APIRouter, Depends # pyrefly: ignore [missing-import]
from sqlalchemy.orm import Session # pyrefly: ignore [missing-import]
from sqlalchemy import func # pyrefly: ignore [missing-import]
from datetime import datetime, date # pyrefly: ignore [missing-import]

from app.db.database import get_db # pyrefly: ignore [missing-import]
from app.models.order import Order # pyrefly: ignore [missing-import]
from app.api.deps import get_current_active_user # pyrefly: ignore [missing-import]
from app.models.user import User # pyrefly: ignore [missing-import]

router = APIRouter()

@router.get("/daily-sales")
def get_daily_sales(db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    """
    Get total sales and order count for today.
    """
    # Simple report logic
    today = date.today()
    orders = db.query(Order).filter(
        func.date(Order.created_at) == today,
        Order.status == "Completed"
    ).all()
    
    total_revenue = sum(order.final_amount for order in orders)
    
    return {
        "date": today,
        "total_orders": len(orders),
        "total_revenue": total_revenue
    }

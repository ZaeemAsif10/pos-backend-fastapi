"""Parties module for Customers, Suppliers, Delivery Areas, and Sales Targets."""
from app.modules.parties.models import (
    DeliveryArea,
    Customer,
    Supplier,
    SalesmanTarget,
)

__all__ = [
    "DeliveryArea",
    "Customer",
    "Supplier",
    "SalesmanTarget",
]

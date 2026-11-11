from typing import Optional, List, Dict, Any, Union
from datetime import datetime, date
from fastapi import APIRouter, Depends, Query, status

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.modules.auth.models import User
from app.modules.auth.router import get_current_user
from app.modules.team.services import TeamService
from app.modules.parties.schemas import (
    DeliveryAreaCreate,
    DeliveryAreaUpdate,
    DeliveryAreaResponse,
    CustomerCreate,
    CustomerUpdate,
    CustomerResponse,
    PaginatedCustomersResponse,
    CustomerStatsResponse,
    SupplierCreate,
    SupplierUpdate,
    SupplierResponse,
    PaginatedSuppliersResponse,
    SupplierStatsResponse,
    CustomerPaymentCreate,
    CustomerPaymentResponse,
    PaginatedCustomerPaymentsResponse,
    CustomerLedgerResponse,
    SupplierPaymentCreate,
    SupplierPaymentResponse,
    PaginatedSupplierPaymentsResponse,
    SupplierLedgerResponse,
    CustomerAgingReportResponse,
    SupplierAgingReportResponse,
)
from app.modules.parties.services import (
    DeliveryAreaService,
    CustomerService,
    SupplierService,
    CustomerPaymentService,
    SupplierPaymentService,
)

router = APIRouter(prefix="/tenant", tags=["Tenant Parties (Customers, Suppliers & Delivery Areas)"])




# ==========================================
# DELIVERY AREAS / ROUTES ENDPOINTS
# ==========================================
@router.get(
    "/delivery-areas",
    response_model=List[DeliveryAreaResponse],
    summary="List Delivery Areas / Routes",
)
async def list_delivery_areas(
    tenant_id: Optional[int] = Query(None, description="Optional tenant ID (for Super Admin)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all delivery routes and areas for the active tenant."""
    tenant = await TeamService.resolve_active_tenant(current_user, db, requested_tenant_id=tenant_id)
    await TeamService.verify_delivery_area_view_permission(current_user, tenant, db)
    return await DeliveryAreaService.list_delivery_areas(db, tenant.id)


@router.post(
    "/delivery-areas",
    response_model=DeliveryAreaResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Delivery Area / Route",
)
async def create_delivery_area(
    payload: DeliveryAreaCreate,
    tenant_id: Optional[int] = Query(None, description="Optional tenant ID (for Super Admin)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new delivery area or route."""
    tenant = await TeamService.resolve_active_tenant(current_user, db, requested_tenant_id=tenant_id)
    await TeamService.verify_delivery_area_create_permission(current_user, tenant, db)
    return await DeliveryAreaService.create_delivery_area(db, tenant.id, payload)


@router.get(
    "/delivery-areas/{area_id}",
    response_model=DeliveryAreaResponse,
    summary="Get Delivery Area Details",
)
async def get_delivery_area(
    area_id: int,
    tenant_id: Optional[int] = Query(None, description="Optional tenant ID (for Super Admin)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a delivery area by ID."""
    tenant = await TeamService.resolve_active_tenant(current_user, db, requested_tenant_id=tenant_id)
    await TeamService.verify_delivery_area_view_permission(current_user, tenant, db)
    area = await DeliveryAreaService.get_delivery_area(db, tenant.id, area_id)
    salesman_name = (
        area.assigned_salesman.full_name
        if area.assigned_salesman
        else None
    )
    resp = DeliveryAreaResponse.model_validate(area)
    resp.assigned_salesman_name = salesman_name
    return resp


@router.put(
    "/delivery-areas/{area_id}",
    response_model=DeliveryAreaResponse,
    summary="Update Delivery Area / Route",
)
async def update_delivery_area(
    area_id: int,
    payload: DeliveryAreaUpdate,
    tenant_id: Optional[int] = Query(None, description="Optional tenant ID (for Super Admin)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update delivery area details or assigned salesman."""
    tenant = await TeamService.resolve_active_tenant(current_user, db, requested_tenant_id=tenant_id)
    await TeamService.verify_delivery_area_edit_permission(current_user, tenant, db)
    return await DeliveryAreaService.update_delivery_area(db, tenant.id, area_id, payload)


@router.delete(
    "/delivery-areas/{area_id}",
    summary="Delete Delivery Area",
)
async def delete_delivery_area(
    area_id: int,
    tenant_id: Optional[int] = Query(None, description="Optional tenant ID (for Super Admin)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a delivery area if no customers are linked to it."""
    tenant = await TeamService.resolve_active_tenant(current_user, db, requested_tenant_id=tenant_id)
    await TeamService.verify_delivery_area_delete_permission(current_user, tenant, db)
    return await DeliveryAreaService.delete_delivery_area(db, tenant.id, area_id)


# ==========================================
# CUSTOMERS ENDPOINTS
# ==========================================
@router.get(
    "/customers/stats",
    response_model=CustomerStatsResponse,
    summary="Customer KPI Statistics",
)
async def get_customer_stats(
    tenant_id: Optional[int] = Query(None, description="Optional tenant ID (for Super Admin)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get customer overview metrics (total, receivables, overdue, credit blocked)."""
    tenant = await TeamService.resolve_active_tenant(current_user, db, requested_tenant_id=tenant_id)
    await TeamService.verify_customer_view_permission(current_user, tenant, db)
    return await CustomerService.get_customer_stats(db, tenant.id)


@router.get(
    "/customers",
    response_model=Union[PaginatedCustomersResponse, List[CustomerResponse]],
    summary="List Customers",
)
async def list_customers(
    search: Optional[str] = Query(None, description="Search by name, code, phone, or city"),
    area_id: Optional[int] = Query(None, description="Filter by delivery route/area"),
    customer_type: Optional[str] = Query(None, description="retailer, wholesaler, corporate"),
    is_active: Optional[bool] = Query(None, description="Filter by status"),
    page: Optional[int] = Query(None, ge=1, description="Page number"),
    size: Optional[int] = Query(None, ge=1, le=100, description="Items per page (default 10)"),
    tenant_id: Optional[int] = Query(None, description="Optional tenant ID (for Super Admin)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all customers with balances, route info, and status (server-paginated when page/size requested)."""
    tenant = await TeamService.resolve_active_tenant(current_user, db, requested_tenant_id=tenant_id)
    await TeamService.verify_customer_view_permission(current_user, tenant, db)
    res = await CustomerService.list_customers(
        db,
        tenant.id,
        search=search,
        area_id=area_id,
        customer_type=customer_type,
        is_active=is_active,
        page=page,
        size=size,
    )
    if page is not None or size is not None:
        items, total, p, s, total_pages = res
        return {
            "items": items,
            "total": total,
            "page": p,
            "size": s,
            "total_pages": total_pages,
        }
    return res


@router.post(
    "/customers",
    response_model=CustomerResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Customer",
)
async def create_customer(
    payload: CustomerCreate,
    tenant_id: Optional[int] = Query(None, description="Optional tenant ID (for Super Admin)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Register a new customer account."""
    tenant = await TeamService.resolve_active_tenant(current_user, db, requested_tenant_id=tenant_id)
    await TeamService.verify_customer_create_permission(current_user, tenant, db)
    return await CustomerService.create_customer(db, tenant.id, payload)


@router.get(
    "/customers/{customer_id}",
    response_model=CustomerResponse,
    summary="Get Customer Details",
)
async def get_customer(
    customer_id: int,
    tenant_id: Optional[int] = Query(None, description="Optional tenant ID (for Super Admin)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get single customer details."""
    tenant = await TeamService.resolve_active_tenant(current_user, db, requested_tenant_id=tenant_id)
    await TeamService.verify_customer_view_permission(current_user, tenant, db)
    c = await CustomerService.get_customer(db, tenant.id, customer_id)
    resp = CustomerResponse.model_validate(c)
    resp.area_name = c.area.name if c.area else None
    resp.branch_name = c.branch.name if c.branch else None
    return resp


@router.put(
    "/customers/{customer_id}",
    response_model=CustomerResponse,
    summary="Update Customer",
)
async def update_customer(
    customer_id: int,
    payload: CustomerUpdate,
    tenant_id: Optional[int] = Query(None, description="Optional tenant ID (for Super Admin)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update customer details, credit limit, or status."""
    tenant = await TeamService.resolve_active_tenant(current_user, db, requested_tenant_id=tenant_id)
    await TeamService.verify_customer_edit_permission(current_user, tenant, db)
    return await CustomerService.update_customer(db, tenant.id, customer_id, payload)


@router.delete(
    "/customers/{customer_id}",
    summary="Delete Customer",
)
async def delete_customer(
    customer_id: int,
    tenant_id: Optional[int] = Query(None, description="Optional tenant ID (for Super Admin)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete customer if balance is 0."""
    tenant = await TeamService.resolve_active_tenant(current_user, db, requested_tenant_id=tenant_id)
    await TeamService.verify_customer_delete_permission(current_user, tenant, db)
    return await CustomerService.delete_customer(db, tenant.id, customer_id)


# ==========================================
# CUSTOMER KHATA WASOOLI / PAYMENTS
# ==========================================
@router.post(
    "/customers/{customer_id}/payments",
    response_model=CustomerPaymentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record Customer Khata Payment (Wasooli)",
)
async def record_customer_payment(
    customer_id: int,
    payload: CustomerPaymentCreate,
    tenant_id: Optional[int] = Query(None, description="Optional tenant ID (for Super Admin)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Record payment received from a customer against udhaar/khata balance."""
    tenant = await TeamService.resolve_active_tenant(current_user, db, requested_tenant_id=tenant_id)
    await TeamService.verify_customer_edit_permission(current_user, tenant, db)
    return await CustomerPaymentService.record_payment(
        db=db,
        tenant_id=tenant.id,
        customer_id=customer_id,
        payload=payload,
        user_id=current_user.id,
    )


@router.get(
    "/customers/{customer_id}/payments",
    response_model=PaginatedCustomerPaymentsResponse,
    summary="List Customer Payment History",
)
async def list_customer_payments(
    customer_id: int,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    tenant_id: Optional[int] = Query(None, description="Optional tenant ID (for Super Admin)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve all payment records / CRVs for a specific customer."""
    tenant = await TeamService.resolve_active_tenant(current_user, db, requested_tenant_id=tenant_id)
    await TeamService.verify_customer_view_permission(current_user, tenant, db)
    return await CustomerPaymentService.list_payments(
        db=db,
        tenant_id=tenant.id,
        customer_id=customer_id,
        page=page,
        size=size,
    )


@router.get(
    "/customers/{customer_id}/ledger",
    response_model=CustomerLedgerResponse,
    summary="Get Customer Ledger Statement",
)
async def get_customer_ledger(
    customer_id: int,
    from_date: Optional[datetime] = Query(None, description="Start date for ledger"),
    to_date: Optional[datetime] = Query(None, description="End date for ledger"),
    tenant_id: Optional[int] = Query(None, description="Optional tenant ID (for Super Admin)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve full chronological ledger with running balance, debits, credits, and summary."""
    tenant = await TeamService.resolve_active_tenant(current_user, db, requested_tenant_id=tenant_id)
    await TeamService.verify_customer_view_permission(current_user, tenant, db)
    return await CustomerService.get_customer_ledger(
        db=db,
        tenant_id=tenant.id,
        customer_id=customer_id,
        from_date=from_date,
        to_date=to_date,
    )


@router.get(
    "/customer-payments",
    response_model=PaginatedCustomerPaymentsResponse,
    summary="List All Customer Recoveries (CRVs)",
)
async def list_all_customer_payments(
    customer_id: Optional[int] = Query(None, description="Filter by customer ID"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    tenant_id: Optional[int] = Query(None, description="Optional tenant ID (for Super Admin)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve tenant-wide customer payment vouchers."""
    tenant = await TeamService.resolve_active_tenant(current_user, db, requested_tenant_id=tenant_id)
    await TeamService.verify_customer_view_permission(current_user, tenant, db)
    return await CustomerPaymentService.list_payments(
        db=db,
        tenant_id=tenant.id,
        customer_id=customer_id,
        page=page,
        size=size,
    )


# ==========================================
# SUPPLIERS ENDPOINTS
# ==========================================
@router.get(
    "/suppliers/stats",
    response_model=SupplierStatsResponse,
    summary="Supplier KPI Statistics",
)
async def get_supplier_stats(
    tenant_id: Optional[int] = Query(None, description="Optional tenant ID (for Super Admin)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get supplier overview metrics (total, payables, active mills, bank accounts)."""
    tenant = await TeamService.resolve_active_tenant(current_user, db, requested_tenant_id=tenant_id)
    await TeamService.verify_supplier_view_permission(current_user, tenant, db)
    return await SupplierService.get_supplier_stats(db, tenant.id)


@router.get(
    "/suppliers",
    response_model=Union[PaginatedSuppliersResponse, List[SupplierResponse]],
    summary="List Suppliers",
)
async def list_suppliers(
    search: Optional[str] = Query(None, description="Search by company, code, person, phone, or city"),
    is_active: Optional[bool] = Query(None, description="Filter by status"),
    page: Optional[int] = Query(None, ge=1, description="Page number"),
    size: Optional[int] = Query(None, ge=1, le=100, description="Items per page (default 10)"),
    tenant_id: Optional[int] = Query(None, description="Optional tenant ID (for Super Admin)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all vendors and suppliers with payable balances (server-paginated when page/size requested)."""
    tenant = await TeamService.resolve_active_tenant(current_user, db, requested_tenant_id=tenant_id)
    await TeamService.verify_supplier_view_permission(current_user, tenant, db)
    res = await SupplierService.list_suppliers(
        db, tenant.id, search=search, is_active=is_active, page=page, size=size
    )
    if page is not None or size is not None:
        items, total, p, s, total_pages = res
        return {
            "items": items,
            "total": total,
            "page": p,
            "size": s,
            "total_pages": total_pages,
        }
    return res


@router.post(
    "/suppliers",
    response_model=SupplierResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Supplier",
)
async def create_supplier(
    payload: SupplierCreate,
    tenant_id: Optional[int] = Query(None, description="Optional tenant ID (for Super Admin)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Register a new supplier / vendor."""
    tenant = await TeamService.resolve_active_tenant(current_user, db, requested_tenant_id=tenant_id)
    await TeamService.verify_supplier_create_permission(current_user, tenant, db)
    return await SupplierService.create_supplier(db, tenant.id, payload)


@router.get(
    "/suppliers/{supplier_id}",
    response_model=SupplierResponse,
    summary="Get Supplier Details",
)
async def get_supplier(
    supplier_id: int,
    tenant_id: Optional[int] = Query(None, description="Optional tenant ID (for Super Admin)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get single supplier details."""
    tenant = await TeamService.resolve_active_tenant(current_user, db, requested_tenant_id=tenant_id)
    await TeamService.verify_supplier_view_permission(current_user, tenant, db)
    s = await SupplierService.get_supplier(db, tenant.id, supplier_id)
    return SupplierResponse.model_validate(s)


@router.put(
    "/suppliers/{supplier_id}",
    response_model=SupplierResponse,
    summary="Update Supplier",
)
async def update_supplier(
    supplier_id: int,
    payload: SupplierUpdate,
    tenant_id: Optional[int] = Query(None, description="Optional tenant ID (for Super Admin)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update supplier information, terms, or bank accounts."""
    tenant = await TeamService.resolve_active_tenant(current_user, db, requested_tenant_id=tenant_id)
    await TeamService.verify_supplier_edit_permission(current_user, tenant, db)
    return await SupplierService.update_supplier(db, tenant.id, supplier_id, payload)


@router.delete(
    "/suppliers/{supplier_id}",
    summary="Delete Supplier",
)
async def delete_supplier(
    supplier_id: int,
    tenant_id: Optional[int] = Query(None, description="Optional tenant ID (for Super Admin)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete supplier if payable balance is 0."""
    tenant = await TeamService.resolve_active_tenant(current_user, db, requested_tenant_id=tenant_id)
    await TeamService.verify_supplier_delete_permission(current_user, tenant, db)
    return await SupplierService.delete_supplier(db, tenant.id, supplier_id)


# ==========================================
# SUPPLIER PAYMENT (CPV) & LEDGER ENDPOINTS
# ==========================================
@router.post(
    "/suppliers/{supplier_id}/payments",
    response_model=SupplierPaymentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record Supplier Payment (CPV)",
)
async def record_supplier_payment(
    supplier_id: int,
    payload: SupplierPaymentCreate,
    tenant_id: Optional[int] = Query(None, description="Optional tenant ID (for Super Admin)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Record cash/bank payment made to a vendor/supplier against payable balance."""
    tenant = await TeamService.resolve_active_tenant(current_user, db, requested_tenant_id=tenant_id)
    await TeamService.verify_supplier_edit_permission(current_user, tenant, db)
    return await SupplierPaymentService.record_payment(
        db=db,
        tenant_id=tenant.id,
        supplier_id=supplier_id,
        payload=payload,
        user_id=current_user.id,
    )


@router.get(
    "/suppliers/{supplier_id}/payments",
    response_model=PaginatedSupplierPaymentsResponse,
    summary="List Supplier Payment History",
)
async def list_supplier_payments(
    supplier_id: int,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    tenant_id: Optional[int] = Query(None, description="Optional tenant ID (for Super Admin)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve all payment records / CPVs for a specific supplier."""
    tenant = await TeamService.resolve_active_tenant(current_user, db, requested_tenant_id=tenant_id)
    await TeamService.verify_supplier_view_permission(current_user, tenant, db)
    return await SupplierPaymentService.list_payments(
        db=db,
        tenant_id=tenant.id,
        supplier_id=supplier_id,
        page=page,
        size=size,
    )


@router.get(
    "/supplier-payments",
    response_model=PaginatedSupplierPaymentsResponse,
    summary="List All Supplier Payment Vouchers (CPVs)",
)
async def list_all_supplier_payments(
    supplier_id: Optional[int] = Query(None, description="Filter by supplier ID"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    tenant_id: Optional[int] = Query(None, description="Optional tenant ID (for Super Admin)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve tenant-wide supplier payment vouchers."""
    tenant = await TeamService.resolve_active_tenant(current_user, db, requested_tenant_id=tenant_id)
    await TeamService.verify_supplier_view_permission(current_user, tenant, db)
    return await SupplierPaymentService.list_payments(
        db=db,
        tenant_id=tenant.id,
        supplier_id=supplier_id,
        page=page,
        size=size,
    )


@router.get(
    "/suppliers/{supplier_id}/ledger",
    response_model=SupplierLedgerResponse,
    summary="Get Supplier Ledger Statement",
)
async def get_supplier_ledger(
    supplier_id: int,
    from_date: Optional[datetime] = Query(None, description="Start date for ledger"),
    to_date: Optional[datetime] = Query(None, description="End date for ledger"),
    tenant_id: Optional[int] = Query(None, description="Optional tenant ID (for Super Admin)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve full chronological vendor ledger with running balance, purchases, and payments."""
    tenant = await TeamService.resolve_active_tenant(current_user, db, requested_tenant_id=tenant_id)
    await TeamService.verify_supplier_view_permission(current_user, tenant, db)
    return await SupplierService.get_supplier_ledger(
        db=db,
        tenant_id=tenant.id,
        supplier_id=supplier_id,
        from_date=from_date,
        to_date=to_date,
    )


# ==========================================
# KHATA & AGING ANALYSIS ENDPOINTS
# ==========================================
@router.get(
    "/aging/receivables",
    response_model=CustomerAgingReportResponse,
    summary="Get Accounts Receivable (AR) Aging Analysis",
)
async def get_receivables_aging(
    branch_id: Optional[int] = Query(None, description="Filter by branch ID"),
    as_of_date: Optional[date] = Query(None, description="As of date (default: today)"),
    search: Optional[str] = Query(None, description="Search customer name, phone, code"),
    filter_type: Optional[str] = Query(None, description="Filter: 'all', 'overdue', 'high_risk'"),
    tenant_id: Optional[int] = Query(None, description="Optional tenant ID (for Super Admin)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve standard 5-bucket Accounts Receivable (AR) Khata Aging Analysis."""
    tenant = await TeamService.resolve_active_tenant(current_user, db, requested_tenant_id=tenant_id)
    await TeamService.verify_aging_view_permission(current_user, tenant, db)
    return await CustomerService.get_receivables_aging(
        db=db,
        tenant_id=tenant.id,
        branch_id=branch_id,
        as_of_date=as_of_date,
        search=search,
        filter_type=filter_type,
    )


@router.post(
    "/customers/{customer_id}/toggle-credit-block",
    response_model=CustomerResponse,
    summary="Toggle Customer Credit Block / Freeze",
)
async def toggle_customer_credit_block(
    customer_id: int,
    tenant_id: Optional[int] = Query(None, description="Optional tenant ID (for Super Admin)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Freeze or unfreeze credit facilities for a customer."""
    tenant = await TeamService.resolve_active_tenant(current_user, db, requested_tenant_id=tenant_id)
    await TeamService.verify_aging_credit_block_permission(current_user, tenant, db)
    return await CustomerService.toggle_credit_block(
        db=db,
        tenant_id=tenant.id,
        customer_id=customer_id,
    )


@router.get(
    "/aging/payables",
    response_model=SupplierAgingReportResponse,
    summary="Get Accounts Payable (AP) Aging Analysis",
)
async def get_payables_aging(
    branch_id: Optional[int] = Query(None, description="Filter by branch ID"),
    as_of_date: Optional[date] = Query(None, description="As of date (default: today)"),
    search: Optional[str] = Query(None, description="Search supplier company, phone, code"),
    filter_type: Optional[str] = Query(None, description="Filter: 'all', 'overdue'"),
    tenant_id: Optional[int] = Query(None, description="Optional tenant ID (for Super Admin)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve standard 5-bucket Accounts Payable (AP) Vendor Aging Analysis."""
    tenant = await TeamService.resolve_active_tenant(current_user, db, requested_tenant_id=tenant_id)
    await TeamService.verify_aging_view_permission(current_user, tenant, db)
    return await SupplierService.get_payables_aging(
        db=db,
        tenant_id=tenant.id,
        branch_id=branch_id,
        as_of_date=as_of_date,
        search=search,
        filter_type=filter_type,
    )


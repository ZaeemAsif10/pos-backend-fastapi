from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.modules.auth.models import User
from app.modules.auth.router import get_current_user
from app.modules.team.services import TeamService
from app.modules.inventory.schemas import (
    PurchaseCreate,
    PurchaseReturnRequest,
    PurchaseResponse,
    PurchaseDetailResponse,
    PurchaseStatsResponse,
    LiveInventoryItem,
    StockMovementResponse,
    StockTransferCreate,
    StockTransferResponse,
    StockAdjustmentCreate,
    StockAdjustmentResponse,
)
from app.modules.inventory.services import (
    PurchaseService,
    InventoryService,
)

router = APIRouter(prefix="/tenant", tags=["Tenant Purchases, Inventory & Stock Movements"])


# ==========================================
# PURCHASES ENDPOINTS
# ==========================================
@router.get(
    "/purchases/stats",
    response_model=PurchaseStatsResponse,
    summary="Purchases KPI Metrics",
)
async def get_purchase_stats(
    tenant_id: Optional[int] = Query(None, description="Optional tenant ID (for Super Admin)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get purchases summary metrics (total volume, monthly volume, unpaid payables)."""
    tenant = await TeamService.resolve_active_tenant(current_user, db, requested_tenant_id=tenant_id)
    await TeamService.verify_purchase_view_permission(current_user, tenant, db)
    return await PurchaseService.get_purchase_stats(db, tenant.id)


@router.get(
    "/purchases",
    response_model=List[PurchaseResponse],
    summary="List Purchase Bills & GRN",
)
async def list_purchases(
    branch_id: Optional[int] = Query(None, description="Filter by receiving branch"),
    supplier_id: Optional[int] = Query(None, description="Filter by vendor"),
    payment_status: Optional[str] = Query(None, description="paid, partial, unpaid"),
    search: Optional[str] = Query(None, description="Search by invoice # or supplier bill #"),
    tenant_id: Optional[int] = Query(None, description="Optional tenant ID (for Super Admin)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List purchase bills with supplier and branch metadata."""
    tenant = await TeamService.resolve_active_tenant(current_user, db, requested_tenant_id=tenant_id)
    await TeamService.verify_purchase_view_permission(current_user, tenant, db)
    return await PurchaseService.list_purchases(
        db, tenant.id, branch_id=branch_id, supplier_id=supplier_id, payment_status=payment_status, search=search
    )


@router.post(
    "/purchases",
    response_model=PurchaseResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create & Post Purchase Bill",
)
async def create_purchase(
    payload: PurchaseCreate,
    tenant_id: Optional[int] = Query(None, description="Optional tenant ID (for Super Admin)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create purchase bill, increment branch stock, post stock ledger, and update supplier payable."""
    tenant = await TeamService.resolve_active_tenant(current_user, db, requested_tenant_id=tenant_id)
    await TeamService.verify_purchase_create_permission(current_user, tenant, db)
    return await PurchaseService.create_purchase(db, tenant.id, current_user.id, payload)


@router.get(
    "/purchases/{purchase_id}",
    response_model=PurchaseDetailResponse,
    summary="Get Purchase Bill Details",
)
async def get_purchase(
    purchase_id: int,
    tenant_id: Optional[int] = Query(None, description="Optional tenant ID (for Super Admin)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get single purchase invoice with full line items breakdown."""
    tenant = await TeamService.resolve_active_tenant(current_user, db, requested_tenant_id=tenant_id)
    await TeamService.verify_purchase_view_permission(current_user, tenant, db)
    return await PurchaseService.get_purchase_detail(db, tenant.id, purchase_id)


@router.delete(
    "/purchases/{purchase_id}",
    summary="Cancel / Reverse Purchase Bill",
)
async def delete_purchase(
    purchase_id: int,
    tenant_id: Optional[int] = Query(None, description="Optional tenant ID (for Super Admin)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Cancel purchase bill, decrement branch stock, and reverse supplier payable balance."""
    tenant = await TeamService.resolve_active_tenant(current_user, db, requested_tenant_id=tenant_id)
    await TeamService.verify_purchase_delete_permission(current_user, tenant, db)
    return await PurchaseService.delete_purchase(db, tenant.id, purchase_id)


@router.post(
    "/purchases/{purchase_id}/return",
    response_model=PurchaseDetailResponse,
    summary="Process Purchase Return / Debit Note",
)
async def return_purchase(
    purchase_id: int,
    payload: Optional[PurchaseReturnRequest] = None,
    tenant_id: Optional[int] = Query(None, description="Optional tenant ID (for Super Admin)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Process full return to supplier (Debit Note):
    Deducts stock, reverses supplier payable, and auto-posts balanced Debit Note JV.
    """
    tenant = await TeamService.resolve_active_tenant(current_user, db, requested_tenant_id=tenant_id)
    await TeamService.verify_purchase_create_permission(current_user, tenant, db)
    reason = payload.reason if payload and payload.reason else "Goods Returned to Supplier / Debit Note"
    refund_method = payload.refund_payment_method if payload and payload.refund_payment_method else "cash"
    p = await PurchaseService.return_purchase(
        db,
        tenant.id,
        purchase_id,
        user_id=current_user.id,
        reason=reason,
        refund_payment_method=refund_method,
    )
    return await PurchaseService.get_purchase_detail(db, tenant.id, p.id)



# ==========================================
# LIVE INVENTORY & STOCK LEDGER ENDPOINTS
# ==========================================
@router.get(
    "/inventory",
    response_model=List[LiveInventoryItem],
    summary="Live Branch Inventory Master",
)
async def list_live_inventory(
    branch_id: Optional[int] = Query(None, description="Filter by branch"),
    category_id: Optional[int] = Query(None, description="Filter by category"),
    brand_id: Optional[int] = Query(None, description="Filter by brand"),
    stock_status: Optional[str] = Query(None, description="'In Stock', 'Low Stock', 'Out of Stock'"),
    search: Optional[str] = Query(None, description="Search product name, SKU, or barcode"),
    tenant_id: Optional[int] = Query(None, description="Optional tenant ID (for Super Admin)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List real-time product stock levels across branches with reorder alerts."""
    tenant = await TeamService.resolve_active_tenant(current_user, db, requested_tenant_id=tenant_id)
    await TeamService.verify_inventory_view_permission(current_user, tenant, db)
    return await InventoryService.list_live_inventory(
        db, tenant.id, branch_id=branch_id, category_id=category_id, brand_id=brand_id, stock_status=stock_status, search=search
    )


@router.get(
    "/inventory/{product_id}/ledger",
    response_model=List[StockMovementResponse],
    summary="Product Stock Ledger (Bin Card)",
)
async def get_product_ledger(
    product_id: int,
    branch_id: Optional[int] = Query(None, description="Optional branch filter"),
    tenant_id: Optional[int] = Query(None, description="Optional tenant ID (for Super Admin)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get complete audit trail of stock movements (IN/OUT) for a product."""
    tenant = await TeamService.resolve_active_tenant(current_user, db, requested_tenant_id=tenant_id)
    await TeamService.verify_inventory_view_permission(current_user, tenant, db)
    return await InventoryService.get_product_ledger(db, tenant.id, product_id, branch_id=branch_id)


# ==========================================
# STOCK TRANSFERS & ADJUSTMENTS ENDPOINTS
# ==========================================
@router.post(
    "/stock/transfers",
    response_model=StockTransferResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Inter-Branch Stock Transfer",
)
async def create_stock_transfer(
    payload: StockTransferCreate,
    tenant_id: Optional[int] = Query(None, description="Optional tenant ID (for Super Admin)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Transfer stock atomically between branches."""
    tenant = await TeamService.resolve_active_tenant(current_user, db, requested_tenant_id=tenant_id)
    await TeamService.verify_stock_transfer_permission(current_user, tenant, db)
    return await InventoryService.create_stock_transfer(db, tenant.id, current_user.id, payload)


@router.post(
    "/stock/adjustments",
    response_model=StockAdjustmentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Post Stock Adjustment",
)
async def create_stock_adjustment(
    payload: StockAdjustmentCreate,
    tenant_id: Optional[int] = Query(None, description="Optional tenant ID (for Super Admin)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Post stock adjustment for damage, expiry, or audit corrections."""
    tenant = await TeamService.resolve_active_tenant(current_user, db, requested_tenant_id=tenant_id)
    await TeamService.verify_inventory_adjust_permission(current_user, tenant, db)
    return await InventoryService.create_stock_adjustment(db, tenant.id, current_user.id, payload)

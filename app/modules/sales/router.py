from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.modules.auth.router import get_current_user
from app.modules.auth.models import User
from app.modules.team.services import TeamService
from app.modules.sales.schemas import (
    SalesCheckoutRequest,
    SalesRefundRequest,
    SalesInvoiceResponse,
    PaginatedSalesInvoiceResponse,
    SalesSummaryStats,
    POSShiftOpenRequest,
    POSShiftCloseRequest,
    POSShiftResponse,
    DayBookResponse,
)
from app.modules.sales.services import SalesService

router = APIRouter(prefix="/tenant/sales", tags=["Sales & POS"])


def _format_invoice(inv) -> dict:
    return {
        "id": inv.id,
        "tenant_id": inv.tenant_id,
        "branch_id": inv.branch_id,
        "branch_name": inv.branch.name if getattr(inv, "branch", None) else None,
        "customer_id": inv.customer_id,
        "customer_name": inv.customer_name or (inv.customer.business_name if getattr(inv, "customer", None) and hasattr(inv.customer, "business_name") else "Walk-in Retail Buyer"),
        "customer_phone": inv.customer_phone or (inv.customer.phone if getattr(inv, "customer", None) else None),
        "customer_ntn_cnic": inv.customer_ntn_cnic or (getattr(inv.customer, "cnic", None) or getattr(inv.customer, "ntn", None) if getattr(inv, "customer", None) else None),
        "invoice_number": inv.invoice_number,
        "sale_type": inv.sale_type,
        "invoice_date": inv.invoice_date,
        "payment_method": inv.payment_method,
        "payment_status": inv.payment_status,
        "subtotal": float(inv.subtotal),
        "discount_amount": float(inv.discount_amount),
        "tax_amount": float(inv.tax_amount),
        "total_amount": float(inv.total_amount),
        "paid_amount": float(inv.paid_amount),
        "change_amount": float(inv.change_amount),
        "balance_due": float(inv.balance_due),
        "fbr_pos_id": inv.fbr_pos_id,
        "fbr_invoice_number": inv.fbr_invoice_number,
        "fbr_qr_code": inv.fbr_qr_code,
        "fbr_status": inv.fbr_status,
        "fbr_response_message": inv.fbr_response_message,
        "fbr_synced_at": inv.fbr_synced_at,
        "status": inv.status,
        "notes": inv.notes,
        "cashier_name": inv.created_by.full_name if getattr(inv, "created_by", None) else None,
        "created_at": inv.created_at,
        "updated_at": inv.updated_at,
        "items": [
            {
                "id": it.id,
                "product_id": it.product_id,
                "product_name": it.product.name if getattr(it, "product", None) else None,
                "sku": it.product.sku if getattr(it, "product", None) else None,
                "barcode": it.product.barcode if getattr(it, "product", None) else None,
                "uom_id": it.uom_id,
                "uom_name": it.uom_name,
                "quantity": float(it.quantity),
                "unit_price": float(it.unit_price),
                "cost_price": float(it.cost_price),
                "discount_amount": float(it.discount_amount),
                "tax_rate": float(it.tax_rate),
                "tax_amount": float(it.tax_amount),
                "pct_code": it.pct_code,
                "total_amount": float(it.total_amount),
            }
            for it in (inv.items or [])
        ],
        "payments": [
            {
                "id": p.id,
                "payment_method": p.payment_method,
                "amount": float(p.amount),
                "reference_no": p.reference_no,
                "payment_date": p.payment_date,
            }
            for p in (inv.payments or [])
        ],
    }


@router.post("/checkout", response_model=SalesInvoiceResponse, status_code=status.HTTP_201_CREATED)
async def checkout_sale(
    data: SalesCheckoutRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new POS or Sales invoice with real-time stock deduction and FBR integration."""
    tenant = await TeamService.resolve_active_tenant(current_user, db)
    inv = await SalesService.checkout(
        db=db,
        tenant_id=tenant.id,
        user_id=current_user.id,
        data=data,
        fbr_mode="mock",
    )
    full_inv = await SalesService.get_invoice(db, tenant.id, inv.id)
    return _format_invoice(full_inv)


@router.get("/invoices", response_model=PaginatedSalesInvoiceResponse)
async def list_sales_invoices(
    branch_id: Optional[int] = None,
    fbr_status: Optional[str] = None,
    payment_status: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(10, ge=1, le=100, description="Items per page (default 10)"),
    limit: Optional[int] = Query(None, description="Legacy limit parameter"),
    offset: Optional[int] = Query(None, description="Legacy offset parameter"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List sales invoices with customer, FBR status, and server-side pagination (default 10 records)."""
    tenant = await TeamService.resolve_active_tenant(current_user, db)

    # Legacy translation if limit/offset were passed
    effective_size = limit if limit is not None else size
    effective_page = ((offset // effective_size) + 1) if (offset is not None and effective_size > 0) else page

    items, total, current_p, total_pages = await SalesService.list_invoices(
        db=db,
        tenant_id=tenant.id,
        branch_id=branch_id,
        fbr_status=fbr_status,
        payment_status=payment_status,
        status=status,
        search=search,
        page=effective_page,
        size=effective_size,
    )
    return {
        "items": [_format_invoice(i) for i in items],
        "total": total,
        "page": current_p,
        "size": effective_size,
        "total_pages": total_pages,
    }


@router.get("/invoices/{invoice_id}", response_model=SalesInvoiceResponse)
async def get_sales_invoice(
    invoice_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve full sales invoice details with line items and FBR fiscal QR code."""
    tenant = await TeamService.resolve_active_tenant(current_user, db)
    inv = await SalesService.get_invoice(db, tenant.id, invoice_id)
    if not inv:
        raise HTTPException(status_code=404, detail="Sales invoice not found")
    return _format_invoice(inv)


@router.post("/invoices/{invoice_id}/refund", response_model=SalesInvoiceResponse)
async def refund_sales_invoice(
    invoice_id: int,
    data: Optional[SalesRefundRequest] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Process full sales return / credit note refund:
    Restores stock, adjusts customer balance, and auto-posts reversing Credit Note JV.
    """
    tenant = await TeamService.resolve_active_tenant(current_user, db)
    perms = await TeamService.get_user_permissions_in_tenant(current_user, tenant.id, db)
    if not any(p in perms for p in ["*", "sales:refund", "sales:create", "sales:manage"]):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. You do not have permission to refund sales invoices.",
        )

    reason = (data.reason if data and data.reason else None) or "Customer Return / Refund"
    refunded_inv = await SalesService.refund_invoice(
        db=db,
        tenant_id=tenant.id,
        user_id=current_user.id,
        invoice_id=invoice_id,
        reason=reason,
    )
    full_inv = await SalesService.get_invoice(db, tenant.id, refunded_inv.id)
    return _format_invoice(full_inv)



@router.get("/summary", response_model=SalesSummaryStats)
async def get_sales_summary(
    branch_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get today's sales, cash collections, and pending FBR count."""
    tenant = await TeamService.resolve_active_tenant(current_user, db)
    return await SalesService.get_sales_summary(db, tenant.id, branch_id)


# ================= POS Shift / Counter Register Endpoints =================
@router.post("/shifts/open", response_model=POSShiftResponse)
async def open_pos_shift(
    data: POSShiftOpenRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Open a new POS shift session for cashier."""
    tenant = await TeamService.resolve_active_tenant(current_user, db)
    shift = await SalesService.open_shift(db, tenant.id, current_user.id, data)
    return shift


@router.post("/shifts/{shift_id}/close", response_model=POSShiftResponse)
async def close_pos_shift(
    shift_id: int,
    data: POSShiftCloseRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Close an active shift and reconcile cash differences."""
    tenant = await TeamService.resolve_active_tenant(current_user, db)
    return await SalesService.close_shift(db, tenant.id, current_user.id, shift_id, data)


@router.get("/shifts/current", response_model=Optional[POSShiftResponse])
async def get_current_shift(
    branch_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Check if the cashier has an active open shift."""
    tenant = await TeamService.resolve_active_tenant(current_user, db)
    return await SalesService.get_current_shift(db, tenant.id, current_user.id, branch_id)


# ================= Day Book / Roznamcha (Cash & Bank Book) =================
@router.get("/daybook", response_model=DayBookResponse)
async def get_day_book(
    date_val: Optional[str] = Query(None, alias="date", description="Target date YYYY-MM-DD"),
    branch_id: Optional[int] = Query(None, description="Optional branch filter"),
    payment_method: Optional[str] = Query(None, description="Optional payment method filter (cash, bank_transfer, all)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Day Book / Roznamcha (Cash & Bank Book) statement for a given date and branch.
    Consolidates Cash Sales, Customer Receipts, and Supplier Payments.
    Enforces 'daybook:view' and 'daybook:all_branches' permissions.
    """
    tenant = await TeamService.resolve_active_tenant(current_user, db)

    # Verify Day Book view permission
    perms = await TeamService.get_user_permissions_in_tenant(current_user, tenant.id, db)
    if not any(p in perms for p in ["*", "daybook:view", "sales:view"]):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. You do not have permission to view the Day Book.",
        )

    # Branch restriction: if user cannot view all branches, restrict to their active branch
    has_all_branches = any(p in perms for p in ["*", "daybook:all_branches"])
    if not has_all_branches:
        active_shift = await SalesService.get_current_shift(db, tenant.id, current_user.id)
        if active_shift:
            if branch_id and branch_id != active_shift.branch_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied. You are only permitted to view your assigned branch's Day Book.",
                )
            branch_id = active_shift.branch_id

    target_date = datetime.now(timezone.utc).date()
    if date_val:
        try:
            target_date = datetime.strptime(date_val, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid date format. Please provide YYYY-MM-DD",
            )

    return await SalesService.get_day_book(
        db=db,
        tenant_id=tenant.id,
        target_date=target_date,
        branch_id=branch_id,
        payment_method_filter=payment_method,
    )


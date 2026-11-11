from datetime import date
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.modules.auth.router import get_current_user
from app.modules.auth.models import User
from app.modules.team.services import TeamService
from app.modules.accounting.schemas import (
    AccountCreate,
    AccountUpdate,
    AccountItem,
    AccountTreeNode,
    TenantAccountingSettingsUpdate,
    TenantAccountingSettingsResponse,
    JournalEntryCreate,
    JournalEntryItem,
    PaginatedJournalEntriesResponse,
    GeneralLedgerAccountReport,
    TrialBalanceResponse,
    ProfitAndLossResponse,
    BalanceSheetResponse,
    ExpenseVoucherCreate,
    ExpenseVoucherItem,
    PaginatedExpenseVouchersResponse,
    ExpenseSummaryResponse,
    YearEndClosingPreviewResponse,
    YearEndClosingExecuteRequest,
    YearEndClosingExecuteResponse,
    BankReconcilableAccountItem,
    BankReconciliationCreateRequest,
    BankReconciliationTransactionItem,
    BankReconciliationSummary,
    BankReconciliationDetailResponse,
    BankReconciliationMatchRequest,
    BankReconciliationCompleteRequest,
)
from app.modules.accounting.services import AccountingService

router = APIRouter(prefix="/tenant/accounting", tags=["Double-Entry Accounting"])


async def _verify_perm(user: User, tenant_id: int, db: AsyncSession, required: List[str]):
    perms = await TeamService.get_user_permissions_in_tenant(user, tenant_id, db)
    allowed = {"*"} | set(required)
    if not any(p in perms for p in allowed):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Insufficient accounting permissions.",
        )


# ================= 1. Chart of Accounts Endpoints =================
@router.get("/accounts", response_model=List[AccountItem])
async def list_accounts(
    account_type: Optional[str] = Query(None, description="asset, liability, equity, revenue, expense"),
    search: Optional[str] = Query(None, description="Search by code or name"),
    active_only: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List Chart of Accounts with real-time computed balances."""
    tenant = await TeamService.resolve_active_tenant(current_user, db)
    await _verify_perm(current_user, tenant.id, db, ["accounting:accounts:view"])
    return await AccountingService.list_accounts(
        db=db,
        tenant_id=tenant.id,
        account_type=account_type,
        search=search,
        active_only=active_only,
    )


@router.get("/accounts/tree", response_model=List[AccountTreeNode])
async def get_account_tree(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get hierarchical Chart of Accounts tree structure."""
    tenant = await TeamService.resolve_active_tenant(current_user, db)
    await _verify_perm(current_user, tenant.id, db, ["accounting:accounts:view"])
    return await AccountingService.get_account_tree(db=db, tenant_id=tenant.id)


@router.post("/accounts", response_model=AccountItem)
async def create_account(
    payload: AccountCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new custom account in Chart of Accounts."""
    tenant = await TeamService.resolve_active_tenant(current_user, db)
    await _verify_perm(current_user, tenant.id, db, ["accounting:accounts:create"])
    acc = await AccountingService.create_account(db=db, tenant_id=tenant.id, data=payload)
    return AccountItem(
        id=acc.id,
        tenant_id=acc.tenant_id,
        code=acc.code,
        name=acc.name,
        account_type=acc.account_type,
        sub_type=acc.sub_type,
        parent_id=acc.parent_id,
        parent_name=acc.parent.name if acc.parent else None,
        currency=acc.currency,
        is_system=acc.is_system,
        is_active=acc.is_active,
        description=acc.description,
        current_balance=0.0,
        created_at=acc.created_at,
    )


@router.put("/accounts/{account_id}", response_model=AccountItem)
async def update_account(
    account_id: int,
    payload: AccountUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update custom account details."""
    tenant = await TeamService.resolve_active_tenant(current_user, db)
    await _verify_perm(current_user, tenant.id, db, ["accounting:accounts:edit"])
    acc = await AccountingService.update_account(db=db, tenant_id=tenant.id, account_id=account_id, data=payload)
    return AccountItem(
        id=acc.id,
        tenant_id=acc.tenant_id,
        code=acc.code,
        name=acc.name,
        account_type=acc.account_type,
        sub_type=acc.sub_type,
        parent_id=acc.parent_id,
        parent_name=acc.parent.name if acc.parent else None,
        currency=acc.currency,
        is_system=acc.is_system,
        is_active=acc.is_active,
        description=acc.description,
        current_balance=0.0,
        created_at=acc.created_at,
    )


@router.delete("/accounts/{account_id}")
async def delete_account(
    account_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a custom non-system account."""
    tenant = await TeamService.resolve_active_tenant(current_user, db)
    await _verify_perm(current_user, tenant.id, db, ["accounting:accounts:delete"])
    await AccountingService.delete_account(db=db, tenant_id=tenant.id, account_id=account_id)
    return {"message": "Account deleted successfully."}


# ================= 2. Account Mapping Configuration (The 1 Screen) =================
@router.get("/settings", response_model=TenantAccountingSettingsResponse)
async def get_accounting_settings(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Fetch current Account Mapping and Auto-Posting preferences."""
    tenant = await TeamService.resolve_active_tenant(current_user, db)
    await _verify_perm(
        current_user,
        tenant.id,
        db,
        ["accounting:mappings:view", "accounting:mappings:save"],
    )
    return await AccountingService.get_tenant_settings(db=db, tenant_id=tenant.id)


@router.put("/settings", response_model=TenantAccountingSettingsResponse)
async def update_accounting_settings(
    payload: TenantAccountingSettingsUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update Account Mapping configuration on the single setup screen."""
    tenant = await TeamService.resolve_active_tenant(current_user, db)
    await _verify_perm(current_user, tenant.id, db, ["accounting:mappings:save"])
    return await AccountingService.update_tenant_settings(db=db, tenant_id=tenant.id, data=payload)


# ================= 3. General Journal Vouchers Endpoints =================
@router.get("/journal", response_model=PaginatedJournalEntriesResponse)
async def list_journal_entries(
    branch_id: Optional[int] = Query(None),
    source_type: Optional[str] = Query(None),
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List paginated General Journal Vouchers with full line details."""
    tenant = await TeamService.resolve_active_tenant(current_user, db)
    await _verify_perm(current_user, tenant.id, db, ["accounting:journal:view"])
    return await AccountingService.list_journal_entries(
        db=db,
        tenant_id=tenant.id,
        branch_id=branch_id,
        source_type=source_type,
        from_date=from_date,
        to_date=to_date,
        search=search,
        page=page,
        page_size=page_size,
    )


@router.post("/journal", response_model=JournalEntryItem)
async def create_journal_entry(
    payload: JournalEntryCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Post a manual balanced Journal Voucher (JV). Enforces Debit == Credit."""
    tenant = await TeamService.resolve_active_tenant(current_user, db)
    await _verify_perm(current_user, tenant.id, db, ["accounting:journal:create"])
    jv = await AccountingService.create_journal_entry(
        db=db,
        tenant_id=tenant.id,
        user_id=current_user.id,
        data=payload,
        source_type="manual_jv",
    )
    # Fetch populated
    paginated = await AccountingService.list_journal_entries(db=db, tenant_id=tenant.id, search=jv.entry_number, page=1, page_size=1)
    if paginated.items:
        return paginated.items[0]
    raise HTTPException(status_code=500, detail="Failed to retrieve posted journal voucher.")


# ================= 4. Financial Statements & Ledger Reports =================
@router.get("/ledger/{account_id}", response_model=GeneralLedgerAccountReport)
async def get_general_ledger(
    account_id: int,
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
    branch_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """General Ledger statement for a specific account with running balance."""
    tenant = await TeamService.resolve_active_tenant(current_user, db)
    await _verify_perm(current_user, tenant.id, db, ["accounting:ledger:view"])
    return await AccountingService.get_general_ledger(
        db=db,
        tenant_id=tenant.id,
        account_id=account_id,
        from_date=from_date,
        to_date=to_date,
        branch_id=branch_id,
    )


@router.get("/trial-balance", response_model=TrialBalanceResponse)
async def get_trial_balance(
    as_of_date: Optional[date] = Query(None),
    branch_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Double-entry Trial Balance verifying sum(Debit) == sum(Credit)."""
    tenant = await TeamService.resolve_active_tenant(current_user, db)
    await _verify_perm(current_user, tenant.id, db, ["accounting:trial_balance:view"])
    return await AccountingService.get_trial_balance(
        db=db,
        tenant_id=tenant.id,
        as_of_date=as_of_date,
        branch_id=branch_id,
    )


@router.get("/profit-and-loss", response_model=ProfitAndLossResponse)
async def get_profit_and_loss(
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
    branch_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    IFRS/GAAP Profit & Loss Statement (Income Statement).
    Revenue - COGS = Gross Profit - Operating Expenses = Net Profit.
    """
    tenant = await TeamService.resolve_active_tenant(current_user, db)
    await _verify_perm(
        current_user,
        tenant.id,
        db,
        ["accounting:financial_statements:view", "accounting:trial_balance:view"],
    )
    return await AccountingService.get_profit_and_loss(
        db=db,
        tenant_id=tenant.id,
        from_date=from_date,
        to_date=to_date,
        branch_id=branch_id,
    )


@router.get("/balance-sheet", response_model=BalanceSheetResponse)
async def get_balance_sheet(
    as_of_date: Optional[date] = Query(None),
    branch_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    IFRS/GAAP Balance Sheet (Statement of Financial Position).
    Enforces strict invariant: Total Assets == Total Liabilities + Total Equity.
    """
    tenant = await TeamService.resolve_active_tenant(current_user, db)
    await _verify_perm(
        current_user,
        tenant.id,
        db,
        ["accounting:financial_statements:view", "accounting:trial_balance:view"],
    )
    return await AccountingService.get_balance_sheet(
        db=db,
        tenant_id=tenant.id,
        as_of_date=as_of_date,
        branch_id=branch_id,
    )


# ================= 5. Direct Expense Voucher Endpoints =================
@router.post("/expenses", response_model=ExpenseVoucherItem)
async def create_expense_voucher(
    payload: ExpenseVoucherCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Record an operational expense voucher (CPV).
    Automatically creates balanced double-entry JV: Dr Expense, Cr Cash/Bank.
    """
    tenant = await TeamService.resolve_active_tenant(current_user, db)
    await _verify_perm(current_user, tenant.id, db, ["accounting:expenses:create"])
    return await AccountingService.create_expense_voucher(
        db=db,
        tenant_id=tenant.id,
        user_id=current_user.id,
        data=payload,
    )


@router.get("/expenses", response_model=PaginatedExpenseVouchersResponse)
async def list_expense_vouchers(
    branch_id: Optional[int] = Query(None),
    expense_account_id: Optional[int] = Query(None),
    payment_method: Optional[str] = Query(None),
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List paginated expense vouchers with filters."""
    tenant = await TeamService.resolve_active_tenant(current_user, db)
    await _verify_perm(current_user, tenant.id, db, ["accounting:expenses:view"])
    return await AccountingService.list_expense_vouchers(
        db=db,
        tenant_id=tenant.id,
        branch_id=branch_id,
        expense_account_id=expense_account_id,
        payment_method=payment_method,
        from_date=from_date,
        to_date=to_date,
        search=search,
        page=page,
        page_size=page_size,
    )


@router.get("/expenses/summary", response_model=ExpenseSummaryResponse)
async def get_expense_summary(
    branch_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get expense KPI totals (today, month, cash, bank) and category breakdown."""
    tenant = await TeamService.resolve_active_tenant(current_user, db)
    await _verify_perm(current_user, tenant.id, db, ["accounting:expenses:view"])
    return await AccountingService.get_expense_summary(
        db=db,
        tenant_id=tenant.id,
        branch_id=branch_id,
    )


@router.get("/expenses/{expense_id}", response_model=ExpenseVoucherItem)
async def get_expense_voucher(
    expense_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Fetch single expense voucher details."""
    tenant = await TeamService.resolve_active_tenant(current_user, db)
    await _verify_perm(current_user, tenant.id, db, ["accounting:expenses:view"])
    return await AccountingService.get_expense_voucher(
        db=db,
        tenant_id=tenant.id,
        expense_id=expense_id,
    )


@router.delete("/expenses/{expense_id}")
async def cancel_expense_voucher(
    expense_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Cancel/void an expense voucher and its corresponding journal entry."""
    tenant = await TeamService.resolve_active_tenant(current_user, db)
    await _verify_perm(current_user, tenant.id, db, ["accounting:expenses:delete"])
    success = await AccountingService.cancel_expense_voucher(
        db=db,
        tenant_id=tenant.id,
        expense_id=expense_id,
        user_id=current_user.id,
    )
    return {"success": success, "message": "Expense voucher cancelled successfully."}


# ================= 6. Fiscal Year Closing Endpoints =================
@router.get("/closing/preview", response_model=YearEndClosingPreviewResponse)
async def preview_year_end_closing(
    closing_date: date = Query(..., description="Fiscal year end date (YYYY-MM-DD)"),
    branch_id: Optional[int] = Query(None, description="Optional branch scope"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Preview fiscal year closing calculations, temporary accounts to zero, and retained earnings impact."""
    tenant = await TeamService.resolve_active_tenant(current_user, db)
    await _verify_perm(current_user, tenant.id, db, ["accounting:financial_statements:view", "accounting:close_year"])
    return await AccountingService.preview_fiscal_year_closing(
        db=db,
        tenant_id=tenant.id,
        closing_date=closing_date,
        branch_id=branch_id,
    )


@router.post("/closing/execute", response_model=YearEndClosingExecuteResponse)
async def execute_year_end_closing(
    payload: YearEndClosingExecuteRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Post the formal fiscal year closing journal voucher zeroing temporary accounts and crediting retained earnings."""
    tenant = await TeamService.resolve_active_tenant(current_user, db)
    await _verify_perm(current_user, tenant.id, db, ["accounting:close_year", "accounting:manage"])
    return await AccountingService.execute_fiscal_year_closing(
        db=db,
        tenant_id=tenant.id,
        user_id=current_user.id,
        closing_date=payload.closing_date,
        branch_id=payload.branch_id,
        notes=payload.notes,
    )


# ================= 7. Bank Reconciliation (BRS) Endpoints =================
@router.get("/reconciliations/accounts", response_model=List[BankReconcilableAccountItem])
async def get_reconcilable_bank_accounts(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Fetch all bank accounts eligible for reconciliation with current balance and pending unreconciled count."""
    tenant = await TeamService.resolve_active_tenant(current_user, db)
    await _verify_perm(current_user, tenant.id, db, ["accounting:accounts:view", "accounting:reconciliation:view"])
    return await AccountingService.get_reconcilable_bank_accounts(db=db, tenant_id=tenant.id)


@router.get("/reconciliations", response_model=List[BankReconciliationSummary])
async def list_bank_reconciliations(
    account_id: Optional[int] = Query(None, description="Optional bank account ID filter"),
    status: Optional[str] = Query(None, description="in_progress, completed, cancelled"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List historical and active Bank Reconciliation Statement (BRS) sessions."""
    tenant = await TeamService.resolve_active_tenant(current_user, db)
    await _verify_perm(current_user, tenant.id, db, ["accounting:reports:view", "accounting:reconciliation:view"])
    return await AccountingService.list_bank_reconciliations(
        db=db,
        tenant_id=tenant.id,
        account_id=account_id,
        status=status,
    )


@router.post("/reconciliations", response_model=BankReconciliationDetailResponse)
async def create_bank_reconciliation(
    payload: BankReconciliationCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Initialize a new Bank Reconciliation session."""
    tenant = await TeamService.resolve_active_tenant(current_user, db)
    await _verify_perm(current_user, tenant.id, db, ["accounting:reconciliation:create", "accounting:manage"])
    return await AccountingService.create_bank_reconciliation(
        db=db,
        tenant_id=tenant.id,
        user_id=current_user.id,
        payload=payload,
    )


@router.get("/reconciliations/{reconciliation_id}", response_model=BankReconciliationDetailResponse)
async def get_bank_reconciliation_details(
    reconciliation_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Fetch full details, transactions, in-transit items, and variance for a BRS session."""
    tenant = await TeamService.resolve_active_tenant(current_user, db)
    await _verify_perm(current_user, tenant.id, db, ["accounting:reports:view", "accounting:reconciliation:view"])
    return await AccountingService.get_bank_reconciliation_details(
        db=db,
        tenant_id=tenant.id,
        reconciliation_id=reconciliation_id,
    )


@router.post("/reconciliations/{reconciliation_id}/match", response_model=BankReconciliationDetailResponse)
async def match_bank_reconciliation_items(
    reconciliation_id: int,
    payload: BankReconciliationMatchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Toggle cleared/matched or in-transit status for selected bank transactions."""
    tenant = await TeamService.resolve_active_tenant(current_user, db)
    await _verify_perm(current_user, tenant.id, db, ["accounting:reconciliation:match", "accounting:manage"])
    return await AccountingService.match_bank_reconciliation_items(
        db=db,
        tenant_id=tenant.id,
        reconciliation_id=reconciliation_id,
        payload=payload,
    )


@router.post("/reconciliations/{reconciliation_id}/complete", response_model=BankReconciliationDetailResponse)
async def complete_bank_reconciliation(
    reconciliation_id: int,
    payload: BankReconciliationCompleteRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Formally finalize and lock the Bank Reconciliation statement (enforces 0.00 difference invariant)."""
    tenant = await TeamService.resolve_active_tenant(current_user, db)
    await _verify_perm(current_user, tenant.id, db, ["accounting:reconciliation:complete", "accounting:manage"])
    return await AccountingService.complete_bank_reconciliation(
        db=db,
        tenant_id=tenant.id,
        user_id=current_user.id,
        reconciliation_id=reconciliation_id,
        payload=payload,
    )




import math
from datetime import datetime, timezone, date
from typing import List, Optional, Dict, Any, Tuple
from fastapi import HTTPException, status
from sqlalchemy import select, func, and_, or_, desc, asc
from sqlalchemy.orm import selectinload, joinedload
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.accounting.models import (
    Account,
    TenantAccountingSettings,
    JournalEntry,
    JournalEntryLine,
    ExpenseVoucher,
    BankReconciliation,
    BankReconciliationItem,
)
from app.modules.accounting.schemas import (
    AccountCreate,
    AccountUpdate,
    AccountItem,
    AccountTreeNode,
    TenantAccountingSettingsUpdate,
    TenantAccountingSettingsResponse,
    JournalEntryCreate,
    JournalEntryItem,
    JournalEntryLineItem,
    PaginatedJournalEntriesResponse,
    GeneralLedgerLine,
    GeneralLedgerAccountReport,
    TrialBalanceItem,
    TrialBalanceResponse,
    ExpenseVoucherCreate,
    ExpenseVoucherItem,
    PaginatedExpenseVouchersResponse,
    ExpenseSummaryResponse,
    ProfitAndLossAccountLine,
    ProfitAndLossResponse,
    BalanceSheetAccountLine,
    BalanceSheetResponse,
    YearEndClosingAccountLine,
    YearEndClosingPreviewResponse,
    YearEndClosingExecuteResponse,
    BankReconcilableAccountItem,
    BankReconciliationCreateRequest,
    BankReconciliationTransactionItem,
    BankReconciliationSummary,
    BankReconciliationDetailResponse,
    BankReconciliationMatchRequest,
    BankReconciliationCompleteRequest,
)
from app.modules.branches.models import Branch
from app.modules.parties.models import Customer, Supplier
from app.modules.auth.models import User



class AccountingService:
    # ================= 1. Chart of Accounts (COA) Management =================
    @staticmethod
    async def list_accounts(
        db: AsyncSession,
        tenant_id: int,
        account_type: Optional[str] = None,
        search: Optional[str] = None,
        active_only: bool = True,
    ) -> List[AccountItem]:
        """List all accounts for a tenant with their computed current balances."""
        filters = [Account.tenant_id == tenant_id]
        if account_type:
            filters.append(Account.account_type == account_type.lower())
        if active_only:
            filters.append(Account.is_active.is_(True))
        if search:
            q = f"%{search.strip().lower()}%"
            filters.append(or_(
                func.lower(Account.code).like(q),
                func.lower(Account.name).like(q),
            ))

        stmt = (
            select(Account)
            .where(and_(*filters))
            .options(selectinload(Account.parent))
            .order_by(Account.code.asc())
        )
        res = await db.execute(stmt)
        accounts = res.scalars().all()

        # Compute balances: sum(debit) - sum(credit) for asset/expense, or credit - debit for liability/equity/revenue
        acc_ids = [a.id for a in accounts]
        balances_map: Dict[int, float] = {}

        if acc_ids:
            bal_stmt = (
                select(
                    JournalEntryLine.account_id,
                    func.coalesce(func.sum(JournalEntryLine.debit), 0.0).label("tot_debit"),
                    func.coalesce(func.sum(JournalEntryLine.credit), 0.0).label("tot_credit"),
                )
                .join(JournalEntry, JournalEntryLine.journal_entry_id == JournalEntry.id)
                .where(
                    JournalEntry.tenant_id == tenant_id,
                    JournalEntry.status == "posted",
                    JournalEntryLine.account_id.in_(acc_ids),
                )
                .group_by(JournalEntryLine.account_id)
            )
            bal_res = await db.execute(bal_stmt)
            for acc_id, d_tot, c_tot in bal_res.all():
                d_val = float(d_tot or 0.0)
                c_val = float(c_tot or 0.0)
                balances_map[acc_id] = round(d_val - c_val, 2)

        items: List[AccountItem] = []
        for a in accounts:
            raw_bal = balances_map.get(a.id, 0.0)
            # Standard accounting normal balance:
            # Asset/Expense: Dr - Cr
            # Liability/Equity/Revenue: Cr - Dr
            if a.account_type in ["liability", "equity", "revenue"]:
                computed_bal = round(-raw_bal, 2)
            else:
                computed_bal = round(raw_bal, 2)

            items.append(AccountItem(
                id=a.id,
                tenant_id=a.tenant_id,
                code=a.code,
                name=a.name,
                account_type=a.account_type,
                sub_type=a.sub_type,
                parent_id=a.parent_id,
                parent_name=a.parent.name if a.parent else None,
                currency=a.currency,
                is_system=a.is_system,
                is_active=a.is_active,
                description=a.description,
                current_balance=computed_bal,
                created_at=a.created_at,
            ))

        return items

    @staticmethod
    async def get_account_tree(db: AsyncSession, tenant_id: int) -> List[AccountTreeNode]:
        """Build hierarchical account tree (Assets, Liabilities, Equity, Revenue, Expense)."""
        accounts = await AccountingService.list_accounts(db, tenant_id, active_only=False)

        node_map: Dict[int, AccountTreeNode] = {}
        for a in accounts:
            node_map[a.id] = AccountTreeNode(
                id=a.id,
                code=a.code,
                name=a.name,
                account_type=a.account_type,
                sub_type=a.sub_type,
                parent_id=a.parent_id,
                currency=a.currency,
                is_system=a.is_system,
                is_active=a.is_active,
                current_balance=a.current_balance,
                children=[],
            )

        root_nodes: List[AccountTreeNode] = []
        for a in accounts:
            node = node_map[a.id]
            if a.parent_id and a.parent_id in node_map:
                node_map[a.parent_id].children.append(node)
            else:
                root_nodes.append(node)

        return root_nodes

    @staticmethod
    async def create_account(
        db: AsyncSession,
        tenant_id: int,
        data: AccountCreate,
    ) -> Account:
        """Create a custom account under a tenant's COA."""
        # 1. Check code uniqueness
        stmt = select(Account).where(Account.tenant_id == tenant_id, Account.code == data.code.strip())
        res = await db.execute(stmt)
        if res.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Account with code '{data.code}' already exists.",
            )

        # 2. Check parent if specified
        if data.parent_id:
            p_stmt = select(Account).where(Account.id == data.parent_id, Account.tenant_id == tenant_id)
            p_res = await db.execute(p_stmt)
            if not p_res.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Parent account not found in this business.",
                )

        acc = Account(
            tenant_id=tenant_id,
            code=data.code.strip(),
            name=data.name.strip(),
            account_type=data.account_type.lower(),
            sub_type=data.sub_type.lower() if data.sub_type else None,
            parent_id=data.parent_id,
            currency=data.currency.upper() if data.currency else "PKR",
            is_system=False,
            is_active=True,
            description=data.description,
        )
        db.add(acc)
        await db.commit()
        await db.refresh(acc)
        return acc

    @staticmethod
    async def update_account(
        db: AsyncSession,
        tenant_id: int,
        account_id: int,
        data: AccountUpdate,
    ) -> Account:
        """Update account details. Preserves is_system constraint."""
        stmt = select(Account).where(Account.id == account_id, Account.tenant_id == tenant_id)
        res = await db.execute(stmt)
        acc = res.scalar_one_or_none()
        if not acc:
            raise HTTPException(status_code=404, detail="Account not found.")

        if data.name is not None:
            acc.name = data.name.strip()
        if data.description is not None:
            acc.description = data.description
        if data.is_active is not None:
            acc.is_active = data.is_active
        if not acc.is_system:
            if data.account_type is not None:
                acc.account_type = data.account_type.lower()
            if data.sub_type is not None:
                acc.sub_type = data.sub_type.lower()
            if data.parent_id is not None:
                if data.parent_id == acc.id:
                    raise HTTPException(status_code=400, detail="Account cannot be its own parent.")
                acc.parent_id = data.parent_id
            if data.currency is not None:
                acc.currency = data.currency.upper()

        await db.commit()
        await db.refresh(acc)
        return acc

    @staticmethod
    async def delete_account(db: AsyncSession, tenant_id: int, account_id: int) -> None:
        """Delete custom account. Cannot delete system account or account with transactions."""
        stmt = select(Account).where(Account.id == account_id, Account.tenant_id == tenant_id)
        res = await db.execute(stmt)
        acc = res.scalar_one_or_none()
        if not acc:
            raise HTTPException(status_code=404, detail="Account not found.")

        if acc.is_system:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Core system accounts cannot be deleted as they are required for automatic posting.",
            )

        # Check if used in transactions
        tx_stmt = select(JournalEntryLine.id).where(JournalEntryLine.account_id == account_id).limit(1)
        tx_res = await db.execute(tx_stmt)
        if tx_res.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot delete account because it has recorded ledger transactions. You can deactivate it instead.",
            )

        await db.delete(acc)
        await db.commit()

    # ================= 2. Account Mapping Configuration (The 1 Screen) =================
    @staticmethod
    async def get_tenant_settings(db: AsyncSession, tenant_id: int) -> TenantAccountingSettings:
        """Fetch or auto-provision TenantAccountingSettings for this business."""
        stmt = (
            select(TenantAccountingSettings)
            .where(TenantAccountingSettings.tenant_id == tenant_id)
            .options(
                selectinload(TenantAccountingSettings.default_sales_income_account),
                selectinload(TenantAccountingSettings.default_ar_account),
                selectinload(TenantAccountingSettings.default_ap_account),
                selectinload(TenantAccountingSettings.default_cash_account),
                selectinload(TenantAccountingSettings.default_bank_account),
                selectinload(TenantAccountingSettings.default_sales_tax_account),
                selectinload(TenantAccountingSettings.default_discount_account),
                selectinload(TenantAccountingSettings.default_cogs_account),
                selectinload(TenantAccountingSettings.default_inventory_asset_account),
            )
        )
        res = await db.execute(stmt)
        sett = res.scalar_one_or_none()
        if not sett:
            sett = TenantAccountingSettings(
                tenant_id=tenant_id,
                base_currency="PKR",
                financial_year_start_month=7,
                auto_posting_enabled=True,
                payment_method_mappings={},
            )
            db.add(sett)
            await db.commit()
            await db.refresh(sett)

        return sett

    @staticmethod
    async def update_tenant_settings(
        db: AsyncSession,
        tenant_id: int,
        data: TenantAccountingSettingsUpdate,
    ) -> TenantAccountingSettings:
        """Update account mapping configuration."""
        sett = await AccountingService.get_tenant_settings(db, tenant_id)

        # Helper to validate account ownership
        async def _check_acc(acc_id: Optional[int]):
            if acc_id:
                s = select(Account.id).where(Account.id == acc_id, Account.tenant_id == tenant_id)
                r = await db.execute(s)
                if not r.scalar_one_or_none():
                    raise HTTPException(status_code=400, detail=f"Account ID {acc_id} does not belong to this business.")

        await _check_acc(data.default_sales_income_account_id)
        await _check_acc(data.default_ar_account_id)
        await _check_acc(data.default_ap_account_id)
        await _check_acc(data.default_cash_account_id)
        await _check_acc(data.default_bank_account_id)
        await _check_acc(data.default_sales_tax_account_id)
        await _check_acc(data.default_discount_account_id)
        await _check_acc(data.default_cogs_account_id)
        await _check_acc(data.default_inventory_asset_account_id)

        if data.base_currency is not None:
            sett.base_currency = data.base_currency.upper()
        if data.financial_year_start_month is not None:
            sett.financial_year_start_month = data.financial_year_start_month
        if data.auto_posting_enabled is not None:
            sett.auto_posting_enabled = data.auto_posting_enabled

        if data.default_sales_income_account_id is not None:
            sett.default_sales_income_account_id = data.default_sales_income_account_id
        if data.default_ar_account_id is not None:
            sett.default_ar_account_id = data.default_ar_account_id
        if data.default_ap_account_id is not None:
            sett.default_ap_account_id = data.default_ap_account_id
        if data.default_cash_account_id is not None:
            sett.default_cash_account_id = data.default_cash_account_id
        if data.default_bank_account_id is not None:
            sett.default_bank_account_id = data.default_bank_account_id
        if data.default_sales_tax_account_id is not None:
            sett.default_sales_tax_account_id = data.default_sales_tax_account_id
        if data.default_discount_account_id is not None:
            sett.default_discount_account_id = data.default_discount_account_id
        if data.default_cogs_account_id is not None:
            sett.default_cogs_account_id = data.default_cogs_account_id
        if data.default_inventory_asset_account_id is not None:
            sett.default_inventory_asset_account_id = data.default_inventory_asset_account_id

        if data.payment_method_mappings is not None:
            sett.payment_method_mappings = data.payment_method_mappings

        await db.commit()
        return await AccountingService.get_tenant_settings(db, tenant_id)

    # ================= 3. General Journal & Double-Entry Posting Engine =================
    @staticmethod
    async def generate_jv_number(db: AsyncSession, tenant_id: int) -> str:
        """Generate next sequential Journal Voucher number: JV-YYYYMM-XXXX."""
        now = datetime.now(timezone.utc)
        prefix = f"JV-{now.strftime('%Y%m')}"
        stmt = (
            select(func.count(JournalEntry.id))
            .where(
                JournalEntry.tenant_id == tenant_id,
                JournalEntry.entry_number.like(f"{prefix}-%"),
            )
        )
        res = await db.execute(stmt)
        count = (res.scalar() or 0) + 1
        return f"{prefix}-{count:04d}"

    @staticmethod
    async def create_journal_entry(
        db: AsyncSession,
        tenant_id: int,
        user_id: Optional[int],
        data: JournalEntryCreate,
        source_type: str = "manual_jv",
        source_id: Optional[int] = None,
    ) -> JournalEntry:
        """
        Post a Journal Entry with strict Double-Entry Invariant: sum(debit) == sum(credit).
        Multi-branch and multi-currency enabled.
        """
        # 1. Invariant Validation: sum(Dr) == sum(Cr)
        tot_debit = round(sum(line.debit for line in data.lines), 2)
        tot_credit = round(sum(line.credit for line in data.lines), 2)

        if abs(tot_debit - tot_credit) > 0.01:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unbalanced Journal Voucher! Total Debits (PKR {tot_debit:,.2f}) must equal Total Credits (PKR {tot_credit:,.2f}). Difference: PKR {abs(tot_debit - tot_credit):,.2f}",
            )

        if tot_debit <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Journal Voucher must have an amount greater than zero.",
            )

        # 2. Validate all accounts belong to tenant
        account_ids = {line.account_id for line in data.lines}
        acc_stmt = select(Account.id).where(Account.tenant_id == tenant_id, Account.id.in_(account_ids))
        acc_res = await db.execute(acc_stmt)
        found_ids = set(acc_res.scalars().all())
        missing = account_ids - found_ids
        if missing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid Account IDs for this business: {list(missing)}",
            )

        entry_no = await AccountingService.generate_jv_number(db, tenant_id)
        jv = JournalEntry(
            tenant_id=tenant_id,
            branch_id=data.branch_id,
            entry_number=entry_no,
            entry_date=data.entry_date or datetime.now(timezone.utc),
            source_type=source_type,
            source_id=source_id,
            reference_no=data.reference_no,
            narration=data.narration,
            currency=data.currency or "PKR",
            exchange_rate=data.exchange_rate or 1.0,
            status="posted",
            total_debit=tot_debit,
            total_credit=tot_credit,
            created_by_id=user_id,
        )

        for line in data.lines:
            jl = JournalEntryLine(
                account_id=line.account_id,
                branch_id=line.branch_id or data.branch_id,
                debit=round(line.debit, 2),
                credit=round(line.credit, 2),
                foreign_amount=round(line.foreign_amount, 2) if line.foreign_amount else None,
                foreign_currency=line.foreign_currency,
                narration=line.narration or data.narration,
                customer_id=line.customer_id,
                supplier_id=line.supplier_id,
            )
            jv.lines.append(jl)

        db.add(jv)
        await db.commit()
        await db.refresh(jv)
        return jv

    @staticmethod
    async def list_journal_entries(
        db: AsyncSession,
        tenant_id: int,
        branch_id: Optional[int] = None,
        source_type: Optional[str] = None,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
        search: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> PaginatedJournalEntriesResponse:
        """Fetch paginated journal entries with full line items."""
        filters = [JournalEntry.tenant_id == tenant_id]
        if branch_id:
            filters.append(JournalEntry.branch_id == branch_id)
        if source_type and source_type != "all":
            filters.append(JournalEntry.source_type == source_type)
        if from_date:
            dt_from = datetime(from_date.year, from_date.month, from_date.day, 0, 0, 0, tzinfo=timezone.utc)
            filters.append(JournalEntry.entry_date >= dt_from)
        if to_date:
            dt_to = datetime(to_date.year, to_date.month, to_date.day, 23, 59, 59, tzinfo=timezone.utc)
            filters.append(JournalEntry.entry_date <= dt_to)
        if search:
            q = f"%{search.strip().lower()}%"
            filters.append(or_(
                func.lower(JournalEntry.entry_number).like(q),
                func.lower(JournalEntry.reference_no).like(q),
                func.lower(JournalEntry.narration).like(q),
            ))

        # Total count
        count_stmt = select(func.count(JournalEntry.id)).where(and_(*filters))
        c_res = await db.execute(count_stmt)
        total = c_res.scalar() or 0

        # Query items
        stmt = (
            select(JournalEntry)
            .where(and_(*filters))
            .options(
                selectinload(JournalEntry.branch),
                selectinload(JournalEntry.created_by),
                selectinload(JournalEntry.lines).selectinload(JournalEntryLine.account),
                selectinload(JournalEntry.lines).selectinload(JournalEntryLine.branch),
                selectinload(JournalEntry.lines).selectinload(JournalEntryLine.customer),
                selectinload(JournalEntry.lines).selectinload(JournalEntryLine.supplier),
            )
            .order_by(JournalEntry.entry_date.desc(), JournalEntry.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        res = await db.execute(stmt)
        entries = res.scalars().all()

        items: List[JournalEntryItem] = []
        for e in entries:
            lines_dto = [
                JournalEntryLineItem(
                    id=l.id,
                    account_id=l.account_id,
                    account_code=l.account.code if l.account else None,
                    account_name=l.account.name if l.account else None,
                    branch_id=l.branch_id,
                    branch_name=l.branch.name if l.branch else None,
                    debit=float(l.debit),
                    credit=float(l.credit),
                    foreign_amount=float(l.foreign_amount) if l.foreign_amount else None,
                    foreign_currency=l.foreign_currency,
                    narration=l.narration,
                    customer_id=l.customer_id,
                    customer_name=l.customer.business_name if l.customer else None,
                    supplier_id=l.supplier_id,
                    supplier_name=l.supplier.company_name if l.supplier else None,
                )
                for l in e.lines
            ]

            items.append(JournalEntryItem(
                id=e.id,
                tenant_id=e.tenant_id,
                branch_id=e.branch_id,
                branch_name=e.branch.name if e.branch else None,
                entry_number=e.entry_number,
                entry_date=e.entry_date,
                source_type=e.source_type,
                source_id=e.source_id,
                reference_no=e.reference_no,
                narration=e.narration,
                currency=e.currency,
                exchange_rate=float(e.exchange_rate),
                status=e.status,
                total_debit=float(e.total_debit),
                total_credit=float(e.total_credit),
                created_by_id=e.created_by_id,
                created_by_name=e.created_by.full_name if e.created_by else None,
                created_at=e.created_at,
                lines=lines_dto,
            ))

        pages = math.ceil(total / page_size) if total > 0 else 1
        return PaginatedJournalEntriesResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            pages=pages,
        )

    # ================= 4. Financial Statements (General Ledger & Trial Balance) =================
    @staticmethod
    async def get_general_ledger(
        db: AsyncSession,
        tenant_id: int,
        account_id: int,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
        branch_id: Optional[int] = None,
    ) -> GeneralLedgerAccountReport:
        """Detailed chronological account statement with running balance."""
        acc_stmt = select(Account).where(Account.id == account_id, Account.tenant_id == tenant_id)
        acc_res = await db.execute(acc_stmt)
        acc = acc_res.scalar_one_or_none()
        if not acc:
            raise HTTPException(status_code=404, detail="Account not found.")

        dt_from = datetime(from_date.year, from_date.month, from_date.day, 0, 0, 0, tzinfo=timezone.utc) if from_date else None
        dt_to = datetime(to_date.year, to_date.month, to_date.day, 23, 59, 59, tzinfo=timezone.utc) if to_date else None

        # 1. Opening Balance prior to from_date
        opening_bal = 0.0
        if dt_from:
            op_filters = [
                JournalEntry.tenant_id == tenant_id,
                JournalEntry.status == "posted",
                JournalEntryLine.account_id == account_id,
                JournalEntry.entry_date < dt_from,
            ]
            if branch_id:
                op_filters.append(JournalEntryLine.branch_id == branch_id)

            op_stmt = (
                select(
                    func.coalesce(func.sum(JournalEntryLine.debit), 0.0),
                    func.coalesce(func.sum(JournalEntryLine.credit), 0.0),
                )
                .join(JournalEntry, JournalEntryLine.journal_entry_id == JournalEntry.id)
                .where(and_(*op_filters))
            )
            op_res = await db.execute(op_stmt)
            d_op, c_op = op_res.first() or (0.0, 0.0)
            raw_op = float(d_op) - float(c_op)
            opening_bal = -raw_op if acc.account_type in ["liability", "equity", "revenue"] else raw_op

        # 2. Transactions within range
        tx_filters = [
            JournalEntry.tenant_id == tenant_id,
            JournalEntry.status == "posted",
            JournalEntryLine.account_id == account_id,
        ]
        if dt_from:
            tx_filters.append(JournalEntry.entry_date >= dt_from)
        if dt_to:
            tx_filters.append(JournalEntry.entry_date <= dt_to)
        if branch_id:
            tx_filters.append(JournalEntryLine.branch_id == branch_id)

        tx_stmt = (
            select(JournalEntryLine, JournalEntry, Branch.name.label("branch_name"))
            .join(JournalEntry, JournalEntryLine.journal_entry_id == JournalEntry.id)
            .outerjoin(Branch, JournalEntryLine.branch_id == Branch.id)
            .where(and_(*tx_filters))
            .order_by(JournalEntry.entry_date.asc(), JournalEntry.id.asc(), JournalEntryLine.id.asc())
        )
        tx_res = await db.execute(tx_stmt)

        lines: List[GeneralLedgerLine] = []
        tot_debit = 0.0
        tot_credit = 0.0
        current_running = opening_bal

        for jl, jv, b_name in tx_res.all():
            d = float(jl.debit)
            c = float(jl.credit)
            tot_debit += d
            tot_credit += c

            if acc.account_type in ["liability", "equity", "revenue"]:
                current_running += (c - d)
            else:
                current_running += (d - c)

            lines.append(GeneralLedgerLine(
                id=jl.id,
                entry_date=jv.entry_date,
                entry_number=jv.entry_number,
                source_type=jv.source_type,
                reference_no=jv.reference_no,
                narration=jl.narration or jv.narration,
                branch_name=b_name,
                debit=d,
                credit=c,
                running_balance=round(current_running, 2),
            ))

        closing_bal = current_running

        return GeneralLedgerAccountReport(
            account_id=acc.id,
            account_code=acc.code,
            account_name=acc.name,
            account_type=acc.account_type,
            sub_type=acc.sub_type,
            currency=acc.currency,
            opening_balance=round(opening_bal, 2),
            total_debit=round(tot_debit, 2),
            total_credit=round(tot_credit, 2),
            closing_balance=round(closing_bal, 2),
            lines=lines,
        )

    @staticmethod
    async def get_trial_balance(
        db: AsyncSession,
        tenant_id: int,
        as_of_date: Optional[date] = None,
        branch_id: Optional[int] = None,
    ) -> TrialBalanceResponse:
        """Generate double-entry Trial Balance verifying sum(Debit) == sum(Credit)."""
        target_date = as_of_date or datetime.now(timezone.utc).date()
        dt_end = datetime(target_date.year, target_date.month, target_date.day, 23, 59, 59, tzinfo=timezone.utc)

        branch_name: Optional[str] = None
        if branch_id:
            b_stmt = select(Branch.name).where(Branch.id == branch_id, Branch.tenant_id == tenant_id)
            b_res = await db.execute(b_stmt)
            branch_name = b_res.scalar_one_or_none()

        # Query all accounts
        acc_stmt = select(Account).where(Account.tenant_id == tenant_id, Account.is_active.is_(True)).order_by(Account.code.asc())
        acc_res = await db.execute(acc_stmt)
        accounts = acc_res.scalars().all()

        # Query debit and credit aggregates up to target_date
        filters = [
            JournalEntry.tenant_id == tenant_id,
            JournalEntry.status == "posted",
            JournalEntry.entry_date <= dt_end,
        ]
        if branch_id:
            filters.append(JournalEntryLine.branch_id == branch_id)

        agg_stmt = (
            select(
                JournalEntryLine.account_id,
                func.coalesce(func.sum(JournalEntryLine.debit), 0.0),
                func.coalesce(func.sum(JournalEntryLine.credit), 0.0),
            )
            .join(JournalEntry, JournalEntryLine.journal_entry_id == JournalEntry.id)
            .where(and_(*filters))
            .group_by(JournalEntryLine.account_id)
        )
        agg_res = await db.execute(agg_stmt)
        agg_map = {acc_id: (float(d), float(c)) for acc_id, d, c in agg_res.all()}

        items: List[TrialBalanceItem] = []
        total_dr = 0.0
        total_cr = 0.0

        for a in accounts:
            d_sum, c_sum = agg_map.get(a.id, (0.0, 0.0))
            if d_sum == 0.0 and c_sum == 0.0:
                continue

            diff = round(d_sum - c_sum, 2)
            dr_bal = 0.0
            cr_bal = 0.0

            if a.account_type in ["asset", "expense"]:
                if diff >= 0:
                    dr_bal = diff
                else:
                    cr_bal = abs(diff)
            else:
                # Liability, Equity, Revenue (Normal Credit)
                if diff <= 0:
                    cr_bal = abs(diff)
                else:
                    dr_bal = diff

            total_dr += dr_bal
            total_cr += cr_bal

            items.append(TrialBalanceItem(
                account_id=a.id,
                account_code=a.code,
                account_name=a.name,
                account_type=a.account_type,
                sub_type=a.sub_type,
                debit_balance=round(dr_bal, 2),
                credit_balance=round(cr_bal, 2),
            ))

        total_dr = round(total_dr, 2)
        total_cr = round(total_cr, 2)
        is_balanced = abs(total_dr - total_cr) < 0.01

        return TrialBalanceResponse(
            as_of_date=target_date.isoformat(),
            branch_id=branch_id,
            branch_name=branch_name or "All Branches",
            items=items,
            total_debits=total_dr,
            total_credits=total_cr,
            is_balanced=is_balanced,
        )

    @staticmethod
    async def get_profit_and_loss(
        db: AsyncSession,
        tenant_id: int,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
        branch_id: Optional[int] = None,
    ) -> ProfitAndLossResponse:
        """
        Generate IFRS/GAAP compliant Profit & Loss (Income Statement) for a specified date range.
        Revenue - COGS = Gross Profit - Operating Expenses = Net Profit.
        """
        now = datetime.now(timezone.utc)
        if not from_date:
            from_date = date(now.year, now.month, 1)
        if not to_date:
            to_date = now.date()

        dt_start = datetime(from_date.year, from_date.month, from_date.day, 0, 0, 0, tzinfo=timezone.utc)
        dt_end = datetime(to_date.year, to_date.month, to_date.day, 23, 59, 59, 999999, tzinfo=timezone.utc)

        branch_name: Optional[str] = None
        if branch_id:
            b_stmt = select(Branch.name).where(Branch.id == branch_id, Branch.tenant_id == tenant_id)
            branch_name = (await db.execute(b_stmt)).scalar_one_or_none()

        # Query all active accounts
        acc_stmt = select(Account).where(Account.tenant_id == tenant_id, Account.is_active.is_(True)).order_by(Account.code.asc())
        accounts = (await db.execute(acc_stmt)).scalars().all()

        # Query debit and credit aggregates for the period
        filters = [
            JournalEntry.tenant_id == tenant_id,
            JournalEntry.status == "posted",
            JournalEntry.entry_date >= dt_start,
            JournalEntry.entry_date <= dt_end,
            JournalEntry.source_type != "year_end_closing",
        ]
        if branch_id:
            filters.append(JournalEntryLine.branch_id == branch_id)

        agg_stmt = (
            select(
                JournalEntryLine.account_id,
                func.coalesce(func.sum(JournalEntryLine.debit), 0.0),
                func.coalesce(func.sum(JournalEntryLine.credit), 0.0),
            )
            .join(JournalEntry, JournalEntryLine.journal_entry_id == JournalEntry.id)
            .where(and_(*filters))
            .group_by(JournalEntryLine.account_id)
        )
        agg_res = await db.execute(agg_stmt)
        agg_map = {acc_id: (float(d), float(c)) for acc_id, d, c in agg_res.all()}

        # 1. Process Revenue
        gross_sales = 0.0
        sales_discounts = 0.0
        revenue_lines: List[ProfitAndLossAccountLine] = []

        # 2. Process COGS
        total_cogs = 0.0
        cogs_lines: List[ProfitAndLossAccountLine] = []

        # 3. Process Operating Expenses
        total_opex = 0.0
        expense_lines: List[ProfitAndLossAccountLine] = []

        for a in accounts:
            d_sum, c_sum = agg_map.get(a.id, (0.0, 0.0))
            if d_sum == 0.0 and c_sum == 0.0:
                continue

            # Revenue: normal credit balance (Credit - Debit)
            if a.account_type == "revenue":
                is_discount = a.code == "4020" or (a.sub_type and "discount" in a.sub_type.lower())
                if is_discount:
                    disc_amt = round(d_sum - c_sum, 2)
                    sales_discounts += max(disc_amt, 0.0)
                    revenue_lines.append(ProfitAndLossAccountLine(
                        account_id=a.id,
                        account_code=a.code,
                        account_name=a.name,
                        amount=-abs(disc_amt),
                    ))
                else:
                    rev_amt = round(c_sum - d_sum, 2)
                    gross_sales += rev_amt
                    revenue_lines.append(ProfitAndLossAccountLine(
                        account_id=a.id,
                        account_code=a.code,
                        account_name=a.name,
                        amount=rev_amt,
                    ))

            # Expense: normal debit balance (Debit - Credit)
            elif a.account_type == "expense":
                is_cogs = a.code.startswith("5") or (a.sub_type and "cogs" in a.sub_type.lower())
                exp_amt = round(d_sum - c_sum, 2)
                if is_cogs:
                    total_cogs += exp_amt
                    cogs_lines.append(ProfitAndLossAccountLine(
                        account_id=a.id,
                        account_code=a.code,
                        account_name=a.name,
                        amount=exp_amt,
                    ))
                else:
                    total_opex += exp_amt
                    expense_lines.append(ProfitAndLossAccountLine(
                        account_id=a.id,
                        account_code=a.code,
                        account_name=a.name,
                        amount=exp_amt,
                    ))

        gross_sales = round(gross_sales, 2)
        sales_discounts = round(sales_discounts, 2)
        net_revenue = round(gross_sales - sales_discounts, 2)
        total_cogs = round(total_cogs, 2)
        gross_profit = round(net_revenue - total_cogs, 2)
        gp_margin_pct = round((gross_profit / net_revenue * 100), 2) if net_revenue > 0 else 0.0

        total_opex = round(total_opex, 2)
        net_profit = round(gross_profit - total_opex, 2)
        net_margin_pct = round((net_profit / net_revenue * 100), 2) if net_revenue > 0 else 0.0

        # Compute percentage of revenue for each line
        if net_revenue > 0:
            for l in revenue_lines:
                l.percentage_of_revenue = round((l.amount / net_revenue * 100), 2)
            for l in cogs_lines:
                l.percentage_of_revenue = round((l.amount / net_revenue * 100), 2)
            for l in expense_lines:
                l.percentage_of_revenue = round((l.amount / net_revenue * 100), 2)

        return ProfitAndLossResponse(
            from_date=from_date.isoformat(),
            to_date=to_date.isoformat(),
            branch_id=branch_id,
            branch_name=branch_name or "All Branches",
            currency="PKR",
            gross_sales=gross_sales,
            sales_discounts=sales_discounts,
            net_revenue=net_revenue,
            revenue_lines=revenue_lines,
            total_cogs=total_cogs,
            cogs_lines=cogs_lines,
            gross_profit=gross_profit,
            gross_profit_margin_pct=gp_margin_pct,
            total_operating_expenses=total_opex,
            expense_lines=expense_lines,
            net_profit=net_profit,
            net_profit_margin_pct=net_margin_pct,
            is_profitable=net_profit >= 0,
        )

    @staticmethod
    async def get_balance_sheet(
        db: AsyncSession,
        tenant_id: int,
        as_of_date: Optional[date] = None,
        branch_id: Optional[int] = None,
    ) -> BalanceSheetResponse:
        """
        Generate IFRS/GAAP Statement of Financial Position (Balance Sheet) as of a specific date.
        Enforces strict Accounting Golden Equation: Total Assets == Total Liabilities + Total Equity.
        """
        target_date = as_of_date or datetime.now(timezone.utc).date()
        dt_end = datetime(target_date.year, target_date.month, target_date.day, 23, 59, 59, 999999, tzinfo=timezone.utc)

        branch_name: Optional[str] = None
        if branch_id:
            b_stmt = select(Branch.name).where(Branch.id == branch_id, Branch.tenant_id == tenant_id)
            branch_name = (await db.execute(b_stmt)).scalar_one_or_none()

        # Query all active accounts
        acc_stmt = select(Account).where(Account.tenant_id == tenant_id, Account.is_active.is_(True)).order_by(Account.code.asc())
        accounts = (await db.execute(acc_stmt)).scalars().all()

        # Query cumulative debit and credit aggregates up to target_date
        filters = [
            JournalEntry.tenant_id == tenant_id,
            JournalEntry.status == "posted",
            JournalEntry.entry_date <= dt_end,
        ]
        if branch_id:
            filters.append(JournalEntryLine.branch_id == branch_id)

        agg_stmt = (
            select(
                JournalEntryLine.account_id,
                func.coalesce(func.sum(JournalEntryLine.debit), 0.0),
                func.coalesce(func.sum(JournalEntryLine.credit), 0.0),
            )
            .join(JournalEntry, JournalEntryLine.journal_entry_id == JournalEntry.id)
            .where(and_(*filters))
            .group_by(JournalEntryLine.account_id)
        )
        agg_res = await db.execute(agg_stmt)
        agg_map = {acc_id: (float(d), float(c)) for acc_id, d, c in agg_res.all()}

        current_assets: List[BalanceSheetAccountLine] = []
        non_current_assets: List[BalanceSheetAccountLine] = []
        tot_curr_assets = 0.0
        tot_non_curr_assets = 0.0

        current_liabilities: List[BalanceSheetAccountLine] = []
        long_term_liabilities: List[BalanceSheetAccountLine] = []
        tot_curr_liab = 0.0
        tot_lt_liab = 0.0

        equity_lines: List[BalanceSheetAccountLine] = []
        tot_equity_capital = 0.0
        retained_earnings = 0.0

        tot_cum_revenue = 0.0
        tot_cum_expenses = 0.0

        for a in accounts:
            d_sum, c_sum = agg_map.get(a.id, (0.0, 0.0))
            if d_sum == 0.0 and c_sum == 0.0:
                continue

            if a.account_type == "asset":
                bal = round(d_sum - c_sum, 2)
                is_fixed = a.code.startswith("15") or a.code.startswith("18") or (a.sub_type and "fixed" in a.sub_type.lower())
                line = BalanceSheetAccountLine(
                    account_id=a.id,
                    account_code=a.code,
                    account_name=a.name,
                    sub_type=a.sub_type,
                    balance=bal,
                )
                if is_fixed:
                    non_current_assets.append(line)
                    tot_non_curr_assets += bal
                else:
                    current_assets.append(line)
                    tot_curr_assets += bal

            elif a.account_type == "liability":
                bal = round(c_sum - d_sum, 2)
                is_long_term = a.code.startswith("25") or (a.sub_type and "long" in a.sub_type.lower())
                line = BalanceSheetAccountLine(
                    account_id=a.id,
                    account_code=a.code,
                    account_name=a.name,
                    sub_type=a.sub_type,
                    balance=bal,
                )
                if is_long_term:
                    long_term_liabilities.append(line)
                    tot_lt_liab += bal
                else:
                    current_liabilities.append(line)
                    tot_curr_liab += bal

            elif a.account_type == "equity":
                bal = round(c_sum - d_sum, 2)
                line = BalanceSheetAccountLine(
                    account_id=a.id,
                    account_code=a.code,
                    account_name=a.name,
                    sub_type=a.sub_type,
                    balance=bal,
                )
                equity_lines.append(line)
                if a.code == "3020" or (a.sub_type and "retained" in a.sub_type.lower()):
                    retained_earnings += bal
                else:
                    tot_equity_capital += bal

            elif a.account_type == "revenue":
                tot_cum_revenue += round(c_sum - d_sum, 2)

            elif a.account_type == "expense":
                tot_cum_expenses += round(d_sum - c_sum, 2)

        tot_curr_assets = round(tot_curr_assets, 2)
        tot_non_curr_assets = round(tot_non_curr_assets, 2)
        total_assets = round(tot_curr_assets + tot_non_curr_assets, 2)

        tot_curr_liab = round(tot_curr_liab, 2)
        tot_lt_liab = round(tot_lt_liab, 2)
        total_liabilities = round(tot_curr_liab + tot_lt_liab, 2)

        tot_equity_capital = round(tot_equity_capital, 2)
        retained_earnings = round(retained_earnings, 2)
        current_net_profit = round(tot_cum_revenue - tot_cum_expenses, 2)
        total_equity = round(tot_equity_capital + retained_earnings + current_net_profit, 2)

        total_liabilities_and_equity = round(total_liabilities + total_equity, 2)
        discrepancy = round(total_assets - total_liabilities_and_equity, 2)
        is_balanced = abs(discrepancy) < 0.01

        return BalanceSheetResponse(
            as_of_date=target_date.isoformat(),
            branch_id=branch_id,
            branch_name=branch_name or "All Branches",
            currency="PKR",
            current_assets=current_assets,
            total_current_assets=tot_curr_assets,
            non_current_assets=non_current_assets,
            total_non_current_assets=tot_non_curr_assets,
            total_assets=total_assets,
            current_liabilities=current_liabilities,
            total_current_liabilities=tot_curr_liab,
            long_term_liabilities=long_term_liabilities,
            total_long_term_liabilities=tot_lt_liab,
            total_liabilities=total_liabilities,
            equity_lines=equity_lines,
            total_equity_capital=tot_equity_capital,
            retained_earnings=retained_earnings,
            current_period_net_profit=current_net_profit,
            total_equity=total_equity,
            total_liabilities_and_equity=total_liabilities_and_equity,
            is_balanced=is_balanced,
            discrepancy=discrepancy,
        )

    # ================= 4.5 Fiscal Year-End Closing Engine (Phase 7.2) =================
    @staticmethod
    def _compute_fiscal_year_range(closing_date: date, start_month: int = 7) -> Tuple[date, date]:
        """Compute the start and end date of the fiscal year ending on closing_date."""
        m = start_month or 7
        if m == 1:
            fy_start = date(closing_date.year, 1, 1)
        elif closing_date.month >= m:
            fy_start = date(closing_date.year, m, 1)
        else:
            fy_start = date(closing_date.year - 1, m, 1)
        return fy_start, closing_date

    @staticmethod
    async def preview_fiscal_year_closing(
        db: AsyncSession,
        tenant_id: int,
        closing_date: date,
        branch_id: Optional[int] = None,
    ) -> YearEndClosingPreviewResponse:
        """
        Preview the formal fiscal year closing:
        Calculates all temporary Revenue and Expense account balances to close,
        the Net Profit/Loss to transfer, and the Retained Earnings balance impact.
        """
        settings = await AccountingService.get_tenant_settings(db, tenant_id)
        fy_start, fy_end = AccountingService._compute_fiscal_year_range(
            closing_date, settings.financial_year_start_month or 7
        )

        dt_start = datetime(fy_start.year, fy_start.month, fy_start.day, 0, 0, 0, tzinfo=timezone.utc)
        dt_end = datetime(fy_end.year, fy_end.month, fy_end.day, 23, 59, 59, 999999, tzinfo=timezone.utc)

        branch_name = None
        if branch_id:
            b_stmt = select(Branch.name).where(Branch.id == branch_id, Branch.tenant_id == tenant_id)
            branch_name = (await db.execute(b_stmt)).scalar_one_or_none()

        # Check existing closing for this date
        close_ref = f"CLOSE-{closing_date.strftime('%Y%m%d')}"
        existing_res = await db.execute(
            select(JournalEntry).where(
                JournalEntry.tenant_id == tenant_id,
                JournalEntry.source_type == "year_end_closing",
                JournalEntry.reference_no == close_ref,
                JournalEntry.status == "posted",
            )
        )
        existing_jv = existing_res.scalars().first()
        already_closed = existing_jv is not None

        # Resolve Retained Earnings Account (3020)
        re_res = await db.execute(
            select(Account).where(Account.tenant_id == tenant_id, Account.code == "3020")
        )
        retained_acc = re_res.scalars().first()
        if not retained_acc:
            fallback_res = await db.execute(
                select(Account).where(
                    Account.tenant_id == tenant_id,
                    Account.account_type == "equity",
                    or_(Account.name.ilike("%retained%"), Account.sub_type.ilike("%retained%")),
                )
            )
            retained_acc = fallback_res.scalars().first()
        if not retained_acc:
            raise HTTPException(
                status_code=400,
                detail="Retained Earnings account (Code 3020) was not found in Chart of Accounts.",
            )

        # Get Retained Earnings balance before
        re_bal_stmt = select(
            func.coalesce(func.sum(JournalEntryLine.credit), 0.0) - func.coalesce(func.sum(JournalEntryLine.debit), 0.0)
        ).join(JournalEntry, JournalEntryLine.journal_entry_id == JournalEntry.id).where(
            JournalEntry.tenant_id == tenant_id,
            JournalEntry.status == "posted",
            JournalEntryLine.account_id == retained_acc.id,
        )
        re_before = float((await db.execute(re_bal_stmt)).scalar() or 0.0)

        # Query all active Revenue and Expense accounts
        acc_stmt = select(Account).where(
            Account.tenant_id == tenant_id,
            Account.is_active.is_(True),
            Account.account_type.in_(["revenue", "expense"]),
        ).order_by(Account.code.asc())
        accounts = (await db.execute(acc_stmt)).scalars().all()

        filters = [
            JournalEntry.tenant_id == tenant_id,
            JournalEntry.status == "posted",
            JournalEntry.entry_date >= dt_start,
            JournalEntry.entry_date <= dt_end,
            JournalEntry.source_type != "year_end_closing",
        ]
        if branch_id:
            filters.append(JournalEntryLine.branch_id == branch_id)

        agg_stmt = (
            select(
                JournalEntryLine.account_id,
                func.coalesce(func.sum(JournalEntryLine.debit), 0.0),
                func.coalesce(func.sum(JournalEntryLine.credit), 0.0),
            )
            .join(JournalEntry, JournalEntryLine.journal_entry_id == JournalEntry.id)
            .where(and_(*filters))
            .group_by(JournalEntryLine.account_id)
        )
        agg_res = await db.execute(agg_stmt)
        agg_map = {acc_id: (float(d), float(c)) for acc_id, d, c in agg_res.all()}

        lines: List[YearEndClosingAccountLine] = []
        tot_rev = 0.0
        tot_exp = 0.0

        for a in accounts:
            d_sum, c_sum = agg_map.get(a.id, (0.0, 0.0))
            if d_sum == 0.0 and c_sum == 0.0:
                continue

            if a.account_type == "revenue":
                net_bal = round(c_sum - d_sum, 2)
                if net_bal > 0:
                    lines.append(YearEndClosingAccountLine(
                        account_id=a.id,
                        account_code=a.code,
                        account_name=a.name,
                        account_type="revenue",
                        current_balance=net_bal,
                        closing_action=f"Debit PKR {net_bal:,.2f}",
                        amount=net_bal,
                    ))
                    tot_rev += net_bal
                elif net_bal < 0:
                    contra_bal = round(abs(net_bal), 2)
                    lines.append(YearEndClosingAccountLine(
                        account_id=a.id,
                        account_code=a.code,
                        account_name=a.name,
                        account_type="revenue",
                        current_balance=-contra_bal,
                        closing_action=f"Credit PKR {contra_bal:,.2f}",
                        amount=-contra_bal,
                    ))
                    tot_rev -= contra_bal

            elif a.account_type == "expense":
                net_bal = round(d_sum - c_sum, 2)
                if net_bal > 0:
                    lines.append(YearEndClosingAccountLine(
                        account_id=a.id,
                        account_code=a.code,
                        account_name=a.name,
                        account_type="expense",
                        current_balance=net_bal,
                        closing_action=f"Credit PKR {net_bal:,.2f}",
                        amount=net_bal,
                    ))
                    tot_exp += net_bal
                elif net_bal < 0:
                    contra_bal = round(abs(net_bal), 2)
                    lines.append(YearEndClosingAccountLine(
                        account_id=a.id,
                        account_code=a.code,
                        account_name=a.name,
                        account_type="expense",
                        current_balance=-contra_bal,
                        closing_action=f"Debit PKR {contra_bal:,.2f}",
                        amount=-contra_bal,
                    ))
                    tot_exp -= contra_bal

        tot_rev = round(tot_rev, 2)
        tot_exp = round(tot_exp, 2)
        net_profit = round(tot_rev - tot_exp, 2)
        re_after = round(re_before + net_profit, 2)

        can_close = not already_closed and len(lines) > 0
        msg = None
        if already_closed:
            msg = f"Fiscal year ending on {closing_date.strftime('%Y-%m-%d')} has already been formally closed with voucher {existing_jv.entry_number}."
        elif len(lines) == 0:
            msg = "No revenue or expense activity found for the selected period."

        return YearEndClosingPreviewResponse(
            closing_date=closing_date.isoformat(),
            financial_year_start=fy_start.isoformat(),
            financial_year_end=fy_end.isoformat(),
            branch_id=branch_id,
            branch_name=branch_name or "All Branches",
            total_revenue_to_close=tot_rev,
            total_expenses_to_close=tot_exp,
            net_profit=net_profit,
            is_profitable=net_profit >= 0,
            retained_earnings_account_id=retained_acc.id,
            retained_earnings_account_code=retained_acc.code,
            retained_earnings_account_name=retained_acc.name,
            retained_earnings_before=re_before,
            retained_earnings_after=re_after,
            lines=lines,
            can_close=can_close,
            already_closed=already_closed,
            existing_jv_number=existing_jv.entry_number if existing_jv else None,
            message=msg,
        )

    @staticmethod
    async def execute_fiscal_year_closing(
        db: AsyncSession,
        tenant_id: int,
        user_id: int,
        closing_date: date,
        branch_id: Optional[int] = None,
        notes: Optional[str] = None,
    ) -> YearEndClosingExecuteResponse:
        """
        Execute formal Fiscal Year Closing (Phase 7.2):
        Posts a balanced closing Journal Voucher bringing all revenue and expense accounts to 0.00
        and transferring net profit/loss into 3020 Retained Earnings.
        """
        settings = await AccountingService.get_tenant_settings(db, tenant_id)
        fy_start, fy_end = AccountingService._compute_fiscal_year_range(
            closing_date, settings.financial_year_start_month or 7
        )

        dt_start = datetime(fy_start.year, fy_start.month, fy_start.day, 0, 0, 0, tzinfo=timezone.utc)
        dt_end = datetime(fy_end.year, fy_end.month, fy_end.day, 23, 59, 59, 999999, tzinfo=timezone.utc)

        close_ref = f"CLOSE-{closing_date.strftime('%Y%m%d')}"
        existing_res = await db.execute(
            select(JournalEntry).where(
                JournalEntry.tenant_id == tenant_id,
                JournalEntry.source_type == "year_end_closing",
                JournalEntry.reference_no == close_ref,
                JournalEntry.status == "posted",
            )
        )
        existing_jv = existing_res.scalars().first()
        if existing_jv:
            raise HTTPException(
                status_code=400,
                detail=f"Fiscal year ending on {closing_date.strftime('%Y-%m-%d')} has already been closed with voucher {existing_jv.entry_number}.",
            )

        # Resolve Retained Earnings Account (3020)
        re_res = await db.execute(
            select(Account).where(Account.tenant_id == tenant_id, Account.code == "3020")
        )
        retained_acc = re_res.scalars().first()
        if not retained_acc:
            fallback_res = await db.execute(
                select(Account).where(
                    Account.tenant_id == tenant_id,
                    Account.account_type == "equity",
                    or_(Account.name.ilike("%retained%"), Account.sub_type.ilike("%retained%")),
                )
            )
            retained_acc = fallback_res.scalars().first()
        if not retained_acc:
            raise HTTPException(
                status_code=400,
                detail="Retained Earnings account (Code 3020) was not found in Chart of Accounts.",
            )

        # Query all active Revenue and Expense accounts
        acc_stmt = select(Account).where(
            Account.tenant_id == tenant_id,
            Account.is_active.is_(True),
            Account.account_type.in_(["revenue", "expense"]),
        ).order_by(Account.code.asc())
        accounts = (await db.execute(acc_stmt)).scalars().all()

        filters = [
            JournalEntry.tenant_id == tenant_id,
            JournalEntry.status == "posted",
            JournalEntry.entry_date >= dt_start,
            JournalEntry.entry_date <= dt_end,
            JournalEntry.source_type != "year_end_closing",
        ]
        if branch_id:
            filters.append(JournalEntryLine.branch_id == branch_id)

        agg_stmt = (
            select(
                JournalEntryLine.account_id,
                func.coalesce(func.sum(JournalEntryLine.debit), 0.0),
                func.coalesce(func.sum(JournalEntryLine.credit), 0.0),
            )
            .join(JournalEntry, JournalEntryLine.journal_entry_id == JournalEntry.id)
            .where(and_(*filters))
            .group_by(JournalEntryLine.account_id)
        )
        agg_res = await db.execute(agg_stmt)
        agg_map = {acc_id: (float(d), float(c)) for acc_id, d, c in agg_res.all()}

        closing_lines: List[JournalEntryLine] = []
        tot_rev = 0.0
        tot_exp = 0.0

        for a in accounts:
            d_sum, c_sum = agg_map.get(a.id, (0.0, 0.0))
            if d_sum == 0.0 and c_sum == 0.0:
                continue

            b_id = branch_id

            if a.account_type == "revenue":
                net_bal = round(c_sum - d_sum, 2)
                if net_bal > 0:
                    closing_lines.append(JournalEntryLine(
                        account_id=a.id,
                        branch_id=b_id,
                        debit=net_bal,
                        credit=0.0,
                        narration=f"Closing Revenue ({a.code} - {a.name}) to Retained Earnings",
                    ))
                    tot_rev += net_bal
                elif net_bal < 0:
                    contra_bal = round(abs(net_bal), 2)
                    closing_lines.append(JournalEntryLine(
                        account_id=a.id,
                        branch_id=b_id,
                        debit=0.0,
                        credit=contra_bal,
                        narration=f"Closing Contra-Revenue ({a.code} - {a.name}) to Retained Earnings",
                    ))
                    tot_rev -= contra_bal

            elif a.account_type == "expense":
                net_bal = round(d_sum - c_sum, 2)
                if net_bal > 0:
                    closing_lines.append(JournalEntryLine(
                        account_id=a.id,
                        branch_id=b_id,
                        debit=0.0,
                        credit=net_bal,
                        narration=f"Closing Expense ({a.code} - {a.name}) to Retained Earnings",
                    ))
                    tot_exp += net_bal
                elif net_bal < 0:
                    contra_bal = round(abs(net_bal), 2)
                    closing_lines.append(JournalEntryLine(
                        account_id=a.id,
                        branch_id=b_id,
                        debit=contra_bal,
                        credit=0.0,
                        narration=f"Closing Expense credit offset ({a.code} - {a.name}) to Retained Earnings",
                    ))
                    tot_exp -= contra_bal

        tot_rev = round(tot_rev, 2)
        tot_exp = round(tot_exp, 2)
        net_profit = round(tot_rev - tot_exp, 2)

        if len(closing_lines) == 0:
            raise HTTPException(status_code=400, detail="No revenue or expense activity found to close for this period.")

        # Transfer Net Profit/Loss to Retained Earnings
        if net_profit > 0:
            closing_lines.append(JournalEntryLine(
                account_id=retained_acc.id,
                branch_id=branch_id,
                debit=0.0,
                credit=net_profit,
                narration=f"Transfer Net Profit for FY ending {closing_date.strftime('%Y-%m-%d')} to Retained Earnings",
            ))
        elif net_profit < 0:
            closing_lines.append(JournalEntryLine(
                account_id=retained_acc.id,
                branch_id=branch_id,
                debit=round(abs(net_profit), 2),
                credit=0.0,
                narration=f"Transfer Net Loss for FY ending {closing_date.strftime('%Y-%m-%d')} to Retained Earnings",
            ))

        tot_dr = round(sum(l.debit for l in closing_lines), 2)
        tot_cr = round(sum(l.credit for l in closing_lines), 2)

        # Strict Invariant verification with penny rounding correction
        diff = round(tot_dr - tot_cr, 2)
        if abs(diff) > 0.00 and abs(diff) <= 0.05:
            for l in closing_lines:
                if l.account_id == retained_acc.id:
                    if l.credit > 0:
                        l.credit = round(l.credit + diff, 2)
                        tot_cr += diff
                    else:
                        l.debit = round(l.debit - diff, 2)
                        tot_dr -= diff
                    break

        tot_dr = round(tot_dr, 2)
        tot_cr = round(tot_cr, 2)

        if abs(tot_dr - tot_cr) > 0.01:
            raise HTTPException(status_code=400, detail=f"Unbalanced closing voucher calculation: Dr {tot_dr} vs Cr {tot_cr}")

        entry_no = await AccountingService.generate_jv_number(db, tenant_id)
        narr = notes or f"Fiscal Year Closing as of {closing_date.strftime('%Y-%m-%d')}: Net Profit PKR {net_profit:,.2f} transferred to Retained Earnings"

        jv = JournalEntry(
            tenant_id=tenant_id,
            branch_id=branch_id,
            entry_number=entry_no,
            entry_date=datetime(closing_date.year, closing_date.month, closing_date.day, 23, 59, 59, tzinfo=timezone.utc),
            source_type="year_end_closing",
            source_id=None,
            reference_no=close_ref,
            narration=narr,
            currency="PKR",
            exchange_rate=1.0,
            status="posted",
            total_debit=tot_dr,
            total_credit=tot_cr,
            created_by_id=user_id,
            lines=closing_lines,
        )
        db.add(jv)
        await db.commit()
        await db.refresh(jv)

        # Get updated Retained Earnings balance
        re_bal_stmt = select(
            func.coalesce(func.sum(JournalEntryLine.credit), 0.0) - func.coalesce(func.sum(JournalEntryLine.debit), 0.0)
        ).join(JournalEntry, JournalEntryLine.journal_entry_id == JournalEntry.id).where(
            JournalEntry.tenant_id == tenant_id,
            JournalEntry.status == "posted",
            JournalEntryLine.account_id == retained_acc.id,
        )
        re_new_bal = float((await db.execute(re_bal_stmt)).scalar() or 0.0)

        return YearEndClosingExecuteResponse(
            message=f"Fiscal year closed successfully. Closing Voucher {entry_no} has been posted.",
            journal_entry_id=jv.id,
            journal_entry_number=jv.entry_number,
            closing_date=closing_date.isoformat(),
            net_profit_transferred=net_profit,
            total_revenue_closed=tot_rev,
            total_expenses_closed=tot_exp,
            retained_earnings_new_balance=round(re_new_bal, 2),
        )

    # ================= 5. Direct Expense Voucher Management =================
    @staticmethod
    async def generate_expense_voucher_number(db: AsyncSession, tenant_id: int) -> str:
        """Generate next sequential Expense Voucher number: EXP-YYYYMM-XXXX."""
        now = datetime.now(timezone.utc)
        prefix = f"EXP-{now.strftime('%Y%m')}"
        stmt = (
            select(func.count(ExpenseVoucher.id))
            .where(
                ExpenseVoucher.tenant_id == tenant_id,
                ExpenseVoucher.voucher_number.like(f"{prefix}-%"),
            )
        )
        res = await db.execute(stmt)
        count = res.scalar() or 0
        return f"{prefix}-{count + 1:04d}"

    @staticmethod
    async def create_expense_voucher(
        db: AsyncSession,
        tenant_id: int,
        user_id: int,
        data: ExpenseVoucherCreate,
    ) -> ExpenseVoucherItem:
        """
        Record a direct operational expense voucher (e.g. Electricity, Chai, Rent, Fuel, Salaries).
        Automatically posts a balanced double-entry Journal Voucher (Dr Expense, Cr Cash/Bank).
        """
        # Validate expense account
        exp_res = await db.execute(
            select(Account).where(
                Account.id == data.expense_account_id,
                Account.tenant_id == tenant_id,
                Account.is_active.is_(True),
            )
        )
        exp_acc = exp_res.scalars().first()
        if not exp_acc:
            raise HTTPException(status_code=400, detail="Invalid or inactive expense account.")
        if exp_acc.account_type != "expense":
            raise HTTPException(
                status_code=400,
                detail=f"Account '{exp_acc.name}' is of type '{exp_acc.account_type}'. Must select an expense head.",
            )

        # Resolve paid from account (Cash drawer or Bank account)
        paid_from_id = data.paid_from_account_id
        if not paid_from_id:
            settings = await AccountingService.get_tenant_settings(db, tenant_id)
            pm_key = (data.payment_method or "cash").lower()
            method_map = settings.payment_method_mappings or {}
            target_id = method_map.get(pm_key)
            if not target_id:
                if pm_key == "cash":
                    target_id = settings.default_cash_account_id
                else:
                    target_id = settings.default_bank_account_id or settings.default_cash_account_id

            if not target_id:
                # Fallback to code 1010 or 1020
                fallback_code = "1010" if pm_key == "cash" else "1020"
                fb_res = await db.execute(
                    select(Account.id).where(Account.tenant_id == tenant_id, Account.code == fallback_code)
                )
                target_id = fb_res.scalar_one_or_none()

            paid_from_id = target_id

        if not paid_from_id:
            raise HTTPException(status_code=400, detail="Could not resolve cash or bank account for payment.")

        paid_res = await db.execute(
            select(Account).where(
                Account.id == paid_from_id,
                Account.tenant_id == tenant_id,
                Account.is_active.is_(True),
            )
        )
        paid_acc = paid_res.scalars().first()
        if not paid_acc:
            raise HTTPException(status_code=400, detail="Invalid or inactive paid-from account.")

        v_number = await AccountingService.generate_expense_voucher_number(db, tenant_id)
        e_date = data.expense_date or datetime.now(timezone.utc)

        expense = ExpenseVoucher(
            tenant_id=tenant_id,
            branch_id=data.branch_id,
            voucher_number=v_number,
            expense_date=e_date,
            expense_account_id=exp_acc.id,
            paid_from_account_id=paid_acc.id,
            amount=round(data.amount, 2),
            payment_method=data.payment_method.lower(),
            payee_name=data.payee_name.strip(),
            reference_no=data.reference_no.strip() if data.reference_no else None,
            narration=data.narration.strip() if data.narration else None,
            attachment_url=data.attachment_url,
            status="posted",
            created_by_id=user_id,
        )
        db.add(expense)
        await db.flush()

        # Auto-post double-entry JV
        from app.modules.accounting.posting import AccountingPostingEngine
        jv = await AccountingPostingEngine.post_expense_voucher(
            db=db,
            tenant_id=tenant_id,
            expense=expense,
            user_id=user_id,
        )

        await db.commit()

        # Fetch populated item for response
        return await AccountingService.get_expense_voucher(db, tenant_id, expense.id)

    @staticmethod
    async def get_expense_voucher(db: AsyncSession, tenant_id: int, expense_id: int) -> ExpenseVoucherItem:
        """Fetch single populated expense voucher."""
        stmt = (
            select(ExpenseVoucher)
            .options(
                joinedload(ExpenseVoucher.branch),
                joinedload(ExpenseVoucher.expense_account),
                joinedload(ExpenseVoucher.paid_from_account),
                joinedload(ExpenseVoucher.created_by),
                joinedload(ExpenseVoucher.journal_entry),
            )
            .where(ExpenseVoucher.id == expense_id, ExpenseVoucher.tenant_id == tenant_id)
        )
        res = await db.execute(stmt)
        ev = res.scalars().first()
        if not ev:
            raise HTTPException(status_code=404, detail="Expense voucher not found.")

        return ExpenseVoucherItem(
            id=ev.id,
            tenant_id=ev.tenant_id,
            branch_id=ev.branch_id,
            branch_name=ev.branch.name if ev.branch else None,
            voucher_number=ev.voucher_number,
            expense_date=ev.expense_date,
            expense_account_id=ev.expense_account_id,
            expense_account_code=ev.expense_account.code,
            expense_account_name=ev.expense_account.name,
            paid_from_account_id=ev.paid_from_account_id,
            paid_from_account_code=ev.paid_from_account.code,
            paid_from_account_name=ev.paid_from_account.name,
            amount=float(ev.amount),
            payment_method=ev.payment_method,
            payee_name=ev.payee_name,
            reference_no=ev.reference_no,
            narration=ev.narration,
            attachment_url=ev.attachment_url,
            status=ev.status,
            journal_entry_id=ev.journal_entry_id,
            journal_entry_number=ev.journal_entry.entry_number if ev.journal_entry else None,
            created_by_name=ev.created_by.full_name if ev.created_by else None,
            created_at=ev.created_at,
        )

    @staticmethod
    async def list_expense_vouchers(
        db: AsyncSession,
        tenant_id: int,
        branch_id: Optional[int] = None,
        expense_account_id: Optional[int] = None,
        payment_method: Optional[str] = None,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
        search: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> PaginatedExpenseVouchersResponse:
        """List paginated expense vouchers with comprehensive filtering."""
        filters = [ExpenseVoucher.tenant_id == tenant_id]

        if branch_id:
            filters.append(ExpenseVoucher.branch_id == branch_id)
        if expense_account_id:
            filters.append(ExpenseVoucher.expense_account_id == expense_account_id)
        if payment_method and payment_method != "all":
            filters.append(ExpenseVoucher.payment_method == payment_method.lower())
        if from_date:
            f_dt = datetime(from_date.year, from_date.month, from_date.day, 0, 0, 0, tzinfo=timezone.utc)
            filters.append(ExpenseVoucher.expense_date >= f_dt)
        if to_date:
            t_dt = datetime(to_date.year, to_date.month, to_date.day, 23, 59, 59, 999999, tzinfo=timezone.utc)
            filters.append(ExpenseVoucher.expense_date <= t_dt)

        if search:
            q = f"%{search.strip().lower()}%"
            filters.append(
                or_(
                    func.lower(ExpenseVoucher.voucher_number).like(q),
                    func.lower(ExpenseVoucher.payee_name).like(q),
                    func.lower(ExpenseVoucher.reference_no).like(q),
                    func.lower(ExpenseVoucher.narration).like(q),
                )
            )

        # Count total
        count_stmt = select(func.count(ExpenseVoucher.id)).where(and_(*filters))
        total = (await db.execute(count_stmt)).scalar() or 0

        # Items
        stmt = (
            select(ExpenseVoucher)
            .options(
                joinedload(ExpenseVoucher.branch),
                joinedload(ExpenseVoucher.expense_account),
                joinedload(ExpenseVoucher.paid_from_account),
                joinedload(ExpenseVoucher.created_by),
                joinedload(ExpenseVoucher.journal_entry),
            )
            .where(and_(*filters))
            .order_by(desc(ExpenseVoucher.expense_date), desc(ExpenseVoucher.id))
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        res = await db.execute(stmt)
        rows = res.scalars().all()

        items = [
            ExpenseVoucherItem(
                id=ev.id,
                tenant_id=ev.tenant_id,
                branch_id=ev.branch_id,
                branch_name=ev.branch.name if ev.branch else None,
                voucher_number=ev.voucher_number,
                expense_date=ev.expense_date,
                expense_account_id=ev.expense_account_id,
                expense_account_code=ev.expense_account.code,
                expense_account_name=ev.expense_account.name,
                paid_from_account_id=ev.paid_from_account_id,
                paid_from_account_code=ev.paid_from_account.code,
                paid_from_account_name=ev.paid_from_account.name,
                amount=float(ev.amount),
                payment_method=ev.payment_method,
                payee_name=ev.payee_name,
                reference_no=ev.reference_no,
                narration=ev.narration,
                attachment_url=ev.attachment_url,
                status=ev.status,
                journal_entry_id=ev.journal_entry_id,
                journal_entry_number=ev.journal_entry.entry_number if ev.journal_entry else None,
                created_by_name=ev.created_by.full_name if ev.created_by else None,
                created_at=ev.created_at,
            )
            for ev in rows
        ]

        pages = math.ceil(total / page_size) if total > 0 else 1
        return PaginatedExpenseVouchersResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            pages=pages,
        )

    @staticmethod
    async def get_expense_summary(
        db: AsyncSession,
        tenant_id: int,
        branch_id: Optional[int] = None,
    ) -> ExpenseSummaryResponse:
        """Get summary KPIs and category breakdown for operational expenses."""
        now = datetime.now(timezone.utc)
        today_start = datetime(now.year, now.month, now.day, 0, 0, 0, tzinfo=timezone.utc)
        today_end = datetime(now.year, now.month, now.day, 23, 59, 59, 999999, tzinfo=timezone.utc)
        month_start = datetime(now.year, now.month, 1, 0, 0, 0, tzinfo=timezone.utc)

        base_filters = [
            ExpenseVoucher.tenant_id == tenant_id,
            ExpenseVoucher.status == "posted",
        ]
        if branch_id:
            base_filters.append(ExpenseVoucher.branch_id == branch_id)

        # 1. Today's total
        t_stmt = select(func.coalesce(func.sum(ExpenseVoucher.amount), 0.0)).where(
            and_(*base_filters, ExpenseVoucher.expense_date >= today_start, ExpenseVoucher.expense_date <= today_end)
        )
        today_tot = float((await db.execute(t_stmt)).scalar() or 0.0)

        # 2. Month's total
        m_stmt = select(func.coalesce(func.sum(ExpenseVoucher.amount), 0.0)).where(
            and_(*base_filters, ExpenseVoucher.expense_date >= month_start)
        )
        month_tot = float((await db.execute(m_stmt)).scalar() or 0.0)

        # 3. Cash total (this month)
        c_stmt = select(func.coalesce(func.sum(ExpenseVoucher.amount), 0.0)).where(
            and_(*base_filters, ExpenseVoucher.expense_date >= month_start, ExpenseVoucher.payment_method == "cash")
        )
        cash_tot = float((await db.execute(c_stmt)).scalar() or 0.0)

        # 4. Bank/Other total (this month)
        b_stmt = select(func.coalesce(func.sum(ExpenseVoucher.amount), 0.0)).where(
            and_(*base_filters, ExpenseVoucher.expense_date >= month_start, ExpenseVoucher.payment_method != "cash")
        )
        bank_tot = float((await db.execute(b_stmt)).scalar() or 0.0)

        # 5. Category-wise breakdown (this month)
        cat_stmt = (
            select(
                Account.id,
                Account.code,
                Account.name,
                func.coalesce(func.sum(ExpenseVoucher.amount), 0.0).label("tot_amount"),
                func.count(ExpenseVoucher.id).label("voucher_count"),
            )
            .join(ExpenseVoucher, ExpenseVoucher.expense_account_id == Account.id)
            .where(and_(*base_filters, ExpenseVoucher.expense_date >= month_start))
            .group_by(Account.id, Account.code, Account.name)
            .order_by(desc("tot_amount"))
        )
        cat_res = await db.execute(cat_stmt)
        cat_breakdown = [
            {
                "account_id": r.id,
                "account_code": r.code,
                "account_name": r.name,
                "amount": round(float(r.tot_amount), 2),
                "count": int(r.voucher_count),
            }
            for r in cat_res.all()
        ]

        return ExpenseSummaryResponse(
            today_total=round(today_tot, 2),
            month_total=round(month_tot, 2),
            cash_total=round(cash_tot, 2),
            bank_total=round(bank_tot, 2),
            category_breakdown=cat_breakdown,
        )

    @staticmethod
    async def cancel_expense_voucher(
        db: AsyncSession,
        tenant_id: int,
        expense_id: int,
        user_id: int,
    ) -> bool:
        """Cancel an expense voucher and void its corresponding journal entry."""
        stmt = select(ExpenseVoucher).where(ExpenseVoucher.id == expense_id, ExpenseVoucher.tenant_id == tenant_id)
        res = await db.execute(stmt)
        ev = res.scalars().first()
        if not ev:
            raise HTTPException(status_code=404, detail="Expense voucher not found.")
        if ev.status == "cancelled":
            raise HTTPException(status_code=400, detail="Expense voucher is already cancelled.")

        ev.status = "cancelled"

        # Void linked JournalEntry if exists
        if ev.journal_entry_id:
            jv_stmt = select(JournalEntry).where(JournalEntry.id == ev.journal_entry_id, JournalEntry.tenant_id == tenant_id)
            jv_res = await db.execute(jv_stmt)
            jv = jv_res.scalars().first()
            if jv:
                jv.status = "void"

        await db.commit()
        return True

    # ================= 6. Bank Reconciliation (BRS) Engine =================
    @staticmethod
    async def get_reconcilable_bank_accounts(
        db: AsyncSession,
        tenant_id: int,
    ) -> List[BankReconcilableAccountItem]:
        """Fetch all bank accounts eligible for reconciliation with current balance and pending unreconciled count."""
        stmt = (
            select(Account)
            .where(
                Account.tenant_id == tenant_id,
                Account.is_active == True,
                or_(Account.sub_type == "bank", Account.code == "1020"),
            )
            .order_by(Account.code.asc())
        )
        res = await db.execute(stmt)
        accounts = res.scalars().all()

        items: List[BankReconcilableAccountItem] = []
        for acc in accounts:
            bal_stmt = (
                select(
                    func.coalesce(func.sum(JournalEntryLine.debit), 0.0).label("tot_dr"),
                    func.coalesce(func.sum(JournalEntryLine.credit), 0.0).label("tot_cr"),
                )
                .join(JournalEntry, JournalEntry.id == JournalEntryLine.journal_entry_id)
                .where(
                    JournalEntry.tenant_id == tenant_id,
                    JournalEntry.status == "posted",
                    JournalEntryLine.account_id == acc.id,
                )
            )
            bal_res = await db.execute(bal_stmt)
            tot_dr, tot_cr = bal_res.first()
            cur_bal = round(float(tot_dr) - float(tot_cr), 2)

            unrec_stmt = (
                select(func.count(JournalEntryLine.id))
                .join(JournalEntry, JournalEntry.id == JournalEntryLine.journal_entry_id)
                .where(
                    JournalEntry.tenant_id == tenant_id,
                    JournalEntry.status == "posted",
                    JournalEntryLine.account_id == acc.id,
                    JournalEntryLine.is_reconciled == False,
                )
            )
            unrec_res = await db.execute(unrec_stmt)
            unrec_count = unrec_res.scalar_one()

            items.append(
                BankReconcilableAccountItem(
                    id=acc.id,
                    code=acc.code,
                    name=acc.name,
                    currency=acc.currency,
                    current_balance=cur_bal,
                    unreconciled_count=unrec_count,
                )
            )
        return items

    @staticmethod
    async def create_bank_reconciliation(
        db: AsyncSession,
        tenant_id: int,
        user_id: int,
        payload: BankReconciliationCreateRequest,
    ) -> BankReconciliationDetailResponse:
        """Initialize a new Bank Reconciliation session."""
        acc = await db.get(Account, payload.account_id)
        if not acc or acc.tenant_id != tenant_id:
            raise HTTPException(status_code=404, detail="Bank account not found.")

        stmt_date = payload.statement_date
        stmt_end_dt = datetime(stmt_date.year, stmt_date.month, stmt_date.day, 23, 59, 59, tzinfo=timezone.utc)
        stmt_start_dt = None
        if payload.statement_start_date:
            s_d = payload.statement_start_date
            stmt_start_dt = datetime(s_d.year, s_d.month, s_d.day, 0, 0, 0, tzinfo=timezone.utc)

        bal_stmt = (
            select(
                func.coalesce(func.sum(JournalEntryLine.debit), 0.0).label("tot_dr"),
                func.coalesce(func.sum(JournalEntryLine.credit), 0.0).label("tot_cr"),
            )
            .join(JournalEntry, JournalEntry.id == JournalEntryLine.journal_entry_id)
            .where(
                JournalEntry.tenant_id == tenant_id,
                JournalEntry.status == "posted",
                JournalEntryLine.account_id == acc.id,
                JournalEntry.entry_date <= stmt_end_dt,
            )
        )
        if payload.branch_id:
            bal_stmt = bal_stmt.where(JournalEntryLine.branch_id == payload.branch_id)

        bal_res = await db.execute(bal_stmt)
        tot_dr, tot_cr = bal_res.first()
        book_balance = round(float(tot_dr) - float(tot_cr), 2)
        stmt_ending_bal = round(payload.statement_ending_balance, 2)

        count_stmt = select(func.count(BankReconciliation.id)).where(BankReconciliation.tenant_id == tenant_id)
        c_res = await db.execute(count_stmt)
        seq = (c_res.scalar_one() or 0) + 1
        rec_number = f"BRS-{stmt_date.strftime('%Y%m')}-{seq:04d}"

        brs = BankReconciliation(
            tenant_id=tenant_id,
            account_id=acc.id,
            branch_id=payload.branch_id,
            reconciliation_number=rec_number,
            statement_date=stmt_end_dt,
            statement_start_date=stmt_start_dt,
            statement_ending_balance=stmt_ending_bal,
            book_balance=book_balance,
            cleared_deposits=0.00,
            cleared_payments=0.00,
            reconciled_balance=stmt_ending_bal,
            difference=round(stmt_ending_bal - book_balance, 2),
            status="in_progress",
            notes=payload.notes,
        )
        db.add(brs)
        await db.flush()

        lines_stmt = (
            select(JournalEntryLine)
            .join(JournalEntry, JournalEntry.id == JournalEntryLine.journal_entry_id)
            .where(
                JournalEntry.tenant_id == tenant_id,
                JournalEntry.status == "posted",
                JournalEntryLine.account_id == acc.id,
                JournalEntryLine.is_reconciled == False,
                JournalEntry.entry_date <= stmt_end_dt,
            )
            .order_by(JournalEntry.entry_date.asc(), JournalEntry.id.asc())
        )
        if stmt_start_dt:
            lines_stmt = lines_stmt.where(JournalEntry.entry_date >= stmt_start_dt)
        if payload.branch_id:
            lines_stmt = lines_stmt.where(JournalEntryLine.branch_id == payload.branch_id)

        lines_res = await db.execute(lines_stmt)
        lines = lines_res.scalars().all()

        for line in lines:
            item = BankReconciliationItem(
                reconciliation_id=brs.id,
                journal_entry_line_id=line.id,
                is_matched=False,
            )
            db.add(item)

        await db.commit()
        return await AccountingService.get_bank_reconciliation_details(db, tenant_id, brs.id)

    @staticmethod
    async def get_bank_reconciliation_details(
        db: AsyncSession,
        tenant_id: int,
        reconciliation_id: int,
    ) -> BankReconciliationDetailResponse:
        """Fetch complete BRS session details with transactions, in-transit items, and live variance."""
        stmt = (
            select(BankReconciliation)
            .options(
                selectinload(BankReconciliation.account),
                selectinload(BankReconciliation.branch),
                selectinload(BankReconciliation.reconciled_by),
                selectinload(BankReconciliation.items).selectinload(BankReconciliationItem.journal_entry_line).selectinload(JournalEntryLine.journal_entry),
            )
            .where(
                BankReconciliation.id == reconciliation_id,
                BankReconciliation.tenant_id == tenant_id,
            )
        )
        res = await db.execute(stmt)
        brs = res.scalars().first()
        if not brs:
            raise HTTPException(status_code=404, detail="Bank reconciliation not found.")

        cleared_deposits = 0.0
        cleared_payments = 0.0
        deposits_in_transit = 0.0
        outstanding_payments = 0.0

        tx_items: List[BankReconciliationTransactionItem] = []
        for item in brs.items:
            line = item.journal_entry_line
            jv = line.journal_entry if line else None
            if not line or not jv:
                continue

            dr = float(line.debit)
            cr = float(line.credit)

            if item.is_matched:
                cleared_deposits += dr
                cleared_payments += cr
            else:
                deposits_in_transit += dr
                outstanding_payments += cr

            tx_items.append(
                BankReconciliationTransactionItem(
                    journal_entry_line_id=line.id,
                    journal_entry_id=jv.id,
                    entry_number=jv.entry_number,
                    entry_date=jv.entry_date.strftime("%Y-%m-%d"),
                    source_type=jv.source_type,
                    reference_no=jv.reference_no,
                    narration=line.narration or jv.narration,
                    debit=dr,
                    credit=cr,
                    is_matched=item.is_matched,
                    matched_at=item.matched_at.isoformat() if item.matched_at else None,
                )
            )

        tx_items.sort(key=lambda x: x.entry_date, reverse=True)

        cleared_deposits = round(cleared_deposits, 2)
        cleared_payments = round(cleared_payments, 2)
        deposits_in_transit = round(deposits_in_transit, 2)
        outstanding_payments = round(outstanding_payments, 2)

        adjusted_bank_balance = round(float(brs.statement_ending_balance) + deposits_in_transit - outstanding_payments, 2)
        difference = round(adjusted_bank_balance - float(brs.book_balance), 2)
        is_balanced = abs(difference) < 0.005

        brs.cleared_deposits = cleared_deposits
        brs.cleared_payments = cleared_payments
        brs.reconciled_balance = adjusted_bank_balance
        brs.difference = difference
        await db.commit()

        summary = BankReconciliationSummary(
            id=brs.id,
            reconciliation_number=brs.reconciliation_number,
            account_id=brs.account_id,
            account_code=brs.account.code if brs.account else "",
            account_name=brs.account.name if brs.account else "",
            branch_id=brs.branch_id,
            statement_date=brs.statement_date.strftime("%Y-%m-%d"),
            statement_start_date=brs.statement_start_date.strftime("%Y-%m-%d") if brs.statement_start_date else None,
            statement_ending_balance=float(brs.statement_ending_balance),
            book_balance=float(brs.book_balance),
            cleared_deposits=cleared_deposits,
            cleared_payments=cleared_payments,
            reconciled_balance=adjusted_bank_balance,
            difference=difference,
            status=brs.status,
            notes=brs.notes,
            reconciled_by_name=brs.reconciled_by.full_name if brs.reconciled_by else None,
            reconciled_at=brs.reconciled_at.isoformat() if brs.reconciled_at else None,
            created_at=brs.created_at.isoformat(),
        )

        return BankReconciliationDetailResponse(
            reconciliation=summary,
            deposits_in_transit=deposits_in_transit,
            outstanding_payments=outstanding_payments,
            adjusted_book_balance=adjusted_bank_balance,
            is_balanced=is_balanced,
            transactions=tx_items,
        )

    @staticmethod
    async def match_bank_reconciliation_items(
        db: AsyncSession,
        tenant_id: int,
        reconciliation_id: int,
        payload: BankReconciliationMatchRequest,
    ) -> BankReconciliationDetailResponse:
        """Mark specific transactions as cleared/matched or keep in transit."""
        brs = await db.get(BankReconciliation, reconciliation_id)
        if not brs or brs.tenant_id != tenant_id:
            raise HTTPException(status_code=404, detail="Bank reconciliation not found.")
        if brs.status != "in_progress":
            raise HTTPException(status_code=400, detail="Cannot modify a completed or cancelled reconciliation.")

        now = datetime.now(timezone.utc)
        if payload.matched_line_ids:
            stmt = (
                select(BankReconciliationItem)
                .where(
                    BankReconciliationItem.reconciliation_id == reconciliation_id,
                    BankReconciliationItem.journal_entry_line_id.in_(payload.matched_line_ids),
                )
            )
            res = await db.execute(stmt)
            for item in res.scalars().all():
                item.is_matched = True
                item.matched_at = now

        if payload.unmatched_line_ids:
            stmt = (
                select(BankReconciliationItem)
                .where(
                    BankReconciliationItem.reconciliation_id == reconciliation_id,
                    BankReconciliationItem.journal_entry_line_id.in_(payload.unmatched_line_ids),
                )
            )
            res = await db.execute(stmt)
            for item in res.scalars().all():
                item.is_matched = False

        await db.commit()
        return await AccountingService.get_bank_reconciliation_details(db, tenant_id, reconciliation_id)

    @staticmethod
    async def complete_bank_reconciliation(
        db: AsyncSession,
        tenant_id: int,
        user_id: int,
        reconciliation_id: int,
        payload: BankReconciliationCompleteRequest,
    ) -> BankReconciliationDetailResponse:
        """Formally finalize and lock the Bank Reconciliation statement."""
        details = await AccountingService.get_bank_reconciliation_details(db, tenant_id, reconciliation_id)
        if details.reconciliation.status != "in_progress":
            raise HTTPException(status_code=400, detail="Reconciliation is not in progress.")

        if not details.is_balanced:
            diff = details.reconciliation.difference
            raise HTTPException(
                status_code=400,
                detail=f"Cannot complete reconciliation: Book and Bank balances are not in equilibrium. Discrepancy: PKR {diff:,.2f}. Difference must be 0.00.",
            )

        brs = await db.get(BankReconciliation, reconciliation_id)
        now = datetime.now(timezone.utc)
        brs.status = "completed"
        brs.reconciled_by_id = user_id
        brs.reconciled_at = now
        if payload.notes:
            brs.notes = payload.notes

        matched_line_ids = [t.journal_entry_line_id for t in details.transactions if t.is_matched]
        if matched_line_ids:
            l_stmt = select(JournalEntryLine).where(JournalEntryLine.id.in_(matched_line_ids))
            l_res = await db.execute(l_stmt)
            for line in l_res.scalars().all():
                line.is_reconciled = True
                line.reconciled_at = now

        await db.commit()
        return await AccountingService.get_bank_reconciliation_details(db, tenant_id, reconciliation_id)

    @staticmethod
    async def list_bank_reconciliations(
        db: AsyncSession,
        tenant_id: int,
        account_id: Optional[int] = None,
        status: Optional[str] = None,
    ) -> List[BankReconciliationSummary]:
        """List past and active bank reconciliation statements."""
        stmt = (
            select(BankReconciliation)
            .options(
                selectinload(BankReconciliation.account),
                selectinload(BankReconciliation.reconciled_by),
            )
            .where(BankReconciliation.tenant_id == tenant_id)
            .order_by(BankReconciliation.statement_date.desc(), BankReconciliation.id.desc())
        )
        if account_id:
            stmt = stmt.where(BankReconciliation.account_id == account_id)
        if status:
            stmt = stmt.where(BankReconciliation.status == status)

        res = await db.execute(stmt)
        reconciliations = res.scalars().all()

        return [
            BankReconciliationSummary(
                id=r.id,
                reconciliation_number=r.reconciliation_number,
                account_id=r.account_id,
                account_code=r.account.code if r.account else "",
                account_name=r.account.name if r.account else "",
                branch_id=r.branch_id,
                statement_date=r.statement_date.strftime("%Y-%m-%d"),
                statement_start_date=r.statement_start_date.strftime("%Y-%m-%d") if r.statement_start_date else None,
                statement_ending_balance=float(r.statement_ending_balance),
                book_balance=float(r.book_balance),
                cleared_deposits=float(r.cleared_deposits),
                cleared_payments=float(r.cleared_payments),
                reconciled_balance=float(r.reconciled_balance),
                difference=float(r.difference),
                status=r.status,
                notes=r.notes,
                reconciled_by_name=r.reconciled_by.full_name if r.reconciled_by else None,
                reconciled_at=r.reconciled_at.isoformat() if r.reconciled_at else None,
                created_at=r.created_at.isoformat(),
            )
            for r in reconciliations
        ]



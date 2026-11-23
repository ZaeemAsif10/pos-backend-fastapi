from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, date, timezone
from fastapi import HTTPException, status
from sqlalchemy import select, func, or_, and_, update, delete
from sqlalchemy.orm import joinedload, selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.inventory.models import (
    Purchase,
    PurchaseItem,
    PurchaseReturn,
    PurchaseReturnItem,
    StockMovement,
    StockTransfer,
    StockTransferItem,
    StockAdjustment,
    StockAdjustmentItem,
    PaymentStatusOption,
)
from app.modules.products.models import Product, BranchStock, ProductUOMConversion
from app.modules.branches.models import Branch
from app.modules.parties.models import Supplier
from app.modules.auth.models import User
from app.modules.inventory.schemas import (
    PurchaseCreate,
    PurchaseUpdate,
    PurchaseResponse,
    PurchaseDetailResponse,
    PurchaseItemResponse,
    PurchaseStatsResponse,
    PurchaseReturnItemInput,
    PurchaseReturnRequest,
    StandalonePurchaseReturnCreate,
    PurchaseReturnResponse,
    PurchaseReturnItemResponse,
    LiveInventoryItem,
    StockMovementResponse,
    StockTransferCreate,
    StockTransferResponse,
    StockAdjustmentCreate,
    StockAdjustmentResponse,
    PaymentStatusOptionCreate,
    PaymentStatusOptionUpdate,
    PaymentStatusOptionResponse,
)


class PaymentStatusService:
    DEFAULT_STATUSES = [
        {
            "name": "Paid",
            "code": "paid",
            "accounting_type": "paid",
            "color": "emerald",
            "description": "Full payment settled immediately via Cash or Bank",
            "is_system": True,
        },
        {
            "name": "Unpaid",
            "code": "unpaid",
            "accounting_type": "unpaid",
            "color": "rose",
            "description": "Credit purchase credited to Supplier Khata (Accounts Payable)",
            "is_system": True,
        },
    ]

    @staticmethod
    async def ensure_defaults(db: AsyncSession, tenant_id: int) -> None:
        res = await db.execute(
            select(PaymentStatusOption).where(PaymentStatusOption.tenant_id == tenant_id)
        )
        existing = {row.code.lower(): row for row in res.scalars().all()}
        now = datetime.now(timezone.utc)
        added = False
        for d in PaymentStatusService.DEFAULT_STATUSES:
            if d["code"] not in existing:
                opt = PaymentStatusOption(
                    tenant_id=tenant_id,
                    name=d["name"],
                    code=d["code"],
                    accounting_type=d["accounting_type"],
                    color=d["color"],
                    description=d["description"],
                    is_system=d["is_system"],
                    is_active=True,
                    created_at=now,
                    updated_at=now,
                )
                db.add(opt)
                added = True
        if added:
            await db.commit()

    @staticmethod
    async def list_payment_statuses(
        db: AsyncSession, tenant_id: int, active_only: bool = False
    ) -> List[PaymentStatusOptionResponse]:
        await PaymentStatusService.ensure_defaults(db, tenant_id)
        stmt = select(PaymentStatusOption).where(PaymentStatusOption.tenant_id == tenant_id)
        if active_only:
            stmt = stmt.where(PaymentStatusOption.is_active.is_(True))
        stmt = stmt.order_by(PaymentStatusOption.id.asc())
        res = await db.execute(stmt)
        return [PaymentStatusOptionResponse.model_validate(r) for r in res.scalars().all()]

    @staticmethod
    async def create_payment_status(
        db: AsyncSession, tenant_id: int, payload: PaymentStatusOptionCreate
    ) -> PaymentStatusOptionResponse:
        await PaymentStatusService.ensure_defaults(db, tenant_id)
        raw_code = (payload.code or payload.name).strip().lower().replace(" ", "_")
        dup = await db.execute(
            select(PaymentStatusOption).where(
                PaymentStatusOption.tenant_id == tenant_id,
                func.lower(PaymentStatusOption.code) == raw_code,
            )
        )
        if dup.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Payment status with code '{raw_code}' already exists.",
            )
        acc_type = (payload.accounting_type or "unpaid").lower()
        if acc_type not in ("paid", "unpaid", "partial"):
            acc_type = "unpaid"

        now = datetime.now(timezone.utc)
        opt = PaymentStatusOption(
            tenant_id=tenant_id,
            name=payload.name.strip(),
            code=raw_code,
            accounting_type=acc_type,
            color=(payload.color or ("emerald" if acc_type == "paid" else "rose")).strip().lower(),
            description=payload.description.strip() if payload.description else None,
            is_system=False,
            is_active=payload.is_active,
            created_at=now,
            updated_at=now,
        )
        db.add(opt)
        await db.commit()
        await db.refresh(opt)
        return PaymentStatusOptionResponse.model_validate(opt)

    @staticmethod
    async def update_payment_status(
        db: AsyncSession, tenant_id: int, status_id: int, payload: PaymentStatusOptionUpdate
    ) -> PaymentStatusOptionResponse:
        res = await db.execute(
            select(PaymentStatusOption).where(
                PaymentStatusOption.tenant_id == tenant_id,
                PaymentStatusOption.id == status_id,
            )
        )
        opt = res.scalar_one_or_none()
        if not opt:
            raise HTTPException(status_code=404, detail="Payment status not found.")

        if payload.name is not None:
            opt.name = payload.name.strip()
        if payload.accounting_type is not None:
            acc_type = payload.accounting_type.lower()
            if acc_type in ("paid", "unpaid", "partial"):
                opt.accounting_type = acc_type
        if payload.color is not None:
            opt.color = payload.color.strip().lower()
        if payload.description is not None:
            opt.description = payload.description.strip() if payload.description else None
        if payload.is_active is not None:
            opt.is_active = payload.is_active
        opt.updated_at = datetime.now(timezone.utc)

        await db.commit()
        await db.refresh(opt)
        return PaymentStatusOptionResponse.model_validate(opt)

    @staticmethod
    async def delete_payment_status(
        db: AsyncSession, tenant_id: int, status_id: int
    ) -> Dict[str, Any]:
        res = await db.execute(
            select(PaymentStatusOption).where(
                PaymentStatusOption.tenant_id == tenant_id,
                PaymentStatusOption.id == status_id,
            )
        )
        opt = res.scalar_one_or_none()
        if not opt:
            raise HTTPException(status_code=404, detail="Payment status not found.")
        if opt.is_system:
            raise HTTPException(
                status_code=400,
                detail=f"Core payment status '{opt.name}' cannot be deleted. You can edit it instead.",
            )
        name = opt.name
        await db.delete(opt)
        await db.commit()
        return {"message": f"Payment status '{name}' deleted successfully."}

    @staticmethod
    async def resolve_behavior(
        db: AsyncSession, tenant_id: int, status_code: Optional[str]
    ) -> Tuple[str, str]:
        await PaymentStatusService.ensure_defaults(db, tenant_id)
        code_clean = (status_code or "unpaid").strip().lower()
        res = await db.execute(
            select(PaymentStatusOption).where(
                PaymentStatusOption.tenant_id == tenant_id,
                func.lower(PaymentStatusOption.code) == code_clean,
            )
        )
        opt = res.scalar_one_or_none()
        if opt:
            return opt.code, opt.accounting_type
        if code_clean == "paid":
            return "paid", "paid"
        if code_clean == "partial":
            return "partial", "partial"
        return code_clean or "unpaid", "unpaid"


class PurchaseService:
    @staticmethod
    async def get_purchase_stats(db: AsyncSession, tenant_id: int) -> PurchaseStatsResponse:
        """Calculate KPI overview for purchases."""
        # Total Purchases count & amount
        tot_stmt = select(
            func.count(Purchase.id),
            func.coalesce(func.sum(Purchase.total_amount), 0),
            func.coalesce(func.sum(Purchase.balance_due), 0),
        ).where(Purchase.tenant_id == tenant_id, Purchase.status != "cancelled")
        tot_res = await db.execute(tot_stmt)
        count, total_amt, unpaid_pay = tot_res.one()

        # Monthly purchases amount (current month)
        current_year = datetime.now(timezone.utc).year
        current_month = datetime.now(timezone.utc).month
        start_date = date(current_year, current_month, 1)

        m_stmt = select(func.coalesce(func.sum(Purchase.total_amount), 0)).where(
            Purchase.tenant_id == tenant_id,
            Purchase.status != "cancelled",
            Purchase.purchase_date >= start_date,
        )
        m_res = await db.execute(m_stmt)
        monthly_amt = m_res.scalar() or 0.0

        return PurchaseStatsResponse(
            total_purchases_count=count or 0,
            total_purchases_amount=float(total_amt or 0.0),
            total_unpaid_payables=float(unpaid_pay or 0.0),
            monthly_purchases_amount=float(monthly_amt or 0.0),
        )

    @staticmethod
    async def list_purchases(
        db: AsyncSession,
        tenant_id: int,
        branch_id: Optional[int] = None,
        supplier_id: Optional[int] = None,
        payment_status: Optional[str] = None,
        search: Optional[str] = None,
    ) -> List[PurchaseResponse]:
        """List purchases with filters and branch/supplier names."""
        stmt = (
            select(
                Purchase,
                func.count(PurchaseItem.id).label("items_count"),
                func.coalesce(func.sum(PurchaseItem.quantity), 0).label("total_qty"),
                func.coalesce(func.sum(PurchaseItem.returned_quantity), 0).label("returned_qty"),
                func.coalesce(func.sum(PurchaseItem.returned_quantity * PurchaseItem.unit_cost), 0).label("returned_amount"),
            )
            .outerjoin(PurchaseItem, PurchaseItem.purchase_id == Purchase.id)
            .options(
                joinedload(Purchase.branch),
                joinedload(Purchase.supplier),
                joinedload(Purchase.paid_from_account),
            )
            .where(Purchase.tenant_id == tenant_id)
            .group_by(Purchase.id)
            .order_by(Purchase.purchase_date.desc(), Purchase.id.desc())
        )

        if branch_id:
            stmt = stmt.where(Purchase.branch_id == branch_id)
        if supplier_id:
            stmt = stmt.where(Purchase.supplier_id == supplier_id)
        if payment_status and payment_status != "all":
            stmt = stmt.where(Purchase.payment_status == payment_status)
        if search:
            s = f"%{search.strip().lower()}%"
            stmt = stmt.where(
                or_(
                    func.lower(Purchase.invoice_number).ilike(s),
                    func.lower(Purchase.supplier_bill_no).ilike(s),
                )
            )

        res = await db.execute(stmt)
        rows = res.unique().all()

        # Fetch linked Journal Vouchers for these purchases
        from app.modules.accounting.models import JournalEntry
        purchase_ids = [p.id for p, _, _, _, _ in rows]
        jv_map = {}
        if purchase_ids:
            jv_res = await db.execute(
                select(JournalEntry.source_id, JournalEntry.entry_number).where(
                    JournalEntry.tenant_id == tenant_id,
                    JournalEntry.source_type == "purchase_invoice",
                    JournalEntry.source_id.in_(purchase_ids),
                    JournalEntry.status == "posted",
                )
            )
            for s_id, e_num in jv_res.all():
                jv_map[s_id] = e_num

        results = []
        for p, count, tot_qty, ret_qty, ret_amt in rows:
            resp = PurchaseResponse.model_validate(p)
            resp.branch_name = p.branch.name if p.branch else None
            resp.supplier_name = p.supplier.company_name if p.supplier else None
            resp.paid_from_account_name = p.paid_from_account.name if p.paid_from_account else None
            resp.paid_from_account_code = p.paid_from_account.code if p.paid_from_account else None
            resp.journal_entry_number = jv_map.get(p.id)
            resp.items_count = count
            resp.total_qty = float(tot_qty or 0.0)
            resp.returned_qty = float(ret_qty or 0.0)
            resp.returned_amount = round(float(ret_amt or 0.0), 2)
            results.append(resp)
        return results

    @staticmethod
    async def get_purchase_detail(
        db: AsyncSession, tenant_id: int, purchase_id: int
    ) -> PurchaseDetailResponse:
        """Get full details of a purchase including all item rows."""
        stmt = (
            select(Purchase)
            .options(
                joinedload(Purchase.branch),
                joinedload(Purchase.supplier),
                joinedload(Purchase.paid_from_account),
                selectinload(Purchase.items).joinedload(PurchaseItem.product),
            )
            .where(Purchase.tenant_id == tenant_id, Purchase.id == purchase_id)
        )
        res = await db.execute(stmt)
        p = res.scalar_one_or_none()
        if not p:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Purchase with ID {purchase_id} was not found.",
            )

        from app.modules.accounting.models import JournalEntry
        jv_num = (
            await db.execute(
                select(JournalEntry.entry_number).where(
                    JournalEntry.tenant_id == tenant_id,
                    JournalEntry.source_type == "purchase_invoice",
                    JournalEntry.source_id == p.id,
                    JournalEntry.status == "posted",
                ).order_by(JournalEntry.id.desc()).limit(1)
            )
        ).scalar_one_or_none()

        resp = PurchaseDetailResponse.model_validate(p)
        resp.branch_name = p.branch.name if p.branch else None
        resp.supplier_name = p.supplier.company_name if p.supplier else None
        resp.paid_from_account_name = p.paid_from_account.name if p.paid_from_account else None
        resp.paid_from_account_code = p.paid_from_account.code if p.paid_from_account else None
        resp.journal_entry_number = jv_num
        resp.items_count = len(p.items)
        resp.total_qty = sum(float(i.quantity or 0.0) for i in p.items)
        resp.returned_qty = sum(float(getattr(i, "returned_quantity", 0.0) or 0.0) for i in p.items)
        resp.returned_amount = round(
            sum(float(getattr(i, "returned_quantity", 0.0) or 0.0) * float(i.unit_cost or 0.0) for i in p.items),
            2,
        )

        item_resps = []
        for item in p.items:
            i_resp = PurchaseItemResponse.model_validate(item)
            i_resp.product_name = item.product.name if item.product else None
            i_resp.product_sku = item.product.sku if item.product else None
            item_resps.append(i_resp)
        resp.items = item_resps
        return resp

    @staticmethod
    async def create_purchase(
        db: AsyncSession, tenant_id: int, user_id: Optional[int], payload: PurchaseCreate
    ) -> PurchaseResponse:
        """Create a purchase bill, increment stock, add stock movements, and update supplier balance."""
        # 1. Validate Branch & Supplier
        b_res = await db.execute(
            select(Branch).where(Branch.tenant_id == tenant_id, Branch.id == payload.branch_id)
        )
        branch = b_res.scalar_one_or_none()
        if not branch:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Branch not found.")

        s_res = await db.execute(
            select(Supplier).where(Supplier.tenant_id == tenant_id, Supplier.id == payload.supplier_id)
        )
        supplier = s_res.scalar_one_or_none()
        if not supplier:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Supplier not found.")

        # 2. Calculate Subtotal and Item Totals
        subtotal = 0.0
        items_tax_total = 0.0
        calculated_items = []
        for item_in in payload.items:
            # Check product
            p_res = await db.execute(
                select(Product).where(Product.tenant_id == tenant_id, Product.id == item_in.product_id)
            )
            product = p_res.scalar_one_or_none()
            if not product:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Product ID {item_in.product_id} not found.",
                )

            # Determine conversion factor
            factor = item_in.conversion_factor
            if item_in.uom_conversion_id:
                u_res = await db.execute(
                    select(ProductUOMConversion).where(
                        ProductUOMConversion.id == item_in.uom_conversion_id,
                        ProductUOMConversion.product_id == item_in.product_id,
                    )
                )
                uom = u_res.scalar_one_or_none()
                if uom:
                    factor = float(uom.conversion_factor)

            base_qty = float(item_in.quantity) * factor
            row_base_total = float(item_in.quantity) * float(item_in.unit_cost)
            row_tax_rate = float(getattr(item_in, "tax_rate", 0.0) or 0.0)
            row_tax_amount = (
                round(row_base_total * (row_tax_rate / 100.0), 2)
                if row_tax_rate > 0
                else float(getattr(item_in, "tax_amount", 0.0) or 0.0)
            )
            row_total = round(row_base_total + row_tax_amount, 2)
            subtotal += row_base_total
            items_tax_total += row_tax_amount

            calculated_items.append({
                "product": product,
                "input": item_in,
                "factor": factor,
                "base_qty": base_qty,
                "row_base_total": row_base_total,
                "row_tax_rate": row_tax_rate,
                "row_tax_amount": row_tax_amount,
                "row_total": row_total,
            })

        # 3. Calculate Bill Totals & Payment Status Behavior
        effective_tax_amount = round(items_tax_total, 2) if items_tax_total > 0 else float(payload.tax_amount or 0.0)
        total_amount = subtotal - payload.discount_amount + effective_tax_amount + payload.shipping_cost

        resolved_code, acc_behavior = await PaymentStatusService.resolve_behavior(
            db, tenant_id, payload.payment_status
        )
        paid_from_acc = None
        if payload.paid_from_account_id:
            from app.modules.accounting.models import Account
            acc_res = await db.execute(
                select(Account).where(Account.tenant_id == tenant_id, Account.id == payload.paid_from_account_id)
            )
            paid_from_acc = acc_res.scalar_one_or_none()

        if acc_behavior == "unpaid" and (payload.paid_amount is None or float(payload.paid_amount) <= 0):
            paid_amount = 0.0
            balance_due = total_amount
            paid_from_account_id = None
            payment_status = resolved_code
        else:
            if payload.paid_amount is not None and float(payload.paid_amount) > 0:
                paid_amount = round(min(float(payload.paid_amount), total_amount), 2)
            else:
                paid_amount = total_amount if acc_behavior == "paid" else 0.0
            balance_due = round(max(0.0, total_amount - paid_amount), 2)
            paid_from_account_id = paid_from_acc.id if (paid_from_acc and paid_amount > 0) else None
            if paid_amount <= 0:
                payment_status = "unpaid"
            elif balance_due > 0:
                payment_status = "partial" if resolved_code in ("paid", "unpaid", "partial") else resolved_code
            else:
                payment_status = resolved_code

        # 4. Generate Unique Invoice Number (PUR-YYYYMM-XXXX)
        now = datetime.now(timezone.utc)
        prefix = f"PUR-{now.strftime('%Y%m')}"
        cnt_res = await db.execute(
            select(func.count(Purchase.id)).where(
                Purchase.tenant_id == tenant_id,
                Purchase.invoice_number.like(f"{prefix}-%"),
            )
        )
        seq = (cnt_res.scalar() or 0) + 1
        invoice_number = f"{prefix}-{str(seq).padStart(4, '0') if hasattr(str, 'padStart') else f'{seq:04d}'}"

        # 5. Insert Purchase
        purchase = Purchase(
            tenant_id=tenant_id,
            branch_id=payload.branch_id,
            supplier_id=payload.supplier_id,
            invoice_number=invoice_number,
            supplier_bill_no=payload.supplier_bill_no.strip() if payload.supplier_bill_no else None,
            purchase_date=payload.purchase_date or now.date(),
            status="received",
            payment_status=payment_status,
            subtotal=subtotal,
            discount_amount=payload.discount_amount,
            tax_amount=effective_tax_amount,
            shipping_cost=payload.shipping_cost,
            total_amount=total_amount,
            paid_amount=paid_amount,
            balance_due=balance_due,
            paid_from_account_id=paid_from_account_id,
            notes=payload.notes.strip() if payload.notes else None,
            created_by_id=user_id,
        )
        db.add(purchase)
        await db.flush()

        # 6. Insert Line Items, Update Branch Stock, and Add Stock Movements
        for ci in calculated_items:
            item_retail_price = float(getattr(ci["input"], "retail_price", 0.0) or 0.0)
            p_item = PurchaseItem(
                tenant_id=tenant_id,
                purchase_id=purchase.id,
                product_id=ci["product"].id,
                uom_conversion_id=ci["input"].uom_conversion_id,
                unit_name=ci["input"].unit_name.strip(),
                quantity=ci["input"].quantity,
                conversion_factor=ci["factor"],
                total_base_quantity=ci["base_qty"],
                unit_cost=ci["input"].unit_cost,
                retail_price=item_retail_price,
                tax_rate=ci["row_tax_rate"],
                tax_amount=ci["row_tax_amount"],
                total_cost=ci["row_total"],
                batch_number=ci["input"].batch_number.strip() if ci["input"].batch_number else None,
                expiry_date=ci["input"].expiry_date,
            )
            db.add(p_item)

            # Update or create branch stock & compute IAS-2 Weighted Average Cost (WAC)
            bs_res = await db.execute(
                select(BranchStock).where(
                    BranchStock.tenant_id == tenant_id,
                    BranchStock.branch_id == payload.branch_id,
                    BranchStock.product_id == ci["product"].id,
                )
            )
            bs = bs_res.scalar_one_or_none()
            old_qty = max(0.0, float(bs.quantity)) if bs else 0.0
            old_cost = float(ci["product"].cost_price or 0.0)
            base_unit_cost = round(float(ci["input"].unit_cost) / max(1.0, float(ci["factor"])), 2)

            if base_unit_cost > 0:
                if old_qty > 0 and old_cost > 0:
                    wac = ((old_qty * old_cost) + (ci["base_qty"] * base_unit_cost)) / (old_qty + ci["base_qty"])
                    ci["product"].cost_price = round(wac, 2)
                else:
                    ci["product"].cost_price = base_unit_cost

            # Sync Sale Price (retail_price) and Tax Rate on Product master record
            if item_retail_price > 0:
                base_retail_price = round(item_retail_price / max(1.0, float(ci["factor"])), 2)
                ci["product"].retail_price = base_retail_price
            if ci["row_tax_rate"] >= 0:
                ci["product"].tax_rate = ci["row_tax_rate"]

            if not bs:
                bs = BranchStock(
                    tenant_id=tenant_id,
                    branch_id=payload.branch_id,
                    product_id=ci["product"].id,
                    quantity=ci["base_qty"],
                    reorder_point=getattr(ci["product"], "min_stock_alert", 5),
                )
                db.add(bs)
                await db.flush()
                new_balance = ci["base_qty"]
            else:
                bs.quantity = float(bs.quantity) + ci["base_qty"]
                bs.updated_at = now
                new_balance = float(bs.quantity)

            # Write immutable stock movement
            movement = StockMovement(
                tenant_id=tenant_id,
                branch_id=payload.branch_id,
                product_id=ci["product"].id,
                movement_type="PURCHASE",
                quantity=ci["base_qty"],
                balance_after=new_balance,
                unit_cost=ci["input"].unit_cost,
                reference_type="purchase",
                reference_id=purchase.id,
                notes=f"Purchase from {supplier.company_name} ({invoice_number})",
            )
            db.add(movement)

        # 7. Update Supplier Payable Balance
        if balance_due > 0:
            supplier.current_balance = float(supplier.current_balance) + balance_due
            supplier.updated_at = now

        # 8. Enterprise Accounting: Auto-post Double-Entry Journal Voucher (GRN)
        posted_jv = None
        try:
            from app.modules.accounting.services import AccountingService
            from app.modules.accounting.posting import AccountingPostingEngine
            await AccountingService.ensure_tenant_coa_and_settings(db, tenant_id, backfill=False)
            posted_jv = await AccountingPostingEngine.post_purchase_invoice(db, tenant_id, purchase, user_id)
        except Exception as e:
            print(f"[ACCOUNTING AUTO-POST WARNING] Failed to post purchase voucher {purchase.invoice_number}: {e}")

        await db.commit()
        await db.refresh(purchase)

        resp = PurchaseResponse.model_validate(purchase)
        resp.branch_name = branch.name
        resp.supplier_name = supplier.company_name
        resp.paid_from_account_name = paid_from_acc.name if (paid_from_acc and purchase.paid_from_account_id) else None
        resp.paid_from_account_code = paid_from_acc.code if (paid_from_acc and purchase.paid_from_account_id) else None
        resp.journal_entry_number = posted_jv.entry_number if posted_jv else None
        resp.items_count = len(payload.items)
        resp.total_qty = sum(float(i.quantity or 0.0) for i in payload.items)
        return resp

    @staticmethod
    async def update_purchase(
        db: AsyncSession,
        tenant_id: int,
        user_id: Optional[int],
        purchase_id: int,
        payload: PurchaseUpdate,
    ) -> PurchaseResponse:
        """
        Update a purchase bill (including changing Payment Status between Paid / Unpaid / custom status)
        and synchronize Supplier Khata payable balance + Double-Entry Journal Voucher (Trial Balance & Balance Sheet).
        """
        stmt = (
            select(Purchase)
            .options(
                joinedload(Purchase.branch),
                joinedload(Purchase.supplier),
                joinedload(Purchase.paid_from_account),
                selectinload(Purchase.items),
            )
            .where(Purchase.tenant_id == tenant_id, Purchase.id == purchase_id)
        )
        res = await db.execute(stmt)
        p = res.scalar_one_or_none()
        if not p:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Purchase with ID {purchase_id} was not found.",
            )

        now = datetime.now(timezone.utc)
        old_balance_due = float(p.balance_due or 0.0)
        total_amount = float(p.total_amount or 0.0)

        if payload.supplier_bill_no is not None:
            p.supplier_bill_no = payload.supplier_bill_no.strip() if payload.supplier_bill_no else None
        if payload.notes is not None:
            p.notes = payload.notes.strip() if payload.notes else None
        if payload.status is not None:
            p.status = payload.status

        paid_from_acc = p.paid_from_account
        if payload.paid_from_account_id is not None:
            if payload.paid_from_account_id > 0:
                from app.modules.accounting.models import Account
                acc_res = await db.execute(
                    select(Account).where(Account.tenant_id == tenant_id, Account.id == payload.paid_from_account_id)
                )
                paid_from_acc = acc_res.scalar_one_or_none()
            else:
                paid_from_acc = None

        if payload.payment_status is not None or payload.paid_amount is not None or payload.paid_from_account_id is not None:
            target_code = payload.payment_status or p.payment_status
            resolved_code, acc_behavior = await PaymentStatusService.resolve_behavior(
                db, tenant_id, target_code
            )
            if acc_behavior == "unpaid" and (payload.paid_amount is None or float(payload.paid_amount) <= 0):
                new_paid = 0.0
                new_due = total_amount
                p.paid_from_account_id = None
                p.payment_status = resolved_code
            else:
                if payload.paid_amount is not None:
                    req_paid = float(payload.paid_amount)
                elif acc_behavior == "paid":
                    req_paid = total_amount
                else:
                    req_paid = float(p.paid_amount or 0.0)
                new_paid = round(min(max(0.0, req_paid), total_amount), 2)
                new_due = round(max(0.0, total_amount - new_paid), 2)
                p.paid_from_account_id = paid_from_acc.id if (paid_from_acc and new_paid > 0) else (p.paid_from_account_id if new_paid > 0 else None)
                if new_paid <= 0:
                    p.payment_status = "unpaid"
                elif new_due > 0:
                    p.payment_status = "partial" if resolved_code in ("paid", "unpaid", "partial") else resolved_code
                else:
                    p.payment_status = resolved_code

            p.paid_amount = round(new_paid, 2)
            p.balance_due = round(new_due, 2)

            # Adjust Supplier Khata balance by the delta in balance_due
            if p.supplier:
                delta_due = round(new_due - old_balance_due, 2)
                p.supplier.current_balance = max(0.0, round(float(p.supplier.current_balance or 0.0) + delta_due, 2))
                p.supplier.updated_at = now

        p.updated_at = now
        await db.flush()

        # Re-post Double-Entry Accounting Journal Voucher to reflect updated Payment Status
        posted_jv = None
        try:
            from app.modules.accounting.services import AccountingService
            from app.modules.accounting.posting import AccountingPostingEngine

            await AccountingService.ensure_tenant_coa_and_settings(db, tenant_id, backfill=False)
            await AccountingPostingEngine.void_source_voucher(
                db,
                tenant_id,
                source_type="purchase_invoice",
                source_id=p.id,
                reason=f"Purchase bill {p.invoice_number} updated (Payment Status: {p.payment_status})",
            )
            posted_jv = await AccountingPostingEngine.post_purchase_invoice(db, tenant_id, p, user_id)
        except Exception as e:
            print(f"[ACCOUNTING UPDATE WARNING] Failed to re-post purchase voucher {p.invoice_number}: {e}")

        await db.commit()
        await db.refresh(p)

        resp = PurchaseResponse.model_validate(p)
        resp.branch_name = p.branch.name if p.branch else None
        resp.supplier_name = p.supplier.company_name if p.supplier else None
        resp.paid_from_account_name = paid_from_acc.name if (paid_from_acc and p.paid_from_account_id) else None
        resp.paid_from_account_code = paid_from_acc.code if (paid_from_acc and p.paid_from_account_id) else None
        resp.journal_entry_number = posted_jv.entry_number if posted_jv else None
        resp.items_count = len(p.items) if p.items else 0
        resp.total_qty = sum(float(i.quantity or 0.0) for i in p.items) if p.items else 0.0
        return resp

    @staticmethod
    async def delete_purchase(
        db: AsyncSession, tenant_id: int, purchase_id: int
    ) -> Dict[str, Any]:
        """Cancel/Delete a purchase bill, reverse branch stock, and update supplier balance."""
        stmt = (
            select(Purchase)
            .options(
                joinedload(Purchase.supplier),
                selectinload(Purchase.items),
            )
            .where(Purchase.tenant_id == tenant_id, Purchase.id == purchase_id)
        )
        res = await db.execute(stmt)
        p = res.scalar_one_or_none()
        if not p:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Purchase with ID {purchase_id} was not found.",
            )

        now = datetime.now(timezone.utc)

        # 1. Reverse branch stocks
        for item in p.items:
            bs_res = await db.execute(
                select(BranchStock).where(
                    BranchStock.tenant_id == tenant_id,
                    BranchStock.branch_id == p.branch_id,
                    BranchStock.product_id == item.product_id,
                )
            )
            bs = bs_res.scalar_one_or_none()
            if bs:
                bs.quantity = max(0.0, float(bs.quantity) - float(item.total_base_quantity))
                bs.updated_at = now
                new_bal = float(bs.quantity)
            else:
                new_bal = 0.0

            # Write reversal movement
            rev_move = StockMovement(
                tenant_id=tenant_id,
                branch_id=p.branch_id,
                product_id=item.product_id,
                movement_type="PURCHASE_CANCELLED",
                quantity=-float(item.total_base_quantity),
                balance_after=new_bal,
                unit_cost=float(item.unit_cost),
                reference_type="purchase",
                reference_id=p.id,
                notes=f"Reversed purchase bill #{p.invoice_number}",
            )
            db.add(rev_move)

        # 2. Reverse Supplier Payable Balance
        if float(p.balance_due) > 0 and p.supplier:
            p.supplier.current_balance = max(0.0, float(p.supplier.current_balance) - float(p.balance_due))
            p.supplier.updated_at = now

        # 3. Enterprise Accounting: Void linked Purchase Journal Voucher (GRN)
        try:
            from app.modules.accounting.posting import AccountingPostingEngine
            await AccountingPostingEngine.void_source_voucher(
                db,
                tenant_id,
                source_type="purchase_invoice",
                source_id=p.id,
                reason=f"Purchase bill {p.invoice_number} cancelled",
            )
        except Exception as e:
            print(f"[ACCOUNTING VOID WARNING] Failed to void purchase voucher {p.invoice_number}: {e}")

        inv_num = p.invoice_number
        await db.delete(p)
        await db.commit()
        return {"message": f"Purchase bill '{inv_num}' cancelled and stock reversed successfully."}

    @staticmethod
    async def _generate_return_number(db: AsyncSession, tenant_id: int) -> str:
        prefix = f"PRN-{datetime.now(timezone.utc).strftime('%Y%m')}-"
        cnt_res = await db.execute(
            select(func.count(PurchaseReturn.id)).where(
                PurchaseReturn.tenant_id == tenant_id,
                PurchaseReturn.return_number.like(f"{prefix}%"),
            )
        )
        seq = (cnt_res.scalar() or 0) + 1
        while True:
            candidate = f"{prefix}{seq:04d}"
            exists = (
                await db.execute(
                    select(PurchaseReturn.id).where(
                        PurchaseReturn.tenant_id == tenant_id,
                        PurchaseReturn.return_number == candidate,
                    )
                )
            ).scalar_one_or_none()
            if not exists:
                return candidate
            seq += 1

    @staticmethod
    async def return_purchase(
        db: AsyncSession,
        tenant_id: int,
        purchase_id: int,
        user_id: int,
        reason: Optional[str] = "Goods Returned to Supplier / Debit Note",
        refund_payment_method: Optional[str] = "credit",
        refund_account_id: Optional[int] = None,
        notes: Optional[str] = None,
        return_items: Optional[List[PurchaseReturnItemInput]] = None,
    ) -> Purchase:
        """
        Process partial or full item-level return to supplier (Debit Note):
        - Example: 100 items received, 80 kept, 20 returned -> deducts 20 from Warehouse stock,
          calculates return amount (20 * unit_cost), creates a PurchaseReturn (PRN) record,
          updates Supplier Khata payable / refund account, and posts a balanced Double-Entry Debit Note JV.
        """
        stmt = (
            select(Purchase)
            .options(
                joinedload(Purchase.supplier),
                selectinload(Purchase.items).joinedload(PurchaseItem.product),
                joinedload(Purchase.branch),
            )
            .where(Purchase.tenant_id == tenant_id, Purchase.id == purchase_id)
        )
        res = await db.execute(stmt)
        p = res.scalar_one_or_none()
        if not p:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Purchase with ID {purchase_id} was not found.",
            )

        if p.status == "returned":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="All quantities on this purchase bill have already been returned.")
        if p.status == "cancelled":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cancelled purchase bills cannot be returned.")

        now = datetime.now(timezone.utc)
        item_map = {item.id: item for item in p.items}
        prod_item_map = {item.product_id: item for item in p.items}

        # Build list of (PurchaseItem, return_qty, return_unit_cost)
        lines_to_return: List[Tuple[PurchaseItem, float, float]] = []
        if return_items and len(return_items) > 0:
            for ri in return_items:
                if float(ri.quantity or 0) <= 0:
                    continue
                target_item = None
                if ri.purchase_item_id and ri.purchase_item_id in item_map:
                    target_item = item_map[ri.purchase_item_id]
                elif ri.product_id in prod_item_map:
                    target_item = prod_item_map[ri.product_id]
                if not target_item:
                    continue
                already_ret = float(getattr(target_item, "returned_quantity", 0.0) or 0.0)
                max_returnable = max(0.0, float(target_item.quantity) - already_ret)
                ret_q = min(float(ri.quantity), max_returnable)
                if ret_q <= 0:
                    continue
                u_cost = float(ri.unit_cost) if ri.unit_cost is not None and ri.unit_cost >= 0 else float(target_item.unit_cost)
                lines_to_return.append((target_item, ret_q, u_cost))
        else:
            # Default: return all remaining unreturned quantities
            for item in p.items:
                already_ret = float(getattr(item, "returned_quantity", 0.0) or 0.0)
                rem_q = max(0.0, float(item.quantity) - already_ret)
                if rem_q > 0:
                    lines_to_return.append((item, rem_q, float(item.unit_cost)))

        if not lines_to_return:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Please enter a valid return quantity greater than 0 (not exceeding purchased quantity).",
            )

        return_number = await PurchaseService._generate_return_number(db, tenant_id)
        total_ret_qty = 0.0
        total_ret_amount = 0.0

        pr_record = PurchaseReturn(
            tenant_id=tenant_id,
            purchase_id=p.id,
            branch_id=p.branch_id,
            supplier_id=p.supplier_id,
            return_number=return_number,
            return_date=now.date(),
            total_qty=0.0,
            total_amount=0.0,
            refund_method=refund_payment_method or "credit",
            refund_account_id=refund_account_id if refund_account_id and refund_account_id > 0 else None,
            reason=reason,
            notes=notes,
            created_by_id=user_id,
        )
        db.add(pr_record)
        await db.flush()

        # 1. Deduct warehouse stock & record PurchaseReturnItem + StockMovement
        for item, ret_q, u_cost in lines_to_return:
            factor = max(1.0, float(item.conversion_factor or 1.0))
            base_ret_q = round(ret_q * factor, 2)
            line_ret_cost = round(ret_q * u_cost, 2)

            item.returned_quantity = round(float(getattr(item, "returned_quantity", 0.0) or 0.0) + ret_q, 2)
            total_ret_qty += ret_q
            total_ret_amount += line_ret_cost

            pr_item = PurchaseReturnItem(
                tenant_id=tenant_id,
                purchase_return_id=pr_record.id,
                purchase_item_id=item.id,
                product_id=item.product_id,
                unit_name=item.unit_name,
                quantity=ret_q,
                conversion_factor=factor,
                total_base_quantity=base_ret_q,
                unit_cost=u_cost,
                total_cost=line_ret_cost,
            )
            db.add(pr_item)

            bs_res = await db.execute(
                select(BranchStock).where(
                    BranchStock.tenant_id == tenant_id,
                    BranchStock.branch_id == p.branch_id,
                    BranchStock.product_id == item.product_id,
                )
            )
            bs = bs_res.scalar_one_or_none()
            if bs:
                bs.quantity = max(0.0, float(bs.quantity) - base_ret_q)
                bs.updated_at = now
                new_bal = float(bs.quantity)
            else:
                new_bal = 0.0

            ret_move = StockMovement(
                tenant_id=tenant_id,
                branch_id=p.branch_id,
                product_id=item.product_id,
                movement_type="PURCHASE_RETURN",
                quantity=-base_ret_q,
                balance_after=new_bal,
                unit_cost=u_cost,
                reference_type="purchase_return",
                reference_id=pr_record.id,
                notes=f"Purchase Return {return_number} (Bill #{p.invoice_number}) from Warehouse '{p.branch.name if p.branch else ''}': {reason}",
            )
            db.add(ret_move)

        total_ret_amount = round(total_ret_amount, 2)
        pr_record.total_qty = round(total_ret_qty, 2)
        pr_record.total_amount = total_ret_amount

        # 2. Adjust Purchase Balance Due & Supplier Payable Balance
        # Reduce unpaid balance_due on the invoice first
        old_balance_due = float(p.balance_due or 0.0)
        balance_reduction = min(old_balance_due, total_ret_amount)
        if balance_reduction > 0:
            p.balance_due = round(max(0.0, old_balance_due - balance_reduction), 2)

        if (refund_payment_method or "credit") == "credit":
            # Full returned amount reduces supplier khata balance
            if p.supplier:
                p.supplier.current_balance = round(float(p.supplier.current_balance or 0.0) - total_ret_amount, 2)
                p.supplier.updated_at = now
        else:
            # Cash/Bank refund received: only unpaid portion reduces supplier khata
            if balance_reduction > 0 and p.supplier:
                p.supplier.current_balance = round(max(0.0, float(p.supplier.current_balance or 0.0) - balance_reduction), 2)
                p.supplier.updated_at = now

        # 3. Determine if all items on purchase bill are fully returned or partially returned
        all_returned = all(
            float(getattr(it, "returned_quantity", 0.0) or 0.0) >= float(it.quantity) - 0.001
            for it in p.items
        )
        p.status = "returned" if all_returned else "partial_returned"
        p.notes = (p.notes or "") + f" | {return_number}: Returned {total_ret_qty:g} qty (PKR {total_ret_amount:,.2f})"
        p.updated_at = now

        # 4. Auto-post Debit Note Journal Voucher for the exact returned amount
        try:
            from app.modules.accounting.services import AccountingService
            from app.modules.accounting.posting import AccountingPostingEngine
            await AccountingService.ensure_tenant_coa_and_settings(db, tenant_id, backfill=False)
            await AccountingPostingEngine.post_purchase_return(
                db,
                tenant_id,
                pr_record,
                user_id=user_id,
                reason=f"{reason} (Bill: {p.invoice_number})",
                refund_payment_method=refund_payment_method,
                return_amount_override=total_ret_amount,
                refund_account_id_override=pr_record.refund_account_id,
                return_voucher_no=return_number,
            )
        except Exception as e:
            print(f"[ACCOUNTING DEBIT NOTE WARNING] Failed to post debit note for {return_number}: {e}")

        await db.commit()
        await db.refresh(p)
        return p

    @staticmethod
    async def create_standalone_purchase_return(
        db: AsyncSession,
        tenant_id: int,
        user_id: int,
        payload: StandalonePurchaseReturnCreate,
    ) -> PurchaseReturnResponse:
        """
        Create a standalone Purchase Return / Debit Note from the dedicated Purchase Returns screen:
        Allows returning any quantity of any product from a specific Warehouse / Branch to a Supplier,
        or linking to an existing purchase bill.
        """
        if payload.purchase_id:
            # Delegate to invoice-linked return and then return the latest PurchaseReturnResponse
            await PurchaseService.return_purchase(
                db,
                tenant_id=tenant_id,
                purchase_id=payload.purchase_id,
                user_id=user_id,
                reason=payload.reason,
                refund_payment_method=payload.refund_method,
                refund_account_id=payload.refund_account_id,
                notes=payload.notes,
                return_items=payload.items,
            )
            latest_pr = (
                await db.execute(
                    select(PurchaseReturn)
                    .where(PurchaseReturn.tenant_id == tenant_id, PurchaseReturn.purchase_id == payload.purchase_id)
                    .order_by(PurchaseReturn.id.desc())
                    .limit(1)
                )
            ).scalar_one()
            return await PurchaseService.get_purchase_return_detail(db, tenant_id, latest_pr.id)

        # Validate Warehouse / Branch and Supplier
        branch = (
            await db.execute(select(Branch).where(Branch.tenant_id == tenant_id, Branch.id == payload.branch_id))
        ).scalar_one_or_none()
        if not branch:
            raise HTTPException(status_code=404, detail="Selected Warehouse / Branch not found.")

        supplier = (
            await db.execute(select(Supplier).where(Supplier.tenant_id == tenant_id, Supplier.id == payload.supplier_id))
        ).scalar_one_or_none()
        if not supplier:
            raise HTTPException(status_code=404, detail="Selected Supplier not found.")

        now = datetime.now(timezone.utc)
        return_number = await PurchaseService._generate_return_number(db, tenant_id)

        pr_record = PurchaseReturn(
            tenant_id=tenant_id,
            purchase_id=None,
            branch_id=branch.id,
            supplier_id=supplier.id,
            return_number=return_number,
            return_date=payload.return_date or now.date(),
            total_qty=0.0,
            total_amount=0.0,
            refund_method=payload.refund_method or "credit",
            refund_account_id=payload.refund_account_id if payload.refund_account_id and payload.refund_account_id > 0 else None,
            reason=payload.reason,
            notes=payload.notes,
            created_by_id=user_id,
        )
        db.add(pr_record)
        await db.flush()

        total_ret_qty = 0.0
        total_ret_amount = 0.0

        for ri in payload.items:
            ret_q = float(ri.quantity or 0.0)
            if ret_q <= 0:
                continue
            prod = (
                await db.execute(select(Product).where(Product.tenant_id == tenant_id, Product.id == ri.product_id))
            ).scalar_one_or_none()
            if not prod:
                raise HTTPException(status_code=404, detail=f"Product ID {ri.product_id} not found.")

            factor = max(1.0, float(ri.conversion_factor or 1.0))
            base_ret_q = round(ret_q * factor, 2)
            u_cost = float(ri.unit_cost) if ri.unit_cost is not None and ri.unit_cost > 0 else float(prod.cost_price or 0.0)
            line_cost = round(ret_q * u_cost, 2)

            total_ret_qty += ret_q
            total_ret_amount += line_cost

            pr_item = PurchaseReturnItem(
                tenant_id=tenant_id,
                purchase_return_id=pr_record.id,
                purchase_item_id=None,
                product_id=prod.id,
                unit_name=ri.unit_name or prod.base_unit or "Piece",
                quantity=ret_q,
                conversion_factor=factor,
                total_base_quantity=base_ret_q,
                unit_cost=u_cost,
                total_cost=line_cost,
            )
            db.add(pr_item)

            # Deduct from Warehouse BranchStock
            bs = (
                await db.execute(
                    select(BranchStock).where(
                        BranchStock.tenant_id == tenant_id,
                        BranchStock.branch_id == branch.id,
                        BranchStock.product_id == prod.id,
                    )
                )
            ).scalar_one_or_none()
            if bs:
                bs.quantity = max(0.0, float(bs.quantity) - base_ret_q)
                bs.updated_at = now
                new_bal = float(bs.quantity)
            else:
                new_bal = 0.0

            ret_move = StockMovement(
                tenant_id=tenant_id,
                branch_id=branch.id,
                product_id=prod.id,
                movement_type="PURCHASE_RETURN",
                quantity=-base_ret_q,
                balance_after=new_bal,
                unit_cost=u_cost,
                reference_type="purchase_return",
                reference_id=pr_record.id,
                notes=f"Direct Purchase Return {return_number} to {supplier.company_name} from Warehouse '{branch.name}': {payload.reason or ''}",
            )
            db.add(ret_move)

        if total_ret_qty <= 0:
            raise HTTPException(status_code=400, detail="Return quantity must be greater than 0.")

        total_ret_amount = round(total_ret_amount, 2)
        pr_record.total_qty = round(total_ret_qty, 2)
        pr_record.total_amount = total_ret_amount

        # Update Supplier Khata balance if refund method is credit
        if (payload.refund_method or "credit") == "credit":
            supplier.current_balance = round(float(supplier.current_balance or 0.0) - total_ret_amount, 2)
            supplier.updated_at = now

        # Auto-post Double-Entry Debit Note JV
        try:
            from app.modules.accounting.services import AccountingService
            from app.modules.accounting.posting import AccountingPostingEngine
            await AccountingService.ensure_tenant_coa_and_settings(db, tenant_id, backfill=False)
            await AccountingPostingEngine.post_purchase_return(
                db,
                tenant_id,
                pr_record,
                user_id=user_id,
                reason=payload.reason,
                refund_payment_method=payload.refund_method,
                return_amount_override=total_ret_amount,
                refund_account_id_override=pr_record.refund_account_id,
                return_voucher_no=return_number,
            )
        except Exception as e:
            print(f"[ACCOUNTING DEBIT NOTE WARNING] Failed to post standalone debit note {return_number}: {e}")

        await db.commit()
        return await PurchaseService.get_purchase_return_detail(db, tenant_id, pr_record.id)

    @staticmethod
    async def list_purchase_returns(
        db: AsyncSession,
        tenant_id: int,
        branch_id: Optional[int] = None,
        supplier_id: Optional[int] = None,
        search: Optional[str] = None,
    ) -> List[PurchaseReturnResponse]:
        stmt = (
            select(PurchaseReturn)
            .options(
                joinedload(PurchaseReturn.branch),
                joinedload(PurchaseReturn.supplier),
                joinedload(PurchaseReturn.purchase),
                joinedload(PurchaseReturn.refund_account),
                selectinload(PurchaseReturn.items).joinedload(PurchaseReturnItem.product),
            )
            .where(PurchaseReturn.tenant_id == tenant_id)
            .order_by(PurchaseReturn.return_date.desc(), PurchaseReturn.id.desc())
        )
        if branch_id:
            stmt = stmt.where(PurchaseReturn.branch_id == branch_id)
        if supplier_id:
            stmt = stmt.where(PurchaseReturn.supplier_id == supplier_id)
        if search:
            s = f"%{search.strip().lower()}%"
            stmt = stmt.where(
                or_(
                    func.lower(PurchaseReturn.return_number).ilike(s),
                    func.lower(PurchaseReturn.reason).ilike(s),
                )
            )
        res = await db.execute(stmt)
        records = res.scalars().unique().all()

        from app.modules.accounting.models import JournalEntry
        pr_ids = [r.id for r in records]
        jv_map = {}
        if pr_ids:
            jv_res = await db.execute(
                select(JournalEntry.source_id, JournalEntry.entry_number).where(
                    JournalEntry.tenant_id == tenant_id,
                    JournalEntry.source_type == "purchase_return",
                    JournalEntry.source_id.in_(pr_ids),
                    JournalEntry.status == "posted",
                )
            )
            for s_id, e_num in jv_res.all():
                jv_map[s_id] = e_num

        out: List[PurchaseReturnResponse] = []
        for r in records:
            out.append(PurchaseService._serialize_purchase_return(r, jv_map.get(r.id)))
        return out

    @staticmethod
    async def get_purchase_return_detail(
        db: AsyncSession,
        tenant_id: int,
        return_id: int,
    ) -> PurchaseReturnResponse:
        stmt = (
            select(PurchaseReturn)
            .options(
                joinedload(PurchaseReturn.branch),
                joinedload(PurchaseReturn.supplier),
                joinedload(PurchaseReturn.purchase),
                joinedload(PurchaseReturn.refund_account),
                selectinload(PurchaseReturn.items).joinedload(PurchaseReturnItem.product),
            )
            .where(PurchaseReturn.tenant_id == tenant_id, PurchaseReturn.id == return_id)
        )
        r = (await db.execute(stmt)).scalar_one_or_none()
        if not r:
            raise HTTPException(status_code=404, detail="Purchase Return not found.")

        from app.modules.accounting.models import JournalEntry
        jv_num = (
            await db.execute(
                select(JournalEntry.entry_number).where(
                    JournalEntry.tenant_id == tenant_id,
                    JournalEntry.source_type == "purchase_return",
                    JournalEntry.source_id == r.id,
                    JournalEntry.status == "posted",
                ).order_by(JournalEntry.id.desc()).limit(1)
            )
        ).scalar_one_or_none()

        return PurchaseService._serialize_purchase_return(r, jv_num)

    @staticmethod
    def _serialize_purchase_return(r: PurchaseReturn, jv_num: Optional[str]) -> PurchaseReturnResponse:
        items_out = []
        for it in r.items or []:
            items_out.append(
                PurchaseReturnItemResponse(
                    id=it.id,
                    purchase_return_id=it.purchase_return_id,
                    purchase_item_id=it.purchase_item_id,
                    product_id=it.product_id,
                    product_name=it.product.name if it.product else None,
                    product_sku=it.product.sku if it.product else None,
                    unit_name=it.unit_name,
                    quantity=float(it.quantity),
                    conversion_factor=float(it.conversion_factor),
                    total_base_quantity=float(it.total_base_quantity),
                    unit_cost=float(it.unit_cost),
                    total_cost=float(it.total_cost),
                )
            )
        return PurchaseReturnResponse(
            id=r.id,
            tenant_id=r.tenant_id,
            purchase_id=r.purchase_id,
            purchase_invoice_number=r.purchase.invoice_number if r.purchase else None,
            branch_id=r.branch_id,
            branch_name=r.branch.name if r.branch else None,
            supplier_id=r.supplier_id,
            supplier_name=r.supplier.company_name if r.supplier else None,
            return_number=r.return_number,
            return_date=r.return_date,
            total_qty=float(r.total_qty),
            total_amount=float(r.total_amount),
            refund_method=r.refund_method,
            refund_account_id=r.refund_account_id,
            refund_account_name=r.refund_account.name if r.refund_account else None,
            refund_account_code=r.refund_account.code if r.refund_account else None,
            journal_entry_number=jv_num,
            reason=r.reason,
            notes=r.notes,
            created_at=r.created_at,
            items=items_out,
        )



class InventoryService:
    @staticmethod
    async def list_live_inventory(
        db: AsyncSession,
        tenant_id: int,
        branch_id: Optional[int] = None,
        category_id: Optional[int] = None,
        brand_id: Optional[int] = None,
        stock_status: Optional[str] = None,
        search: Optional[str] = None,
    ) -> List[LiveInventoryItem]:
        """List live branch-wise inventory with live stock status and reorder alerts."""
        # Query products joined with BranchStock
        stmt = (
            select(
                Product,
                BranchStock,
                Branch,
            )
            .join(BranchStock, BranchStock.product_id == Product.id)
            .join(Branch, Branch.id == BranchStock.branch_id)
            .options(
                joinedload(Product.category),
                joinedload(Product.brand),
            )
            .where(
                Product.tenant_id == tenant_id,
                Product.is_active.is_(True),
            )
        )

        if branch_id:
            stmt = stmt.where(BranchStock.branch_id == branch_id)
        if category_id:
            stmt = stmt.where(Product.category_id == category_id)
        if brand_id:
            stmt = stmt.where(Product.brand_id == brand_id)
        if search:
            s = f"%{search.strip().lower()}%"
            stmt = stmt.where(
                or_(
                    func.lower(Product.name).ilike(s),
                    func.lower(Product.sku).ilike(s),
                    func.lower(Product.barcode).ilike(s),
                )
            )

        stmt = stmt.order_by(Product.name.asc())
        res = await db.execute(stmt)
        rows = res.all()

        results = []
        for prod, bs, br in rows:
            cur_stock = float(bs.quantity)
            reorder = float(bs.reorder_point or prod.min_stock_alert or 10.0)

            if cur_stock <= 0:
                status_label = "Out of Stock"
            elif cur_stock <= reorder:
                status_label = "Low Stock"
            else:
                status_label = "In Stock"

            if stock_status and stock_status != "all":
                if stock_status.lower() != status_label.lower():
                    continue

            eff_retail = float(prod.retail_price) if float(prod.retail_price) > 0 else float(prod.cost_price)
            results.append(
                LiveInventoryItem(
                    product_id=prod.id,
                    product_name=prod.name,
                    sku=prod.sku,
                    barcode=prod.barcode,
                    category_id=prod.category_id,
                    category_name=prod.category.name if prod.category else None,
                    brand_id=prod.brand_id,
                    brand_name=prod.brand.name if prod.brand else None,
                    base_unit=prod.base_unit,
                    branch_id=br.id,
                    branch_name=br.name,
                    current_stock=cur_stock,
                    reorder_point=reorder,
                    cost_price=float(prod.cost_price),
                    retail_price=eff_retail,
                    wholesale_price=float(prod.wholesale_price or eff_retail),
                    tax_rate=float(prod.tax_rate or 0.0),
                    is_fbr_third_schedule=bool(prod.is_fbr_third_schedule),
                    image_url=prod.image_url,
                    stock_status=status_label,
                )
            )
        return results

    @staticmethod
    async def get_product_ledger(
        db: AsyncSession, tenant_id: int, product_id: int, branch_id: Optional[int] = None
    ) -> List[StockMovementResponse]:
        """Fetch bin card / audit ledger movements for a product."""
        stmt = (
            select(StockMovement)
            .options(
                joinedload(StockMovement.branch),
                joinedload(StockMovement.product),
            )
            .where(StockMovement.tenant_id == tenant_id, StockMovement.product_id == product_id)
        )
        if branch_id:
            stmt = stmt.where(StockMovement.branch_id == branch_id)

        stmt = stmt.order_by(StockMovement.created_at.desc(), StockMovement.id.desc())
        res = await db.execute(stmt)
        movements = res.scalars().all()

        results = []
        for m in movements:
            resp = StockMovementResponse.model_validate(m)
            resp.branch_name = m.branch.name if m.branch else None
            resp.product_name = m.product.name if m.product else None
            results.append(resp)
        return results

    @staticmethod
    async def create_stock_transfer(
        db: AsyncSession, tenant_id: int, user_id: Optional[int], payload: StockTransferCreate
    ) -> StockTransferResponse:
        """Execute an atomic inter-branch stock transfer."""
        if payload.from_branch_id == payload.to_branch_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Source and destination branches cannot be the same.",
            )

        now = datetime.now(timezone.utc)
        prefix = f"TRF-{now.strftime('%Y%m')}"
        cnt_res = await db.execute(
            select(func.count(StockTransfer.id)).where(
                StockTransfer.tenant_id == tenant_id,
                StockTransfer.transfer_number.like(f"{prefix}-%"),
            )
        )
        seq = (cnt_res.scalar() or 0) + 1
        transfer_number = f"{prefix}-{seq:04d}"

        transfer = StockTransfer(
            tenant_id=tenant_id,
            transfer_number=transfer_number,
            from_branch_id=payload.from_branch_id,
            to_branch_id=payload.to_branch_id,
            transfer_date=payload.transfer_date or now.date(),
            status="completed",
            notes=payload.notes.strip() if payload.notes else None,
            created_by_id=user_id,
        )
        db.add(transfer)
        await db.flush()

        for item_in in payload.items:
            # 1. Deduct from source branch
            src_bs_res = await db.execute(
                select(BranchStock).where(
                    BranchStock.tenant_id == tenant_id,
                    BranchStock.branch_id == payload.from_branch_id,
                    BranchStock.product_id == item_in.product_id,
                )
            )
            src_bs = src_bs_res.scalar_one_or_none()
            if not src_bs or float(src_bs.quantity) < float(item_in.quantity):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Insufficient stock in source branch for product ID {item_in.product_id}.",
                )

            src_bs.quantity = float(src_bs.quantity) - float(item_in.quantity)
            src_bs.updated_at = now
            src_new_bal = float(src_bs.quantity)

            # 2. Add to destination branch
            dst_bs_res = await db.execute(
                select(BranchStock).where(
                    BranchStock.tenant_id == tenant_id,
                    BranchStock.branch_id == payload.to_branch_id,
                    BranchStock.product_id == item_in.product_id,
                )
            )
            dst_bs = dst_bs_res.scalar_one_or_none()
            if not dst_bs:
                dst_bs = BranchStock(
                    tenant_id=tenant_id,
                    branch_id=payload.to_branch_id,
                    product_id=item_in.product_id,
                    quantity=item_in.quantity,
                )
                db.add(dst_bs)
                dst_new_bal = float(item_in.quantity)
            else:
                dst_bs.quantity = float(dst_bs.quantity) + float(item_in.quantity)
                dst_bs.updated_at = now
                dst_new_bal = float(dst_bs.quantity)

            # Insert transfer item row
            trf_item = StockTransferItem(
                tenant_id=tenant_id,
                transfer_id=transfer.id,
                product_id=item_in.product_id,
                quantity=item_in.quantity,
            )
            db.add(trf_item)

            # Write two stock movements
            db.add(
                StockMovement(
                    tenant_id=tenant_id,
                    branch_id=payload.from_branch_id,
                    product_id=item_in.product_id,
                    movement_type="TRANSFER_OUT",
                    quantity=-float(item_in.quantity),
                    balance_after=src_new_bal,
                    reference_type="transfer",
                    reference_id=transfer.id,
                    notes=f"Transferred to Branch #{payload.to_branch_id}",
                )
            )
            db.add(
                StockMovement(
                    tenant_id=tenant_id,
                    branch_id=payload.to_branch_id,
                    product_id=item_in.product_id,
                    movement_type="TRANSFER_IN",
                    quantity=float(item_in.quantity),
                    balance_after=dst_new_bal,
                    reference_type="transfer",
                    reference_id=transfer.id,
                    notes=f"Received from Branch #{payload.from_branch_id}",
                )
            )

        await db.commit()
        await db.refresh(transfer)

        resp = StockTransferResponse.model_validate(transfer)
        resp.items_count = len(payload.items)
        return resp

    @staticmethod
    async def create_stock_adjustment(
        db: AsyncSession, tenant_id: int, user_id: Optional[int], payload: StockAdjustmentCreate
    ) -> StockAdjustmentResponse:
        """Create a stock adjustment (damage, shrinkage, audit correction)."""
        now = datetime.now(timezone.utc)
        prefix = f"ADJ-{now.strftime('%Y%m')}"
        cnt_res = await db.execute(
            select(func.count(StockAdjustment.id)).where(
                StockAdjustment.tenant_id == tenant_id,
                StockAdjustment.adjustment_number.like(f"{prefix}-%"),
            )
        )
        seq = (cnt_res.scalar() or 0) + 1
        adj_number = f"{prefix}-{seq:04d}"

        adjustment = StockAdjustment(
            tenant_id=tenant_id,
            branch_id=payload.branch_id,
            adjustment_number=adj_number,
            adjustment_date=payload.adjustment_date or now.date(),
            reason=payload.reason,
            notes=payload.notes.strip() if payload.notes else None,
            created_by_id=user_id,
        )
        db.add(adjustment)
        await db.flush()

        for item_in in payload.items:
            bs_res = await db.execute(
                select(BranchStock).where(
                    BranchStock.tenant_id == tenant_id,
                    BranchStock.branch_id == payload.branch_id,
                    BranchStock.product_id == item_in.product_id,
                )
            )
            bs = bs_res.scalar_one_or_none()
            if not bs:
                bs = BranchStock(
                    tenant_id=tenant_id,
                    branch_id=payload.branch_id,
                    product_id=item_in.product_id,
                    quantity=0.0,
                )
                db.add(bs)
                await db.flush()

            is_add = item_in.adjustment_type.upper() == "ADD"
            delta = float(item_in.quantity) if is_add else -float(item_in.quantity)
            bs.quantity = max(0.0, float(bs.quantity) + delta)
            bs.updated_at = now
            new_bal = float(bs.quantity)

            db.add(
                StockAdjustmentItem(
                    tenant_id=tenant_id,
                    adjustment_id=adjustment.id,
                    product_id=item_in.product_id,
                    adjustment_type=item_in.adjustment_type.upper(),
                    quantity=item_in.quantity,
                )
            )

            db.add(
                StockMovement(
                    tenant_id=tenant_id,
                    branch_id=payload.branch_id,
                    product_id=item_in.product_id,
                    movement_type="ADJUSTMENT_ADD" if is_add else "ADJUSTMENT_SUB",
                    quantity=delta,
                    balance_after=new_bal,
                    reference_type="adjustment",
                    reference_id=adjustment.id,
                    notes=f"Adjustment: {payload.reason}",
                )
            )

        # Enterprise Accounting: Auto-post Stock Adjustment Journal Voucher (Inventory vs COGS/Shrinkage)
        try:
            from app.modules.accounting.posting import AccountingPostingEngine
            await AccountingPostingEngine.post_stock_adjustment(
                db=db,
                tenant_id=tenant_id,
                adjustment=adjustment,
                items_in=payload.items,
                user_id=user_id,
            )
        except Exception as e:
            print(f"[ACCOUNTING AUTO-POST WARNING] Failed to post stock adjustment voucher {adjustment.adjustment_number}: {e}")

        await db.commit()
        await db.refresh(adjustment)

        resp = StockAdjustmentResponse.model_validate(adjustment)
        resp.items_count = len(payload.items)
        return resp

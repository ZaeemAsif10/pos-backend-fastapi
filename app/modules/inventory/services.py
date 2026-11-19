from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, date, timezone
from fastapi import HTTPException, status
from sqlalchemy import select, func, or_, and_, update, delete
from sqlalchemy.orm import joinedload, selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.inventory.models import (
    Purchase,
    PurchaseItem,
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
            )
            .outerjoin(PurchaseItem, PurchaseItem.purchase_id == Purchase.id)
            .options(
                joinedload(Purchase.branch),
                joinedload(Purchase.supplier),
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
        results = []
        for p, count in res.unique().all():
            resp = PurchaseResponse.model_validate(p)
            resp.branch_name = p.branch.name if p.branch else None
            resp.supplier_name = p.supplier.company_name if p.supplier else None
            resp.items_count = count
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

        resp = PurchaseDetailResponse.model_validate(p)
        resp.branch_name = p.branch.name if p.branch else None
        resp.supplier_name = p.supplier.company_name if p.supplier else None
        resp.items_count = len(p.items)

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
        if acc_behavior == "paid":
            paid_amount = total_amount
            balance_due = 0.0
            payment_status = resolved_code
        elif acc_behavior == "unpaid":
            paid_amount = 0.0
            balance_due = total_amount
            payment_status = resolved_code
        else:
            paid_amount = min(payload.paid_amount, total_amount)
            balance_due = max(0.0, total_amount - paid_amount)
            payment_status = resolved_code if resolved_code else (
                "paid" if balance_due <= 0 else ("partial" if paid_amount > 0 else "unpaid")
            )

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
        try:
            from app.modules.accounting.services import AccountingService
            from app.modules.accounting.posting import AccountingPostingEngine
            await AccountingService.ensure_tenant_coa_and_settings(db, tenant_id, backfill=False)
            await AccountingPostingEngine.post_purchase_invoice(db, tenant_id, purchase, user_id)
        except Exception as e:
            print(f"[ACCOUNTING AUTO-POST WARNING] Failed to post purchase voucher {purchase.invoice_number}: {e}")

        await db.commit()
        await db.refresh(purchase)

        resp = PurchaseResponse.model_validate(purchase)
        resp.branch_name = branch.name
        resp.supplier_name = supplier.company_name
        resp.items_count = len(payload.items)
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

        if payload.payment_status is not None or payload.paid_amount is not None:
            target_code = payload.payment_status or p.payment_status
            resolved_code, acc_behavior = await PaymentStatusService.resolve_behavior(
                db, tenant_id, target_code
            )
            if acc_behavior == "paid":
                new_paid = total_amount
                new_due = 0.0
            elif acc_behavior == "unpaid" and (payload.paid_amount is None or payload.paid_amount <= 0):
                new_paid = 0.0
                new_due = total_amount
            else:
                req_paid = float(payload.paid_amount) if payload.paid_amount is not None else float(p.paid_amount or 0.0)
                new_paid = min(max(0.0, req_paid), total_amount)
                new_due = max(0.0, total_amount - new_paid)

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
            await AccountingPostingEngine.post_purchase_invoice(db, tenant_id, p, user_id)
        except Exception as e:
            print(f"[ACCOUNTING UPDATE WARNING] Failed to re-post purchase voucher {p.invoice_number}: {e}")

        await db.commit()
        await db.refresh(p)

        resp = PurchaseResponse.model_validate(p)
        resp.branch_name = p.branch.name if p.branch else None
        resp.supplier_name = p.supplier.company_name if p.supplier else None
        resp.items_count = len(p.items) if p.items else 0
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
    async def return_purchase(
        db: AsyncSession,
        tenant_id: int,
        purchase_id: int,
        user_id: int,
        reason: Optional[str] = "Goods Returned to Supplier / Debit Note",
        refund_payment_method: Optional[str] = "cash",
    ) -> Purchase:
        """
        Process full return to supplier (Debit Note):
        1. Validates purchase bill state (cannot return already returned or cancelled bill).
        2. Deducts returned stock from BranchStock and writes immutable StockMovement (PURCHASE_RETURN).
        3. Reverses supplier payable balance.
        4. Updates purchase status to 'returned'.
        5. Auto-posts balanced Debit Note Journal Voucher (IFRS / IAS-2).
        """
        stmt = (
            select(Purchase)
            .options(
                joinedload(Purchase.supplier),
                selectinload(Purchase.items),
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
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This purchase bill has already been returned.")
        if p.status == "cancelled":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cancelled purchase bills cannot be returned.")

        now = datetime.now(timezone.utc)

        # 1. Deduct branch stocks & add immutable StockMovements
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

            # Write purchase return movement
            ret_move = StockMovement(
                tenant_id=tenant_id,
                branch_id=p.branch_id,
                product_id=item.product_id,
                movement_type="PURCHASE_RETURN",
                quantity=-float(item.total_base_quantity),
                balance_after=new_bal,
                unit_cost=float(item.unit_cost),
                reference_type="purchase",
                reference_id=p.id,
                notes=f"Debit Note / Return to {p.supplier.company_name if p.supplier else 'Supplier'} (#{p.invoice_number}): {reason}",
            )
            db.add(ret_move)

        # 2. Reverse Supplier Payable Balance
        if float(p.balance_due) > 0 and p.supplier:
            p.supplier.current_balance = max(0.0, float(p.supplier.current_balance) - float(p.balance_due))
            p.supplier.updated_at = now

        # If paid amount and refund method is "credit" (supplier ledger credit):
        if float(p.paid_amount) > 0 and refund_payment_method == "credit" and p.supplier:
            p.supplier.current_balance = float(p.supplier.current_balance) - float(p.paid_amount)
            p.supplier.updated_at = now

        # 3. Mark status as returned
        p.status = "returned"
        p.notes = (p.notes or "") + (f" | Debit Note: {reason}" if reason else " | Debit Note")
        p.updated_at = now

        # 4. Auto-post Debit Note Journal Voucher
        try:
            from app.modules.accounting.posting import AccountingPostingEngine
            await AccountingPostingEngine.post_purchase_return(
                db,
                tenant_id,
                p,
                user_id=user_id,
                reason=reason,
                refund_payment_method=refund_payment_method,
            )
        except Exception as e:
            print(f"[ACCOUNTING DEBIT NOTE WARNING] Failed to post debit note for {p.invoice_number}: {e}")

        await db.commit()
        await db.refresh(p)
        return p



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

from datetime import datetime, date, timezone
from typing import List, Optional, Tuple
from sqlalchemy import select, func, and_, desc, or_
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status

from app.modules.sales.models import POSShift, SalesInvoice, SalesInvoiceItem, SalesPayment
from app.modules.sales.schemas import (
    POSShiftOpenRequest,
    POSShiftCloseRequest,
    SalesCheckoutRequest,
    DayBookResponse,
    DayBookSummary,
    DayBookEntry,
    DayBookPaymentMethodsSummary,
)
from app.modules.products.models import Product, ProductUOMConversion, BranchStock
from app.modules.branches.models import Branch
from app.modules.parties.models import Customer, CustomerPayment, Supplier, SupplierPayment
from app.modules.inventory.models import StockMovement
from app.modules.accounting.models import ExpenseVoucher, Account
from app.integrations.fbr.client import FBRClient
from app.integrations.fbr.schemas import FBRInvoicePayload, FBRInvoiceItemPayload
from app.core.config import settings


class SalesService:
    @staticmethod
    async def get_current_shift(
        db: AsyncSession, tenant_id: int, user_id: int, branch_id: int
    ) -> Optional[POSShift]:
        """Get the active/open shift for the current user in this branch."""
        stmt = select(POSShift).where(
            POSShift.tenant_id == tenant_id,
            POSShift.branch_id == branch_id,
            POSShift.cashier_id == user_id,
            POSShift.status == "open",
        ).order_by(desc(POSShift.id)).limit(1)
        res = await db.execute(stmt)
        return res.scalars().first()

    @staticmethod
    async def open_shift(
        db: AsyncSession, tenant_id: int, user_id: int, data: POSShiftOpenRequest
    ) -> POSShift:
        """Open a new register shift session."""
        existing = await SalesService.get_current_shift(db, tenant_id, user_id, data.branch_id)
        if existing:
            return existing

        shift = POSShift(
            tenant_id=tenant_id,
            branch_id=data.branch_id,
            cashier_id=user_id,
            opening_cash=data.opening_cash,
            notes=data.notes,
            status="open",
        )
        db.add(shift)
        await db.commit()
        await db.refresh(shift)
        return shift

    @staticmethod
    async def close_shift(
        db: AsyncSession, tenant_id: int, user_id: int, shift_id: int, data: POSShiftCloseRequest
    ) -> POSShift:
        """Close an active shift and compute cash differences."""
        stmt = select(POSShift).where(
            POSShift.id == shift_id,
            POSShift.tenant_id == tenant_id,
        )
        res = await db.execute(stmt)
        shift = res.scalars().first()
        if not shift:
            raise HTTPException(status_code=404, detail="Shift not found")
        if shift.status == "closed":
            return shift

        # Calculate cash sales during this shift (excluding cancelled/refunded and returns)
        cash_sales_stmt = select(func.coalesce(func.sum(SalesInvoice.paid_amount), 0)).where(
            SalesInvoice.pos_shift_id == shift.id,
            SalesInvoice.payment_method == "cash",
            SalesInvoice.status.notin_(["cancelled", "refunded"]),
            SalesInvoice.sale_type != "return_credit_note",
        )
        cash_res = await db.execute(cash_sales_stmt)
        total_cash_sales = float(cash_res.scalar() or 0.0)

        cash_returns_stmt = select(func.coalesce(func.sum(SalesInvoice.paid_amount), 0)).where(
            SalesInvoice.pos_shift_id == shift.id,
            SalesInvoice.payment_method == "cash",
            SalesInvoice.status != "cancelled",
            SalesInvoice.sale_type == "return_credit_note",
        )
        ret_res = await db.execute(cash_returns_stmt)
        total_cash_returns = float(ret_res.scalar() or 0.0)

        expected_cash = float(shift.opening_cash) + total_cash_sales - total_cash_returns
        diff = float(data.closing_cash) - expected_cash

        shift.closing_cash = data.closing_cash
        shift.expected_cash = expected_cash
        shift.cash_difference = diff
        shift.notes = (shift.notes or "") + f" | Closed: {data.notes or ''}"
        shift.status = "closed"
        shift.closed_at = datetime.now(timezone.utc)

        await db.commit()
        await db.refresh(shift)
        return shift

    @staticmethod
    async def checkout(
        db: AsyncSession,
        tenant_id: int,
        user_id: int,
        data: SalesCheckoutRequest,
        fbr_mode: str = "mock",
    ) -> SalesInvoice:
        """Process POS counter checkout or Wholesale sales invoice with FBR integration."""
        # 1. Validate Branch
        b_stmt = select(Branch).where(Branch.id == data.branch_id, Branch.tenant_id == tenant_id)
        b_res = await db.execute(b_stmt)
        branch = b_res.scalars().first()
        if not branch:
            raise HTTPException(status_code=400, detail="Invalid branch selected")

        # 2. Generate sequential invoice number
        now = datetime.now(timezone.utc)
        today_date = now.strftime("%Y%m%d")
        count_stmt = select(func.count(SalesInvoice.id)).where(
            SalesInvoice.tenant_id == tenant_id,
            SalesInvoice.branch_id == data.branch_id,
            func.date(SalesInvoice.created_at) == now.date(),
        )
        c_res = await db.execute(count_stmt)
        seq = (c_res.scalar() or 0) + 1
        b_code = branch.code.replace(" ", "").upper()[:4]
        inv_number = f"INV-{b_code}-{today_date}-{seq:04d}"

        # 3. Process line items, resolve products, stock, and calculate subtotal/tax
        is_return = data.sale_type == "return_credit_note"
        subtotal = 0.0
        tax_total = 0.0
        db_items: List[SalesInvoiceItem] = []
        db_movements: List[StockMovement] = []
        fbr_items: List[FBRInvoiceItemPayload] = []

        for item_in in data.items:
            p_stmt = select(Product).where(Product.id == item_in.product_id, Product.tenant_id == tenant_id)
            p_res = await db.execute(p_stmt)
            product = p_res.scalars().first()
            if not product:
                raise HTTPException(status_code=404, detail=f"Product ID {item_in.product_id} not found")

            # UOM and conversion
            uom_name = product.base_unit or "Piece"
            conversion_factor = 1.0
            if item_in.uom_id:
                uom_stmt = select(ProductUOMConversion).where(
                    ProductUOMConversion.id == item_in.uom_id,
                    ProductUOMConversion.product_id == product.id,
                )
                uom_res = await db.execute(uom_stmt)
                uom_obj = uom_res.scalars().first()
                if uom_obj:
                    uom_name = uom_obj.unit_name
                    conversion_factor = float(uom_obj.conversion_factor or 1.0)

            base_qty = float(item_in.quantity) * conversion_factor
            unit_price = float(item_in.unit_price)
            line_discount = float(item_in.discount_amount)
            line_subtotal = (unit_price * float(item_in.quantity)) - line_discount
            if line_subtotal < 0:
                line_subtotal = 0.0

            # Tax rate from item or product
            tax_rate = float(item_in.tax_rate) if item_in.tax_rate > 0 else float(product.tax_rate or 0.0)
            line_tax = round((line_subtotal * tax_rate) / 100.0, 2)
            line_total = line_subtotal + line_tax

            subtotal += line_subtotal
            tax_total += line_tax

            cost_price = float(product.cost_price or 0.0)
            unit_cost_for_uom = round(cost_price * conversion_factor, 2)
            pct_code = getattr(product, "pct_code", None) or "1905.9000"

            invoice_item = SalesInvoiceItem(
                tenant_id=tenant_id,
                product_id=product.id,
                uom_id=item_in.uom_id,
                uom_name=uom_name,
                quantity=item_in.quantity,
                unit_price=unit_price,
                cost_price=unit_cost_for_uom,
                discount_amount=line_discount,
                tax_rate=tax_rate,
                tax_amount=line_tax,
                pct_code=pct_code,
                total_amount=line_total,
            )
            db_items.append(invoice_item)

            # Update inventory stock in BranchStock (deduct for sale, add for return)
            bs_stmt = select(BranchStock).where(
                BranchStock.tenant_id == tenant_id,
                BranchStock.branch_id == branch.id,
                BranchStock.product_id == product.id,
            )
            bs_res = await db.execute(bs_stmt)
            b_stock = bs_res.scalars().first()
            if not b_stock:
                b_stock = BranchStock(
                    tenant_id=tenant_id,
                    branch_id=branch.id,
                    product_id=product.id,
                    quantity=0.0,
                )
                db.add(b_stock)

            old_qty = float(b_stock.quantity)
            qty_delta = base_qty if is_return else -base_qty
            new_qty = old_qty + qty_delta
            b_stock.quantity = new_qty

            # Add Stock Movement ledger entry
            movement = StockMovement(
                tenant_id=tenant_id,
                branch_id=branch.id,
                product_id=product.id,
                movement_type="SALE_RETURN" if is_return else "SALE",
                quantity=qty_delta,
                balance_after=new_qty,
                unit_cost=cost_price,
                reference_type="sales_invoice",
                reference_id=0,  # updated after invoice flush
                notes=f"POS Sale Return: {inv_number}" if is_return else f"POS Sale Invoice: {inv_number}",
            )
            db.add(movement)
            db_movements.append(movement)

            # FBR item payload
            fbr_items.append(
                FBRInvoiceItemPayload(
                    ItemCode=product.sku or str(product.id),
                    ItemName=product.name,
                    PCTCode=pct_code,
                    Quantity=float(item_in.quantity),
                    TaxRate=tax_rate,
                    SaleValue=line_subtotal,
                    TaxCharged=line_tax,
                    Discount=line_discount,
                    TotalAmount=line_total,
                )
            )

        # 4. Final bill calculations
        total_discount = float(data.discount_amount)
        final_bill = max(0.0, round(subtotal + tax_total - total_discount, 2))
        paid_amount = float(data.paid_amount)
        change_amount = max(0.0, round(paid_amount - final_bill, 2)) if data.payment_method == "cash" else 0.0
        balance_due = max(0.0, round(final_bill - paid_amount, 2))

        payment_status = "paid" if balance_due <= 0 else ("partial" if paid_amount > 0 else "unpaid")

        # 5. Customer Balance update if on credit
        if data.customer_id and balance_due > 0:
            c_stmt = select(Customer).where(Customer.id == data.customer_id, Customer.tenant_id == tenant_id)
            c_res = await db.execute(c_stmt)
            cust = c_res.scalars().first()
            if cust:
                if is_return:
                    cust.current_balance = max(0.0, float(cust.current_balance or 0.0) - balance_due)
                else:
                    cust.current_balance = float(cust.current_balance or 0.0) + balance_due

        # 6. Build SalesInvoice record
        invoice = SalesInvoice(
            tenant_id=tenant_id,
            branch_id=branch.id,
            customer_id=data.customer_id,
            pos_shift_id=data.pos_shift_id,
            customer_name=data.customer_name or "Walk-in Retail Buyer",
            customer_phone=data.customer_phone,
            customer_ntn_cnic=data.customer_ntn_cnic,
            invoice_number=inv_number,
            sale_type=data.sale_type,
            payment_method=data.payment_method,
            payment_status=payment_status,
            subtotal=subtotal,
            discount_amount=total_discount,
            tax_amount=tax_total,
            total_amount=final_bill,
            paid_amount=paid_amount,
            change_amount=change_amount,
            balance_due=balance_due,
            salesman_id=None,
            created_by_id=user_id,
            notes=data.notes,
            status="completed",
        )
        invoice.items = db_items

        # Payments
        if data.payments:
            for p in data.payments:
                pm = SalesPayment(
                    tenant_id=tenant_id,
                    payment_method=p.payment_method,
                    amount=p.amount,
                    reference_no=p.reference_no,
                    received_by_id=user_id,
                )
                invoice.payments.append(pm)
        elif paid_amount > 0:
            pm = SalesPayment(
                tenant_id=tenant_id,
                payment_method=data.payment_method,
                amount=min(paid_amount, final_bill),
                received_by_id=user_id,
            )
            invoice.payments.append(pm)

        db.add(invoice)
        await db.flush()  # assign invoice.id

        # Update reference_id for stock movements
        for m in db_movements:
            m.reference_id = invoice.id


        # 7. Execute FBR Integration
        pos_id_int = int(branch.fbr_pos_id) if branch.fbr_pos_id and branch.fbr_pos_id.isdigit() else 101
        fbr_payload = FBRInvoicePayload(
            POSID=pos_id_int,
            USIN=inv_number,
            DateTime=now.strftime("%Y-%m-%d %H:%M:%S"),
            BuyerName=data.customer_name,
            BuyerPhoneNumber=data.customer_phone,
            BuyerCNIC=data.customer_ntn_cnic,
            TotalSaleValue=subtotal,
            TotalQuantity=sum(float(i.quantity) for i in data.items),
            TotalTaxCharged=tax_total,
            TotalBillAmount=final_bill,
            Discount=total_discount,
            PaymentMode=1 if data.payment_method == "cash" else (2 if data.payment_method == "card" else 4),
            InvoiceType=1 if data.sale_type == "pos_retail" else 2,
            Items=fbr_items,
        )

        # Determine active FBR mode and authorization token
        active_mode = settings.FBR_MODE if fbr_mode == "mock" else fbr_mode
        active_token = settings.FBR_AUTH_TOKEN or None
        fbr_client = FBRClient(mode=active_mode, pos_id=str(pos_id_int), auth_token=active_token)
        fbr_response = await fbr_client.post_invoice(fbr_payload)

        invoice.fbr_pos_id = str(pos_id_int)
        invoice.fbr_invoice_number = fbr_response.fbr_invoice_number
        invoice.fbr_qr_code = fbr_response.fbr_qr_code
        invoice.fbr_status = fbr_response.status
        invoice.fbr_response_message = fbr_response.message
        invoice.fbr_synced_at = now

        # 8. Double-Entry General Ledger Auto-Posting
        try:
            from app.modules.accounting.posting import AccountingPostingEngine
            if is_return:
                await AccountingPostingEngine.post_sales_return(db, tenant_id, invoice, user_id)
            else:
                await AccountingPostingEngine.post_sales_invoice(db, tenant_id, invoice, user_id)
        except Exception as e:
            print(f"[ACCOUNTING POSTING ERROR] Sales invoice {invoice.invoice_number}: {e}")

        await db.commit()
        await db.refresh(invoice)
        return invoice

    @staticmethod
    async def list_invoices(
        db: AsyncSession,
        tenant_id: int,
        branch_id: Optional[int] = None,
        fbr_status: Optional[str] = None,
        payment_status: Optional[str] = None,
        status: Optional[str] = None,
        search: Optional[str] = None,
        page: int = 1,
        size: int = 10,
    ) -> Tuple[List[SalesInvoice], int, int, int]:
        """Fetch invoices with relations and server-side pagination (default 10)."""
        if page < 1:
            page = 1
        if size < 1:
            size = 10
        if size > 100:
            size = 100

        base_stmt = select(SalesInvoice).where(SalesInvoice.tenant_id == tenant_id)
        if branch_id:
            base_stmt = base_stmt.where(SalesInvoice.branch_id == branch_id)
        if fbr_status:
            base_stmt = base_stmt.where(SalesInvoice.fbr_status == fbr_status)
        if payment_status:
            base_stmt = base_stmt.where(SalesInvoice.payment_status == payment_status)
        if status:
            base_stmt = base_stmt.where(SalesInvoice.status == status)
        if search:
            s = f"%{search.strip()}%"
            base_stmt = base_stmt.where(
                or_(
                    SalesInvoice.invoice_number.ilike(s),
                    SalesInvoice.customer_name.ilike(s),
                    SalesInvoice.fbr_invoice_number.ilike(s),
                )
            )

        # Count total records matching filters
        count_stmt = select(func.count()).select_from(base_stmt.order_by(None).subquery())
        total_res = await db.execute(count_stmt)
        total = total_res.scalar_one_or_none() or 0

        # Fetch paginated items
        items_stmt = (
            base_stmt
            .options(
                selectinload(SalesInvoice.items).selectinload(SalesInvoiceItem.product),
                selectinload(SalesInvoice.payments),
                selectinload(SalesInvoice.branch),
                selectinload(SalesInvoice.customer),
                selectinload(SalesInvoice.created_by),
            )
            .order_by(desc(SalesInvoice.id))
            .offset((page - 1) * size)
            .limit(size)
        )
        res = await db.execute(items_stmt)
        items = list(res.scalars().all())

        total_pages = (total + size - 1) // size if total > 0 else 1
        return items, total, page, total_pages

    @staticmethod
    async def get_invoice(db: AsyncSession, tenant_id: int, invoice_id: int) -> Optional[SalesInvoice]:
        stmt = (
            select(SalesInvoice)
            .where(SalesInvoice.id == invoice_id, SalesInvoice.tenant_id == tenant_id)
            .options(
                selectinload(SalesInvoice.items).selectinload(SalesInvoiceItem.product),
                selectinload(SalesInvoice.payments),
                selectinload(SalesInvoice.branch),
                selectinload(SalesInvoice.customer),
                selectinload(SalesInvoice.created_by),
            )
        )
        res = await db.execute(stmt)
        return res.scalars().first()

    @staticmethod
    async def refund_invoice(
        db: AsyncSession,
        tenant_id: int,
        user_id: int,
        invoice_id: int,
        reason: Optional[str] = "Customer Return / Refund",
    ) -> SalesInvoice:
        """
        Process a full return/refund for an existing sales invoice:
        1. Validates invoice state (reject if already refunded or cancelled).
        2. Restores branch stock for all line items and logs immutable StockMovement (SALE_RETURN).
        3. If credit sale, reverses customer khata balance.
        4. Marks invoice status = 'refunded'.
        5. Auto-posts balanced Credit Note / Sales Return Journal Voucher (IFRS / IAS-2).
        """
        stmt = (
            select(SalesInvoice)
            .where(SalesInvoice.id == invoice_id, SalesInvoice.tenant_id == tenant_id)
            .options(
                selectinload(SalesInvoice.items).selectinload(SalesInvoiceItem.product),
                selectinload(SalesInvoice.payments),
                selectinload(SalesInvoice.branch),
                selectinload(SalesInvoice.customer),
                selectinload(SalesInvoice.created_by),
            )
        )
        res = await db.execute(stmt)
        invoice = res.scalars().first()
        if not invoice:
            raise HTTPException(status_code=404, detail="Sales invoice not found")

        if invoice.status == "refunded":
            raise HTTPException(status_code=400, detail="This invoice has already been refunded.")
        if invoice.status == "cancelled":
            raise HTTPException(status_code=400, detail="Cancelled invoices cannot be refunded.")
        if invoice.sale_type == "return_credit_note":
            raise HTTPException(status_code=400, detail="A credit note cannot be refunded.")

        now = datetime.now(timezone.utc)

        # 1. Restore Inventory Stock in BranchStock and add StockMovements
        for item in (invoice.items or []):
            conversion_factor = 1.0
            if item.uom_id:
                uom_stmt = select(ProductUOMConversion.conversion_factor).where(
                    ProductUOMConversion.id == item.uom_id,
                    ProductUOMConversion.product_id == item.product_id,
                )
                uom_res = await db.execute(uom_stmt)
                conversion_factor = float(uom_res.scalar_one_or_none() or 1.0)

            base_qty = float(item.quantity) * conversion_factor

            bs_stmt = select(BranchStock).where(
                BranchStock.tenant_id == tenant_id,
                BranchStock.branch_id == invoice.branch_id,
                BranchStock.product_id == item.product_id,
            )
            bs_res = await db.execute(bs_stmt)
            b_stock = bs_res.scalars().first()
            if not b_stock:
                b_stock = BranchStock(
                    tenant_id=tenant_id,
                    branch_id=invoice.branch_id,
                    product_id=item.product_id,
                    quantity=0.0,
                )
                db.add(b_stock)

            old_qty = float(b_stock.quantity)
            new_qty = old_qty + base_qty
            b_stock.quantity = new_qty
            b_stock.updated_at = now

            cost_price = float(item.cost_price or 0.0)
            if cost_price <= 0 and item.product:
                cost_price = float(item.product.cost_price or 0.0)

            movement = StockMovement(
                tenant_id=tenant_id,
                branch_id=invoice.branch_id,
                product_id=item.product_id,
                movement_type="SALE_RETURN",
                quantity=base_qty,
                balance_after=new_qty,
                unit_cost=cost_price,
                reference_type="sales_invoice",
                reference_id=invoice.id,
                notes=f"Sales Return / Refund: {invoice.invoice_number} ({reason or 'Customer return'})",
            )
            db.add(movement)

        # 2. Reverse customer khata balance if credit sale
        balance_due = float(invoice.balance_due or 0.0)
        if invoice.customer_id and balance_due > 0 and invoice.customer:
            invoice.customer.current_balance = max(0.0, float(invoice.customer.current_balance or 0.0) - balance_due)
            invoice.customer.updated_at = now

        # 3. Update invoice status
        invoice.status = "refunded"
        invoice.notes = (invoice.notes or "") + (f" | Refunded: {reason}" if reason else " | Refunded")
        invoice.updated_at = now

        # 4. Auto-post Double-Entry Credit Note / Return Voucher
        try:
            from app.modules.accounting.posting import AccountingPostingEngine
            await AccountingPostingEngine.post_sales_return(db, tenant_id, invoice, user_id, reason=reason)
        except Exception as e:
            print(f"[ACCOUNTING REFUND POST WARNING] Failed to post credit note for {invoice.invoice_number}: {e}")

        await db.commit()
        await db.refresh(invoice)
        return invoice


    @staticmethod
    async def get_sales_summary(db: AsyncSession, tenant_id: int, branch_id: Optional[int] = None):
        """Today's quick metrics for the POS bar and sales dashboard."""
        today = datetime.now(timezone.utc).date()
        base_filters = [SalesInvoice.tenant_id == tenant_id, func.date(SalesInvoice.created_at) == today]
        if branch_id:
            base_filters.append(SalesInvoice.branch_id == branch_id)

        sales_stmt = select(
            func.coalesce(func.sum(SalesInvoice.total_amount), 0),
            func.count(SalesInvoice.id),
            func.coalesce(func.sum(SalesInvoice.paid_amount), 0),
        ).where(and_(*base_filters, SalesInvoice.status != "cancelled"))

        sales_res = await db.execute(sales_stmt)
        row = sales_res.one()

        pending_fbr_stmt = select(func.count(SalesInvoice.id)).where(
            SalesInvoice.tenant_id == tenant_id,
            SalesInvoice.fbr_status.in_(["pending", "failed"]),
        )
        pending_res = await db.execute(pending_fbr_stmt)
        pending_fbr = pending_res.scalar() or 0

        return {
            "today_sales": float(row[0]),
            "today_invoices_count": int(row[1]),
            "today_cash_collected": float(row[2]),
            "pending_fbr_sync_count": int(pending_fbr),
        }

    @staticmethod
    async def get_day_book(
        db: AsyncSession,
        tenant_id: int,
        target_date: date,
        branch_id: Optional[int] = None,
        payment_method_filter: Optional[str] = None,
    ) -> DayBookResponse:
        """
        Consolidate daily transactions into Day Book / Roznamcha (Cash & Bank Book).
        - Sales Cash & Bank Inflows
        - Customer Khata Wasooli (CRV) Inflows
        - Supplier Khata Adaiygi (CPV) Outflows
        - Opening Shift Cash
        - Running Cash Balance
        """
        start_of_day = datetime(target_date.year, target_date.month, target_date.day, 0, 0, 0, tzinfo=timezone.utc)
        end_of_day = datetime(target_date.year, target_date.month, target_date.day, 23, 59, 59, 999999, tzinfo=timezone.utc)

        # 1. Branch info
        branch_name: Optional[str] = None
        if branch_id:
            branch_q = await db.execute(select(Branch).where(Branch.id == branch_id, Branch.tenant_id == tenant_id))
            branch_obj = branch_q.scalars().first()
            if branch_obj:
                branch_name = branch_obj.name

        # 2. Opening Cash from POSShift
        shift_filters = [
            POSShift.tenant_id == tenant_id,
            POSShift.opened_at >= start_of_day,
            POSShift.opened_at <= end_of_day,
        ]
        if branch_id:
            shift_filters.append(POSShift.branch_id == branch_id)

        shift_q = await db.execute(
            select(func.coalesce(func.sum(POSShift.opening_cash), 0.0)).where(and_(*shift_filters))
        )
        opening_cash = float(shift_q.scalar() or 0.0)

        raw_entries = []

        # 3. Fetch Sales Payments
        sales_filters = [
            SalesInvoice.tenant_id == tenant_id,
            SalesPayment.payment_date >= start_of_day,
            SalesPayment.payment_date <= end_of_day,
            SalesInvoice.status != "cancelled",
        ]
        if branch_id:
            sales_filters.append(SalesInvoice.branch_id == branch_id)
        if payment_method_filter and payment_method_filter != "all":
            sales_filters.append(SalesPayment.payment_method == payment_method_filter)

        sales_stmt = (
            select(SalesPayment, SalesInvoice, Branch.name.label("branch_name"))
            .join(SalesInvoice, SalesPayment.sales_invoice_id == SalesInvoice.id)
            .outerjoin(Branch, SalesInvoice.branch_id == Branch.id)
            .options(selectinload(SalesPayment.received_by))
            .where(and_(*sales_filters))
        )
        sales_res = await db.execute(sales_stmt)
        for sp, inv, b_name in sales_res.all():
            amt = float(sp.amount or 0.0)
            u_name = sp.received_by.full_name if sp.received_by else inv.cashier_name
            raw_entries.append({
                "id": f"SALE-{sp.id}",
                "entry_type": "sale",
                "timestamp": sp.payment_date,
                "voucher_no": inv.invoice_number,
                "party_name": inv.customer_name or "Walk-in Customer",
                "payment_method": sp.payment_method or "cash",
                "cash_in": amt,
                "cash_out": 0.0,
                "user_name": u_name,
                "branch_name": b_name,
                "notes": inv.notes or "POS Counter Sale",
            })

        # 4. Fetch Customer Payments (CRV)
        crv_filters = [
            CustomerPayment.tenant_id == tenant_id,
            CustomerPayment.created_at >= start_of_day,
            CustomerPayment.created_at <= end_of_day,
        ]
        if branch_id:
            crv_filters.append(CustomerPayment.branch_id == branch_id)
        if payment_method_filter and payment_method_filter != "all":
            crv_filters.append(CustomerPayment.payment_method == payment_method_filter)

        crv_stmt = (
            select(CustomerPayment, Customer.business_name.label("cust_name"), Branch.name.label("branch_name"))
            .join(Customer, CustomerPayment.customer_id == Customer.id)
            .outerjoin(Branch, CustomerPayment.branch_id == Branch.id)
            .options(selectinload(CustomerPayment.received_by))
            .where(and_(*crv_filters))
        )
        crv_res = await db.execute(crv_stmt)
        for crv, c_name, b_name in crv_res.all():
            amt = float(crv.amount or 0.0)
            u_name = crv.received_by.full_name if crv.received_by else None
            raw_entries.append({
                "id": f"CRV-{crv.id}",
                "entry_type": "customer_payment",
                "timestamp": crv.created_at,
                "voucher_no": crv.voucher_number,
                "party_name": c_name or "Customer",
                "payment_method": crv.payment_method or "cash",
                "cash_in": amt,
                "cash_out": 0.0,
                "user_name": u_name,
                "branch_name": b_name,
                "notes": crv.notes or "Customer Khata Wasooli",
            })

        # 5. Fetch Supplier Payments (CPV)
        cpv_filters = [
            SupplierPayment.tenant_id == tenant_id,
            SupplierPayment.created_at >= start_of_day,
            SupplierPayment.created_at <= end_of_day,
        ]
        if branch_id:
            cpv_filters.append(SupplierPayment.branch_id == branch_id)
        if payment_method_filter and payment_method_filter != "all":
            cpv_filters.append(SupplierPayment.payment_method == payment_method_filter)

        cpv_stmt = (
            select(SupplierPayment, Supplier.company_name.label("supp_name"), Branch.name.label("branch_name"))
            .join(Supplier, SupplierPayment.supplier_id == Supplier.id)
            .outerjoin(Branch, SupplierPayment.branch_id == Branch.id)
            .options(selectinload(SupplierPayment.paid_by))
            .where(and_(*cpv_filters))
        )
        cpv_res = await db.execute(cpv_stmt)
        for cpv, s_name, b_name in cpv_res.all():
            amt = float(cpv.amount or 0.0)
            u_name = cpv.paid_by.full_name if cpv.paid_by else None
            raw_entries.append({
                "id": f"CPV-{cpv.id}",
                "entry_type": "supplier_payment",
                "timestamp": cpv.created_at,
                "voucher_no": cpv.voucher_number,
                "party_name": s_name or "Supplier",
                "payment_method": cpv.payment_method or "cash",
                "cash_in": 0.0,
                "cash_out": amt,
                "user_name": u_name,
                "branch_name": b_name,
                "notes": cpv.notes or "Supplier Khata Payment",
            })

        # 5.5 Fetch Direct Expenses (CPV / Akhrajaat)
        exp_filters = [
            ExpenseVoucher.tenant_id == tenant_id,
            ExpenseVoucher.expense_date >= start_of_day,
            ExpenseVoucher.expense_date <= end_of_day,
            ExpenseVoucher.status == "posted",
        ]
        if branch_id:
            exp_filters.append(ExpenseVoucher.branch_id == branch_id)
        if payment_method_filter and payment_method_filter != "all":
            exp_filters.append(ExpenseVoucher.payment_method == payment_method_filter)

        exp_stmt = (
            select(
                ExpenseVoucher,
                Account.name.label("exp_acc_name"),
                Branch.name.label("branch_name"),
            )
            .join(Account, ExpenseVoucher.expense_account_id == Account.id)
            .outerjoin(Branch, ExpenseVoucher.branch_id == Branch.id)
            .options(selectinload(ExpenseVoucher.created_by))
            .where(and_(*exp_filters))
        )
        exp_res = await db.execute(exp_stmt)
        for ev, acc_name, b_name in exp_res.all():
            amt = float(ev.amount or 0.0)
            u_name = ev.created_by.full_name if ev.created_by else None
            raw_entries.append({
                "id": f"EXP-{ev.id}",
                "entry_type": "expense",
                "timestamp": ev.expense_date,
                "voucher_no": ev.voucher_number,
                "party_name": f"{ev.payee_name} ({acc_name})",
                "payment_method": ev.payment_method or "cash",
                "cash_in": 0.0,
                "cash_out": amt,
                "user_name": u_name,
                "branch_name": b_name,
                "notes": ev.narration or f"Expense: {acc_name}",
            })

        # 6. Sort chronologically
        raw_entries.sort(key=lambda x: x["timestamp"])

        # 7. Calculate Running Balance & Method Breakdown
        pm_totals = {
            "cash": 0.0,
            "bank_transfer": 0.0,
            "card": 0.0,
            "raast": 0.0,
            "cheque": 0.0,
            "other": 0.0,
        }

        cash_sales = 0.0
        customer_wasooli = 0.0
        supplier_payments = 0.0
        cash_expenses = 0.0
        total_cash_in = 0.0
        total_cash_out = 0.0
        non_cash_inflow = 0.0

        current_running = opening_cash
        final_entries = []

        for item in raw_entries:
            pm = (item["payment_method"] or "cash").lower()
            is_cash = pm == "cash"

            c_in = item["cash_in"]
            c_out = item["cash_out"]

            if item["entry_type"] == "sale":
                if is_cash:
                    cash_sales += c_in
                else:
                    non_cash_inflow += c_in
            elif item["entry_type"] == "customer_payment":
                if is_cash:
                    customer_wasooli += c_in
                else:
                    non_cash_inflow += c_in
            elif item["entry_type"] == "supplier_payment":
                if is_cash:
                    supplier_payments += c_out
            elif item["entry_type"] == "expense":
                if is_cash:
                    cash_expenses += c_out

            if is_cash:
                total_cash_in += c_in
                total_cash_out += c_out
                current_running += (c_in - c_out)
                item_running = current_running
            else:
                item_running = current_running

            # Payment method breakdown
            if pm in pm_totals:
                pm_totals[pm] += (c_in - c_out)
            else:
                pm_totals["other"] += (c_in - c_out)

            final_entries.append(DayBookEntry(
                id=item["id"],
                entry_type=item["entry_type"],
                timestamp=item["timestamp"],
                voucher_no=item["voucher_no"],
                party_name=item["party_name"],
                payment_method=item["payment_method"],
                cash_in=round(c_in, 2),
                cash_out=round(c_out, 2),
                running_balance=round(item_running, 2),
                user_name=item["user_name"],
                branch_name=item["branch_name"],
                notes=item["notes"],
            ))

        closing_cash = opening_cash + total_cash_in - total_cash_out

        summary = DayBookSummary(
            opening_cash=round(opening_cash, 2),
            total_cash_in=round(total_cash_in, 2),
            total_cash_out=round(total_cash_out, 2),
            closing_cash=round(closing_cash, 2),
            cash_sales=round(cash_sales, 2),
            customer_wasooli=round(customer_wasooli, 2),
            supplier_payments=round(supplier_payments, 2),
            cash_expenses=round(cash_expenses, 2),
            non_cash_inflow=round(non_cash_inflow, 2),
            total_turnover=round(cash_sales + non_cash_inflow, 2),
            total_entries_count=len(final_entries),
        )

        pm_summary = DayBookPaymentMethodsSummary(
            cash=round(pm_totals["cash"], 2),
            bank_transfer=round(pm_totals["bank_transfer"], 2),
            card=round(pm_totals["card"], 2),
            raast=round(pm_totals["raast"], 2),
            cheque=round(pm_totals["cheque"], 2),
            other=round(pm_totals["other"], 2),
        )

        return DayBookResponse(
            date=target_date.isoformat(),
            branch_id=branch_id,
            branch_name=branch_name or "All Branches",
            summary=summary,
            payment_methods=pm_summary,
            entries=final_entries,
        )

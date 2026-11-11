from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.modules.accounting.models import (
    Account,
    TenantAccountingSettings,
    JournalEntry,
    JournalEntryLine,
)
from app.modules.accounting.services import AccountingService


class AccountingPostingEngine:
    """
    Automatic Double-Entry Posting Engine for Enterprise ERP transactions.
    Resolves tenant's pre-configured Account Mappings and posts balanced Journal Entries.
    Zero-touch for cashiers and counter staff.
    """

    @staticmethod
    async def _resolve_inventory_asset_account_id(
        db: AsyncSession,
        tenant_id: int,
        settings: TenantAccountingSettings,
    ) -> Optional[int]:
        """
        Safely resolve the Merchandise Inventory Asset account (Head 1040).
        Prevents accidental mapping to Cash (1010) or Bank (1020) accounts.
        """
        inv_acc_id = settings.default_inventory_asset_account_id
        if inv_acc_id:
            acc_res = await db.execute(
                select(Account).where(Account.id == inv_acc_id, Account.tenant_id == tenant_id)
            )
            acc = acc_res.scalar_one_or_none()
            if acc and acc.code not in ("1010", "1020") and (acc.sub_type or "").lower() not in ("cash", "bank"):
                return acc.id

        # Fallback to 1040 Merchandise Inventory (Stock)
        fallback_res = await db.execute(
            select(Account.id).where(Account.tenant_id == tenant_id, Account.code == "1040")
        )
        return fallback_res.scalar_one_or_none()

    @staticmethod
    async def _resolve_cogs_account_id(
        db: AsyncSession,
        tenant_id: int,
        settings: TenantAccountingSettings,
    ) -> Optional[int]:
        """Safely resolve the Cost of Goods Sold (COGS) account (Head 5010)."""
        if settings.default_cogs_account_id:
            return settings.default_cogs_account_id
        res = await db.execute(
            select(Account.id).where(Account.tenant_id == tenant_id, Account.code == "5010")
        )
        return res.scalar_one_or_none()

    @staticmethod
    async def post_sales_invoice(
        db: AsyncSession,
        tenant_id: int,
        invoice,  # SalesInvoice model instance
        user_id: Optional[int] = None,
    ) -> Optional[JournalEntry]:
        """
        Auto-post balanced double-entry Journal Voucher for a POS / Sales Invoice (IFRS / IAS-2 Perpetual Inventory).
        1. Revenue & Tender Side:
           - Dr. Cash/Bank (for payment received)
           - Dr. Accounts Receivable (for customer balance due / credit sale)
           - Dr. Sales Discounts Allowed (4020) (if discount given)
           - Cr. Sales Revenue (4010) (gross sales or net sales)
           - Cr. Sales Tax Payable (2020) (tax amount)
        2. Perpetual Inventory COGS & Stock Relief Side:
           - Dr. Cost of Goods Sold - COGS (5010) (sum of item qty * cost_price)
           - Cr. Merchandise Inventory Asset (1040) (sum of item qty * cost_price)
        """
        settings = await AccountingService.get_tenant_settings(db, tenant_id)
        if not settings.auto_posting_enabled:
            return None

        # Resolve accounts from mapping settings
        sales_acc_id = settings.default_sales_income_account_id
        discount_acc_id = settings.default_discount_account_id
        ar_acc_id = settings.default_ar_account_id
        tax_acc_id = settings.default_sales_tax_account_id
        cash_acc_id = settings.default_cash_account_id
        bank_acc_id = settings.default_bank_account_id or cash_acc_id
        cogs_acc_id = await AccountingPostingEngine._resolve_cogs_account_id(db, tenant_id, settings)
        inventory_acc_id = await AccountingPostingEngine._resolve_inventory_asset_account_id(db, tenant_id, settings)

        if not sales_acc_id:
            s_res = await db.execute(select(Account.id).where(Account.tenant_id == tenant_id, Account.code == "4010"))
            sales_acc_id = s_res.scalar_one_or_none()
        if not discount_acc_id:
            d_res = await db.execute(select(Account.id).where(Account.tenant_id == tenant_id, Account.code == "4020"))
            discount_acc_id = d_res.scalar_one_or_none()
        if not ar_acc_id:
            ar_res = await db.execute(select(Account.id).where(Account.tenant_id == tenant_id, Account.code == "1030"))
            ar_acc_id = ar_res.scalar_one_or_none()
        if not cash_acc_id:
            c_res = await db.execute(select(Account.id).where(Account.tenant_id == tenant_id, Account.code == "1010"))
            cash_acc_id = c_res.scalar_one_or_none()
        if not tax_acc_id:
            t_res = await db.execute(select(Account.id).where(Account.tenant_id == tenant_id, Account.code == "2020"))
            tax_acc_id = t_res.scalar_one_or_none()

        if not sales_acc_id:
            # Cannot post without a revenue account
            return None

        lines: List[JournalEntryLine] = []
        tot_debit = 0.0
        tot_credit = 0.0

        # 1. Debit Payment Asset Accounts (Cash / Bank / Raast / Card)
        method_map = settings.payment_method_mappings or {}
        paid_amt = float(invoice.paid_amount or 0.0)
        final_bill = float(invoice.total_amount or 0.0)
        balance_due = float(invoice.balance_due or 0.0)

        # Handle split payments if present
        payments = getattr(invoice, "payments", [])
        if payments and len(payments) > 0:
            for pmt in payments:
                p_amt = float(pmt.amount or 0.0)
                if p_amt <= 0:
                    continue
                pm_key = (pmt.payment_method or "cash").lower()
                target_acc_id = method_map.get(pm_key) or (cash_acc_id if pm_key == "cash" else bank_acc_id)
                if target_acc_id:
                    lines.append(JournalEntryLine(
                        account_id=target_acc_id,
                        branch_id=invoice.branch_id,
                        debit=round(p_amt, 2),
                        credit=0.0,
                        narration=f"Payment received via {pm_key.upper()} (Inv: {invoice.invoice_number})",
                        customer_id=invoice.customer_id,
                    ))
                    tot_debit += p_amt
        elif paid_amt > 0:
            pm_key = (invoice.payment_method or "cash").lower()
            target_acc_id = method_map.get(pm_key) or (cash_acc_id if pm_key == "cash" else bank_acc_id)
            actual_paid = min(paid_amt, final_bill)
            if target_acc_id and actual_paid > 0:
                lines.append(JournalEntryLine(
                    account_id=target_acc_id,
                    branch_id=invoice.branch_id,
                    debit=round(actual_paid, 2),
                    credit=0.0,
                    narration=f"Payment received via {pm_key.upper()} (Inv: {invoice.invoice_number})",
                    customer_id=invoice.customer_id,
                ))
                tot_debit += actual_paid

        # 2. Debit Accounts Receivable (Customer Khata) if on credit / balance due
        if balance_due > 0 and ar_acc_id:
            lines.append(JournalEntryLine(
                account_id=ar_acc_id,
                branch_id=invoice.branch_id,
                debit=round(balance_due, 2),
                credit=0.0,
                narration=f"Credit sale balance due (Inv: {invoice.invoice_number})",
                customer_id=invoice.customer_id,
            ))
            tot_debit += balance_due

        # 3. Sales Revenue & Contra-Revenue Sales Discounts
        subtotal = round(float(invoice.subtotal or 0.0), 2)
        discount = round(float(invoice.discount_amount or 0.0), 2)
        net_sales = max(0.0, round(subtotal - discount, 2))

        if discount > 0 and discount_acc_id and subtotal >= discount:
            # Post Gross Sales to 4010 and Discount Allowed to 4020
            lines.append(JournalEntryLine(
                account_id=discount_acc_id,
                branch_id=invoice.branch_id,
                debit=discount,
                credit=0.0,
                narration=f"Sales discount allowed (Inv: {invoice.invoice_number})",
                customer_id=invoice.customer_id,
            ))
            tot_debit += discount

            lines.append(JournalEntryLine(
                account_id=sales_acc_id,
                branch_id=invoice.branch_id,
                debit=0.0,
                credit=subtotal,
                narration=f"Gross sales revenue (Inv: {invoice.invoice_number})",
                customer_id=invoice.customer_id,
            ))
            tot_credit += subtotal
        elif net_sales > 0:
            lines.append(JournalEntryLine(
                account_id=sales_acc_id,
                branch_id=invoice.branch_id,
                debit=0.0,
                credit=net_sales,
                narration=f"Gross sales revenue (Inv: {invoice.invoice_number})",
                customer_id=invoice.customer_id,
            ))
            tot_credit += net_sales

        # 4. Credit Sales Tax Payable (FBR / PRA Output Tax)
        tax_amt = float(invoice.tax_amount or 0.0)
        if tax_amt > 0 and tax_acc_id:
            lines.append(JournalEntryLine(
                account_id=tax_acc_id,
                branch_id=invoice.branch_id,
                debit=0.0,
                credit=round(tax_amt, 2),
                narration=f"Sales tax payable (Inv: {invoice.invoice_number})",
                customer_id=invoice.customer_id,
            ))
            tot_credit += tax_amt

        # Invariant check on Revenue side: ensure Debit == Credit (handle penny rounding)
        diff = round(tot_debit - tot_credit, 2)
        if abs(diff) > 0.00 and abs(diff) <= 0.05:
            for l in lines:
                if l.account_id == sales_acc_id:
                    l.credit = round(l.credit + diff, 2)
                    tot_credit += diff
                    break

        # 5. Perpetual Inventory COGS & Stock Asset Relief (IFRS IAS-2)
        total_cogs = 0.0
        inv_items = getattr(invoice, "items", []) or []
        for item in inv_items:
            qty = float(getattr(item, "quantity", 0.0) or 0.0)
            c_price = float(getattr(item, "cost_price", 0.0) or 0.0)
            if c_price <= 0 and getattr(item, "product_id", None):
                from app.modules.products.models import Product
                p_cost = (
                    await db.execute(select(Product.cost_price).where(Product.id == item.product_id))
                ).scalar_one_or_none()
                c_price = float(p_cost or 0.0)
            if qty > 0 and c_price > 0:
                total_cogs += round(qty * c_price, 2)

        total_cogs = round(total_cogs, 2)
        if total_cogs > 0 and cogs_acc_id and inventory_acc_id:
            # Dr. Cost of Goods Sold (5010)
            lines.append(JournalEntryLine(
                account_id=cogs_acc_id,
                branch_id=invoice.branch_id,
                debit=total_cogs,
                credit=0.0,
                narration=f"Cost of goods sold - COGS (Inv: {invoice.invoice_number})",
                customer_id=invoice.customer_id,
            ))
            # Cr. Merchandise Inventory Asset (1040)
            lines.append(JournalEntryLine(
                account_id=inventory_acc_id,
                branch_id=invoice.branch_id,
                debit=0.0,
                credit=total_cogs,
                narration=f"Inventory stock relieved on sale (Inv: {invoice.invoice_number})",
                customer_id=invoice.customer_id,
            ))
            tot_debit += total_cogs
            tot_credit += total_cogs

        tot_debit = round(tot_debit, 2)
        tot_credit = round(tot_credit, 2)

        if abs(tot_debit - tot_credit) > 0.01 or tot_debit <= 0:
            return None

        entry_no = await AccountingService.generate_jv_number(db, tenant_id)
        jv = JournalEntry(
            tenant_id=tenant_id,
            branch_id=invoice.branch_id,
            entry_number=entry_no,
            entry_date=invoice.invoice_date or invoice.created_at or datetime.now(timezone.utc),
            source_type="sales_invoice",
            source_id=invoice.id,
            reference_no=invoice.invoice_number,
            narration=f"POS Sale Invoice: {invoice.invoice_number} ({invoice.customer_name or 'Walk-in'})",
            currency="PKR",
            exchange_rate=1.0,
            status="posted",
            total_debit=tot_debit,
            total_credit=tot_credit,
            created_by_id=user_id or invoice.created_by_id,
            lines=lines,
        )
        db.add(jv)
        await db.flush()
        return jv

    @staticmethod
    async def post_customer_payment(
        db: AsyncSession,
        tenant_id: int,
        payment,  # CustomerPayment model instance
        user_id: Optional[int] = None,
    ) -> Optional[JournalEntry]:
        """
        Auto-post balanced Journal Voucher for Customer Wasooli (CRV).
        Dr. Cash/Bank (Tender Account)
        Cr. Accounts Receivable (Customer Khata)
        """
        settings = await AccountingService.get_tenant_settings(db, tenant_id)
        if not settings.auto_posting_enabled:
            return None

        amt = float(payment.amount or 0.0)
        if amt <= 0:
            return None

        method_map = settings.payment_method_mappings or {}
        pm_key = (payment.payment_method or "cash").lower()
        cash_acc_id = settings.default_cash_account_id
        bank_acc_id = settings.default_bank_account_id or cash_acc_id
        ar_acc_id = settings.default_ar_account_id

        target_tender_acc_id = method_map.get(pm_key) or (cash_acc_id if pm_key == "cash" else bank_acc_id)
        if not target_tender_acc_id or not ar_acc_id:
            return None

        lines = [
            JournalEntryLine(
                account_id=target_tender_acc_id,
                branch_id=payment.branch_id,
                debit=round(amt, 2),
                credit=0.0,
                narration=f"Customer recovery received via {pm_key.upper()} ({payment.voucher_number})",
                customer_id=payment.customer_id,
            ),
            JournalEntryLine(
                account_id=ar_acc_id,
                branch_id=payment.branch_id,
                debit=0.0,
                credit=round(amt, 2),
                narration=f"Customer account credited ({payment.voucher_number})",
                customer_id=payment.customer_id,
            ),
        ]

        entry_no = await AccountingService.generate_jv_number(db, tenant_id)
        e_date = getattr(payment, "payment_date", None) or getattr(payment, "created_at", None) or datetime.now(timezone.utc)
        jv = JournalEntry(
            tenant_id=tenant_id,
            branch_id=payment.branch_id,
            entry_number=entry_no,
            entry_date=e_date,
            source_type="customer_payment",
            source_id=payment.id,
            reference_no=payment.voucher_number,
            narration=f"Customer Wasooli (CRV): {payment.voucher_number}",
            currency="PKR",
            exchange_rate=1.0,
            status="posted",
            total_debit=round(amt, 2),
            total_credit=round(amt, 2),
            created_by_id=user_id or payment.received_by_id,
            lines=lines,
        )
        db.add(jv)
        await db.flush()
        return jv

    @staticmethod
    async def post_supplier_payment(
        db: AsyncSession,
        tenant_id: int,
        payment,  # SupplierPayment model instance
        user_id: Optional[int] = None,
    ) -> Optional[JournalEntry]:
        """
        Auto-post balanced Journal Voucher for Supplier Adaiygi (CPV).
        Dr. Accounts Payable (Supplier Khata)
        Cr. Cash/Bank (Tender Account)
        """
        settings = await AccountingService.get_tenant_settings(db, tenant_id)
        if not settings.auto_posting_enabled:
            return None

        amt = float(payment.amount or 0.0)
        if amt <= 0:
            return None

        method_map = settings.payment_method_mappings or {}
        pm_key = (payment.payment_method or "cash").lower()
        cash_acc_id = settings.default_cash_account_id
        bank_acc_id = settings.default_bank_account_id or cash_acc_id
        ap_acc_id = settings.default_ap_account_id

        target_tender_acc_id = method_map.get(pm_key) or (cash_acc_id if pm_key == "cash" else bank_acc_id)
        if not target_tender_acc_id or not ap_acc_id:
            return None

        lines = [
            JournalEntryLine(
                account_id=ap_acc_id,
                branch_id=payment.branch_id,
                debit=round(amt, 2),
                credit=0.0,
                narration=f"Supplier liability settled ({payment.voucher_number})",
                supplier_id=payment.supplier_id,
            ),
            JournalEntryLine(
                account_id=target_tender_acc_id,
                branch_id=payment.branch_id,
                debit=0.0,
                credit=round(amt, 2),
                narration=f"Disbursement via {pm_key.upper()} ({payment.voucher_number})",
                supplier_id=payment.supplier_id,
            ),
        ]

        entry_no = await AccountingService.generate_jv_number(db, tenant_id)
        e_date = getattr(payment, "payment_date", None) or getattr(payment, "created_at", None) or datetime.now(timezone.utc)
        jv = JournalEntry(
            tenant_id=tenant_id,
            branch_id=payment.branch_id,
            entry_number=entry_no,
            entry_date=e_date,
            source_type="supplier_payment",
            source_id=payment.id,
            reference_no=payment.voucher_number,
            narration=f"Supplier Payment (CPV): {payment.voucher_number}",
            currency="PKR",
            exchange_rate=1.0,
            status="posted",
            total_debit=round(amt, 2),
            total_credit=round(amt, 2),
            created_by_id=user_id or payment.paid_by_id,
            lines=lines,
        )
        db.add(jv)
        await db.flush()
        return jv

    @staticmethod
    async def post_purchase_invoice(
        db: AsyncSession,
        tenant_id: int,
        purchase,  # Purchase model instance
        user_id: Optional[int] = None,
    ) -> Optional[JournalEntry]:
        """
        Auto-post balanced double-entry Journal Voucher for a Purchase Invoice / Goods Received Note (GRN).
        Dr. Inventory Asset / Stock in Hand (Head 1040) (for merchandise net cost)
        Dr. Input Tax / Sales Tax (Head 2020) (if tax paid on purchase)
        Cr. Accounts Payable / Supplier Khata (Head 2010) (for credit portion / balance due)
        Cr. Cash / Bank (Head 1010 / 1020) (for instant payment made on purchase)
        """
        settings = await AccountingService.get_tenant_settings(db, tenant_id)
        if not settings.auto_posting_enabled:
            return None

        # Resolve accounts from mapping settings (safely guarding Inventory Asset against Cash/Bank)
        inventory_acc_id = await AccountingPostingEngine._resolve_inventory_asset_account_id(db, tenant_id, settings)
        if not inventory_acc_id:
            inventory_acc_id = await AccountingPostingEngine._resolve_cogs_account_id(db, tenant_id, settings)
        ap_acc_id = settings.default_ap_account_id
        tax_acc_id = settings.default_sales_tax_account_id
        cash_acc_id = settings.default_cash_account_id
        bank_acc_id = settings.default_bank_account_id or cash_acc_id

        # Fallbacks to standard account codes
        if not ap_acc_id:
            ap_res = await db.execute(select(Account.id).where(Account.tenant_id == tenant_id, Account.code == "2010"))
            ap_acc_id = ap_res.scalar_one_or_none()
        if not cash_acc_id:
            c_res = await db.execute(select(Account.id).where(Account.tenant_id == tenant_id, Account.code == "1010"))
            cash_acc_id = c_res.scalar_one_or_none()
        if not tax_acc_id:
            t_res = await db.execute(select(Account.id).where(Account.tenant_id == tenant_id, Account.code == "2020"))
            tax_acc_id = t_res.scalar_one_or_none()

        if not inventory_acc_id:
            # Cannot post purchase without an inventory/purchase asset account
            return None

        subtotal = float(purchase.subtotal or 0.0)
        discount = float(purchase.discount_amount or 0.0)
        shipping = float(purchase.shipping_cost or 0.0)
        tax_amt = float(purchase.tax_amount or 0.0)
        paid_amt = float(purchase.paid_amount or 0.0)
        balance_due = float(purchase.balance_due or 0.0)
        final_bill = float(purchase.total_amount or 0.0)

        # Net merchandise valuation into stock (Subtotal - Discount + Freight Inward)
        net_stock_value = max(0.0, round(subtotal - discount + shipping, 2))

        lines: List[JournalEntryLine] = []
        tot_debit = 0.0
        tot_credit = 0.0

        # 1. Debit Inventory Asset (Stock Valuation)
        if net_stock_value > 0:
            lines.append(JournalEntryLine(
                account_id=inventory_acc_id,
                branch_id=purchase.branch_id,
                debit=round(net_stock_value, 2),
                credit=0.0,
                narration=f"Stock received into inventory (Bill: {purchase.invoice_number})",
                supplier_id=purchase.supplier_id,
            ))
            tot_debit += net_stock_value

        # 2. Debit Input Tax / Sales Tax (if applicable)
        if tax_amt > 0 and tax_acc_id:
            lines.append(JournalEntryLine(
                account_id=tax_acc_id,
                branch_id=purchase.branch_id,
                debit=round(tax_amt, 2),
                credit=0.0,
                narration=f"Input sales tax on purchase (Bill: {purchase.invoice_number})",
                supplier_id=purchase.supplier_id,
            ))
            tot_debit += tax_amt

        # 3. Credit Accounts Payable (Supplier Khata) for balance due / credit purchase
        if balance_due > 0 and ap_acc_id:
            lines.append(JournalEntryLine(
                account_id=ap_acc_id,
                branch_id=purchase.branch_id,
                debit=0.0,
                credit=round(balance_due, 2),
                narration=f"Supplier payable balance due (Bill: {purchase.invoice_number})",
                supplier_id=purchase.supplier_id,
            ))
            tot_credit += balance_due

        # 4. Credit Cash / Bank for instant paid amount
        if paid_amt > 0:
            actual_paid = min(paid_amt, final_bill)
            method_map = settings.payment_method_mappings or {}
            # Check if purchase has payment method or default to cash
            pm_key = getattr(purchase, "payment_method", "cash") or "cash"
            target_tender_acc_id = method_map.get(pm_key.lower()) or (cash_acc_id if pm_key.lower() == "cash" else bank_acc_id)

            if target_tender_acc_id and actual_paid > 0:
                lines.append(JournalEntryLine(
                    account_id=target_tender_acc_id,
                    branch_id=purchase.branch_id,
                    debit=0.0,
                    credit=round(actual_paid, 2),
                    narration=f"Instant purchase payment via {pm_key.upper()} (Bill: {purchase.invoice_number})",
                    supplier_id=purchase.supplier_id,
                ))
                tot_credit += actual_paid

        # Double-entry invariant balance adjustment (handle penny roundings)
        diff = round(tot_debit - tot_credit, 2)
        if abs(diff) > 0.00 and abs(diff) <= 0.05:
            for l in lines:
                if l.account_id == inventory_acc_id:
                    l.debit = round(l.debit - diff, 2)
                    tot_debit -= diff
                    break

        tot_debit = round(tot_debit, 2)
        tot_credit = round(tot_credit, 2)

        if abs(tot_debit - tot_credit) > 0.01 or tot_debit <= 0:
            # Cannot post unbalanced or zero-amount voucher
            return None

        entry_no = await AccountingService.generate_jv_number(db, tenant_id)
        p_date = getattr(purchase, "purchase_date", None)
        if isinstance(p_date, datetime):
            e_date = p_date
        elif p_date:
            e_date = datetime(p_date.year, p_date.month, p_date.day, 12, 0, 0, tzinfo=timezone.utc)
        else:
            e_date = datetime.now(timezone.utc)

        ref_str = purchase.invoice_number
        if purchase.supplier_bill_no:
            ref_str += f" (Ref: {purchase.supplier_bill_no})"

        jv = JournalEntry(
            tenant_id=tenant_id,
            branch_id=purchase.branch_id,
            entry_number=entry_no,
            entry_date=e_date,
            source_type="purchase_invoice",
            source_id=purchase.id,
            reference_no=ref_str,
            narration=f"Purchase Bill (GRN): {purchase.invoice_number}",
            currency="PKR",
            exchange_rate=1.0,
            status="posted",
            total_debit=tot_debit,
            total_credit=tot_credit,
            created_by_id=user_id or purchase.created_by_id,
            lines=lines,
        )
        db.add(jv)
        await db.flush()
        return jv

    @staticmethod
    async def post_expense_voucher(
        db: AsyncSession,
        tenant_id: int,
        expense,  # ExpenseVoucher model instance
        user_id: Optional[int] = None,
    ) -> Optional[JournalEntry]:
        """
        Auto-post balanced double-entry Journal Voucher for an operational Expense Voucher (CPV).
        Dr. Operating Expense Account (e.g. 6010 Rent, 6030 Utilities, 6040 Tea, etc.)
        Cr. Cash Drawer / Bank Account (1010 / 1020)
        Enforces strict Double-Entry Invariant (sum(Debit) == sum(Credit)).
        """
        amt = round(float(expense.amount or 0.0), 2)
        if amt <= 0:
            return None

        # Fetch expense account and cash/bank account
        exp_res = await db.execute(
            select(Account).where(Account.id == expense.expense_account_id, Account.tenant_id == tenant_id)
        )
        exp_acc = exp_res.scalars().first()
        if not exp_acc:
            return None

        paid_res = await db.execute(
            select(Account).where(Account.id == expense.paid_from_account_id, Account.tenant_id == tenant_id)
        )
        paid_acc = paid_res.scalars().first()
        if not paid_acc:
            return None

        lines: List[JournalEntryLine] = []

        # 1. Debit Expense Head
        lines.append(JournalEntryLine(
            account_id=exp_acc.id,
            branch_id=expense.branch_id,
            debit=amt,
            credit=0.0,
            narration=f"Expense ({exp_acc.name}): Paid to {expense.payee_name}" + (f" - {expense.narration}" if expense.narration else ""),
        ))

        # 2. Credit Cash / Bank Account
        lines.append(JournalEntryLine(
            account_id=paid_acc.id,
            branch_id=expense.branch_id,
            debit=0.0,
            credit=amt,
            narration=f"Paid via {expense.payment_method.upper()} for {exp_acc.name} to {expense.payee_name}",
        ))

        entry_no = await AccountingService.generate_jv_number(db, tenant_id)
        e_date = expense.expense_date or datetime.now(timezone.utc)

        ref_str = expense.voucher_number
        if expense.reference_no:
            ref_str += f" (Ref: {expense.reference_no})"

        jv = JournalEntry(
            tenant_id=tenant_id,
            branch_id=expense.branch_id,
            entry_number=entry_no,
            entry_date=e_date,
            source_type="expense_voucher",
            source_id=expense.id,
            reference_no=ref_str,
            narration=f"Direct Expense: {exp_acc.name} - {expense.payee_name}",
            currency="PKR",
            exchange_rate=1.0,
            status="posted",
            total_debit=amt,
            total_credit=amt,
            created_by_id=user_id or expense.created_by_id,
            lines=lines,
        )
        db.add(jv)
        await db.flush()

        expense.journal_entry_id = jv.id
        await db.flush()
        return jv

    @staticmethod
    async def post_stock_adjustment(
        db: AsyncSession,
        tenant_id: int,
        adjustment,  # StockAdjustment model instance
        items_in: list,
        user_id: Optional[int] = None,
    ) -> Optional[JournalEntry]:
        """
        Auto-post balanced double-entry Journal Voucher for a Stock Adjustment (IAS-2 Perpetual Inventory).
        - For SUB (Damage, Shrinkage, Expiry): Dr. COGS / Stock Loss (5010), Cr. Merchandise Inventory (1040)
        - For ADD (Audit Surplus, Found Stock): Dr. Merchandise Inventory (1040), Cr. COGS / Stock Recovery (5010)
        """
        settings = await AccountingService.get_tenant_settings(db, tenant_id)
        if not settings.auto_posting_enabled:
            return None

        inventory_acc_id = await AccountingPostingEngine._resolve_inventory_asset_account_id(db, tenant_id, settings)
        cogs_acc_id = await AccountingPostingEngine._resolve_cogs_account_id(db, tenant_id, settings)
        if not inventory_acc_id or not cogs_acc_id:
            return None

        from app.modules.products.models import Product

        add_val = 0.0
        sub_val = 0.0
        for item_in in items_in:
            p_cost = (
                await db.execute(select(Product.cost_price).where(Product.id == item_in.product_id, Product.tenant_id == tenant_id))
            ).scalar_one_or_none()
            cost_price = float(p_cost or 0.0)
            qty = float(item_in.quantity or 0.0)
            if qty <= 0 or cost_price <= 0:
                continue
            val = round(qty * cost_price, 2)
            if item_in.adjustment_type.upper() == "ADD":
                add_val += val
            else:
                sub_val += val

        add_val = round(add_val, 2)
        sub_val = round(sub_val, 2)
        if add_val <= 0 and sub_val <= 0:
            return None

        lines: List[JournalEntryLine] = []
        tot_debit = 0.0
        tot_credit = 0.0

        if sub_val > 0:
            lines.append(JournalEntryLine(
                account_id=cogs_acc_id,
                branch_id=adjustment.branch_id,
                debit=sub_val,
                credit=0.0,
                narration=f"Stock shrinkage/damage expense ({adjustment.adjustment_number}: {adjustment.reason})",
            ))
            lines.append(JournalEntryLine(
                account_id=inventory_acc_id,
                branch_id=adjustment.branch_id,
                debit=0.0,
                credit=sub_val,
                narration=f"Inventory reduced due to {adjustment.reason} ({adjustment.adjustment_number})",
            ))
            tot_debit += sub_val
            tot_credit += sub_val

        if add_val > 0:
            lines.append(JournalEntryLine(
                account_id=inventory_acc_id,
                branch_id=adjustment.branch_id,
                debit=add_val,
                credit=0.0,
                narration=f"Inventory increased via audit/adjustment ({adjustment.adjustment_number}: {adjustment.reason})",
            ))
            lines.append(JournalEntryLine(
                account_id=cogs_acc_id,
                branch_id=adjustment.branch_id,
                debit=0.0,
                credit=add_val,
                narration=f"COGS offset from positive stock adjustment ({adjustment.adjustment_number})",
            ))
            tot_debit += add_val
            tot_credit += add_val

        tot_debit = round(tot_debit, 2)
        tot_credit = round(tot_credit, 2)

        entry_no = await AccountingService.generate_jv_number(db, tenant_id)
        adj_date = getattr(adjustment, "adjustment_date", None)
        if isinstance(adj_date, datetime):
            e_date = adj_date
        elif adj_date:
            e_date = datetime(adj_date.year, adj_date.month, adj_date.day, 12, 0, 0, tzinfo=timezone.utc)
        else:
            e_date = datetime.now(timezone.utc)

        jv = JournalEntry(
            tenant_id=tenant_id,
            branch_id=adjustment.branch_id,
            entry_number=entry_no,
            entry_date=e_date,
            source_type="stock_adjustment",
            source_id=adjustment.id,
            reference_no=adjustment.adjustment_number,
            narration=f"Stock Adjustment ({adjustment.reason}): {adjustment.adjustment_number}",
            currency="PKR",
            exchange_rate=1.0,
            status="posted",
            total_debit=tot_debit,
            total_credit=tot_credit,
            created_by_id=user_id or adjustment.created_by_id,
            lines=lines,
        )
        db.add(jv)
        await db.flush()
        return jv

    @staticmethod
    async def post_sales_return(
        db: AsyncSession,
        tenant_id: int,
        invoice,  # SalesInvoice model instance
        user_id: Optional[int] = None,
        reason: Optional[str] = None,
    ) -> Optional[JournalEntry]:
        """
        Auto-post balanced Credit Note / Sales Return Journal Voucher (IFRS / IAS-2 Perpetual Inventory).
        1. Revenue & Tender Reversal Side:
           - Dr. Sales Revenue (4010) (reversing gross/net sales)
           - Cr. Sales Discounts Allowed (4020) (if discount was granted)
           - Dr. Sales Tax Payable (2020) (reversing output tax)
           - Cr. Cash/Bank (1010/1020) (for cash/tender refunded to buyer)
           - Cr. Accounts Receivable (1030) (for credit balance due cancelled)
        2. Perpetual Inventory Return & COGS Reversal Side:
           - Dr. Merchandise Inventory Asset (1040) (restoring returned stock value)
           - Cr. Cost of Goods Sold - COGS (5010) (reducing COGS expense)
        """
        settings = await AccountingService.get_tenant_settings(db, tenant_id)
        if not settings.auto_posting_enabled:
            return None

        # Prevent duplicate sales_return JV for the same invoice
        existing_res = await db.execute(
            select(JournalEntry).where(
                JournalEntry.tenant_id == tenant_id,
                JournalEntry.source_type == "sales_return",
                JournalEntry.source_id == invoice.id,
                JournalEntry.status == "posted",
            )
        )
        existing_jv = existing_res.scalars().first()
        if existing_jv:
            return existing_jv

        sales_acc_id = settings.default_sales_income_account_id
        discount_acc_id = settings.default_discount_account_id
        ar_acc_id = settings.default_ar_account_id
        tax_acc_id = settings.default_sales_tax_account_id
        cash_acc_id = settings.default_cash_account_id
        bank_acc_id = settings.default_bank_account_id or cash_acc_id
        cogs_acc_id = await AccountingPostingEngine._resolve_cogs_account_id(db, tenant_id, settings)
        inventory_acc_id = await AccountingPostingEngine._resolve_inventory_asset_account_id(db, tenant_id, settings)

        if not sales_acc_id:
            s_res = await db.execute(select(Account.id).where(Account.tenant_id == tenant_id, Account.code == "4010"))
            sales_acc_id = s_res.scalar_one_or_none()
        if not discount_acc_id:
            d_res = await db.execute(select(Account.id).where(Account.tenant_id == tenant_id, Account.code == "4020"))
            discount_acc_id = d_res.scalar_one_or_none()
        if not ar_acc_id:
            ar_res = await db.execute(select(Account.id).where(Account.tenant_id == tenant_id, Account.code == "1030"))
            ar_acc_id = ar_res.scalar_one_or_none()
        if not cash_acc_id:
            c_res = await db.execute(select(Account.id).where(Account.tenant_id == tenant_id, Account.code == "1010"))
            cash_acc_id = c_res.scalar_one_or_none()
        if not tax_acc_id:
            t_res = await db.execute(select(Account.id).where(Account.tenant_id == tenant_id, Account.code == "2020"))
            tax_acc_id = t_res.scalar_one_or_none()

        if not sales_acc_id:
            return None

        lines: List[JournalEntryLine] = []
        tot_debit = 0.0
        tot_credit = 0.0

        # 1. Reverse Sales Revenue & Sales Discounts
        subtotal = round(float(invoice.subtotal or 0.0), 2)
        discount = round(float(invoice.discount_amount or 0.0), 2)
        net_sales = max(0.0, round(subtotal - discount, 2))

        if discount > 0 and discount_acc_id and subtotal >= discount:
            lines.append(JournalEntryLine(
                account_id=sales_acc_id,
                branch_id=invoice.branch_id,
                debit=subtotal,
                credit=0.0,
                narration=f"Sales revenue reversed on return (Inv: {invoice.invoice_number})",
                customer_id=invoice.customer_id,
            ))
            tot_debit += subtotal

            lines.append(JournalEntryLine(
                account_id=discount_acc_id,
                branch_id=invoice.branch_id,
                debit=0.0,
                credit=discount,
                narration=f"Sales discount reversed on return (Inv: {invoice.invoice_number})",
                customer_id=invoice.customer_id,
            ))
            tot_credit += discount
        elif net_sales > 0:
            lines.append(JournalEntryLine(
                account_id=sales_acc_id,
                branch_id=invoice.branch_id,
                debit=net_sales,
                credit=0.0,
                narration=f"Sales revenue reversed on return (Inv: {invoice.invoice_number})",
                customer_id=invoice.customer_id,
            ))
            tot_debit += net_sales

        # 2. Reverse Sales Tax Payable (Output Tax)
        tax_amt = round(float(invoice.tax_amount or 0.0), 2)
        if tax_amt > 0 and tax_acc_id:
            lines.append(JournalEntryLine(
                account_id=tax_acc_id,
                branch_id=invoice.branch_id,
                debit=tax_amt,
                credit=0.0,
                narration=f"Output sales tax reversed on return (Inv: {invoice.invoice_number})",
                customer_id=invoice.customer_id,
            ))
            tot_debit += tax_amt

        # 3. Credit Cash / Bank for Refunded Tender
        method_map = settings.payment_method_mappings or {}
        paid_amt = float(invoice.paid_amount or 0.0)
        final_bill = float(invoice.total_amount or 0.0)
        balance_due = float(invoice.balance_due or 0.0)

        payments = getattr(invoice, "payments", [])
        if payments and len(payments) > 0:
            for pmt in payments:
                p_amt = float(pmt.amount or 0.0)
                if p_amt <= 0:
                    continue
                pm_key = (pmt.payment_method or "cash").lower()
                target_acc_id = method_map.get(pm_key) or (cash_acc_id if pm_key == "cash" else bank_acc_id)
                if target_acc_id:
                    lines.append(JournalEntryLine(
                        account_id=target_acc_id,
                        branch_id=invoice.branch_id,
                        debit=0.0,
                        credit=round(p_amt, 2),
                        narration=f"Payment refunded via {pm_key.upper()} (Inv: {invoice.invoice_number})",
                        customer_id=invoice.customer_id,
                    ))
                    tot_credit += p_amt
        elif paid_amt > 0:
            pm_key = (invoice.payment_method or "cash").lower()
            target_acc_id = method_map.get(pm_key) or (cash_acc_id if pm_key == "cash" else bank_acc_id)
            actual_paid = min(paid_amt, final_bill)
            if target_acc_id and actual_paid > 0:
                lines.append(JournalEntryLine(
                    account_id=target_acc_id,
                    branch_id=invoice.branch_id,
                    debit=0.0,
                    credit=round(actual_paid, 2),
                    narration=f"Payment refunded via {pm_key.upper()} (Inv: {invoice.invoice_number})",
                    customer_id=invoice.customer_id,
                ))
                tot_credit += actual_paid

        # 4. Credit Accounts Receivable (Customer Khata) for credit balance reversed
        if balance_due > 0 and ar_acc_id:
            lines.append(JournalEntryLine(
                account_id=ar_acc_id,
                branch_id=invoice.branch_id,
                debit=0.0,
                credit=round(balance_due, 2),
                narration=f"Customer receivable credited on return (Inv: {invoice.invoice_number})",
                customer_id=invoice.customer_id,
            ))
            tot_credit += balance_due

        # Penny rounding invariant check on Revenue/Tender side
        diff = round(tot_debit - tot_credit, 2)
        if abs(diff) > 0.00 and abs(diff) <= 0.05:
            for l in lines:
                if l.account_id == sales_acc_id:
                    l.debit = round(l.debit - diff, 2)
                    tot_debit -= diff
                    break

        # 5. Perpetual Inventory Return & COGS Reversal (IAS-2)
        total_cogs = 0.0
        inv_items = getattr(invoice, "items", []) or []
        for item in inv_items:
            qty = float(getattr(item, "quantity", 0.0) or 0.0)
            c_price = float(getattr(item, "cost_price", 0.0) or 0.0)
            if c_price <= 0 and getattr(item, "product_id", None):
                from app.modules.products.models import Product
                p_cost = (
                    await db.execute(select(Product.cost_price).where(Product.id == item.product_id))
                ).scalar_one_or_none()
                c_price = float(p_cost or 0.0)
            if qty > 0 and c_price > 0:
                total_cogs += round(qty * c_price, 2)

        total_cogs = round(total_cogs, 2)
        if total_cogs > 0 and cogs_acc_id and inventory_acc_id:
            # Dr. Merchandise Inventory Asset (1040)
            lines.append(JournalEntryLine(
                account_id=inventory_acc_id,
                branch_id=invoice.branch_id,
                debit=total_cogs,
                credit=0.0,
                narration=f"Inventory stock restored on sales return (Inv: {invoice.invoice_number})",
                customer_id=invoice.customer_id,
            ))
            # Cr. Cost of Goods Sold (5010)
            lines.append(JournalEntryLine(
                account_id=cogs_acc_id,
                branch_id=invoice.branch_id,
                debit=0.0,
                credit=total_cogs,
                narration=f"COGS reversed on sales return (Inv: {invoice.invoice_number})",
                customer_id=invoice.customer_id,
            ))
            tot_debit += total_cogs
            tot_credit += total_cogs

        tot_debit = round(tot_debit, 2)
        tot_credit = round(tot_credit, 2)

        if abs(tot_debit - tot_credit) > 0.01 or tot_debit <= 0:
            return None

        entry_no = await AccountingService.generate_jv_number(db, tenant_id)
        ref_no = f"CN-{invoice.invoice_number}" if getattr(invoice, "status", "") == "refunded" else invoice.invoice_number
        narr = f"Sales Return / Credit Note: {invoice.invoice_number} ({invoice.customer_name or 'Walk-in'})"
        if reason:
            narr += f" - Reason: {reason}"

        jv = JournalEntry(
            tenant_id=tenant_id,
            branch_id=invoice.branch_id,
            entry_number=entry_no,
            entry_date=datetime.now(timezone.utc),
            source_type="sales_return",
            source_id=invoice.id,
            reference_no=ref_no,
            narration=narr,
            currency="PKR",
            exchange_rate=1.0,
            status="posted",
            total_debit=tot_debit,
            total_credit=tot_credit,
            created_by_id=user_id or invoice.created_by_id,
            lines=lines,
        )
        db.add(jv)
        await db.flush()
        return jv

    @staticmethod
    async def post_purchase_return(
        db: AsyncSession,
        tenant_id: int,
        purchase,  # Purchase model instance
        user_id: Optional[int] = None,
        reason: Optional[str] = None,
        refund_payment_method: Optional[str] = None,
    ) -> Optional[JournalEntry]:
        """
        Auto-post balanced Debit Note / Purchase Return Journal Voucher (IFRS / IAS-2 Perpetual Inventory).
        Reverses the original purchase invoice:
        - Dr. Accounts Payable (2010) (for unpaid balance due relieved)
        - Dr. Cash Drawer / Bank (1010/1020) (if cash/bank refund received for paid amount)
          OR Dr. Accounts Payable (2010) (if paid amount is kept as credit balance on supplier khata)
        - Cr. Merchandise Inventory Asset (1040) (net merchandise cost returned)
        - Cr. Input Tax / Sales Tax (2020) (if tax was paid on purchase and reversed)
        """
        settings = await AccountingService.get_tenant_settings(db, tenant_id)
        if not settings.auto_posting_enabled:
            return None

        # Check existing posted purchase_return JV to avoid duplication
        existing_res = await db.execute(
            select(JournalEntry).where(
                JournalEntry.tenant_id == tenant_id,
                JournalEntry.source_type == "purchase_return",
                JournalEntry.source_id == purchase.id,
                JournalEntry.status == "posted",
            )
        )
        existing_jv = existing_res.scalars().first()
        if existing_jv:
            return existing_jv

        inventory_acc_id = await AccountingPostingEngine._resolve_inventory_asset_account_id(db, tenant_id, settings)
        ap_acc_id = settings.default_ap_account_id
        tax_acc_id = settings.default_sales_tax_account_id
        cash_acc_id = settings.default_cash_account_id
        bank_acc_id = settings.default_bank_account_id or cash_acc_id

        if not ap_acc_id:
            ap_res = await db.execute(select(Account.id).where(Account.tenant_id == tenant_id, Account.code == "2010"))
            ap_acc_id = ap_res.scalar_one_or_none()
        if not cash_acc_id:
            c_res = await db.execute(select(Account.id).where(Account.tenant_id == tenant_id, Account.code == "1010"))
            cash_acc_id = c_res.scalar_one_or_none()
        if not tax_acc_id:
            t_res = await db.execute(select(Account.id).where(Account.tenant_id == tenant_id, Account.code == "2020"))
            tax_acc_id = t_res.scalar_one_or_none()

        if not inventory_acc_id or not ap_acc_id:
            return None

        subtotal = float(purchase.subtotal or 0.0)
        discount = float(purchase.discount_amount or 0.0)
        shipping = float(purchase.shipping_cost or 0.0)
        tax_amt = float(purchase.tax_amount or 0.0)
        paid_amt = float(purchase.paid_amount or 0.0)
        balance_due = float(purchase.balance_due or 0.0)
        final_bill = float(purchase.total_amount or 0.0)

        net_stock_value = max(0.0, round(subtotal - discount + shipping, 2))

        lines: List[JournalEntryLine] = []
        tot_debit = 0.0
        tot_credit = 0.0

        # 1. Debit Accounts Payable (Supplier Khata) for balance due being cancelled
        if balance_due > 0 and ap_acc_id:
            lines.append(JournalEntryLine(
                account_id=ap_acc_id,
                branch_id=purchase.branch_id,
                debit=round(balance_due, 2),
                credit=0.0,
                narration=f"Supplier payable debited on return (DN: {purchase.invoice_number})",
                supplier_id=purchase.supplier_id,
            ))
            tot_debit += balance_due

        # 2. Paid amount handling
        if paid_amt > 0:
            actual_paid = min(paid_amt, final_bill)
            method_map = settings.payment_method_mappings or {}
            pm_key = (refund_payment_method or getattr(purchase, "payment_method", "cash") or "cash").lower()

            if pm_key in ("cash", "bank", "bank_transfer", "card", "raast"):
                target_tender_acc_id = method_map.get(pm_key) or (cash_acc_id if pm_key == "cash" else bank_acc_id)
                lines.append(JournalEntryLine(
                    account_id=target_tender_acc_id,
                    branch_id=purchase.branch_id,
                    debit=round(actual_paid, 2),
                    credit=0.0,
                    narration=f"Refund received from supplier via {pm_key.upper()} (DN: {purchase.invoice_number})",
                    supplier_id=purchase.supplier_id,
                ))
                tot_debit += actual_paid
            else:
                # Credit on supplier khata (reduces AP / creates advance debit balance)
                lines.append(JournalEntryLine(
                    account_id=ap_acc_id,
                    branch_id=purchase.branch_id,
                    debit=round(actual_paid, 2),
                    credit=0.0,
                    narration=f"Supplier khata credited for return (DN: {purchase.invoice_number})",
                    supplier_id=purchase.supplier_id,
                ))
                tot_debit += actual_paid

        # 3. Credit Merchandise Inventory Asset (relieving stock value)
        if net_stock_value > 0:
            lines.append(JournalEntryLine(
                account_id=inventory_acc_id,
                branch_id=purchase.branch_id,
                debit=0.0,
                credit=round(net_stock_value, 2),
                narration=f"Inventory relieved on purchase return (DN: {purchase.invoice_number})",
                supplier_id=purchase.supplier_id,
            ))
            tot_credit += net_stock_value

        # 4. Credit Input Tax (if tax was reversed)
        if tax_amt > 0 and tax_acc_id:
            lines.append(JournalEntryLine(
                account_id=tax_acc_id,
                branch_id=purchase.branch_id,
                debit=0.0,
                credit=round(tax_amt, 2),
                narration=f"Input tax reversed on purchase return (DN: {purchase.invoice_number})",
                supplier_id=purchase.supplier_id,
            ))
            tot_credit += tax_amt

        # Invariant check penny rounding
        diff = round(tot_debit - tot_credit, 2)
        if abs(diff) > 0.00 and abs(diff) <= 0.05:
            for l in lines:
                if l.account_id == inventory_acc_id:
                    l.credit = round(l.credit + diff, 2)
                    tot_credit += diff
                    break

        tot_debit = round(tot_debit, 2)
        tot_credit = round(tot_credit, 2)

        if abs(tot_debit - tot_credit) > 0.01 or tot_debit <= 0:
            return None

        entry_no = await AccountingService.generate_jv_number(db, tenant_id)
        ref_no = f"DN-{purchase.invoice_number}"
        narr = f"Purchase Return / Debit Note: {purchase.invoice_number}"
        if purchase.supplier_bill_no:
            narr += f" (Ref: {purchase.supplier_bill_no})"
        if reason:
            narr += f" - Reason: {reason}"

        jv = JournalEntry(
            tenant_id=tenant_id,
            branch_id=purchase.branch_id,
            entry_number=entry_no,
            entry_date=datetime.now(timezone.utc),
            source_type="purchase_return",
            source_id=purchase.id,
            reference_no=ref_no,
            narration=narr,
            currency="PKR",
            exchange_rate=1.0,
            status="posted",
            total_debit=tot_debit,
            total_credit=tot_credit,
            created_by_id=user_id or purchase.created_by_id,
            lines=lines,
        )
        db.add(jv)
        await db.flush()
        return jv

    @staticmethod
    async def void_source_voucher(
        db: AsyncSession,
        tenant_id: int,
        source_type: str,
        source_id: int,
        reason: Optional[str] = None,
    ) -> int:
        """
        Void/Cancel any posted JournalEntry linked to a deleted or cancelled source document
        (e.g., purchase_invoice, customer_payment, supplier_payment).
        """
        stmt = select(JournalEntry).where(
            JournalEntry.tenant_id == tenant_id,
            JournalEntry.source_type == source_type,
            JournalEntry.source_id == source_id,
            JournalEntry.status == "posted",
        )
        res = await db.execute(stmt)
        vouchers = res.scalars().all()
        count = 0
        for jv in vouchers:
            jv.status = "cancelled"
            if reason:
                jv.narration = (jv.narration or "") + f" [VOIDED: {reason}]"
            count += 1
        if count > 0:
            await db.flush()
        return count




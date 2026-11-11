"""Seed realistic dummy business transactions for Tenant 5 (Business 1 - Zaeem Asif)."""
import asyncio
from datetime import datetime, timezone, date
from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.modules.auth.models import User, Tenant
from app.modules.branches.models import Branch
from app.modules.parties.models import Customer, Supplier
from app.modules.products.models import Product
from app.modules.accounting.models import Account, TenantAccountingSettings, JournalEntry
from app.modules.accounting.services import AccountingService
from app.modules.accounting.schemas import JournalEntryCreate, JournalEntryLineCreate
from app.modules.inventory.schemas import PurchaseCreate, PurchaseItemCreate
from app.modules.inventory.services import PurchaseService
from app.modules.sales.schemas import SalesCheckoutRequest, SalesInvoiceItemCreate, SalesPaymentCreate
from app.modules.sales.services import SalesService
from app.modules.parties.schemas import CustomerPaymentCreate, SupplierPaymentCreate
from app.modules.parties.services import CustomerPaymentService, SupplierPaymentService


async def seed_scenario(tenant_id: int = 5):
    print(f"=== Seeding Realistic Business Scenario for Tenant {tenant_id} ===")
    async with AsyncSessionLocal() as db:
        # 1. Fetch Tenant Context
        t_res = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
        tenant = t_res.scalar_one_or_none()
        if not tenant:
            print(f"Tenant {tenant_id} not found!")
            return

        u_res = await db.execute(select(User).where(User.id == 5))
        user = u_res.scalar_one_or_none() or (await db.execute(select(User).limit(1))).scalars().first()

        b_res = await db.execute(select(Branch).where(Branch.tenant_id == tenant_id).limit(1))
        branch = b_res.scalars().first()

        print(f"Business: {tenant.name} | User: {user.full_name} | Branch: {branch.name}")

        # Ensure Settings are populated
        settings = await AccountingService.get_tenant_settings(db, tenant_id)
        settings.auto_posting_enabled = True
        await db.commit()

        # Fetch COA Accounts
        acc_stmt = select(Account).where(Account.tenant_id == tenant_id)
        acc_res = await db.execute(acc_stmt)
        accounts_by_code = {a.code: a for a in acc_res.scalars().all()}

        cash_acc = accounts_by_code.get("1010")
        bank_acc = accounts_by_code.get("1020")
        ar_acc = accounts_by_code.get("1030")
        inv_acc = accounts_by_code.get("1040")
        ap_acc = accounts_by_code.get("2010")
        equity_acc = accounts_by_code.get("3010")
        sales_acc = accounts_by_code.get("4010")

        # -------------------------------------------------------------
        # 1. Owner Capital Injection (Manual JV)
        # -------------------------------------------------------------
        print("\n1. Posting Initial Owner Capital Injection JV...")
        jv_capital = JournalEntryCreate(
            branch_id=branch.id,
            entry_date=datetime.now(timezone.utc).date().isoformat(),
            reference_no="CAPITAL-INJECT-01",
            narration="Initial Equity & Working Capital Injection by Owner Zaeem Asif",
            lines=[
                JournalEntryLineCreate(
                    account_id=bank_acc.id,
                    branch_id=branch.id,
                    debit=250000.0,
                    credit=0.0,
                    narration="Capital deposited in Main Bank Account",
                ),
                JournalEntryLineCreate(
                    account_id=cash_acc.id,
                    branch_id=branch.id,
                    debit=50000.0,
                    credit=0.0,
                    narration="Opening Till Cash in Counter Drawer",
                ),
                JournalEntryLineCreate(
                    account_id=equity_acc.id,
                    branch_id=branch.id,
                    debit=0.0,
                    credit=300000.0,
                    narration="Owner Capital Investment",
                ),
            ],
        )
        posted_cap = await AccountingService.create_journal_entry(
            db, tenant_id, user.id, jv_capital, source_type="manual_jv"
        )
        print(f"   [✓] Capital JV Posted: {posted_cap.entry_number} (Total: PKR {posted_cap.total_debit:,.2f})")

        # -------------------------------------------------------------
        # 2. Purchase Bills (Stock Receiving from Suppliers)
        # -------------------------------------------------------------
        print("\n2. Creating Purchase Invoices (GRN)...")
        # Find Supplier 1 & Product 1
        s1_res = await db.execute(select(Supplier).where(Supplier.tenant_id == tenant_id, Supplier.company_name.ilike("%Shan%")).limit(1))
        supplier_shan = s1_res.scalars().first() or (await db.execute(select(Supplier).where(Supplier.tenant_id == tenant_id).limit(1))).scalars().first()

        p1_res = await db.execute(select(Product).where(Product.tenant_id == tenant_id, Product.name.ilike("%Masala%")).limit(1))
        product_masala = p1_res.scalars().first() or (await db.execute(select(Product).where(Product.tenant_id == tenant_id).limit(1))).scalars().first()

        # Purchase 1: Shan Foods (Total: PKR 8,500, Paid: PKR 3,500, Udhar: PKR 5,000)
        p1_payload = PurchaseCreate(
            branch_id=branch.id,
            supplier_id=supplier_shan.id,
            supplier_bill_no="INV-SHAN-4411",
            purchase_date=date.today(),
            items=[
                PurchaseItemCreate(
                    product_id=product_masala.id,
                    unit_name="Piece",
                    quantity=100,
                    conversion_factor=1.0,
                    unit_cost=90.0,
                )
            ],
            discount_amount=500.0,
            tax_amount=0.0,
            shipping_cost=0.0,
            paid_amount=3500.0,
            notes="Bulk masala supply for main counter",
        )
        pur1 = await PurchaseService.create_purchase(db, tenant_id, user.id, p1_payload)
        print(f"   [✓] Purchase 1 Created: {pur1.invoice_number} from {supplier_shan.company_name} (Total: PKR {pur1.total_amount:,.2f})")

        # Purchase 2: Dalda Foods (Total: PKR 50,000, Paid: PKR 20,000 via Bank, Udhar: PKR 30,000)
        s2_res = await db.execute(select(Supplier).where(Supplier.tenant_id == tenant_id, Supplier.company_name.ilike("%Dalda%")).limit(1))
        supplier_dalda = s2_res.scalars().first() or supplier_shan

        p2_res = await db.execute(select(Product).where(Product.tenant_id == tenant_id, Product.name.ilike("%Oil%")).limit(1))
        product_oil = p2_res.scalars().first() or product_masala

        p2_payload = PurchaseCreate(
            branch_id=branch.id,
            supplier_id=supplier_dalda.id,
            supplier_bill_no="BIL-DALDA-902",
            purchase_date=date.today(),
            items=[
                PurchaseItemCreate(
                    product_id=product_oil.id,
                    unit_name="Can",
                    quantity=20,
                    conversion_factor=1.0,
                    unit_cost=2500.0,
                )
            ],
            discount_amount=0.0,
            tax_amount=0.0,
            shipping_cost=0.0,
            paid_amount=20000.0,
            notes="Weekly cooking oil inventory shipment",
        )
        pur2 = await PurchaseService.create_purchase(db, tenant_id, user.id, p2_payload)
        print(f"   [✓] Purchase 2 Created: {pur2.invoice_number} from {supplier_dalda.company_name} (Total: PKR {pur2.total_amount:,.2f})")

        # -------------------------------------------------------------
        # 3. Sales Invoices (POS Counter & Wholesale)
        # -------------------------------------------------------------
        print("\n3. Posting Sales Invoices...")
        # Sale 1: Walk-in Cash Buyer
        sale1_payload = SalesCheckoutRequest(
            branch_id=branch.id,
            customer_name="Walk-in Retail Shopper",
            sale_type="pos_retail",
            paid_amount=2550.0,
            payment_method="cash",
            items=[
                SalesInvoiceItemCreate(
                    product_id=product_masala.id,
                    quantity=10,
                    unit_price=135.0,
                ),
                SalesInvoiceItemCreate(
                    product_id=product_oil.id,
                    quantity=1,
                    unit_price=1200.0,
                ),
            ],
            discount_amount=0.0,
            notes="Cash counter checkout",
        )
        inv1 = await SalesService.checkout(db, tenant_id, user.id, sale1_payload)
        print(f"   [✓] Sale 1 (Walk-in Cash) Created: {inv1.invoice_number} (PKR {inv1.total_amount:,.2f})")

        # Sale 2: Credit Sale to Regular Customer (Madina General Store)
        c_res = await db.execute(select(Customer).where(Customer.tenant_id == tenant_id).limit(1))
        customer_madina = c_res.scalars().first()

        sale2_payload = SalesCheckoutRequest(
            branch_id=branch.id,
            customer_id=customer_madina.id,
            customer_name=customer_madina.business_name,
            customer_phone=customer_madina.phone,
            sale_type="wholesale_invoice",
            paid_amount=5500.0,
            payment_method="card",
            items=[
                SalesInvoiceItemCreate(
                    product_id=product_masala.id,
                    quantity=50,
                    unit_price=110.0,
                ),
                SalesInvoiceItemCreate(
                    product_id=product_oil.id,
                    quantity=5,
                    unit_price=3000.0,
                ),
            ],
            discount_amount=0.0,
            notes="Wholesale shipment on 15 days credit terms",
        )
        inv2 = await SalesService.checkout(db, tenant_id, user.id, sale2_payload)
        print(f"   [✓] Sale 2 (Credit Sale to {customer_madina.business_name}) Created: {inv2.invoice_number} (Total: PKR {inv2.total_amount:,.2f}, Due: PKR {inv2.balance_due:,.2f})")

        # -------------------------------------------------------------
        # 4. Customer Wasooli (Cash Receipt Voucher - CRV)
        # -------------------------------------------------------------
        print("\n4. Recording Customer Wasooli (CRV)...")
        crv_payload = CustomerPaymentCreate(
            amount=8000.0,
            payment_method="cash",
            branch_id=branch.id,
            reference_number="CRV-RECEIPT-01",
            notes=f"Cash received against ledger from {customer_madina.business_name}",
        )
        crv = await CustomerPaymentService.record_payment(db, tenant_id, customer_madina.id, crv_payload, user.id)
        print(f"   [✓] Wasooli Recorded: {crv.voucher_number} (PKR {crv.amount:,.2f}) from {customer_madina.business_name}")

        # -------------------------------------------------------------
        # 5. Supplier Payment (Cash Payment Voucher - CPV)
        # -------------------------------------------------------------
        print("\n5. Recording Supplier Payment (CPV)...")
        cpv_payload = SupplierPaymentCreate(
            amount=4000.0,
            payment_method="cash",
            branch_id=branch.id,
            reference_number="CPV-DISBURSE-01",
            notes=f"Cash payment to {supplier_shan.company_name} towards bill {pur1.invoice_number}",
        )
        cpv = await SupplierPaymentService.record_payment(db, tenant_id, supplier_shan.id, cpv_payload, user.id)
        print(f"   [✓] Supplier Payment Recorded: {cpv.voucher_number} (PKR {cpv.amount:,.2f}) to {supplier_shan.company_name}")

        # -------------------------------------------------------------
        # 6. Audit & Equilibrium Verification
        # -------------------------------------------------------------
        print("\n=== Final Double-Entry Financial Equilibrium Verification ===")
        tb = await AccountingService.get_trial_balance(db, tenant_id)
        print(f"Total Debits : PKR {tb.total_debits:,.2f}")
        print(f"Total Credits: PKR {tb.total_credits:,.2f}")
        print(f"Balanced?    : {tb.is_balanced}")
        print("\nActive Ledger Balances:")
        for item in tb.items:
            if item.debit_balance > 0 or item.credit_balance > 0:
                dir_str = f"Dr PKR {item.debit_balance:,.2f}" if item.debit_balance > 0 else f"Cr PKR {item.credit_balance:,.2f}"
                print(f"  • [{item.account_code}] {item.account_name:<36}: {dir_str}")


if __name__ == "__main__":
    asyncio.run(seed_scenario(tenant_id=5))

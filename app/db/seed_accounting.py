"""
Master Seeder for Enterprise Double-Entry Accounting.
Provisions clean basic Chart of Accounts (COA) and TenantAccountingSettings for all tenants.
Also registers 'accounting:*' permissions.
"""
import asyncio
from datetime import datetime, timezone
from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.modules.auth.models import (
    Tenant,
    Permission,
    Role,
    RolePermission,
)
from app.modules.accounting.models import (
    Account,
    TenantAccountingSettings,
)

BASIC_COA_TEMPLATE = [
    # 1. ASSETS
    {"code": "1010", "name": "Cash Drawer / Counter Cash", "account_type": "asset", "sub_type": "cash", "is_system": True, "description": "Physical cash in register counter drawers"},
    {"code": "1020", "name": "Main Bank Account", "account_type": "asset", "sub_type": "bank", "is_system": True, "description": "Primary operating bank account"},
    {"code": "1030", "name": "Accounts Receivable (Customer Khata)", "account_type": "asset", "sub_type": "receivable", "is_system": True, "description": "Outstanding trade balances owed by credit customers"},
    {"code": "1040", "name": "Merchandise Inventory (Stock)", "account_type": "asset", "sub_type": "current_asset", "is_system": True, "description": "Valuation of live stock and goods available for sale"},

    # 2. LIABILITIES
    {"code": "2010", "name": "Accounts Payable (Supplier Khata)", "account_type": "liability", "sub_type": "payable", "is_system": True, "description": "Trade balances owed to vendors and mills"},
    {"code": "2020", "name": "Sales Tax / FBR Output Payable", "account_type": "liability", "sub_type": "tax", "is_system": True, "description": "Sales tax charged on invoices to be paid to FBR/PRA"},

    # 3. EQUITY
    {"code": "3010", "name": "Owner's Capital / Investment", "account_type": "equity", "sub_type": "equity", "is_system": True, "description": "Initial capital and investments into the business"},
    {"code": "3020", "name": "Retained Earnings", "account_type": "equity", "sub_type": "equity", "is_system": True, "description": "Accumulated net profits of past accounting periods"},

    # 4. REVENUE
    {"code": "4010", "name": "Sales Revenue (Gross)", "account_type": "revenue", "sub_type": "operating_revenue", "is_system": True, "description": "Gross sales turnover from products and merchandise"},
    {"code": "4020", "name": "Sales Discounts Allowed", "account_type": "revenue", "sub_type": "operating_revenue", "is_system": True, "description": "Discounts given to customers at checkout (Contra-revenue)"},

    # 5. COST OF GOODS SOLD
    {"code": "5010", "name": "Cost of Goods Sold (COGS)", "account_type": "expense", "sub_type": "cogs", "is_system": True, "description": "Purchase cost of merchandise sold to buyers"},

    # 6. OPERATING EXPENSES (AKHRAJAAT)
    {"code": "6010", "name": "Shop Rent Expense", "account_type": "expense", "sub_type": "operating_expense", "is_system": True, "description": "Premises and warehouse rental charges"},
    {"code": "6020", "name": "Staff Salaries & Wages", "account_type": "expense", "sub_type": "operating_expense", "is_system": True, "description": "Monthly and daily employee compensation"},
    {"code": "6030", "name": "Electricity & Utility Bills", "account_type": "expense", "sub_type": "operating_expense", "is_system": True, "description": "WAPDA/K-Electric, gas, water, and internet bills"},
    {"code": "6040", "name": "Tea, Food & Refreshment", "account_type": "expense", "sub_type": "operating_expense", "is_system": True, "description": "Daily staff tea, food, and customer hospitality"},
    {"code": "6050", "name": "Freight & Delivery Charges", "account_type": "expense", "sub_type": "operating_expense", "is_system": True, "description": "Transport, cargo, courier, and carriage charges"},
    {"code": "6060", "name": "Repairs & Maintenance", "account_type": "expense", "sub_type": "operating_expense", "is_system": True, "description": "Shop, vehicle, machinery, and equipment repairs"},
    {"code": "6090", "name": "General & Miscellaneous Expenses", "account_type": "expense", "sub_type": "operating_expense", "is_system": True, "description": "Other petty operational and sundry expenses"},
]

ACCOUNTING_PERMISSIONS = [
    # Legacy / Bundle
    {
        "module": "accounting",
        "code": "accounting:view",
        "name": "View Accounts & Financial Statements",
        "description": "View Chart of Accounts, General Ledger, and Trial Balance",
    },
    {
        "module": "accounting",
        "code": "accounting:manage",
        "name": "Manage Accounts & Mappings",
        "description": "Create custom COA accounts and configure default posting mappings",
    },
    {
        "module": "accounting",
        "code": "accounting:post",
        "name": "Post Manual Journal Vouchers",
        "description": "Create and post manual debit/credit Journal Vouchers (JVs)",
    },

    # 1. Account Mappings (The 1 Screen)
    {
        "module": "accounting",
        "code": "accounting:mappings:view",
        "name": "View Account Mappings",
        "description": "View default COA posting accounts for sales, receipts, and payments",
    },
    {
        "module": "accounting",
        "code": "accounting:mappings:manage",
        "name": "Manage Account Mappings",
        "description": "Configure and update tenant default accounts and tender method mappings",
    },

    # 2. Chart of Accounts (COA)
    {
        "module": "accounting",
        "code": "accounting:accounts:view",
        "name": "View Chart of Accounts",
        "description": "View business Chart of Accounts list, balances, and hierarchical tree",
    },
    {
        "module": "accounting",
        "code": "accounting:accounts:manage",
        "name": "Manage Chart of Accounts",
        "description": "Create, edit, and deactivate custom sub-accounts",
    },

    # 3. General Journal (JV)
    {
        "module": "accounting",
        "code": "accounting:journal:view",
        "name": "View General Journal Vouchers",
        "description": "View journal voucher audit trail, debit/credit breakdowns, and source documents",
    },
    {
        "module": "accounting",
        "code": "accounting:journal:post",
        "name": "Post Journal Vouchers",
        "description": "Create, balance, and post manual Journal Vouchers (JVs)",
    },

    # 4. Trial Balance & General Ledger
    {
        "module": "accounting",
        "code": "accounting:reports:view",
        "name": "View Trial Balance & Ledger",
        "description": "View account running ledgers, period statements, and Trial Balance equilibrium",
    },
    {
        "module": "accounting",
        "code": "accounting:reports:print",
        "name": "Print Financial Statements",
        "description": "Print and export official A4 Trial Balance and General Ledger statements",
    },
]


async def seed_accounting():
    now = datetime.now(timezone.utc)
    print("=== Starting Double-Entry Accounting Seeder ===")

    async with AsyncSessionLocal() as db:
        # 1. Seed Permissions
        print("1. Seeding Accounting Permissions...")
        perm_objs = {}
        for p_data in ACCOUNTING_PERMISSIONS:
            stmt = select(Permission).where(Permission.code == p_data["code"])
            res = await db.execute(stmt)
            existing = res.scalar_one_or_none()
            if not existing:
                p = Permission(
                    module=p_data["module"],
                    code=p_data["code"],
                    name=p_data["name"],
                    description=p_data["description"],
                    created_at=now,
                )
                db.add(p)
                await db.flush()
                perm_objs[p_data["code"]] = p
                print(f"   Created permission: {p_data['code']}")
            else:
                perm_objs[p_data["code"]] = existing

        # Assign permissions to roles
        roles_stmt = select(Role).where(Role.name.in_(["Super Admin", "Admin", "Owner", "Accountant"]))
        roles_res = await db.execute(roles_stmt)
        roles = roles_res.scalars().all()
        for role in roles:
            rp_stmt = select(RolePermission.permission_id).where(RolePermission.role_id == role.id)
            rp_res = await db.execute(rp_stmt)
            existing_perm_ids = set(rp_res.scalars().all())

            for code, perm in perm_objs.items():
                if perm.id not in existing_perm_ids:
                    db.add(RolePermission(role_id=role.id, permission_id=perm.id, created_at=now))

        await db.commit()

        # 2. Provision COA & Mapping Settings for all Tenants
        print("2. Provisioning Chart of Accounts & Mappings for Tenants...")
        tenants_stmt = select(Tenant)
        tenants_res = await db.execute(tenants_stmt)
        tenants = tenants_res.scalars().all()
        print(f"   Found {len(tenants)} tenant(s) to provision.")

        for tenant in tenants:
            print(f"   --> Provisioning Tenant: {tenant.name} (ID: {tenant.id})")
            created_accounts = {}

            # Seed basic COA accounts for this tenant
            for item in BASIC_COA_TEMPLATE:
                acc_stmt = select(Account).where(
                    Account.tenant_id == tenant.id,
                    Account.code == item["code"],
                )
                acc_res = await db.execute(acc_stmt)
                acc = acc_res.scalar_one_or_none()

                if not acc:
                    acc = Account(
                        tenant_id=tenant.id,
                        code=item["code"],
                        name=item["name"],
                        account_type=item["account_type"],
                        sub_type=item["sub_type"],
                        currency="PKR",
                        is_system=item["is_system"],
                        is_active=True,
                        description=item["description"],
                        created_at=now,
                    )
                    db.add(acc)
                    await db.flush()
                created_accounts[item["code"]] = acc

            # Seed or update TenantAccountingSettings
            sett_stmt = select(TenantAccountingSettings).where(TenantAccountingSettings.tenant_id == tenant.id)
            sett_res = await db.execute(sett_stmt)
            settings = sett_res.scalar_one_or_none()

            cash_acc = created_accounts.get("1010")
            bank_acc = created_accounts.get("1020")
            ar_acc = created_accounts.get("1030")
            inv_acc = created_accounts.get("1040")
            ap_acc = created_accounts.get("2010")
            tax_acc = created_accounts.get("2020")
            sales_acc = created_accounts.get("4010")
            disc_acc = created_accounts.get("4020")
            cogs_acc = created_accounts.get("5010")

            payment_mappings = {
                "cash": cash_acc.id if cash_acc else None,
                "bank_transfer": bank_acc.id if bank_acc else None,
                "raast": bank_acc.id if bank_acc else None,
                "card": bank_acc.id if bank_acc else None,
                "cheque": cash_acc.id if cash_acc else None,
            }

            if not settings:
                settings = TenantAccountingSettings(
                    tenant_id=tenant.id,
                    base_currency="PKR",
                    financial_year_start_month=7,
                    default_sales_income_account_id=sales_acc.id if sales_acc else None,
                    default_ar_account_id=ar_acc.id if ar_acc else None,
                    default_ap_account_id=ap_acc.id if ap_acc else None,
                    default_cash_account_id=cash_acc.id if cash_acc else None,
                    default_bank_account_id=bank_acc.id if bank_acc else None,
                    default_sales_tax_account_id=tax_acc.id if tax_acc else None,
                    default_discount_account_id=disc_acc.id if disc_acc else None,
                    default_cogs_account_id=cogs_acc.id if cogs_acc else None,
                    default_inventory_asset_account_id=inv_acc.id if inv_acc else None,
                    payment_method_mappings=payment_mappings,
                    auto_posting_enabled=True,
                    created_at=now,
                )
                db.add(settings)
            else:
                # Update null values if any
                if not settings.default_sales_income_account_id and sales_acc:
                    settings.default_sales_income_account_id = sales_acc.id
                if not settings.default_ar_account_id and ar_acc:
                    settings.default_ar_account_id = ar_acc.id
                if not settings.default_ap_account_id and ap_acc:
                    settings.default_ap_account_id = ap_acc.id
                if not settings.default_cash_account_id and cash_acc:
                    settings.default_cash_account_id = cash_acc.id
                if not settings.default_bank_account_id and bank_acc:
                    settings.default_bank_account_id = bank_acc.id
                if not settings.default_sales_tax_account_id and tax_acc:
                    settings.default_sales_tax_account_id = tax_acc.id
                if not settings.default_discount_account_id and disc_acc:
                    settings.default_discount_account_id = disc_acc.id
                if not settings.default_cogs_account_id and cogs_acc:
                    settings.default_cogs_account_id = cogs_acc.id
                if not settings.default_inventory_asset_account_id and inv_acc:
                    settings.default_inventory_asset_account_id = inv_acc.id
                if not settings.payment_method_mappings:
                    settings.payment_method_mappings = payment_mappings

        await db.commit()
        print("=== Double-Entry Accounting Seeded Successfully for All Tenants! ===")


if __name__ == "__main__":
    asyncio.run(seed_accounting())

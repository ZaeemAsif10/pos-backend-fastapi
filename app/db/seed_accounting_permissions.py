"""Seed exact button-action permissions for all Accounting screens."""
import asyncio
from datetime import datetime, timezone
from sqlalchemy import select, delete
from app.db.session import AsyncSessionLocal
from app.modules.auth.models import (
    Permission,
    Role,
    RolePermission,
)

BUTTON_ACTION_PERMISSIONS = [
    # 1. Account Mappings Screen
    {
        "module": "accounting",
        "code": "accounting:mappings:view",
        "name": "View Account Mappings",
        "description": "View default COA accounts and tender channel mappings",
    },
    {
        "module": "accounting",
        "code": "accounting:mappings:save",
        "name": "Save Account Mappings",
        "description": "Save changes button to update default posting heads and payment mappings",
    },

    # 2. Chart of Accounts Screen
    {
        "module": "accounting",
        "code": "accounting:accounts:view",
        "name": "View Chart of Accounts",
        "description": "View account directory, running balances, and hierarchy tree",
    },
    {
        "module": "accounting",
        "code": "accounting:accounts:create",
        "name": "Add New Account",
        "description": "Add New Account button to create custom heads in COA",
    },
    {
        "module": "accounting",
        "code": "accounting:accounts:edit",
        "name": "Edit Account",
        "description": "Edit button to modify account name, code, sub-type, or description",
    },
    {
        "module": "accounting",
        "code": "accounting:accounts:delete",
        "name": "Delete Account",
        "description": "Delete button to remove unused custom heads from COA",
    },

    # 3. General Journal Screen
    {
        "module": "accounting",
        "code": "accounting:journal:view",
        "name": "View Journal Entries",
        "description": "View audit list of all posted journal vouchers and filters",
    },
    {
        "module": "accounting",
        "code": "accounting:journal:details",
        "name": "View Voucher Breakdown",
        "description": "View Details button to inspect multi-line debit/credit breakdown",
    },
    {
        "module": "accounting",
        "code": "accounting:journal:create",
        "name": "Post Journal Voucher",
        "description": "New Journal Voucher button to create and post manual balanced JVs",
    },

    # 4. Trial Balance & General Ledger Screen
    {
        "module": "accounting",
        "code": "accounting:trial_balance:view",
        "name": "View Trial Balance",
        "description": "View Trial Balance tab and verify debit/credit equilibrium",
    },
    {
        "module": "accounting",
        "code": "accounting:ledger:view",
        "name": "View General Ledger",
        "description": "View Statement button to generate account-wise running ledgers",
    },
    {
        "module": "accounting",
        "code": "accounting:financial_statements:view",
        "name": "View Financial Statements (P&L & Balance Sheet)",
        "description": "View Profit & Loss Statement and Balance Sheet financial statements",
    },
    {
        "module": "accounting",
        "code": "accounting:reports:print",
        "name": "Print Financial Statements",
        "description": "Print Report button to generate A4 print-ready statements",
    },
    {
        "module": "accounting",
        "code": "accounting:reports:export",
        "name": "Export Financial Reports",
        "description": "Export CSV / Excel button for ledger and financial statements",
    },

    # 5. Direct Expense Vouchers Screen
    {
        "module": "accounting",
        "code": "accounting:expenses:view",
        "name": "View Expense Vouchers",
        "description": "View list, history, and KPI breakdown of operational expenses",
    },
    {
        "module": "accounting",
        "code": "accounting:expenses:create",
        "name": "Record Expense Voucher",
        "description": "Record Expense button to post direct cash/bank operational expenses",
    },
    {
        "module": "accounting",
        "code": "accounting:expenses:delete",
        "name": "Cancel Expense Voucher",
        "description": "Cancel button to void an expense voucher and reverse its journal entry",
    },

    # 6. Fiscal Year Closing
    {
        "module": "accounting",
        "code": "accounting:close_year",
        "name": "Close Fiscal Year",
        "description": "Execute formal fiscal year-end closing, zeroing temporary accounts to Retained Earnings",
    },

    # 7. Bank Reconciliation Screen (Exact Button Actions)
    {
        "module": "accounting",
        "code": "accounting:reconciliation:view",
        "name": "View Bank Reconciliations",
        "description": "View bank reconciliation history, statement cards, and reconciliation workspace",
    },
    {
        "module": "accounting",
        "code": "accounting:reconciliation:create",
        "name": "Start Bank Reconciliation",
        "description": "Start Reconciliation button to begin a new bank reconciliation session",
    },
    {
        "module": "accounting",
        "code": "accounting:reconciliation:match",
        "name": "Match Bank Items",
        "description": "Toggle checkboxes to match cleared bank transactions and uncleared items",
    },
    {
        "module": "accounting",
        "code": "accounting:reconciliation:complete",
        "name": "Complete Reconciliation",
        "description": "Complete Reconciliation button to finalize and lock balanced BRS statement",
    },

    # 8. Khata & Aging Screen (Exact Button Actions)
    {
        "module": "accounting",
        "code": "accounting:aging:view",
        "name": "View Khata Aging Schedule",
        "description": "View AR customer and AP supplier overdue aging schedule, buckets, and DSO/DPO metrics",
    },
    {
        "module": "accounting",
        "code": "accounting:aging:statement",
        "name": "View & Print Khata Statement",
        "description": "View running balance ledger statement and print customer or supplier statement slips",
    },
    {
        "module": "accounting",
        "code": "accounting:aging:whatsapp",
        "name": "Send WhatsApp Khata Reminder",
        "description": "Dispatch one-click WhatsApp balance and payment reminders to parties",
    },
    {
        "module": "accounting",
        "code": "accounting:aging:credit_block",
        "name": "Freeze Customer Credit",
        "description": "Freeze or unfreeze customer credit facilities and prevent new credit sales",
    },
]


async def seed_accounting_permissions():
    now = datetime.now(timezone.utc)
    print("=== Seeding Accounting Button-Action Permissions ===")

    async with AsyncSessionLocal() as session:
        # Remove obsolete generic manage permission if present
        manage_perm_res = await session.execute(
            select(Permission).where(Permission.code == "accounting:reconciliation:manage")
        )
        old_manage_perm = manage_perm_res.scalar_one_or_none()
        if old_manage_perm:
            await session.execute(
                delete(RolePermission).where(RolePermission.permission_id == old_manage_perm.id)
            )
            await session.delete(old_manage_perm)
            await session.flush()
            print("Removed obsolete permission: accounting:reconciliation:manage")

        # Fetch existing or create
        perm_objects = []
        for p_data in BUTTON_ACTION_PERMISSIONS:
            res = await session.execute(
                select(Permission).where(Permission.code == p_data["code"])
            )
            existing = res.scalar_one_or_none()
            if not existing:
                p = Permission(
                    module=p_data["module"],
                    code=p_data["code"],
                    name=p_data["name"],
                    description=p_data["description"],
                    created_at=now,
                )
                session.add(p)
                perm_objects.append(p)
                print(f"Created permission: {p_data['code']}")
            else:
                existing.name = p_data["name"]
                existing.description = p_data["description"]
                perm_objects.append(existing)

        await session.flush()

        roles_res = await session.execute(
            select(Role).where(Role.name.in_(["Super Admin", "Superadmin", "Admin", "Owner", "Accountant", "Cashier"]))
        )
        target_roles = roles_res.scalars().all()

        assigned_count = 0
        for role in target_roles:
            rp_res = await session.execute(
                select(RolePermission.permission_id).where(RolePermission.role_id == role.id)
            )
            existing_perm_ids = set(rp_res.scalars().all())
            r_name = role.name.lower()

            for p in perm_objects:
                if r_name == "accountant" and p.code == "accounting:mappings:save":
                    continue
                if r_name == "cashier" and p.code not in ["accounting:expenses:view", "accounting:expenses:create"]:
                    continue

                if p.id not in existing_perm_ids:
                    session.add(RolePermission(role_id=role.id, permission_id=p.id, created_at=now))
                    assigned_count += 1

        await session.commit()
        print(f"Assigned {assigned_count} permissions across roles.")
        print("=== Accounting Permissions Seeded Successfully! ===")


if __name__ == "__main__":
    asyncio.run(seed_accounting_permissions())

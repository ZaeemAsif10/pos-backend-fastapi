import asyncio
from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.modules.auth.models import Permission, Role, RolePermission


INVENTORY_PERMISSIONS = [
    # Purchases Permissions
    {
        "module": "purchases",
        "code": "purchases:view",
        "name": "View Purchases",
        "description": "View purchase bills, GRN, and vendor procurement history",
    },
    {
        "module": "purchases",
        "code": "purchases:create",
        "name": "Add Purchases",
        "description": "Create and post purchase bills and goods receipts",
    },
    {
        "module": "purchases",
        "code": "purchases:edit",
        "name": "Edit Purchases",
        "description": "Update purchase orders and supplier invoices",
    },
    {
        "module": "purchases",
        "code": "purchases:delete",
        "name": "Delete Purchases",
        "description": "Cancel or delete purchase bills and reverse stock",
    },
    
    # Inventory & Live Stock
    {
        "module": "inventory",
        "code": "inventory:view",
        "name": "View Inventory",
        "description": "View live branch stock balances, valuation, and bin cards",
    },
    {
        "module": "inventory",
        "code": "inventory:adjust",
        "name": "Adjust Stock",
        "description": "Post stock adjustments, shrinkage, damage, and audit corrections",
    },
    
    # Stock Transfers
    {
        "module": "stock_transfers",
        "code": "stock_transfers:view",
        "name": "View Stock Transfers",
        "description": "View inter-branch stock transfer orders and transit logs",
    },
    {
        "module": "stock_transfers",
        "code": "stock_transfers:create",
        "name": "Add Stock Transfers",
        "description": "Create and dispatch stock transfers between branches",
    },
    {
        "module": "stock_transfers",
        "code": "stock_transfers:edit",
        "name": "Edit Stock Transfers",
        "description": "Update and acknowledge received stock transfers",
    },
    {
        "module": "stock_transfers",
        "code": "stock_transfers:delete",
        "name": "Delete Stock Transfers",
        "description": "Cancel pending stock transfers",
    },
]


async def seed_inventory_permissions():
    async with AsyncSessionLocal() as db:
        print("=== Seeding Inventory & Purchases Permissions ===")

        created_perms = []
        for p_data in INVENTORY_PERMISSIONS:
            stmt = select(Permission).where(Permission.code == p_data["code"])
            res = await db.execute(stmt)
            perm = res.scalar_one_or_none()

            if not perm:
                perm = Permission(
                    code=p_data["code"],
                    name=p_data["name"],
                    module=p_data["module"],
                    description=p_data["description"],
                )
                db.add(perm)
                await db.flush()
                print(f"Created permission: {p_data['code']}")
            created_perms.append(perm)

        await db.commit()

        # Assign all new permissions to Admin and Owner roles across all tenants
        roles_stmt = select(Role).where(Role.name.in_(["Admin", "Owner"]))
        roles_res = await db.execute(roles_stmt)
        admin_roles = roles_res.scalars().all()
        print(f"Found {len(admin_roles)} admin/owner roles to update.")

        count_assigned = 0
        for role in admin_roles:
            for perm in created_perms:
                rp_stmt = select(RolePermission).where(
                    RolePermission.role_id == role.id,
                    RolePermission.permission_id == perm.id,
                )
                rp_res = await db.execute(rp_stmt)
                if not rp_res.scalar_one_or_none():
                    db.add(RolePermission(role_id=role.id, permission_id=perm.id))
                    count_assigned += 1

        await db.commit()
        print(f"Assigned {count_assigned} new role permissions.")
        print("=== Inventory & Purchases Permissions Seeded Successfully! ===")


if __name__ == "__main__":
    asyncio.run(seed_inventory_permissions())

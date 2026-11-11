"""Seed permissions for Customers, Suppliers, and Delivery Areas."""
import asyncio
from datetime import datetime, timezone
from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.modules.auth.models import (
    Permission,
    Role,
    RolePermission,
)

PARTIES_PERMISSIONS = [
    # Customers
    {
        "module": "customers",
        "code": "customers:view",
        "name": "View Customers",
        "description": "View customer directory, udhaar balances, and credit status",
    },
    {
        "module": "customers",
        "code": "customers:create",
        "name": "Add Customers",
        "description": "Create new customer accounts with credit terms and CNIC",
    },
    {
        "module": "customers",
        "code": "customers:edit",
        "name": "Edit Customers",
        "description": "Update customer details, credit limits, payment days, and routes",
    },
    {
        "module": "customers",
        "code": "customers:delete",
        "name": "Delete Customers",
        "description": "Remove customer accounts from the directory",
    },

    # Suppliers
    {
        "module": "suppliers",
        "code": "suppliers:view",
        "name": "View Suppliers",
        "description": "View vendor directory, payables, and payment terms",
    },
    {
        "module": "suppliers",
        "code": "suppliers:create",
        "name": "Add Suppliers",
        "description": "Register new supplier profiles, mills, and bank accounts",
    },
    {
        "module": "suppliers",
        "code": "suppliers:edit",
        "name": "Edit Suppliers",
        "description": "Update supplier contact information, NTN/STRN, and bank details",
    },
    {
        "module": "suppliers",
        "code": "suppliers:delete",
        "name": "Delete Suppliers",
        "description": "Remove supplier profiles from the system",
    },

    # Delivery Areas
    {
        "module": "delivery_areas",
        "code": "delivery_areas:view",
        "name": "View Delivery Areas",
        "description": "View market beats, delivery routes, and assigned salesmen",
    },
    {
        "module": "delivery_areas",
        "code": "delivery_areas:create",
        "name": "Create Delivery Areas",
        "description": "Define new delivery sectors, beats, and delivery day schedules",
    },
    {
        "module": "delivery_areas",
        "code": "delivery_areas:edit",
        "name": "Edit Delivery Areas",
        "description": "Update delivery area names, descriptions, and salesman assignments",
    },
    {
        "module": "delivery_areas",
        "code": "delivery_areas:delete",
        "name": "Delete Delivery Areas",
        "description": "Remove delivery areas from the distribution network",
    },
]


async def seed_parties_permissions():
    now = datetime.now(timezone.utc)
    print("=== Seeding Parties Permissions ===")

    async with AsyncSessionLocal() as session:
        # 1. Fetch or create permissions
        new_perm_objects = []
        for p_data in PARTIES_PERMISSIONS:
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
                new_perm_objects.append(p)
                print(f"Created permission: {p_data['code']}")
            else:
                new_perm_objects.append(existing)

        await session.flush()

        # 2. Assign to all Admin / Owner roles across all tenants
        roles_res = await session.execute(
            select(Role).where(Role.name.in_(["Admin", "Owner", "Superadmin"]))
        )
        admin_roles = roles_res.scalars().all()
        print(f"Found {len(admin_roles)} admin/owner roles to update.")

        assigned_count = 0
        for role in admin_roles:
            # Check existing role permissions
            rp_res = await session.execute(
                select(RolePermission.permission_id).where(RolePermission.role_id == role.id)
            )
            existing_perm_ids = set(rp_res.scalars().all())

            for p in new_perm_objects:
                if p.id not in existing_perm_ids:
                    session.add(RolePermission(role_id=role.id, permission_id=p.id))
                    assigned_count += 1

        await session.commit()
        print(f"Assigned {assigned_count} new role permissions.")
        print("=== Parties Permissions Seeded Successfully! ===")


if __name__ == "__main__":
    asyncio.run(seed_parties_permissions())

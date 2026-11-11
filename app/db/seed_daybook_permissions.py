"""Seed permissions for Day Book / Roznamcha (Cash & Bank Book)."""
import asyncio
from datetime import datetime, timezone
from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.modules.auth.models import (
    Permission,
    Role,
    RolePermission,
)

DAYBOOK_PERMISSIONS = [
    {
        "module": "daybook",
        "code": "daybook:view",
        "name": "View Day Book (Roznamcha)",
        "description": "View daily cash & bank ledger, drawer balance, and transactions",
    },
    {
        "module": "daybook",
        "code": "daybook:print",
        "name": "Print Day Book & Closing Slips",
        "description": "Print 80mm/58mm thermal closing slips and full A4 audit statements",
    },
    {
        "module": "daybook",
        "code": "daybook:export",
        "name": "Export & WhatsApp Daily Closing",
        "description": "Share daily closing reports via WhatsApp or export audit statements",
    },
    {
        "module": "daybook",
        "code": "daybook:all_branches",
        "name": "View All Branches Day Book",
        "description": "View consolidated cash & bank ledger across all business branches",
    },
]


async def seed_daybook_permissions():
    now = datetime.now(timezone.utc)
    print("=== Seeding Day Book (Roznamcha) Permissions ===")

    async with AsyncSessionLocal() as session:
        # 1. Ensure master permissions exist in Permission table
        perm_objects = {}
        for p_data in DAYBOOK_PERMISSIONS:
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
                await session.flush()
                perm_objects[p_data["code"]] = p
                print(f"Created permission: {p_data['code']}")
            else:
                perm_objects[p_data["code"]] = existing

        await session.flush()

        # 2. Roles Assignment Matrix:
        # - Admin & Super Admin: All Day Book permissions
        # - Accountant: daybook:view, daybook:print, daybook:export
        # - Cashier: daybook:view, daybook:print
        roles_res = await session.execute(
            select(Role).where(Role.name.in_(["Super Admin", "Admin", "Owner", "Accountant", "Cashier"]))
        )
        roles = roles_res.scalars().all()
        print(f"Found {len(roles)} relevant roles to configure.")

        assigned_count = 0
        for role in roles:
            # Query existing role permissions
            rp_res = await session.execute(
                select(RolePermission.permission_id).where(RolePermission.role_id == role.id)
            )
            existing_perm_ids = set(rp_res.scalars().all())

            # Determine allowed codes based on role name
            if role.name in ["Super Admin", "Admin", "Owner"]:
                target_codes = ["daybook:view", "daybook:print", "daybook:export", "daybook:all_branches"]
            elif role.name == "Accountant":
                target_codes = ["daybook:view", "daybook:print", "daybook:export"]
            elif role.name == "Cashier":
                target_codes = ["daybook:view", "daybook:print"]
            else:
                target_codes = []

            for code in target_codes:
                perm = perm_objects.get(code)
                if perm and perm.id not in existing_perm_ids:
                    session.add(RolePermission(role_id=role.id, permission_id=perm.id, created_at=now))
                    existing_perm_ids.add(perm.id)
                    assigned_count += 1

        await session.commit()
        print(f"Assigned {assigned_count} new Day Book permissions across roles.")
        print("=== Day Book Permissions Seeded Successfully! ===")


if __name__ == "__main__":
    asyncio.run(seed_daybook_permissions())

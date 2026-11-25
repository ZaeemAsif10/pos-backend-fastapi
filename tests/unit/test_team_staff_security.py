"""Regression tests for BUG-001: cross-tenant user hijack & global password overwrite."""
import asyncio
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException

import app.db.base  # noqa: F401 - ensure all SQLAlchemy models are registered
from app.modules.team.schemas import StaffCreateRequest, StaffUpdateRequest
from app.modules.team.services import TeamService


def _scalar_result(value):
    res = MagicMock()
    res.scalar_one_or_none.return_value = value
    return res


class TestTeamStaffSecurity(unittest.TestCase):
    def setUp(self):
        self.tenant = SimpleNamespace(id=2, name="Attacker Tenant", plan_tier="free_trial")
        self.attacker_owner = SimpleNamespace(id=20, is_superadmin=False)
        self.role = SimpleNamespace(id=5, tenant_id=2, name="Cashier")

    def test_create_staff_blocks_superadmin_attachment(self):
        superadmin_user = SimpleNamespace(id=1, email="superadmin@gmail.com", phone="03000000000", is_superadmin=True)
        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _scalar_result(self.role),       # Role lookup
                _scalar_result(superadmin_user), # Global User lookup
                _scalar_result(None),            # Not yet in Tenant 2
            ]
        )
        payload = StaffCreateRequest(
            full_name="Hijack",
            email="superadmin@gmail.com",
            password="Password123",
            role_id=5,
        )

        with (
            patch.object(TeamService, "verify_staff_create_permission", AsyncMock()),
            patch.object(TeamService, "get_plan_staff_quota", AsyncMock(return_value=(1, 5, "Free Trial"))),
            patch("app.modules.team.services.EntitlementService.check_quota_limit", AsyncMock()),
        ):
            with self.assertRaises(HTTPException) as ctx:
                asyncio.run(TeamService.create_staff(db, self.tenant, payload, self.attacker_owner))

        self.assertEqual(ctx.exception.status_code, 403)
        db.commit.assert_not_awaited()

    def test_create_staff_blocks_existing_cross_tenant_user(self):
        other_tenant_owner = SimpleNamespace(id=10, email="ownerA@shop.pk", phone="03111111111", is_superadmin=False)
        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _scalar_result(self.role),
                _scalar_result(other_tenant_owner),
                _scalar_result(None),
            ]
        )
        payload = StaffCreateRequest(
            full_name="Hijack",
            email="ownerA@shop.pk",
            password="Password123",
            role_id=5,
        )

        with (
            patch.object(TeamService, "verify_staff_create_permission", AsyncMock()),
            patch.object(TeamService, "get_plan_staff_quota", AsyncMock(return_value=(1, 5, "Free Trial"))),
            patch("app.modules.team.services.EntitlementService.check_quota_limit", AsyncMock()),
        ):
            with self.assertRaises(HTTPException) as ctx:
                asyncio.run(TeamService.create_staff(db, self.tenant, payload, self.attacker_owner))

        self.assertEqual(ctx.exception.status_code, 409)
        db.commit.assert_not_awaited()

    def test_create_staff_allows_brand_new_user(self):
        db = AsyncMock()
        db.add = MagicMock()
        db.execute = AsyncMock(
            side_effect=[
                _scalar_result(self.role),
                _scalar_result(None),  # No existing global User
            ]
        )

        async def _refresh(obj):
            if getattr(obj, "id", None) is None:
                obj.id = 99
            if not getattr(obj, "joined_at", None):
                obj.joined_at = datetime.now(timezone.utc)
            if not hasattr(obj, "last_login_at"):
                obj.last_login_at = None

        db.refresh = AsyncMock(side_effect=_refresh)

        payload = StaffCreateRequest(
            full_name="New Cashier",
            email="newcashier@shop.pk",
            password="Password123",
            role_id=5,
        )

        with (
            patch.object(TeamService, "verify_staff_create_permission", AsyncMock()),
            patch.object(TeamService, "get_plan_staff_quota", AsyncMock(return_value=(1, 5, "Free Trial"))),
            patch("app.modules.team.services.EntitlementService.check_quota_limit", AsyncMock()),
        ):
            res = asyncio.run(TeamService.create_staff(db, self.tenant, payload, self.attacker_owner))

        self.assertEqual(res.email, "newcashier@shop.pk")
        self.assertEqual(res.role_name, "Cashier")
        db.commit.assert_awaited_once()

    def test_update_staff_blocks_password_overwrite_on_multi_tenant_user(self):
        victim_user = SimpleNamespace(
            id=10,
            full_name="Victim Owner",
            email="ownerA@shop.pk",
            phone=None,
            is_superadmin=False,
            password_hash="original_hash",
            last_login_at=None,
        )
        membership = SimpleNamespace(
            id=55,
            tenant_id=2,
            user_id=10,
            role_id=5,
            is_owner=False,
            is_active=True,
            max_discount_pct=0.0,
            joined_at=datetime.now(timezone.utc),
            user=victim_user,
            role=self.role,
        )
        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _scalar_result(membership),  # Membership lookup
                _scalar_result(77),          # Exists in another tenant!
            ]
        )
        payload = StaffUpdateRequest(password="AttackerPassword123")

        with patch.object(TeamService, "verify_staff_edit_permission", AsyncMock()):
            with self.assertRaises(HTTPException) as ctx:
                asyncio.run(TeamService.update_staff(db, self.tenant, 55, payload, self.attacker_owner))

        self.assertEqual(ctx.exception.status_code, 403)
        self.assertEqual(victim_user.password_hash, "original_hash")
        db.commit.assert_not_awaited()

    def test_update_staff_allows_single_tenant_staff_password_update(self):
        staff_user = SimpleNamespace(
            id=30,
            full_name="Staff One",
            email="staff1@shop.pk",
            phone=None,
            is_superadmin=False,
            password_hash="old_hash",
            last_login_at=None,
        )
        membership = SimpleNamespace(
            id=56,
            tenant_id=2,
            user_id=30,
            role_id=5,
            is_owner=False,
            is_active=True,
            max_discount_pct=0.0,
            joined_at=datetime.now(timezone.utc),
            user=staff_user,
            role=self.role,
        )
        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _scalar_result(membership),  # Membership lookup
                _scalar_result(None),        # No other tenant memberships
                _scalar_result(self.role),   # Reload role
            ]
        )
        payload = StaffUpdateRequest(full_name="Staff Updated", password="NewPassword123")

        with patch.object(TeamService, "verify_staff_edit_permission", AsyncMock()):
            res = asyncio.run(TeamService.update_staff(db, self.tenant, 56, payload, self.attacker_owner))

        self.assertEqual(res.full_name, "Staff Updated")
        self.assertNotEqual(staff_user.password_hash, "old_hash")
        db.commit.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()


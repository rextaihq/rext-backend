"""Guards the RBAC invariants around global (platform-scoped) roles.

History: migration 20260904rbacfloor established a platform-floor 'user' role
auto-assigned to every account. Migration 20260921nofloor removed it — its
grants (user.read/user.update/license.*) were redundant because every
own-account route that checked them is now gated on authentication alone.
get_user_permissions() still unions global (workspace_id IS NULL) roles into
every workspace, so any workspace permission granted to a global role would
still become a floor no workspace role can sit below. That invariant is
guarded here. Run against a migrated, seeded DB:

    python -m pytest tests/test_rbac_permission_floor.py
"""

import os
import re

import psycopg
import pytest

# The remaining global roles whose grants can leak into every workspace.
GLOBAL_ROLES = ("admin", "support")


def _dsn() -> str:
    url = os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:5432/rext")
    return re.sub(r"^postgresql\+\w+://", "postgresql://", url.strip('"'))


@pytest.fixture(scope="module")
def conn():
    try:
        with psycopg.connect(_dsn()) as c:
            yield c
    except psycopg.OperationalError as exc:
        pytest.skip(f"database unavailable: {exc}")


def _perms(conn, role_name):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT p.name FROM roles r
            JOIN role_permissions rp ON rp.role_id = r.id
            JOIN permissions p ON p.id = rp.permission_id
            WHERE r.name = %s
            """,
            (role_name,),
        )
        return {row[0] for row in cur.fetchall()}


def test_platform_user_role_is_gone(conn):
    """20260921nofloor removed the floor role; it must never come back.
    If it reappears, signup would need re-teaching and the redundancy
    returns."""
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM roles WHERE name = 'user'")
        assert cur.fetchall() == []


def test_no_orphaned_user_role_assignments(conn):
    """The floor cleanup must not leave dangling user_roles rows."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT ur.id FROM user_roles ur
            LEFT JOIN roles r ON r.id = ur.role_id
            WHERE r.id IS NULL
            """
        )
        assert cur.fetchall() == []


def test_demotion_actually_removes_permissions(conn):
    """editor -> viewer must lose permissions; viewer is not decorative."""
    assert _perms(conn, "editor") - _perms(conn, "viewer")


def test_no_workspace_role_assigned_globally(conn):
    """A workspace role with workspace_id IS NULL applies in every workspace."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT u.email, r.name FROM user_roles ur
            JOIN roles r ON r.id = ur.role_id
            JOIN users u ON u.id = ur.user_id
            WHERE ur.workspace_id IS NULL AND r.is_workspace_role IS TRUE
            """
        )
        assert cur.fetchall() == []


def test_user_manage_is_admin_only(conn):
    """SEC-RBAC-01/02/03: the admin-only user.manage permission must never sit
    on non-admin roles, and admin/super_admin must hold it."""
    assert "user.manage" not in _perms(conn, "support")
    assert "user.manage" not in _perms(conn, "viewer")
    assert "user.manage" not in _perms(conn, "editor")
    assert "user.manage" in _perms(conn, "admin")
    assert "user.manage" in _perms(conn, "super_admin")


def test_admin_never_holds_billing_manage(conn):
    """SEC-RBAC-11: admin is 'everything except billing.manage'; a CROSS JOIN
    grant must not have swept it in."""
    assert "billing.manage" not in _perms(conn, "admin")
    assert "billing.manage" in _perms(conn, "super_admin")


def test_workspace_roles_never_hold_billing(conn):
    """billing.* routes are global-scoped; a workspace role can never use them."""
    for role in ("workspace_owner", "workspace_admin", "editor", "viewer"):
        assert "billing.read" not in _perms(conn, role)
        assert "billing.manage" not in _perms(conn, role)

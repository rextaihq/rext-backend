"""Guards the invariant the 20260904rbacfloor migration establishes.

get_user_permissions() unions global (workspace_id IS NULL) roles into every
workspace, so any workspace permission on a global role becomes a floor no
workspace role can sit below. That is what made 'viewer' a no-op and made
demotion impossible. Run against a seeded DB:

    python -m pytest tests/test_rbac_permission_floor.py
"""

import os
import re

import psycopg
import pytest

# Mirrors AuthService.DEFAULT_PERMISSIONS.
PLATFORM_PERMISSIONS = {"user.read", "user.update", "workspace.create"}

GLOBAL_ROLES = ("user", "support")


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


def test_global_user_role_holds_only_platform_permissions(conn):
    assert _perms(conn, "user") == PLATFORM_PERMISSIONS


def test_viewer_grants_something_over_the_global_floor(conn):
    """If viewer adds nothing over 'user', the role is decorative."""
    assert _perms(conn, "viewer") - _perms(conn, "user")


def test_demotion_actually_removes_permissions(conn):
    """editor -> viewer must lose permissions once the floor is subtracted."""
    floor = _perms(conn, "user")
    assert (_perms(conn, "editor") | floor) - (_perms(conn, "viewer") | floor)


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


def test_every_user_has_a_global_platform_role(conn):
    """Without one, /users/me and billing 403 for that account."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT u.email FROM users u WHERE NOT EXISTS (
                SELECT 1 FROM user_roles ur
                JOIN roles r ON r.id = ur.role_id
                WHERE ur.user_id = u.id
                  AND ur.workspace_id IS NULL
                  AND r.is_workspace_role IS NOT TRUE
            )
            """
        )
        assert cur.fetchall() == []


def test_user_manage_is_admin_only(conn):
    """SEC-RBAC-01/02/03: the admin-only user.manage permission must never sit on
    the default user role (or other non-admin roles), and admin/super_admin must
    hold it."""
    assert "user.manage" not in _perms(conn, "user")
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

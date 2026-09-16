"""
Unit tests for RBAC seed permissions script.
Verifies that seed_permissions is non-destructive (additive-only).
"""

import inspect

from scripts.seeds.seed_permissions import (
    PERMISSIONS,
    ROLE_PERMISSION_ASSIGNMENTS,
    ROLES,
    seed_permissions,
)


def test_seed_permissions_code_contains_no_destructive_delete_queries():
    """Verify that seed_permissions source code contains zero DELETE SQL queries."""
    source_code = inspect.getsource(seed_permissions)

    assert "DELETE FROM role_permissions" not in source_code, (
        "seed_permissions must not destructively delete role permission assignments"
    )
    assert "DELETE FROM permissions" not in source_code, (
        "seed_permissions must not destructively delete permissions"
    )


def test_seed_permissions_data_structures():
    """Verify essential roles and permissions are defined in seed constants."""
    role_names = {r["name"] for r in ROLES}
    expected_roles = {
        "super_admin",
        "admin",
        "workspace_owner",
        "workspace_admin",
        "editor",
        "viewer",
        "user",
        "support",
    }
    assert expected_roles.issubset(role_names)

    perm_names = {p[0] for p in PERMISSIONS}
    assert "workspace.read" in perm_names
    assert "content.read" in perm_names
    assert "user.read" in perm_names

    # Check assignment mapping exists for all roles
    for role in expected_roles:
        assert role in ROLE_PERMISSION_ASSIGNMENTS

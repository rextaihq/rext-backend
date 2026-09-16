"""
Unit tests for backend permission dependency resolution.

The map must match the final approved technical map exactly (and the frontend
copy in rext-admin/lib/permission-dependencies.ts).
"""

from scripts.seeds.seed_permissions import PERMISSIONS, ROLE_PERMISSION_ASSIGNMENTS
from src.constants.permission_dependencies import (
    PERMISSION_DEPENDENCIES,
    remove_permission_with_dependents,
    resolve_permission_prerequisites,
)

APPROVED_MAP = {
    # Content
    "content.create": ["content.read"],
    "content.update": ["content.read"],
    "content.delete": ["content.read"],
    "content.publish": ["content.read"],

    # Member
    "member.update_role": ["member.read"],
    "member.invite": ["member.read"],
    "member.remove": ["member.read"],

    # Workspace
    "workspace.update": ["workspace.read"],
    "workspace.delete": ["workspace.read"],

    # Role
    "role.create": ["role.read"],
    "role.update": ["role.read"],
    "role.delete": ["role.read"],
    "role.manage_permissions": ["role.read"],

    # User
    "user.invite": ["user.read"],
    "user.update": ["user.read"],
    "user.delete": ["user.read"],
    "user.manage_roles": ["user.read", "role.read"],

    # Billing
    "billing.manage": ["billing.read"],
    "integration.create": ["integration.read"],
    "integration.update": ["integration.read"],
    "integration.delete": ["integration.read"],
    "brand_voice.update": ["brand_voice.read"],
    "brand_voice.delete": ["brand_voice.read"],
    "persona.create": ["persona.read"],
    "persona.update": ["persona.read"],
    "persona.delete": ["persona.read"],
    "security.manage": ["security.read"],
}

# Removed by migration 20260916permcleanup; they must not come back.
REMOVED_PERMISSIONS = {
    "content.approve",
    "content.reject",
    "content.submit_for_review",
    "content.export",
    "member.update",
    "user.create",
    "permission.create",
    "permission.delete",
    "audit.write",
    "admin.invite",
    "license.read",
    "license.view",
    "license.activate",
    "license.deactivate",
    "license.revoke",
    "member.resend_invitation",
    "member.revoke_invitation",
    "workspace.manage_roles",
    "workspace.manage_members",
    "workspace.manage_billing",
    "workspace.transfer",
    "workspace.transfer_ownership",
    "workspace.write",
    "workspace.invite",
    "usage.read",
}

SEEDED = {name for name, *_ in PERMISSIONS}

# Domains where every action needs the domain's read permission first.
# workspace.create is the exception: you create a workspace before you can read it.
READ_GATED_DOMAINS = {
    "content", "member", "workspace", "role", "billing",
    "integration", "brand_voice", "persona", "security",
}


def test_map_matches_approved_map_exactly():
    assert PERMISSION_DEPENDENCIES == APPROVED_MAP


def test_every_seeded_action_selects_its_read_permission():
    # Guards the content.approve bug: a selectable action without its read prerequisite.
    for name in SEEDED:
        domain, action = name.split(".", 1)
        if domain in READ_GATED_DOMAINS and action != "read" and name != "workspace.create":
            assert f"{domain}.read" in resolve_permission_prerequisites([name]), name


def test_map_only_references_seeded_permissions():
    referenced = set(PERMISSION_DEPENDENCIES) | {
        dep for deps in PERMISSION_DEPENDENCIES.values() for dep in deps
    }
    assert referenced <= SEEDED


def test_removed_permissions_are_not_seeded_mapped_or_granted():
    assert not REMOVED_PERMISSIONS & SEEDED
    assert not REMOVED_PERMISSIONS & set(PERMISSION_DEPENDENCIES)
    for role, granted in ROLE_PERMISSION_ASSIGNMENTS.items():
        assert not REMOVED_PERMISSIONS & set(granted), role


def test_workflow_capabilities_are_not_technical_dependencies():
    for name in ("content.publish", "content.create"):
        assert PERMISSION_DEPENDENCIES[name] == ["content.read"]
    assert PERMISSION_DEPENDENCIES["member.invite"] == ["member.read"]
    assert PERMISSION_DEPENDENCIES["role.create"] == ["role.read"]


def test_resolve_content_publish_only_adds_read():
    assert resolve_permission_prerequisites(["content.publish"]) == ["content.publish", "content.read"]


def test_resolve_member_update_role_transitive():
    assert resolve_permission_prerequisites(["member.update_role"]) == [
        "member.read",
        "member.update_role",
    ]


def test_resolve_role_manage_permissions_minimal():
    assert resolve_permission_prerequisites(["role.manage_permissions"]) == [
        "role.manage_permissions",
        "role.read",
    ]


def test_resolve_workspace_update_minimal():
    assert resolve_permission_prerequisites(["workspace.update"]) == [
        "workspace.read",
        "workspace.update",
    ]


def test_remove_preserves_shared_prerequisite():
    held = ["content.read", "content.create", "content.publish"]
    assert remove_permission_with_dependents(held, "content.publish") == [
        "content.create",
        "content.read",
    ]


def test_remove_base_prerequisite_cascades_to_dependents():
    held = ["content.read", "content.create", "content.publish", "workspace.read"]
    assert remove_permission_with_dependents(held, "content.read") == ["workspace.read"]


def test_remove_member_read_cascades_to_update_role():
    held = resolve_permission_prerequisites(["member.update_role", "workspace.read"])
    assert remove_permission_with_dependents(held, "member.read") == [
        "workspace.read",
    ]

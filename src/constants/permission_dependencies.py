"""
Approved Technical Permission Prerequisites Map

Maps each permission string to its direct technical prerequisite permissions.
Used by RoleService to resolve transitive dependencies for Custom Roles.

Only technical prerequisites belong here. Workflow bundles (author, publisher,
reviewer) are optional UI presets and must not be encoded as dependencies.
Mirrors rext-admin/lib/permission-dependencies.ts.
"""

from typing import Dict, List, Set

PERMISSION_DEPENDENCIES: Dict[str, List[str]] = {
    # Content Domain
    "content.create": ["content.read"],
    "content.update": ["content.read"],
    "content.delete": ["content.read"],
    "content.publish": ["content.read"],
    # Member Domain
    "member.invite": ["member.read"],
    "member.update_role": ["member.read"],
    "member.remove": ["member.read"],
    # Workspace Domain
    "workspace.update": ["workspace.read"],
    "workspace.delete": ["workspace.read"],
    # Role Domain
    "role.create": ["role.read"],
    "role.update": ["role.read"],
    "role.delete": ["role.read"],
    "role.manage_permissions": ["role.read"],
    # User Domain
    "user.invite": ["user.read"],
    "user.update": ["user.read"],
    "user.delete": ["user.read"],
    "user.manage_roles": ["user.read", "role.read"],
    # Billing Domain
    "billing.manage": ["billing.read"],
    # Integration and workspace identity domains
    "integration.create": ["integration.read"],
    "integration.update": ["integration.read"],
    "integration.delete": ["integration.read"],
    "brand_voice.update": ["brand_voice.read"],
    "persona.create": ["persona.read"],
    "persona.update": ["persona.read"],
    "persona.delete": ["persona.read"],
    "security.manage": ["security.read"],
}


def resolve_permission_prerequisites(selected_permission_names: List[str]) -> List[str]:
    """
    Given a list of permission names, compute the transitive closure
    including all required prerequisite permissions.
    """
    result_set: Set[str] = set(selected_permission_names)
    queue: List[str] = list(selected_permission_names)

    while queue:
        current = queue.pop(0)
        deps = PERMISSION_DEPENDENCIES.get(current, [])
        for dep in deps:
            if dep not in result_set:
                result_set.add(dep)
                queue.append(dep)

    return sorted(list(result_set))


def remove_permission_with_dependents(
    held_permission_names: List[str], removed_name: str
) -> List[str]:
    """
    Remove a permission and every held permission that transitively requires it.

    Prerequisites of the removed permission are never removed, so a shared
    prerequisite (e.g. content.read) survives for the permissions still using it.
    """
    to_remove: Set[str] = {removed_name}
    changed = True
    while changed:
        changed = False
        for name, deps in PERMISSION_DEPENDENCIES.items():
            if name not in to_remove and any(dep in to_remove for dep in deps):
                to_remove.add(name)
                changed = True

    return sorted(name for name in set(held_permission_names) if name not in to_remove)

"""
Display-role resolution.

Shared by the ORM serializer (models/user_models/users.py) and the response
schema (schema/user_schema.py) so both always show the same role for a user.
"""

DEFAULT_DISPLAY_ROLE = "User"

# Roles at or above this hierarchy level are Super Admin. Mirrors
# SUPER_ADMIN_HIERARCHY_THRESHOLD in src/utils/rbac_utils.py.
SUPER_ADMIN_HIERARCHY_LEVEL = 100


def is_super_admin_from_roles(user_roles) -> bool:
    """
    Decide whether a user is a Super Admin from already-loaded UserRole rows.

    Super Admin is a platform-wide grant (``workspace_id IS NULL``) with a
    hierarchy level of 100 or more. Reads only what is in memory so it is safe
    to call from the sync ORM serializer.
    """
    for ur in user_roles or []:
        role = getattr(ur, "role", None)
        if role is None:
            continue
        if getattr(ur, "workspace_id", None) is not None:
            continue
        if (getattr(role, "hierarchy_level", 0) or 0) >= SUPER_ADMIN_HIERARCHY_LEVEL:
            return True
    return False


def _live_roles(user_roles):
    """
    Drop UserRole rows whose workspace has been soft-deleted.

    Deleting a workspace only stamps ``deleted_at`` (see
    WorkspaceService.delete_workspace) and leaves the owner's UserRole row
    behind, so a user who created and deleted twenty workspaces still carries
    twenty ``workspace_owner`` grants. Every user-facing workspace query
    filters ``deleted_at IS NULL``; role display did not, so the admin Users
    table showed a wall of "Workspace Owner" badges for workspaces that no
    longer exist.

    ``workspace`` is only touched when it was eager-loaded — reading an
    unloaded relationship would lazy-load inside async context.
    """
    from sqlalchemy import inspect as sa_inspect

    live = []
    for ur in user_roles or []:
        if getattr(ur, "role", None) is None:
            continue
        if ur.workspace_id is not None and "workspace" not in sa_inspect(ur).unloaded:
            workspace = ur.workspace
            if workspace is None or workspace.deleted_at is not None:
                continue
        live.append(ur)
    return live


def resolve_display_role(user_roles) -> str:
    """
    Return the role name to display for a user, ranked by hierarchy.

    A user normally holds several roles at once: the global ``user`` role
    granted at registration plus workspace roles such as ``viewer`` picked up
    by accepting an invitation.

    This used to return the first row with ``is_primary`` set. That flag does
    not single out one role — it is set on nearly every assignment and is used
    together with ``workspace_id IS NULL`` to load a user's global roles for
    permissions (see AuthService) — and the ``user_roles`` relationship has no
    ``order_by``, so "first primary" meant "whichever row the database handed
    back first". An invited Viewer displayed as "User" for that reason, and the
    answer could change between queries.

    Rank by ``hierarchy_level`` instead (viewer 10 beats user 1, super_admin
    100 beats workspace_owner 60), breaking ties on role name so the result is
    stable.

    Args:
        user_roles: UserRole rows for the user, each with a loaded ``role``

    Returns:
        The highest-ranked role's display name, or "User" when there is none
    """
    from sqlalchemy import inspect as sa_inspect

    roles = []
    for ur in user_roles or []:
        role = getattr(ur, "role", None)
        if role is None:
            continue

        if ur.workspace_id is not None:
            try:
                is_unloaded = "workspace" in sa_inspect(ur).unloaded
            except Exception:
                is_unloaded = False

            if not is_unloaded:
                workspace = getattr(ur, "workspace", None)
                if (
                    workspace is None
                    or getattr(workspace, "deleted_at", None) is not None
                    or getattr(workspace, "is_deleted", False)
                ):
                    continue

        roles.append(role)

    if not roles:
        return DEFAULT_DISPLAY_ROLE

    best = max(
        roles,
        key=lambda r: (
            getattr(r, "hierarchy_level", 0) or 0,
            getattr(r, "name", "") or "",
        ),
    )
    return getattr(best, "display_name", None) or DEFAULT_DISPLAY_ROLE


def resolve_role_list(user_roles) -> list[dict]:
    """
    Return every role a user holds, ranked like ``resolve_display_role``.

    ``resolve_display_role`` collapses to the single highest-ranked role, which
    hides the rest: a user who is ``user`` platform-wide, ``viewer`` in one
    workspace and ``support`` in another showed only "Viewer". The admin Users
    table needs all of them, and needs to tell platform-wide assignments
    (``workspace_id IS NULL`` - they grant nothing inside a workspace) apart
    from workspace-scoped ones.

    ``workspace_name`` is filled in only when the ``workspace`` relationship was
    eager-loaded; touching it otherwise would lazy-load inside async context.

    Args:
        user_roles: UserRole rows for the user, each with a loaded ``role``

    Returns:
        List of dicts ordered highest hierarchy first, ties broken on name.
    """
    from sqlalchemy import inspect as sa_inspect

    rows = []
    for ur in _live_roles(user_roles):
        role = ur.role

        workspace_name = None
        if ur.workspace_id is not None:
            try:
                is_unloaded = "workspace" in sa_inspect(ur).unloaded
            except Exception:
                is_unloaded = False

            if not is_unloaded:
                workspace = getattr(ur, "workspace", None)
                if (
                    workspace is None
                    or getattr(workspace, "deleted_at", None) is not None
                    or getattr(workspace, "is_deleted", False)
                ):
                    continue
                workspace_name = getattr(workspace, "name", None)

        rows.append({
            "role_id": str(role.id),
            "name": role.name,
            "display_name": role.display_name or role.name,
            "hierarchy_level": role.hierarchy_level or 0,
            "workspace_id": str(ur.workspace_id) if ur.workspace_id else None,
            "workspace_name": workspace_name,
            "is_platform": ur.workspace_id is None,
        })

    rows.sort(key=lambda r: (-r["hierarchy_level"], r["name"]))
    return rows

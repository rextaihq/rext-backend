"""
Display-role resolution.

Shared by the ORM serializer (models/user_models/users.py) and the response
schema (schema/user_schema.py) so both always show the same role for a user.
"""

DEFAULT_DISPLAY_ROLE = "User"


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
    roles = [
        ur.role for ur in (user_roles or []) if getattr(ur, "role", None) is not None
    ]
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

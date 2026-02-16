from src.utils.rbac_utils import check_permission_or_admin


async def check_role_permission(db, user_id, required_permission):
    """Backward-compatible wrapper. Delegates to check_permission_or_admin."""
    return await check_permission_or_admin(
        db, user_id, required_permission, raise_on_deny=True, use_http_exception=True
    )
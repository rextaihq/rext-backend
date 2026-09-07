"""Helper utility for creating audit log entries."""
from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Request
from src.api.models.audit_models.audit_logs import AuditLog
from src.utils.logger import logger
import uuid


async def create_audit_log(
    db: AsyncSession,
    user_id: Optional[uuid.UUID],
    action: str,
    resource_type: str,
    resource_id: str,
    old_values: Optional[Dict[str, Any]] = None,
    new_values: Optional[Dict[str, Any]] = None,
    request: Optional[Request] = None,
    workspace_id: Optional[uuid.UUID] = None,
    full_name: Optional[str] = None,
    user_email: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    status: str = "success",
    error_message: Optional[str] = None,
    **kwargs
) -> Optional[AuditLog]:
    """
    Create an audit log entry.

    Args:
        db: Async database session
        user_id: ID of user performing the action
        action: Action being performed (e.g., "user.suspend", "role.assign")
        resource_type: Type of resource (e.g., "user", "role", "workspace")
        resource_id: ID of the resource being acted upon
        old_values: Previous state of the resource
        new_values: New state of the resource
        request: FastAPI request object (for IP and user agent)
        workspace_id: ID of the workspace context
        full_name: Full name (denormalized for historical record)
        user_email: User email (denormalized for historical record)
        metadata: Additional context information (aliased as 'details' in some calls)
        status: Status of the action (success, failed, partial)
        error_message: Error message if status is failed
        **kwargs: Additional parameters for backward compatibility (e.g., 'details', 'username')

    Returns:
        AuditLog: Created audit log entry, or None if creation failed
    """
    # Support 'details' as an alias for 'metadata'
    if not metadata and 'details' in kwargs:
        metadata = kwargs.get('details')

    # Support 'username' as an alias for 'full_name' for backward compatibility
    if not full_name and 'username' in kwargs:
        full_name = kwargs.get('username')

    if not user_email and 'user_email' in kwargs:
        user_email = kwargs.get('user_email')

    try:
        # Backfill the denormalised actor fields from the user row when the
        # caller didn't pass them. Most call sites don't, and the audit UI
        # reads user_email directly, so without this they all render as
        # "System". db.get() hits the session identity map when the user is
        # already loaded, which is the common case.
        if user_id and (not user_email or not full_name):
            from src.api.models.user_models.users import Users
            actor = await db.get(Users, user_id)
            if actor:
                user_email = user_email or actor.email
                full_name = full_name or actor.full_name or actor.display_name

        # Extract request details if provided
        ip_address = None
        user_agent = None
        request_id = None

        if request:
            # Get IP address from request
            ip_address = request.client.host if request.client else None

            # Get user agent from headers
            user_agent = request.headers.get("user-agent")

            # Generate or extract request ID
            request_id = request.headers.get("x-request-id", str(uuid.uuid4()))

        # Create audit log entry
        audit_log = AuditLog(
            user_id=user_id,
            full_name=full_name,
            user_email=user_email,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            workspace_id=workspace_id,
            ip_address=ip_address,
            user_agent=user_agent,
            request_id=request_id,
            old_values=old_values,
            new_values=new_values,
            audit_metadata=metadata,
            status=status,
            error_message=error_message
        )

        db.add(audit_log)
        await db.flush()

        logger.info(f"Audit log created: {action} on {resource_type}:{resource_id} by user:{user_id}")
        return audit_log

    except Exception as e:
        logger.error(
            f"Failed to create audit log for action '{action}' on "
            f"{resource_type}:{resource_id}: {type(e).__name__}: {str(e)}"
        )
        # DO NOT rollback here - let the decorator handle transaction rollback
        # Rolling back here would cause the entire request transaction to fail
        return None

# Alias for backward compatibility and explicit async naming
create_audit_log_async = create_audit_log
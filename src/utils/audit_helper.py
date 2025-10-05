"""Helper utility for creating audit log entries."""
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from fastapi import Request
from src.api.models.audit_models.audit_logs import AuditLog
from src.utils.logger import logger
import uuid


def create_audit_log(
    db: Session,
    user_id: Optional[uuid.UUID],
    action: str,
    resource_type: str,
    resource_id: str,
    old_values: Optional[Dict[str, Any]] = None,
    new_values: Optional[Dict[str, Any]] = None,
    request: Optional[Request] = None,
    workspace_id: Optional[uuid.UUID] = None,
    username: Optional[str] = None,
    user_email: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    status: str = "success",
    error_message: Optional[str] = None
) -> Optional[AuditLog]:
    """
    Create an audit log entry.

    Args:
        db: Database session
        user_id: ID of user performing the action
        action: Action being performed (e.g., "user.suspend", "role.assign")
        resource_type: Type of resource (e.g., "user", "role", "workspace")
        resource_id: ID of the resource being acted upon
        old_values: Previous state of the resource
        new_values: New state of the resource
        request: FastAPI request object (for IP and user agent)
        workspace_id: ID of the workspace context
        username: Username (denormalized for historical record)
        user_email: User email (denormalized for historical record)
        metadata: Additional context information
        status: Status of the action (success, failed, partial)
        error_message: Error message if status is failed

    Returns:
        AuditLog: Created audit log entry, or None if creation failed
    """
    try:
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
            username=username,
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
        db.commit()
        db.refresh(audit_log)

        logger.info(f"Audit log created: {action} on {resource_type}:{resource_id} by user:{user_id}")
        return audit_log

    except Exception as e:
        logger.error(f"Failed to create audit log: {str(e)}")
        db.rollback()
        return None

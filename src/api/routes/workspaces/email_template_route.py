"""
Email Template Routes

Endpoints for managing workspace email templates.
"""
from fastapi import APIRouter, Depends, Request, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone
from typing import Optional

from src.utils.logger import logger
from src.utils.response_utils import success, error, created
from src.utils.db_utils import get_or_404, ensure_unique
from src.utils.route_decorators import db_transaction_handler, require_permissions
from src.utils.email_template_utils import (
    render_template,
    extract_variables,
    validate_template_variables,
    get_sample_variables,
    TEMPLATE_VARIABLES,
    DEFAULT_TEMPLATES,
    get_default_template
)
from src.api.database.async_database import get_async_db
from src.api.security.dependencies import get_current_user
from src.api.middleware.exceptions import (
    DuplicateResourceException,
    ResourceNotFoundException,
    WrextValidationException,
    WrextAuthenticationException
)
from src.api.schema.response_schemas import ErrorCode, ErrorSeverity
from src.api.schema.email_template_schema import (
    CreateEmailTemplateRequest,
    UpdateEmailTemplateRequest,
    EmailTemplateResponse,
    EmailTemplateListResponse,
    TemplateVariablesResponse,
    PreviewEmailRequest,
    PreviewEmailResponse
)
from src.api.models.user_models.users import Users
from src.api.models.workspace_models.workspace_model import WorkspaceModel
from src.api.models.workspace_models.workspace_member import WorkspaceMembers
from src.api.models.workspace_models.email_template import EmailTemplate, TemplateType

router = APIRouter(
    prefix="/workspace/email-templates",
    tags=["workspace", "email-templates"],
    responses={404: {"description": "Not found"}},
)


@router.get("/variables/{template_type}")
@db_transaction_handler("get template variables", auto_commit=False)
async def get_template_variables(
    template_type: str,
    request: Request,
):
    """
    Get available variables for a template type.

    Returns the list of variables that can be used in email templates.
    """
    if template_type not in TEMPLATE_VARIABLES:
        raise WrextValidationException(
            message="Invalid template type",
            validation_errors={"template_type": f"Unknown template type: {template_type}"}
        )

    template_info = TEMPLATE_VARIABLES[template_type]

    return {
        "template_type": template_type,
        "available_variables": template_info["variables"],
        "example_usage": template_info["example"]
    }


@router.post("/preview")
@db_transaction_handler("preview email template", auto_commit=False)
async def preview_email_template(
    preview_request: PreviewEmailRequest,
    request: Request,
):
    """
    Preview an email template with sample data.

    Renders the template with sample variable values to show what it will look like.
    """
    # Validate template variables
    is_valid, error_msg = validate_template_variables(
        preview_request.subject + " " + preview_request.body,
        preview_request.template_type
    )

    if not is_valid:
        raise WrextValidationException(
            message="Invalid template variables",
            validation_errors={"variables": error_msg}
        )

    # Get sample variables
    sample_vars = get_sample_variables(preview_request.template_type)

    # Render template
    rendered_subject = render_template(preview_request.subject, sample_vars)
    rendered_body = render_template(preview_request.body, sample_vars)

    # Extract variables used
    variables_used = extract_variables(preview_request.subject + " " + preview_request.body)

    return {
        "subject": rendered_subject,
        "body": rendered_body,
        "variables_used": variables_used
    }


@router.get("/{workspace_id}")
@db_transaction_handler("list email templates", auto_commit=False)
async def list_email_templates(
    workspace_id: str,
    request: Request,
    template_type: Optional[str] = Query(None, description="Filter by template type"),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    List all email templates for a workspace.

    Optionally filter by template type.
    """
    user_id = current_user.get("identity")

    # Verify workspace exists and user has access
    result = await db.execute(
        select(WorkspaceMembers).where(
            WorkspaceMembers.workspace_id == workspace_id,
            WorkspaceMembers.user_id == user_id
        )
    )
    membership = result.scalar_one_or_none()

    if not membership:
        raise WrextAuthenticationException(
            message="You are not a member of this workspace",
            context={"workspace_id": workspace_id}
        )

    # Build query
    query = select(EmailTemplate).where(
        EmailTemplate.workspace_id == workspace_id
    )

    if template_type:
        query = query.where(EmailTemplate.template_type == template_type)

    result = await db.execute(query.order_by(EmailTemplate.created_at.desc()))
    templates = result.scalars().all()

    return {
        "templates": [t.to_dict() for t in templates],
        "total_count": len(templates)
    }


@router.post("/", status_code=status.HTTP_201_CREATED)
@db_transaction_handler("create email template", auto_commit=True)
@require_permissions("workspace.update", workspace_scoped=True)
async def create_email_template(
    template_data: CreateEmailTemplateRequest,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Create a new email template for a workspace.

    Validates template variables and creates the template.
    """
    user_id = current_user.get("identity")

    # Verify workspace exists and user has access
    result = await db.execute(
        select(WorkspaceMembers).where(
            WorkspaceMembers.workspace_id == template_data.workspace_id,
            WorkspaceMembers.user_id == user_id
        )
    )
    membership = result.scalar_one_or_none()

    if not membership:
        raise WrextAuthenticationException(
            message="You are not a member of this workspace",
            context={"workspace_id": template_data.workspace_id}
        )

    # Validate template type
    try:
        template_type_enum = TemplateType(template_data.template_type)
    except ValueError:
        raise WrextValidationException(
            message="Invalid template type",
            validation_errors={"template_type": f"Unknown template type: {template_data.template_type}"}
        )

    # Validate template variables
    is_valid, error_msg = validate_template_variables(
        template_data.subject + " " + template_data.body,
        template_data.template_type
    )

    if not is_valid:
        raise WrextValidationException(
            message="Invalid template variables",
            validation_errors={"variables": error_msg}
        )

    # Check for existing template of same type (only one active per type per workspace)
    result = await db.execute(
        select(EmailTemplate).where(
            EmailTemplate.workspace_id == template_data.workspace_id,
            EmailTemplate.template_type == template_type_enum,
            EmailTemplate.is_active == True
        )
    )
    existing_template = result.scalar_one_or_none()

    if existing_template:
        raise DuplicateResourceException(
            message="An active template of this type already exists",
            resource_type="email_template",
            conflicting_field="template_type",
            conflicting_value=template_data.template_type
        )

    # Create template
    template = EmailTemplate(
        workspace_id=template_data.workspace_id,
        template_type=template_type_enum,
        subject=template_data.subject,
        body=template_data.body,
        is_active=True,
        is_default=False,
        created_by_user_id=user_id
    )

    db.add(template)
    await db.flush()
    await db.refresh(template)

    logger.info(f"Created email template {template.id} for workspace {template_data.workspace_id}")

    return template.to_dict()


@router.put("/{template_id}")
@db_transaction_handler("update email template", auto_commit=True)
@require_permissions("workspace.update", workspace_scoped=True)
async def update_email_template(
    template_id: str,
    template_data: UpdateEmailTemplateRequest,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Update an existing email template.

    Validates template variables if subject or body is being updated.
    """
    user_id = current_user.get("identity")

    # Get template
    template = await get_or_404(db, EmailTemplate, template_id, "email_template")

    # Verify user has access to workspace
    result = await db.execute(
        select(WorkspaceMembers).where(
            WorkspaceMembers.workspace_id == template.workspace_id,
            WorkspaceMembers.user_id == user_id
        )
    )
    membership = result.scalar_one_or_none()

    if not membership:
        raise WrextAuthenticationException(
            message="You are not a member of this workspace",
            context={"workspace_id": str(template.workspace_id)}
        )

    # Update fields
    if template_data.subject is not None:
        template.subject = template_data.subject
    if template_data.body is not None:
        template.body = template_data.body
    if template_data.is_active is not None:
        template.is_active = template_data.is_active

    # Validate if content changed
    if template_data.subject or template_data.body:
        template_type_str = template.template_type.value if isinstance(template.template_type, TemplateType) else template.template_type
        is_valid, error_msg = validate_template_variables(
            template.subject + " " + template.body,
            template_type_str
        )

        if not is_valid:
            raise WrextValidationException(
                message="Invalid template variables",
                validation_errors={"variables": error_msg}
            )

    template.updated_at = datetime.now(timezone.utc)

    await db.flush()
    await db.refresh(template)

    logger.info(f"Updated email template {template_id}")

    return template.to_dict()


@router.delete("/{template_id}")
@db_transaction_handler("delete email template", auto_commit=True)
@require_permissions("workspace.update", workspace_scoped=True)
async def delete_email_template(
    template_id: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Delete an email template.

    Cannot delete default templates.
    """
    user_id = current_user.get("identity")

    # Get template
    template = await get_or_404(db, EmailTemplate, template_id, "email_template")

    # Verify user has access to workspace
    result = await db.execute(
        select(WorkspaceMembers).where(
            WorkspaceMembers.workspace_id == template.workspace_id,
            WorkspaceMembers.user_id == user_id
        )
    )
    membership = result.scalar_one_or_none()

    if not membership:
        raise WrextAuthenticationException(
            message="You are not a member of this workspace",
            context={"workspace_id": str(template.workspace_id)}
        )

    # Cannot delete default templates
    if template.is_default:
        raise WrextValidationException(
            message="Cannot delete default templates",
            validation_errors={"template_id": "This is a default template"}
        )

    await db.delete(template)

    logger.info(f"Deleted email template {template_id}")

    return {"template_id": template_id}


@router.get("/defaults/{template_type}")
@db_transaction_handler("get default template", auto_commit=False)
async def get_default_template_for_type(
    template_type: str,
    request: Request,
):
    """
    Get the default template for a specific type.

    Useful for resetting or starting with a default template.
    """
    default_template = get_default_template(template_type)

    if not default_template:
        raise ResourceNotFoundException(
            message="Default template not found",
            resource_type="default_template",
            resource_id=template_type
        )

    return {
        "template_type": template_type,
        "subject": default_template["subject"],
        "body": default_template["body"]
    }

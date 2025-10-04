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
async def get_template_variables(
    template_type: str,
    request: Request,
):
    """
    Get available variables for a template type.

    Returns the list of variables that can be used in email templates.
    """
    try:
        if template_type not in TEMPLATE_VARIABLES:
            raise WrextValidationException(
                message="Invalid template type",
                validation_errors={"template_type": f"Unknown template type: {template_type}"}
            )

        template_info = TEMPLATE_VARIABLES[template_type]

        return success(
            data={
                "template_type": template_type,
                "available_variables": template_info["variables"],
                "example_usage": template_info["example"]
            },
            request=request,
            message="Template variables retrieved successfully"
        )

    except WrextValidationException:
        raise
    except Exception as e:
        logger.error(f"Error getting template variables: {str(e)}")
        return error(
            message="Failed to get template variables",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.LOW,
            request=request
        )


@router.post("/preview")
async def preview_email_template(
    preview_request: PreviewEmailRequest,
    request: Request,
):
    """
    Preview an email template with sample data.

    Renders the template with sample variable values to show what it will look like.
    """
    try:
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

        return success(
            data={
                "subject": rendered_subject,
                "body": rendered_body,
                "variables_used": variables_used
            },
            request=request,
            message="Template preview generated successfully"
        )

    except WrextValidationException:
        raise
    except Exception as e:
        logger.error(f"Error previewing template: {str(e)}")
        return error(
            message="Failed to preview template",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.LOW,
            request=request
        )


@router.get("/{workspace_id}")
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
    try:
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

        return success(
            data={
                "templates": [t.to_dict() for t in templates],
                "total_count": len(templates)
            },
            request=request,
            message="Email templates retrieved successfully"
        )

    except WrextAuthenticationException:
        raise
    except Exception as e:
        logger.error(f"Error listing email templates: {str(e)}")
        return error(
            message="Failed to list email templates",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.MEDIUM,
            request=request
        )


@router.post("/", status_code=status.HTTP_201_CREATED)
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
    try:
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
        await db.commit()
        await db.refresh(template)

        logger.info(f"Created email template {template.id} for workspace {template_data.workspace_id}")

        return created(
            data=template.to_dict(),
            request=request,
            message="Email template created successfully"
        )

    except (DuplicateResourceException, WrextAuthenticationException, WrextValidationException):
        raise
    except Exception as e:
        logger.error(f"Error creating email template: {str(e)}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create email template"
        )


@router.put("/{template_id}")
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
    try:
        user_id = current_user.get("identity")

        # Get template
        result = await db.execute(select(EmailTemplate).where(EmailTemplate.id == template_id))
        template = result.scalar_one_or_none()

        if not template:
            raise ResourceNotFoundException(
                message="Email template not found",
                resource_type="email_template",
                resource_id=template_id
            )

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

        await db.commit()
        await db.refresh(template)

        logger.info(f"Updated email template {template_id}")

        return success(
            data=template.to_dict(),
            request=request,
            message="Email template updated successfully"
        )

    except (ResourceNotFoundException, WrextAuthenticationException, WrextValidationException):
        raise
    except Exception as e:
        logger.error(f"Error updating email template: {str(e)}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update email template"
        )


@router.delete("/{template_id}")
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
    try:
        user_id = current_user.get("identity")

        # Get template
        result = await db.execute(select(EmailTemplate).where(EmailTemplate.id == template_id))
        template = result.scalar_one_or_none()

        if not template:
            raise ResourceNotFoundException(
                message="Email template not found",
                resource_type="email_template",
                resource_id=template_id
            )

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
        await db.commit()

        logger.info(f"Deleted email template {template_id}")

        return success(
            data={"template_id": template_id},
            request=request,
            message="Email template deleted successfully"
        )

    except (ResourceNotFoundException, WrextAuthenticationException, WrextValidationException):
        raise
    except Exception as e:
        logger.error(f"Error deleting email template: {str(e)}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete email template"
        )


@router.get("/defaults/{template_type}")
async def get_default_template_for_type(
    template_type: str,
    request: Request,
):
    """
    Get the default template for a specific type.

    Useful for resetting or starting with a default template.
    """
    try:
        default_template = get_default_template(template_type)

        if not default_template:
            raise ResourceNotFoundException(
                message="Default template not found",
                resource_type="default_template",
                resource_id=template_type
            )

        return success(
            data={
                "template_type": template_type,
                "subject": default_template["subject"],
                "body": default_template["body"]
            },
            request=request,
            message="Default template retrieved successfully"
        )

    except ResourceNotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error getting default template: {str(e)}")
        return error(
            message="Failed to get default template",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.LOW,
            request=request
        )

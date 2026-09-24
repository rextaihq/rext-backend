"""
Email Template Service - Business Logic for Email Template Management

This service encapsulates all business logic related to email template
management, including template CRUD operations, validation, and rendering.

Responsibilities:
- Email template creation, update, and deletion
- Template variable validation
- Template rendering with sample data
- Workspace membership verification
- Default template management

Does NOT:
- Handle HTTP requests/responses (that's routes)
- Commit transactions (that's decorators/routes)
- Send actual emails (that's email service)
"""

from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.middleware.exceptions import (
    DuplicateResourceException,
    ResourceNotFoundException,
    RextAuthenticationException,
    RextValidationException,
)
from src.api.models.workspace_models.email_template import EmailTemplate, TemplateType
from src.api.models.workspace_models.workspace_member import WorkspaceMembers
from src.utils.email_template_utils import (
    TEMPLATE_VARIABLES,
    extract_variables,
    get_default_template,
    get_sample_variables,
    render_template,
    validate_template_variables,
)
from src.utils.logger import logger


class EmailTemplateService:
    """Service for email template management"""

    def __init__(self, db: AsyncSession):
        """
        Initialize EmailTemplateService.

        Args:
            db: Async database session
        """
        self.db = db

    async def get_template_variables(self, template_type: str) -> Dict[str, Any]:
        """
        Get available variables for a template type.

        Args:
            template_type: Template type string

        Returns:
            Dict with template_type, available_variables, and example_usage

        Raises:
            RextValidationException: If template type is invalid
        """
        if template_type not in TEMPLATE_VARIABLES:
            raise RextValidationException(
                message="Invalid template type",
                field_errors={"template_type": [f"Unknown template type: {template_type}"]},
            )

        template_info = TEMPLATE_VARIABLES[template_type]

        return {
            "template_type": template_type,
            "available_variables": template_info["variables"],
            "example_usage": template_info["example"],
        }

    async def preview_template(self, subject: str, body: str, template_type: str) -> Dict[str, Any]:
        """
        Preview email template with sample data.

        Business Rules:
        - Validates template variables before rendering
        - Uses sample data for preview
        - Extracts variables used in template

        Args:
            subject: Email subject template
            body: Email body template
            template_type: Type of template

        Returns:
            Dict with rendered subject, body, and variables_used

        Raises:
            RextValidationException: If template variables are invalid
        """
        # Validate template variables
        is_valid, error_msg = validate_template_variables(subject + " " + body, template_type)

        if not is_valid:
            raise RextValidationException(
                message="Invalid template variables", field_errors={"variables": [error_msg]}
            )

        # Get sample variables
        sample_vars = get_sample_variables(template_type)

        # Render template
        rendered_subject = render_template(subject, sample_vars)
        rendered_body = render_template(body, sample_vars)

        # Extract variables used
        variables_used = extract_variables(subject + " " + body)

        return {
            "subject": rendered_subject,
            "body": rendered_body,
            "variables_used": variables_used,
        }

    async def list_templates(
        self, workspace_id: UUID, user_id: UUID, template_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        List email templates for a workspace.

        Business Rules:
        - User must be workspace member
        - Can filter by template type

        Args:
            workspace_id: Workspace UUID
            user_id: User UUID (for membership check)
            template_type: Optional template type filter

        Returns:
            Dict with templates list and total_count

        Raises:
            RextAuthenticationException: If user not workspace member
        """
        # Verify workspace membership
        await self._verify_workspace_membership(workspace_id, user_id)

        # Build query
        query = select(EmailTemplate).where(EmailTemplate.workspace_id == workspace_id)

        if template_type:
            query = query.where(EmailTemplate.template_type == template_type)

        result = await self.db.execute(query.order_by(EmailTemplate.created_at.desc()))
        templates = result.scalars().all()

        return {"templates": [t.to_dict() for t in templates], "total_count": len(templates)}

    async def create_template(
        self, workspace_id: UUID, user_id: UUID, template_type: str, subject: str, body: str
    ) -> EmailTemplate:
        """
        Create new email template.

        Business Rules:
        - User must be workspace member
        - Template type must be valid
        - Template variables must be valid
        - Only one active template per type per workspace

        Args:
            workspace_id: Workspace UUID
            user_id: User UUID (creator)
            template_type: Template type string
            subject: Email subject template
            body: Email body template

        Returns:
            Created EmailTemplate object

        Raises:
            RextAuthenticationException: If user not workspace member
            RextValidationException: If template type or variables invalid
            DuplicateResourceException: If active template exists
        """
        # Verify workspace membership
        await self._verify_workspace_membership(workspace_id, user_id)
        await self._verify_workspace_write_permission(workspace_id, user_id)

        # Validate template type
        try:
            template_type_enum = TemplateType(template_type)
        except ValueError:
            raise RextValidationException(
                message="Invalid template type",
                field_errors={"template_type": [f"Unknown template type: {template_type}"]},
            )

        # Validate template variables
        is_valid, error_msg = validate_template_variables(subject + " " + body, template_type)

        if not is_valid:
            raise RextValidationException(
                message="Invalid template variables", field_errors={"variables": [error_msg]}
            )

        # Check for existing active template of same type
        result = await self.db.execute(
            select(EmailTemplate).where(
                EmailTemplate.workspace_id == workspace_id,
                EmailTemplate.template_type == template_type_enum,
                EmailTemplate.is_active.is_(True),
            )
        )
        existing_template = result.scalar_one_or_none()

        if existing_template:
            raise DuplicateResourceException(
                message="An active template of this type already exists",
                resource_type="email_template",
                conflicting_field="template_type",
                conflicting_value=template_type,
            )

        # Create template
        template = EmailTemplate(
            workspace_id=workspace_id,
            template_type=template_type_enum,
            subject=subject,
            body=body,
            is_active=True,
            is_default=False,
            created_by_user_id=user_id,
        )

        self.db.add(template)
        await self.db.flush()
        await self.db.refresh(template)

        logger.info(
            f"Created email template {template.id} for workspace {workspace_id}",
            extra={"template_id": str(template.id), "template_type": template_type},
        )

        return template

    async def update_template(
        self,
        template_id: UUID,
        user_id: UUID,
        subject: Optional[str] = None,
        body: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> EmailTemplate:
        """
        Update email template.

        Business Rules:
        - User must be workspace member
        - Validates template variables if content changed
        - Updates timestamp

        Args:
            template_id: Template UUID
            user_id: User UUID (for membership check)
            subject: Optional new subject
            body: Optional new body
            is_active: Optional active status

        Returns:
            Updated EmailTemplate object

        Raises:
            ResourceNotFoundException: If template not found
            RextAuthenticationException: If user not workspace member
            RextValidationException: If variables invalid
        """
        # Get template
        template = await self._get_template_or_404(template_id)

        # Verify workspace membership
        await self._verify_workspace_membership(template.workspace_id, user_id)
        await self._verify_workspace_write_permission(template.workspace_id, user_id)

        # Update fields
        if subject is not None:
            template.subject = subject
        if body is not None:
            template.body = body
        if is_active is not None:
            template.is_active = is_active

        # Validate if content changed
        if subject or body:
            template_type_str = (
                template.template_type.value
                if isinstance(template.template_type, TemplateType)
                else template.template_type
            )
            is_valid, error_msg = validate_template_variables(
                template.subject + " " + template.body, template_type_str
            )

            if not is_valid:
                raise RextValidationException(
                    message="Invalid template variables", field_errors={"variables": [error_msg]}
                )

        template.updated_at = datetime.now(timezone.utc)

        await self.db.flush()
        await self.db.refresh(template)

        logger.info(
            f"Updated email template {template_id}", extra={"template_id": str(template_id)}
        )

        return template

    async def delete_template(self, template_id: UUID, user_id: UUID) -> None:
        """
        Delete email template.

        Business Rules:
        - User must be workspace member
        - Cannot delete default templates

        Args:
            template_id: Template UUID
            user_id: User UUID (for membership check)

        Raises:
            ResourceNotFoundException: If template not found
            RextAuthenticationException: If user not workspace member
            RextValidationException: If trying to delete default template
        """
        # Get template
        template = await self._get_template_or_404(template_id)

        # Verify workspace membership
        await self._verify_workspace_membership(template.workspace_id, user_id)
        await self._verify_workspace_write_permission(template.workspace_id, user_id)

        # Cannot delete default templates
        if template.is_default:
            raise RextValidationException(
                message="Cannot delete default templates",
                field_errors={"template_id": ["This is a default template"]},
            )

        await self.db.delete(template)

        logger.info(
            f"Deleted email template {template_id}", extra={"template_id": str(template_id)}
        )

    async def get_default_template(self, template_type: str) -> Dict[str, str]:
        """
        Get default template for a specific type.

        Args:
            template_type: Template type string

        Returns:
            Dict with template_type, subject, and body

        Raises:
            ResourceNotFoundException: If default template not found
        """
        default_template = get_default_template(template_type)

        if not default_template:
            raise ResourceNotFoundException(
                resource_type="default_template",
                resource_id=template_type,
                message="Default template not found",
            )

        return {
            "template_type": template_type,
            "subject": default_template["subject"],
            "body": default_template["body"],
        }

    # ========================================================================
    # Private Helper Methods
    # ========================================================================

    async def _get_template_or_404(self, template_id: UUID) -> EmailTemplate:
        """
        Get email template or raise 404.

        Args:
            template_id: Template UUID

        Returns:
            EmailTemplate object

        Raises:
            ResourceNotFoundException: If template not found
        """
        result = await self.db.execute(select(EmailTemplate).where(EmailTemplate.id == template_id))
        template = result.scalar_one_or_none()

        if not template:
            raise ResourceNotFoundException(
                resource_type="EmailTemplate", resource_id=str(template_id)
            )

        return template

    async def _verify_workspace_membership(
        self, workspace_id: UUID, user_id: UUID
    ) -> WorkspaceMembers:
        """
        Verify user is workspace member.

        Args:
            workspace_id: Workspace UUID
            user_id: User UUID

        Returns:
            WorkspaceMembers object

        Raises:
            RextAuthenticationException: If user not member
        """
        result = await self.db.execute(
            select(WorkspaceMembers).where(
                WorkspaceMembers.workspace_id == workspace_id, WorkspaceMembers.user_id == user_id
            )
        )
        membership = result.scalar_one_or_none()

        if not membership:
            raise RextAuthenticationException(
                message="You are not a member of this workspace",
                context={"workspace_id": str(workspace_id)},
            )

        return membership

    async def _verify_workspace_write_permission(self, workspace_id: UUID, user_id: UUID) -> None:
        """
        Require workspace.update in this workspace for template writes.

        SEC-RBAC-13: the route decorators for create/update/delete were declared
        workspace_scoped=True without a workspace_id parameter, so they raised
        and every write 500'd. The permission check lives here instead, where the
        workspace_id is always known. Membership is verified by the caller.
        """
        from src.api.middleware.exceptions import RextAuthorizationException
        from src.utils import rbac_utils

        if await rbac_utils.is_user_super_admin(self.db, user_id):
            return
        if not await rbac_utils.check_all_permissions(
            self.db, user_id, ["workspace.update"], workspace_id
        ):
            raise RextAuthorizationException(
                message="You do not have permission to manage email templates",
                context={"required_permission": "workspace.update"},
            )

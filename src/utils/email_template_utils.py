"""
Email Template Utilities

Handles rendering of email templates with variable substitution.
"""

import re
from typing import Dict, List, Optional

# Template variable definitions for each template type
TEMPLATE_VARIABLES = {
    "workspace_invitation": {
        "variables": [
            {
                "name": "workspace_name",
                "description": "Name of the workspace",
                "example": "My Awesome Workspace",
            },
            {
                "name": "inviter_name",
                "description": "Name of person sending invitation",
                "example": "John Doe",
            },
            {
                "name": "recipient_email",
                "description": "Email of the recipient",
                "example": "jane@example.com",
            },
            {"name": "role_name", "description": "Role being assigned", "example": "Editor"},
            {
                "name": "invitation_url",
                "description": "Link to accept invitation",
                "example": "https://app.rext.ai/accept?token=abc123",
            },
            {"name": "expiry_days", "description": "Days until invitation expires", "example": "7"},
        ],
        "example": """
Subject: You're invited to join {{workspace_name}}

Hi there,

{{inviter_name}} has invited you to join the "{{workspace_name}}" workspace as a {{role_name}}.

Click the link below to accept the invitation:
{{invitation_url}}

This invitation will expire in {{expiry_days}} days.

Best regards,
The Rext AI Team
        """,
    },
    "invitation_accepted": {
        "variables": [
            {
                "name": "workspace_name",
                "description": "Name of the workspace",
                "example": "My Awesome Workspace",
            },
            {
                "name": "member_name",
                "description": "Name of member who accepted",
                "example": "Jane Smith",
            },
            {
                "name": "member_email",
                "description": "Email of new member",
                "example": "jane@example.com",
            },
            {"name": "role_name", "description": "Role assigned", "example": "Editor"},
        ],
        "example": """
Subject: {{member_name}} has joined {{workspace_name}}

Good news!

{{member_name}} ({{member_email}}) has accepted your invitation and joined the "{{workspace_name}}" workspace as a {{role_name}}.

Best regards,
The Rext AI Team
        """,
    },
    "role_changed": {
        "variables": [
            {
                "name": "workspace_name",
                "description": "Name of the workspace",
                "example": "My Awesome Workspace",
            },
            {
                "name": "recipient_name",
                "description": "Name of member whose role changed",
                "example": "Jane Smith",
            },
            {"name": "old_role_name", "description": "Previous role", "example": "Viewer"},
            {"name": "new_role_name", "description": "New role", "example": "Editor"},
            {
                "name": "changed_by_name",
                "description": "Person who made the change",
                "example": "John Doe",
            },
        ],
        "example": """
Subject: Your role in {{workspace_name}} has been updated

Hi {{recipient_name}},

Your role in the "{{workspace_name}}" workspace has been changed from {{old_role_name}} to {{new_role_name}} by {{changed_by_name}}.

Best regards,
The Rext AI Team
        """,
    },
    "member_removed": {
        "variables": [
            {
                "name": "workspace_name",
                "description": "Name of the workspace",
                "example": "My Awesome Workspace",
            },
            {
                "name": "recipient_name",
                "description": "Name of removed member",
                "example": "Jane Smith",
            },
            {
                "name": "removed_by_name",
                "description": "Person who removed the member",
                "example": "John Doe",
            },
        ],
        "example": """
Subject: You have been removed from {{workspace_name}}

Hi {{recipient_name}},

You have been removed from the "{{workspace_name}}" workspace by {{removed_by_name}}.

If you believe this was a mistake, please contact the workspace administrator.

Best regards,
The Rext AI Team
        """,
    },
    "welcome": {
        "variables": [
            {
                "name": "workspace_name",
                "description": "Name of the workspace",
                "example": "My Awesome Workspace",
            },
            {
                "name": "recipient_name",
                "description": "Name of new member",
                "example": "Jane Smith",
            },
            {"name": "role_name", "description": "Role assigned", "example": "Editor"},
        ],
        "example": """
Subject: Welcome to {{workspace_name}}!

Hi {{recipient_name}},

Welcome to the "{{workspace_name}}" workspace! You've been added as a {{role_name}}.

We're excited to have you on board.

Best regards,
The Rext AI Team
        """,
    },
}


# Default email templates
DEFAULT_TEMPLATES = {
    "workspace_invitation": {
        "subject": "You're invited to join {{workspace_name}}",
        "body": """Hi there,

{{inviter_name}} has invited you to join the "{{workspace_name}}" workspace as a {{role_name}}.

Click the link below to accept the invitation:
{{invitation_url}}

This invitation will expire in {{expiry_days}} days.

If you don't want to join this workspace, you can ignore this email.

Best regards,
The Rext AI Team""",
    },
    "invitation_accepted": {
        "subject": "{{member_name}} has joined {{workspace_name}}",
        "body": """Good news!

{{member_name}} ({{member_email}}) has accepted your invitation and joined the "{{workspace_name}}" workspace as a {{role_name}}.

Best regards,
The Rext AI Team""",
    },
    "role_changed": {
        "subject": "Your role in {{workspace_name}} has been updated",
        "body": """Hi {{recipient_name}},

Your role in the "{{workspace_name}}" workspace has been changed from {{old_role_name}} to {{new_role_name}} by {{changed_by_name}}.

Your permissions have been updated accordingly.

Best regards,
The Rext AI Team""",
    },
    "member_removed": {
        "subject": "You have been removed from {{workspace_name}}",
        "body": """Hi {{recipient_name}},

You have been removed from the "{{workspace_name}}" workspace by {{removed_by_name}}.

If you believe this was a mistake, please contact the workspace administrator.

Best regards,
The Rext AI Team""",
    },
    "welcome": {
        "subject": "Welcome to {{workspace_name}}!",
        "body": """Hi {{recipient_name}},

Welcome to the "{{workspace_name}}" workspace! You've been added as a {{role_name}}.

We're excited to have you on board.

Best regards,
The Rext AI Team""",
    },
}


def render_template(template: str, variables: Dict[str, str]) -> str:
    """
    Render a template string by replacing variables.

    Args:
        template: Template string with {{variable}} placeholders
        variables: Dictionary of variable names and values

    Returns:
        Rendered template string
    """
    rendered = template
    for key, value in variables.items():
        placeholder = f"{{{{{key}}}}}"
        rendered = rendered.replace(placeholder, str(value))

    return rendered


def extract_variables(template: str) -> List[str]:
    """
    Extract all variable names from a template.

    Args:
        template: Template string with {{variable}} placeholders

    Returns:
        List of variable names found in template
    """
    pattern = r"\{\{(\w+)\}\}"
    matches = re.findall(pattern, template)
    return list(set(matches))  # Remove duplicates


def validate_template_variables(template: str, template_type: str) -> tuple[bool, Optional[str]]:
    """
    Validate that a template only uses allowed variables for its type.

    Args:
        template: Template string to validate
        template_type: Type of template (workspace_invitation, etc.)

    Returns:
        Tuple of (is_valid, error_message)
    """
    if template_type not in TEMPLATE_VARIABLES:
        return False, f"Unknown template type: {template_type}"

    used_variables = extract_variables(template)
    allowed_variables = [v["name"] for v in TEMPLATE_VARIABLES[template_type]["variables"]]

    invalid_variables = [v for v in used_variables if v not in allowed_variables]

    if invalid_variables:
        return (
            False,
            f"Invalid variables: {', '.join(invalid_variables)}. Allowed: {', '.join(allowed_variables)}",
        )

    return True, None


def get_sample_variables(template_type: str) -> Dict[str, str]:
    """
    Get sample variable values for preview purposes.

    Args:
        template_type: Type of template

    Returns:
        Dictionary of variable names and sample values
    """
    if template_type not in TEMPLATE_VARIABLES:
        return {}

    variables = TEMPLATE_VARIABLES[template_type]["variables"]
    return {v["name"]: v["example"] for v in variables}


def get_default_template(template_type: str) -> Optional[Dict[str, str]]:
    """
    Get the default template for a given type.

    Args:
        template_type: Type of template

    Returns:
        Dictionary with 'subject' and 'body' keys, or None if not found
    """
    return DEFAULT_TEMPLATES.get(template_type)


async def get_workspace_template(db, workspace_id: str, template_type: str) -> Dict[str, str]:
    """
    Get email template for a workspace, falling back to default if not found.

    Lookup order:
    1. Workspace-specific custom template (workspace_id matches, is_default=False)
    2. Database default template (is_default=True)
    3. Hardcoded default template
    4. Generic fallback

    Args:
        db: Async database session
        workspace_id: ID of the workspace
        template_type: Type of template (string value like "workspace_invitation")

    Returns:
        Dictionary with 'subject' and 'body' keys
    """
    from sqlalchemy import String, cast, select

    from src.api.models.workspace_models.email_template import EmailTemplate
    from src.utils.logger import logger

    try:
        # First, try to find active custom template for this specific workspace
        # Use cast() to ensure proper type comparison with the database enum
        query = select(EmailTemplate).where(
            EmailTemplate.workspace_id == workspace_id,
            cast(EmailTemplate.template_type, String) == template_type,
            EmailTemplate.is_active.is_(True),
            EmailTemplate.is_default.is_(False),
        )
        result = await db.execute(query)
        custom_template = result.scalar_one_or_none()

        if custom_template:
            return {"subject": custom_template.subject, "body": custom_template.body}

        # Second, try to find database default template (is_default=True)
        default_query = select(EmailTemplate).where(
            EmailTemplate.workspace_id == workspace_id,
            cast(EmailTemplate.template_type, String) == template_type,
            EmailTemplate.is_active.is_(True),
            EmailTemplate.is_default.is_(True),
        )
        result = await db.execute(default_query)
        db_default_template = result.scalar_one_or_none()

        if db_default_template:
            return {"subject": db_default_template.subject, "body": db_default_template.body}
    except Exception as e:
        # If database query fails, log the error and continue to hardcoded defaults
        logger.error(f"Error fetching email template from database: {str(e)}")
        pass

    # Third, fall back to hardcoded default template
    hardcoded_default = get_default_template(template_type)
    if hardcoded_default:
        return hardcoded_default

    # Ultimate fallback
    return {"subject": "Notification from Rext AI", "body": "You have a notification from Rext AI."}


async def render_workspace_email(
    db, workspace_id: str, template_type: str, variables: Dict[str, str]
) -> Dict[str, str]:
    """
    Get and render an email template for a workspace.

    Args:
        db: Async database session
        workspace_id: ID of the workspace
        template_type: Type of template
        variables: Dictionary of variable values to substitute

    Returns:
        Dictionary with rendered 'subject' and 'body'
    """
    template = await get_workspace_template(db, workspace_id, template_type)

    return {
        "subject": render_template(template["subject"], variables),
        "body": render_template(template["body"], variables),
    }

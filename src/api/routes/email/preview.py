"""
Email Preview Routes

API endpoints for previewing email templates before sending.
Useful for testing and debugging email designs.
"""
import sys
from pathlib import Path
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import HTMLResponse
from typing import Literal
import os

# Add emails directory to path
emails_path = Path(__file__).parent.parent.parent.parent.parent / "emails"
sys.path.insert(0, str(emails_path.parent))

from src.api.schema.email_preview_schema import (
    AuthEmailPreviewRequest,
    WorkspaceEmailPreviewRequest,
    EmailPreviewResponse
)
from src.api.security.dependencies import get_current_user
from src.utils.logger import logger

# Import email templates
from emails.templates.auth import (
    create_verification_email,
    create_password_reset_email,
    create_welcome_email
)
from emails.templates.workspace import (
    create_workspace_invitation_email,
    create_invitation_accepted_email,
    create_role_changed_email,
    create_member_removed_email
)

router = APIRouter(
    prefix="/preview",
    tags=["email-preview"]
)


def get_subject_for_template(template_type: str, **kwargs) -> str:
    """Get suggested subject line for template type."""
    subjects = {
        # Auth templates
        "verification": "Verify Your Email Address - WREXT",
        "password_reset": "Reset Your Password - WREXT",
        "welcome": "Welcome to WREXT!",
        # Workspace templates
        "invitation": f"You've been invited to join {kwargs.get('workspace_name', 'a workspace')}",
        "invitation_accepted": f"New member joined {kwargs.get('workspace_name', 'your workspace')}",
        "role_changed": f"Your role in {kwargs.get('workspace_name', 'the workspace')} has been updated",
        "member_removed": f"Removed from {kwargs.get('workspace_name', 'workspace')}"
    }
    return subjects.get(template_type, "Email from WREXT")


def extract_preview_text(html: str) -> str:
    """Extract preview text from HTML email."""
    # Look for preview text div
    import re
    match = re.search(r'<div[^>]*display: none[^>]*>([^<]+)</div>', html)
    if match:
        return match.group(1).strip()
    return ""


@router.post("/auth", response_model=EmailPreviewResponse)
async def preview_auth_email(
    request: AuthEmailPreviewRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Preview auth email templates.

    Generates a preview of authentication emails (verification, password reset, welcome).
    Useful for testing designs before deploying changes.

    **Requires authentication** - Only accessible to logged-in users.
    """
    try:
        frontend_url = request.frontend_url or os.getenv("FRONTEND_URL", "https://app.wrext.com")

        # Generate HTML based on template type
        if request.template_type == "verification":
            html = create_verification_email(
                user_name=request.user_name,
                verification_token=request.token,
                frontend_url=frontend_url
            )

        elif request.template_type == "password_reset":
            html = create_password_reset_email(
                user_name=request.user_name,
                reset_token=request.token,
                user_email=request.user_email,
                frontend_url=frontend_url
            )

        elif request.template_type == "welcome":
            html = create_welcome_email(
                user_name=request.user_name,
                frontend_url=frontend_url
            )

        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown template type: {request.template_type}"
            )

        # Extract preview text
        preview_text = extract_preview_text(html)

        # Get subject
        subject = get_subject_for_template(request.template_type)

        logger.info(
            f"Auth email preview generated",
            extra={
                "template_type": request.template_type,
                "user_id": current_user.get("identity"),
                "size_bytes": len(html)
            }
        )

        return EmailPreviewResponse(
            html=html,
            template_type=request.template_type,
            subject=subject,
            preview_text=preview_text,
            metadata={
                "template_name": f"Auth - {request.template_type.replace('_', ' ').title()}",
                "size_bytes": len(html),
                "frontend_url": frontend_url
            }
        )

    except Exception as e:
        logger.error(f"Failed to preview auth email: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate preview: {str(e)}"
        )


@router.post("/workspace", response_model=EmailPreviewResponse)
async def preview_workspace_email(
    request: WorkspaceEmailPreviewRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Preview workspace email templates.

    Generates a preview of workspace emails (invitation, invitation_accepted,
    role_changed, member_removed).

    **Requires authentication** - Only accessible to logged-in users.
    """
    try:
        frontend_url = request.frontend_url or os.getenv("FRONTEND_URL", "https://app.wrext.com")

        # Generate HTML based on template type
        if request.template_type == "invitation":
            html = create_workspace_invitation_email(
                workspace_name=request.workspace_name,
                inviter_name=request.user_name,
                invitation_token=request.invitation_token,
                role_name=request.role_name,
                expiry_days=request.expiry_days,
                workspace_description=request.workspace_description,
                frontend_url=frontend_url
            )

        elif request.template_type == "invitation_accepted":
            html = create_invitation_accepted_email(
                workspace_name=request.workspace_name,
                new_member_name=request.secondary_user_name or request.user_name,
                new_member_email=request.user_email or "member@example.com",
                role_name=request.role_name,
                workspace_id=request.workspace_id,
                frontend_url=frontend_url
            )

        elif request.template_type == "role_changed":
            html = create_role_changed_email(
                workspace_name=request.workspace_name,
                member_name=request.user_name,
                old_role_name=request.old_role_name or "Viewer",
                new_role_name=request.role_name,
                changed_by_name=request.secondary_user_name or "Admin",
                workspace_id=request.workspace_id,
                frontend_url=frontend_url
            )

        elif request.template_type == "member_removed":
            html = create_member_removed_email(
                workspace_name=request.workspace_name,
                member_name=request.user_name,
                removed_by_name=request.secondary_user_name or "Admin",
                reason=request.reason,
                frontend_url=frontend_url
            )

        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown template type: {request.template_type}"
            )

        # Extract preview text
        preview_text = extract_preview_text(html)

        # Get subject
        subject = get_subject_for_template(
            request.template_type,
            workspace_name=request.workspace_name
        )

        logger.info(
            f"Workspace email preview generated",
            extra={
                "template_type": request.template_type,
                "workspace_name": request.workspace_name,
                "user_id": current_user.get("identity"),
                "size_bytes": len(html)
            }
        )

        return EmailPreviewResponse(
            html=html,
            template_type=request.template_type,
            subject=subject,
            preview_text=preview_text,
            metadata={
                "template_name": f"Workspace - {request.template_type.replace('_', ' ').title()}",
                "size_bytes": len(html),
                "workspace_name": request.workspace_name,
                "frontend_url": frontend_url
            }
        )

    except Exception as e:
        logger.error(f"Failed to preview workspace email: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate preview: {str(e)}"
        )


@router.post("/auth/html", response_class=HTMLResponse)
async def preview_auth_email_html(
    request: AuthEmailPreviewRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Preview auth email as raw HTML.

    Returns the HTML directly for rendering in browser or iframe.
    Useful for visual testing and design iteration.

    **Requires authentication** - Only accessible to logged-in users.
    """
    response = await preview_auth_email(request, current_user)
    return HTMLResponse(content=response.html)


@router.post("/workspace/html", response_class=HTMLResponse)
async def preview_workspace_email_html(
    request: WorkspaceEmailPreviewRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Preview workspace email as raw HTML.

    Returns the HTML directly for rendering in browser or iframe.

    **Requires authentication** - Only accessible to logged-in users.
    """
    response = await preview_workspace_email(request, current_user)
    return HTMLResponse(content=response.html)

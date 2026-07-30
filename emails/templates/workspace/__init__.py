"""
Workspace Email Templates

Templates for workspace-related notifications:
- Workspace invitation
- Invitation accepted
- Role changed
- Member removed
"""
from .invitation import render_workspace_invitation_email, create_workspace_invitation_email
from .invitation_accepted import render_invitation_accepted_email, create_invitation_accepted_email
from .role_changed import render_role_changed_email, create_role_changed_email
from .member_removed import render_member_removed_email, create_member_removed_email
from .workspace_deleted import render_workspace_deleted_email, create_workspace_deleted_email
from .workspace_restored import render_workspace_restored_email, create_workspace_restored_email

__all__ = [
    # Invitation
    "render_workspace_invitation_email",
    "create_workspace_invitation_email",
    # Invitation Accepted
    "render_invitation_accepted_email",
    "create_invitation_accepted_email",
    # Role Changed
    "render_role_changed_email",
    "create_role_changed_email",
    # Member Removed
    "render_member_removed_email",
    "create_member_removed_email",
    # Workspace Deleted
    "render_workspace_deleted_email",
    "create_workspace_deleted_email",
    # Workspace Restored
    "render_workspace_restored_email",
    "create_workspace_restored_email",
]

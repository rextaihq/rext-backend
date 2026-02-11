import sys
import os

# Add src to path
sys.path.append(os.getcwd())

try:
    from src.api.models.user_models.user_roles import UserRole
    from src.api.models.user_models.role_permissions import RolePermission
    from src.api.models.workspace_models.workspace_member import WorkspaceMembers
    from src.api.models.workspace_models.workspace_model import WorkspaceModel
    from src.api.models.user_models.invitations import UserInvitations
    from src.api.models.admin_models.error_log import ErrorLog
    from src.api.models.subscription_models.subscriptions import UserSubscription
    print("Successfully imported all modified models")
except Exception as e:
    print(f"Error importing models: {e}")
    import traceback
    traceback.print_exc()

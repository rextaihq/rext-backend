import json
# Import all models to resolve relationships
from src.api.models.user_models.users import Users
from src.api.models.user_models.roles import Role
from src.api.models.user_models.user_roles import UserRole
from src.api.models.user_models.permissions import Permission
from src.api.models.user_models.role_permissions import RolePermission
from src.api.models.user_models.invitations import UserInvitations
from src.api.models.workspace_models.workspace_member import WorkspaceMembers
from src.api.models.workspace_models.workspace_model import WorkspaceModel
from src.api.models.knowledge_models.knowledge_model import BrandVoice
from src.api.database.database import get_db

from src.api.models.user_models.permissions import Permission
import uuid
from datetime import datetime

permissions_to_create = [
    {"name": "content.create", "display_name": "Create Content", "description": "Allows creating new content", "resource": "content", "action": "create"},
    {"name": "content.update", "display_name": "Update Content", "description": "Allows updating content", "resource": "content", "action": "update"},
    {"name": "content.delete", "display_name": "Delete Content", "description": "Allows deleting content", "resource": "content", "action": "delete"},
    {"name": "topic.create", "display_name": "Create Topic", "description": "Allows creating new topics", "resource": "topic", "action": "create"},
    {"name": "topic.update", "display_name": "Update Topic", "description": "Allows updating topics", "resource": "topic", "action": "update"},
    {"name": "topic.delete", "display_name": "Delete Topic", "description": "Allows deleting topics", "resource": "topic", "action": "delete"},
]

db_gen = get_db()
db = next(db_gen) 

try:
    for perm_data in permissions_to_create:
        # Check if permission already exists
        exists = db.query(Permission).filter_by(name=perm_data["name"]).first()
        if not exists:
            perm = Permission(
                id=uuid.uuid4(),
                name=perm_data["name"],
                display_name=perm_data["display_name"],
                description=perm_data["description"],
                resource=perm_data["resource"],
                action=perm_data["action"],
                created_at=datetime.utcnow()
            )
            db.add(perm)

    db.commit()
    print("Default permissions seeded successfully!")

except Exception as e:
    db.rollback()
    print(f"Error seeding permissions: {e}")

finally:
    db.close()


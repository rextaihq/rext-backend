
import asyncio
from sqlalchemy import select
from src.api.database.async_database import get_async_db_context
from src.api.models.user_models.roles import Role
from src.api.models.user_models.user_roles import UserRole
from src.api.models.user_models.users import Users
from src.api.models.workspace_models.workspace_model import WorkspaceModel

async def check_roles():
    async with get_async_db_context() as db:
        # Check all Roles
        print("--- ROLES ---")
        result = await db.execute(select(Role))
        roles = result.scalars().all()
        for role in roles:
            print(f"Name: {role.name}, Hierarchy: {role.hierarchy_level}, Is WS Role: {role.is_workspace_role}")
        
        # Check Workspaces
        print("\n--- WORKSPACES ---")
        result = await db.execute(select(WorkspaceModel))
        workspaces = result.scalars().all()
        for ws in workspaces:
            print(f"ID: {ws.id}, Name: {ws.name}, Owner User ID: {ws.user_id}")
            
        # Check UserRoles
        print("\n--- USER ROLES (First 10) ---")
        result = await db.execute(select(UserRole).limit(10))
        user_roles = result.scalars().all()
        for ur in user_roles:
            print(f"User ID: {ur.user_id}, Role ID: {ur.role_id}, WS ID: {ur.workspace_id}")

if __name__ == "__main__":
    asyncio.run(check_roles())

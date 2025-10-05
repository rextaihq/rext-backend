from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID

from src.utils.logger import logger
from src.utils.response_utils import success, error
from src.utils.workspace_utils import resolve_workspace, verify_workspace_membership, resolve_and_verify_workspace
from src.utils.auth_utils import verify_current_user
from src.api.database.async_database import get_async_db
from src.api.security.dependencies import get_current_user
from src.api.middleware.exceptions import (
    ResourceNotFoundException,
    WrextAuthenticationException
)
from src.api.schema.response_schemas import ErrorCode, ErrorSeverity
from src.api.models.workspace_models.workspace_member import WorkspaceMembers
from src.api.models.user_models.users import Users
from src.api.models.knowledge_models.knowledge_model import Website, KnowledgeFiles, TextKnowledge

router = APIRouter()


# -------------------------
# Get all knowledge for workspace
# -------------------------
@router.get("/knowledge/all")
async def get_workspace_knowledge(request: Request, workspace_id: str, db: AsyncSession = Depends(get_async_db), user: dict = Depends(get_current_user)):
    """
    Get all knowledge (web, file, text) for a workspace.

    Args:
        workspace_id: Workspace UUID or slug (query parameter)

    Requires:
        - JWT authentication
        - Workspace membership verification
    """
    user_id = user.get("identity")
    db_user = await verify_current_user(db, user_id)

    try:
        # Verify workspace access and membership in one call
        workspace, membership = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

        # Get all knowledge types for this workspace
        result = await db.execute(select(Website).where(Website.workspace_id == workspace.id))
        web_knowledge = result.scalars().all()

        result = await db.execute(select(KnowledgeFiles).where(KnowledgeFiles.workspace_id == workspace.id))
        file_knowledge = result.scalars().all()

        result = await db.execute(select(TextKnowledge).where(TextKnowledge.workspace_id == workspace.id))
        text_knowledge = result.scalars().all()

        # Use to_dict() for consistent structure with type annotation
        web_data = [{"type": "web", **item.to_dict()} for item in web_knowledge]
        file_data = [{"type": "file", **item.to_dict()} for item in file_knowledge]
        text_data = [{"type": "text", **item.to_dict()} for item in text_knowledge]

        return success(
            data={
                "web_knowledge": web_data,
                "file_knowledge": file_data,
                "text_knowledge": text_data,
                "summary": {
                    "web_count": len(web_data),
                    "file_count": len(file_data),
                    "text_count": len(text_data),
                    "total_count": len(web_data) + len(file_data) + len(text_data)
                }
            },
            request=request,
            message="Retrieved all knowledge successfully"
        )

    except ResourceNotFoundException:
        raise
    except Exception as e:
        logger.exception(f"Error fetching workspace knowledge {workspace_id}")
        return error(
            message="Failed to retrieve workspace knowledge",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            request=request
        )


# -------------------------
# Get web knowledge for workspace
# -------------------------
@router.get("/knowledge/web")
async def get_workspace_web_knowledge(request: Request, workspace_id: str, db: AsyncSession = Depends(get_async_db), user: dict = Depends(get_current_user)):
    user_id = user.get("identity")
    db_user = await verify_current_user(db, user_id)

    try:
        # Verify workspace access
        workspace, membership = await verify_workspace_membership(db, UUID(workspace_id), user_id)

        # Get web knowledge for this workspace
        result = await db.execute(select(Website).where(Website.workspace_id == workspace.id))
        web_knowledge = result.scalars().all()

        # Use to_dict() to match the structure from /api/workspace/web_knowledge/all
        web_data = [item.to_dict() for item in web_knowledge]

        return success(
            data={"web_knowledge": web_data, "total_count": len(web_data)},
            request=request,
            message=f"Retrieved {len(web_data)} web knowledge items"
        )

    except ResourceNotFoundException:
        raise
    except Exception as e:
        logger.exception(f"Error fetching workspace web knowledge {workspace_id}")
        return error(
            message="Failed to retrieve web knowledge",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            request=request
        )


# -------------------------
# Get file knowledge for workspace
# -------------------------
@router.get("/knowledge/files")
async def get_workspace_file_knowledge(request: Request, workspace_id: str, db: AsyncSession = Depends(get_async_db), user: dict = Depends(get_current_user)):
    user_id = user.get("identity")
    db_user = await verify_current_user(db, user_id)

    try:
        # Verify workspace access
        workspace, membership = await verify_workspace_membership(db, UUID(workspace_id), user_id)

        # Get file knowledge for this workspace
        result = await db.execute(select(KnowledgeFiles).where(KnowledgeFiles.workspace_id == workspace.id))
        file_knowledge = result.scalars().all()

        # Use to_dict() to match the structure from /api/workspace/file/all
        file_data = [item.to_dict() for item in file_knowledge]

        return success(
            data={"file_knowledge": file_data, "total_count": len(file_data)},
            request=request,
            message=f"Retrieved {len(file_data)} file knowledge items"
        )

    except ResourceNotFoundException:
        raise
    except Exception as e:
        logger.exception(f"Error fetching workspace file knowledge {workspace_id}")
        return error(
            message="Failed to retrieve file knowledge",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            request=request
        )


# -------------------------
# Get text knowledge for workspace
# -------------------------
@router.get("/knowledge/text")
async def get_workspace_text_knowledge(request: Request, workspace_id: str, db: AsyncSession = Depends(get_async_db), user: dict = Depends(get_current_user)):
    user_id = user.get("identity")
    db_user = await verify_current_user(db, user_id)

    try:
        # Verify workspace access
        workspace, membership = await verify_workspace_membership(db, UUID(workspace_id), user_id)

        # Get text knowledge for this workspace
        result = await db.execute(select(TextKnowledge).where(TextKnowledge.workspace_id == workspace.id))
        text_knowledge = result.scalars().all()

        # Use to_dict() to match the structure from /api/workspace/text/all
        text_data = [item.to_dict() for item in text_knowledge]

        return success(
            data={"text_knowledge": text_data, "total_count": len(text_data)},
            request=request,
            message=f"Retrieved {len(text_data)} text knowledge items"
        )

    except ResourceNotFoundException:
        raise
    except Exception as e:
        logger.exception(f"Error fetching workspace text knowledge {workspace_id}")
        return error(
            message="Failed to retrieve text knowledge",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            request=request
        )

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from src.utils.logger import logger
from src.utils.route_decorators import db_transaction_handler, require_permissions
from src.api.database.async_database import get_async_db
from src.api.security.dependencies import get_current_user
from src.api.schema.content_schema import ContentCreate, ContentUpdate, ContentResponse
from src.utils.workspace_utils import resolve_and_verify_workspace
from src.services.content_service import ContentService

router = APIRouter()

# Note: This file contains other CRUD operations (update, delete, etc.)
# The publish endpoint has been moved to publish_content.py
from fastapi import APIRouter, Depends, Request, BackgroundTasks, Header
from src.utils.logger import logger
from src.api.security.dependencies import get_current_user
from src.services.notifications_services import NotificationService
from src.api.security.token_utils import verify_token
from src.api.config import get_settings
from sqlalchemy.ext.asyncio import AsyncSession
from src.services.email_service import EmailService
from src.api.database.async_database import get_async_db
from src.utils.response_utils import success, error, created
from src.api.schema.response_schemas import ErrorCode, ErrorSeverity
from src.api.middleware.exceptions import (
    DuplicateResourceException,
    WrextAuthenticationException,
    ResourceNotFoundException,
    BusinessRuleViolationException
)
from datetime import datetime
from user_agents import parse as parse_user_agent
import os
from src.api.middleware.rate_limiter import (
    login_rate_limit,
    registration_rate_limit
)
from src.services.auth_service import AuthService
from uuid import UUID

router = APIRouter()



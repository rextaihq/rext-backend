from fastapi import APIRouter, Request
from src.services.sse_service import event_stream_manager
from src.services.notifications_services import NotificationService
from uuid import UUID
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from uuid import UUID
from src.services.notifications_services import event_stream_manager
from src.api.security.token_utils import verify_token

router = APIRouter(prefix="/events", tags=["Events"])
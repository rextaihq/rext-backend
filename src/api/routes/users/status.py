from fastapi import APIRouter
from src.api.schema.response.status_responses import ServiceStatusResponse

router = APIRouter()


@router.get("/status", response_model=ServiceStatusResponse)
def get_user_status():
    """
    Endpoint to check the user service status.
    """
    return {"status": "running", "service": "user_service"}

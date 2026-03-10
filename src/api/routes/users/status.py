from fastapi import APIRouter, Request
from src.api.schema.response.status_responses import ServiceStatusResponse
from src.api.schema.response_schemas import SuccessResponse
from src.utils.response_utils import success

router = APIRouter()


@router.get("/status", response_model=SuccessResponse[ServiceStatusResponse])
def get_user_status(request: Request):
    """
    Endpoint to check the user service status.
    """
    return success(
        data={"status": "running", "service": "user_service"},
        request=request,
        message="User service is operational"
    )

from fastapi import APIRouter

router = APIRouter()


@router.get("/status")
def get_user_status():
    """
    Endpoint to check the user service status.
    """
    return {"status": "running", "service": "user_service"}

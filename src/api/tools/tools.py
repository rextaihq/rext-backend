from fastapi import APIRouter   


router = APIRouter(
    prefix="/tools",
    tags=["Tools"],
)

router.get("/")
def get_tools():
    return {"message": "Tools"}

from pydantic import BaseModel

class ServiceStatusResponse(BaseModel):
    status: str
    service: str

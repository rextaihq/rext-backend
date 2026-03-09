from pydantic import BaseModel

class GenericResponse(BaseModel):
    """
    Empty response body for action/trigger endpoints.
    These endpoints signal success via HTTP status only; no
    data fields are present. Adding model_config with
    extra='forbid' ensures the frontend schema stays clean.
    """
    model_config = {"extra": "forbid"}

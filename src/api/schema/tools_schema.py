from pydantic import BaseModel

# Input Model
class SchemaRequest(BaseModel):
    schema_type: str
    description: str


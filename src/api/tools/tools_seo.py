from fastapi import APIRouter
from src.api.tools.Schema.tools_schema import SchemaRequest
# FastAPI Router

router = APIRouter(
    prefix="/tools",
    tags=["Tools"],
)

@router.get("/")
def get_tools():
    return {"message": "Tools"}

# -----------------------------
# Schema Builder Function
# -----------------------------
def build_schema(data: SchemaRequest) -> dict:
    """
    Build Schema.org JSON-LD directly from request data.
    Only includes fields that are provided by the user.
    """
    schema = {
        "@context": "https://schema.org",
        "@type": data.schema_type,
        "name": data.name
    }

    # Only add optional fields if they are provided
    if data.description:
        schema["description"] = data.description

    if data.url:
        schema["url"] = data.url

    if data.image_url:
        schema["image"] = data.image_url

    if data.author_name:
        schema["author"] = {
            "@type": "Person",
            "name": data.author_name
        }

    if data.date_published:
        schema["datePublished"] = data.date_published

    return schema

# -----------------------------
# API Endpoint
# -----------------------------
@router.post("/schema-generator")
def schema_generator(payload: SchemaRequest):
    """
    Generate Schema.org JSON-LD
    
    Only generates schema fields that are provided in the request.
    URLs are validated for proper http:// or https:// format.
    Date must be in MM/DD/YYYY format.
    """
    return build_schema(payload)

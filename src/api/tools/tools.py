import os
import json
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv
from openai import OpenAI

# Load environment variables (.env)
load_dotenv()

# Initialize OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# FastAPI Router
router = APIRouter(
    prefix="/tools",
    tags=["Tools"],
)

# -----------------------------
# Request Model
# -----------------------------
class SchemaRequest(BaseModel):
    schema_type: str
    description: str


# -----------------------------
# AI Schema Generator Function
# -----------------------------
def generate_schema_with_ai(schema_type: str, description: str):
    prompt = f"""
You are an SEO and Schema.org expert.

Generate a VALID Schema.org JSON-LD for schema type "{schema_type}".

STRICT RULES:
- Output ONLY valid JSON (no markdown, no text)
- Must include "@context" and "@type"
- Follow official Schema.org structure
- Keep it minimal but complete
- Do NOT explain anything

User description:
{description}
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You generate valid Schema.org JSON-LD only."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1
        )

        content = response.choices[0].message.content.strip()
        return json.loads(content)

    except json.JSONDecodeError:
        raise HTTPException(
            status_code=500,
            detail="AI returned invalid JSON-LD"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


# -----------------------------
# API Endpoint
# -----------------------------
@router.post("/schema-generator")
def schema_generator(payload: SchemaRequest):
    """
    Generate Schema.org JSON-LD using AI
    """
    return generate_schema_with_ai(
        schema_type=payload.schema_type,
        description=payload.description
    )

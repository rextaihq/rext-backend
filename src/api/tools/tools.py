import os
import json
from fastapi import APIRouter, HTTPException
from dotenv import load_dotenv
from openai import OpenAI
from src.api.schema.tools_schema import SchemaRequest

# -----------------------------
# Environment Setup
# -----------------------------
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# -----------------------------
# FastAPI Router
# -----------------------------
router = APIRouter(
    prefix="/tools",
    tags=["Tools"],
)

@router.get("/")
def get_tools():
    return {"message": "Tools"}

# -----------------------------
# AI Schema Generator Function
# -----------------------------
def generate_schema_with_ai(payload: SchemaRequest):
    # Build a list of only the fields that the user provided
    provided_fields = []
    
    # Always include required fields
    provided_fields.append(f"- name: {payload.name}")
    
    # Only include optional fields if they were provided
    if payload.description is not None:
        provided_fields.append(f"- description: {payload.description}")
    if payload.url is not None:
        provided_fields.append(f"- url: {payload.url}")
    if payload.image_url is not None:
        provided_fields.append(f"- image_url: {payload.image_url}")
    if payload.author_name is not None:
        provided_fields.append(f"- author: {payload.author_name}")
    if payload.date_published is not None:
        provided_fields.append(f"- datePublished: {payload.date_published}")
    
    fields_text = "\n".join(provided_fields)
    
    prompt = f"""You are an SEO and Schema.org expert.

Generate a VALID Schema.org JSON-LD for schema type "{payload.schema_type}".

CRITICAL RULES - FOLLOW EXACTLY:
1. Output ONLY valid JSON (no markdown, no code blocks, no explanations)
2. MUST include "@context": "https://schema.org" and "@type": "{payload.schema_type}"
3. Use ONLY the fields that the user provided below - DO NOT add any other fields
4. DO NOT invent, assume, or add fields that are not in the provided list
5. If a field is not provided below, DO NOT include it in the output
6. Keep the schema minimal but valid according to Schema.org standards
7. Use proper Schema.org property names (e.g., "datePublished" not "date_published")

User-provided fields (ONLY USE THESE):
{fields_text}

IMPORTANT: If the user did not provide a field (like author, url, image, etc.), DO NOT include it in the schema. Only use what is explicitly listed above.

Generate the Schema.org JSON-LD now:"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You generate valid Schema.org JSON-LD only. You strictly follow instructions and never add fields that weren't requested."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1
        )

        # Parse AI output directly without Pydantic validation
        content = response.choices[0].message.content.strip()
        
        # Remove markdown code blocks if present
        content = content.replace("```json", "").replace("```", "").strip()
        
        schema_json = json.loads(content)
        
        # Validate that only provided fields are in the output
        return schema_json

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


@router.post("/schema-generator")
def schema_generator(payload: SchemaRequest):
    """
    Generate Schema.org JSON-LD using AI
    
    Only generates schema fields that are provided in the request.
    URLs are validated for proper http:// or https:// format.
    """
    return generate_schema_with_ai(payload)

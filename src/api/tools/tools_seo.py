from fastapi import APIRouter, HTTPException, Request
from src.api.tools.Schema.tools_schema import (
    SchemaRequest, ReadabilityRequest,ReadabilityResponse
)
import json
import traceback
import os
from src.flow.model.llm_manager import load_model
import re
import textstat

# Initialize model through manager
llm = load_model()

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
    """Build Schema.org JSON-LD directly from request data."""
    schema = {
        "@context": "https://schema.org",
        "@type": data.schema_type,
        "name": data.name
    }
    if data.description: schema["description"] = data.description
    if data.url: schema["url"] = data.url
    if data.image_url: schema["image"] = data.image_url
    if data.author_name:
        schema["author"] = {"@type": "Person", "name": data.author_name}
    if data.date_published: schema["datePublished"] = data.date_published
    return schema

@router.post("/schema-generator")
def schema_generator(payload: SchemaRequest):
    """Generate Schema.org JSON-LD"""
    return build_schema(payload)

# readibility Checker Tool


def calculate_readability(content: str) -> dict:

    flesch = round(textstat.flesch_reading_ease(content), 2)
    fk_grade = round(textstat.flesch_kincaid_grade(content), 2)

    metrics = {
        "readability_score": flesch,
        "grade_level": fk_grade,
        "sentence_complexity": round(textstat.gunning_fog(content), 2),
        "word_count": textstat.lexicon_count(content, removepunct=True),
        "sentence_count": textstat.sentence_count(content),
    }
# Add a human-readable level
    if flesch >= 70:
        metrics["reading_level"] = "Easy"
    elif flesch >= 50:
        metrics["reading_level"] = "Standard"
    else:
        metrics["reading_level"] = "Difficult"

    return metrics
@router.post("/readability-checker", response_model=ReadabilityResponse)
def readability_checker(payload: ReadabilityRequest):
    try:
        return calculate_readability(payload.content)
    except Exception:
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail="Failed to calculate readability"
        )

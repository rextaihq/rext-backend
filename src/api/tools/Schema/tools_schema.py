from typing import Optional
from pydantic import BaseModel, Field, field_validator
import re


class SchemaRequest(BaseModel):
    # Required fields
    schema_type: str = Field(...,min_length=1, description="Schema.org type (e.g. Article, Product)")
    name: str = Field(...,min_length=1,description="Main title or name of the schema item")

    # Optional fields
    description: Optional[str] = Field(
        None, description="Short description or summary"
    )
    url: Optional[str] = Field(None, description="Canonical URL of the page")
    image_url: Optional[str] = Field(None, description="Image URL for the schema")
    author_name: Optional[str] = Field(None, description="Author name")
    date_published: Optional[str] = Field(
        None, description="Publish date in MM/DD/YYYY format"
    )

    @field_validator('url', 'image_url')
    @classmethod
    def validate_url(cls, v, info):
        # Treat empty string as None for optional fields
        if v is None or v == "" or (isinstance(v, str) and v.strip() == ""):
            return None
        
        # URL regex pattern
        url_pattern = re.compile(
            r'^https?://'  # http:// or https://
            r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain...
            r'localhost|'  # localhost...
            r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ...or ip
            r'(?::\d+)?'  # optional port
            r'(?:/?|[/?]\S+)$', re.IGNORECASE
        )
        
        if not url_pattern.match(v):
            raise ValueError(
                f'{info.field_name} must be a valid URL starting with http:// or https://. '
                f'Got: {v}'
            )
        return v

    @field_validator('date_published')
    @classmethod
    def validate_date(cls, v):
        # Treat empty string as None for optional fields
        if v is None or v == "" or (isinstance(v, str) and v.strip() == ""):
            return None
        
        # Validate MM/DD/YYYY date format with proper month (01-12) and day (01-31) ranges
        date_pattern = re.compile(r'^(0[1-9]|1[0-2])/(0[1-9]|[12][0-9]|3[01])/\d{4}$')
        if not date_pattern.match(v):
            raise ValueError(
                'date_published must be in MM/DD/YYYY format (e.g., 01/20/2026). '
                f'Got: {v}'
            )
        return v


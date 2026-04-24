from typing import List, Optional
from pydantic import BaseModel, Field
from pydantic.json_schema import SkipJsonSchema
from src.flow.model.structure.content import ImageAltText, Link, SchemaMarkup
from typing import Any
from pydantic import model_validator
from src.flow.model.structure.outline import Fact


class BaseGeneratedContent(BaseModel):
    """Base model for all generated content types."""
    title: SkipJsonSchema[str] = ""  # set programmatically from outline, not by LLM
    slug: Optional[str] = Field(default=None, description="URL-friendly slug containing the keyphrase.")
    meta_title: Optional[str] = Field(default=None, description="Meta title — use the exact outline title, do not truncate.")
    meta_description: Optional[str] = Field(default=None, description="Meta description (150-160 chars).")
    tags: List[str] = Field(default_factory=list, description="List of tags.")
    focus_keyphrase: Optional[str] = Field(default=None, description="Primary focus keyphrase.")
    keyphrase_density: Optional[float] = Field(default=None, description="Keyphrase density percentage.")
    secondary_keywords: List[str] = Field(default_factory=list, description="Secondary keywords.")
    introduction: Optional[str] = Field(default=None, description="Opening paragraph(s) containing the keyphrase.")
    body_markdown: Optional[str] = Field(default=None, description="Complete body in Markdown (excluding introduction).")
    images: List[ImageAltText] = Field(default_factory=list, description="SEO-optimized image alt suggestions.")
    internal_links: List[Link] = Field(default_factory=list, description="Internal link suggestions.")
    outbound_links: List[Link] = Field(default_factory=list, description="Outbound link suggestions.")
    schema_markup: Optional[SchemaMarkup] = Field(default=None, description="JSON-LD schema markup.")
    facts: List[Fact] = Field(default_factory=list, description="Verifiable facts/statistics.")

    @model_validator(mode='before')
    @classmethod
    def fix_links_raw(cls, data: Any) -> Any:
        if isinstance(data, dict):
            for field_name in ['internal_links', 'outbound_links']:
                raw_links = data.get(field_name, [])
                
                if not isinstance(raw_links, list):
                    raw_links = []

                fixed_links = []
                
                for link_raw in raw_links:
                    if isinstance(link_raw, dict):
                        link_dict = link_raw.copy()

                        # ✅ FIX: infer link_type correctly
                        if field_name == "internal_links":
                            link_dict.setdefault('link_type', 'internal')
                        else:
                            link_dict.setdefault('link_type', 'external')

                        # ✅ FIX: required fallback fields
                        link_dict.setdefault('placement', 'body')

                        # 🚨 CRITICAL FIX
                        link_dict.setdefault(
                            'anchor_text',
                            link_dict.get('url', 'Read more')
                        )

                        fixed_links.append(link_dict)
                
                data[field_name] = fixed_links
        
        return data

if __name__=="__main__":
    pass
from fastapi import HTTPException, APIRouter
from pydantic import BaseModel, Field
from typing import List
import traceback

from src.api.tool.tools import (
    build_schema,
    calculate_readability,
    generate_content_ideas,
    generate_faqs,
    count_text_metrics, 
    generate_meta_description, 
    validate_meta_description, 
    generate_title_tags,
    generate_canonical_tag,
    generate_hreflang_tags,
    broken_link_checker,
    generate_sitemap,
    build_sitemap_xml
)


from src.api.tool.schema.schema import (
    TitleRequest, 
    BrokenLinkRequest,
    BrokenLinkResponse,
    TitleResponse,
    SchemaRequest,
    ReadabilityRequest,
    ReadabilityResponse,
    IdeaGeneratorRequest,
    IdeaGeneratorResponse,
    MetaDescriptionRequest,
    MetaDescriptionResponse,
    CanonicalTagRequest,
    CanonicalTagResponse,
    HreflangRequest,
    HreflangResponse,
    FAQResponse,
    FAQRequest,
)

router = APIRouter(prefix='/tools', tags=['tools'])

@router.get("/")
def get_tools():
    return {"message": "tools"}

# Define Schemas for Word Counter
class TextInput(BaseModel):
    # Ensures text is not just an empty string at the schema level
    text: str = Field(..., min_length=1)

class TextMetricsOutput(BaseModel):
    words: int
    characters: int
    sentences: int
    paragraphs: int
    min_read: int

# Word Counter Endpoint
@router.post("/count_metrics", response_model=TextMetricsOutput)
async def get_metrics(input_data: TextInput):
    """
    API endpoint to receive text via POST request and return metrics.
    URL will be: POST /tools/count_metrics
    """
    try:
        metrics = count_text_metrics(input_data.text)
        return metrics
    except Exception as e:
        # Generic error handling for the underlying logic
        raise HTTPException(status_code=500, detail=str(e))

# Meta Description Generator Endpoint
@router.post("/meta-description/generate", response_model=MetaDescriptionResponse)
async def generate_meta_desc(request: MetaDescriptionRequest):
    """
    API endpoint to generate meta description.
    URL will be: POST /tools/meta-description/generate
    """
    try:
        # Generate the meta description
        meta_description = generate_meta_description(
            page_title=request.page_title,
            target_keywords=request.target_keywords
        )

        # Validate it
        validation = validate_meta_description(meta_description)

        return MetaDescriptionResponse(
            meta_description=meta_description,
            validation=validation
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate meta description: {str(e)}")

# Title Tag Generator Endpoint
@router.post("/title-tags/generate", response_model=TitleResponse)
async def generate_titles(request: TitleRequest):
    """
    API endpoint to generate SEO-friendly title tags.
    URL will be: POST /tools/title-tags/generate
    """
    try:
        titles = generate_title_tags(
            keyword=request.keyword,
            topic=request.topic,
            brand=request.brand,
            tone=request.tone
        )
        return TitleResponse(titles=titles)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate title tags: {str(e)}")

#Schema Generator Endpoint
@router.post("/schema-generator")
async def schema_generator(payload: SchemaRequest):
    """Generate Schema.org JSON-LD"""
    try:
        return build_schema(payload)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate schema: {str(e)}")

# Readability Checker Endpoint
@router.post("/readability-checker", response_model=ReadabilityResponse)
async def readability_checker(payload: ReadabilityRequest):
    """Analyze text readability"""
    try:
        return calculate_readability(payload.content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to calculate readability: {str(e)}")

#Canonical Tag Generator Endpoint
@router.post("/canonical-tag-generator", response_model=CanonicalTagResponse)
async def canonical_tag_generator(request: CanonicalTagRequest):
    """
    AI-powered Canonical Tag Generator.
    Generates an SEO-friendly canonical tag to prevent duplicate content issues.
    """
    try:
        return generate_canonical_tag(str(request.url))
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate canonical tag: {str(e)}"
        )

# Hreflang Tag Generator Endpoint
@router.post("/hreflang-tag-generator", response_model=HreflangResponse)
async def hreflang_tag_generator(request: HreflangRequest):
    """
    AI-powered Google-compliant Hreflang Tag Generator.
    """
    try:
        return generate_hreflang_tags(request)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate hreflang tags: {str(e)}"
        )

@router.post("/link-checker", response_model=BrokenLinkResponse)
async def broken_link_checker_route(request: BrokenLinkRequest):
    """
    URL: POST /tools/link-checker
    """
    try:
        result = broken_link_checker(request.url)
        return BrokenLinkResponse(working=result)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to check link: {str(e)}"
        )
#content idea genration tool endpoints
@router.post("/content-idea-generator", response_model=IdeaGeneratorResponse)
def content_idea_generator(payload: IdeaGeneratorRequest):
    """Generate curated content ideas for various platforms."""
    try:
        return generate_content_ideas(payload)
    except Exception:
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail="Failed to generate content ideas"
        )


@router.post("/sitemap-generator", response_model=SitemapResponse)
async def sitemap_generator_route(request: SitemapRequest):
    """
    URL: POST /tools/sitemap-generator
    """
    try:
        urls = generate_sitemap(str(request.url))
        sitemap_xml = build_sitemap_xml(urls)

        return SitemapResponse(
            urls=urls,
            sitemap_xml=sitemap_xml
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate sitemap: {str(e)}"
        )
# -----------------------------
# FAQ Generator Endpoint

@router.post("/faq/generate", response_model=FAQResponse)
def generate_faq_endpoint(request: FAQRequest):
    """
    Generate high-quality FAQs for a given topic.

    - **topic**: Main topic for FAQ generation
    - **faq_count**: Number of FAQs to generate (1-20)
    - **tone**: Tone of the FAQs (simple, professional, friendly)
    """
    try:
        # Call the tool logic
        response = generate_faqs(request)
        return response
    except Exception as e:
        # Return a proper error response in case of failure
        raise HTTPException(status_code=500, detail=f"Failed to generate FAQs: {str(e)}")
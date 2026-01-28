from fastapi import HTTPException, APIRouter
from typing import List
import traceback

from src.api.tool.test_tool import generate_conclusion
from src.api.tool.tool_test import generate_questions

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
    generate_robots_txt,
    grammar_checker,
    generate_hooks,
    generate_seo_blog_titles,
    keyword_density_checker
)

from src.api.tool.schema.schema import (
    TextInput,
    TextMetricsOutput,
    MetaDescriptionRequest, 
    MetaDescriptionResponse, 
    BrokenLinkRequest, 
    BrokenLinkResponse,
    TitleRequest,
    TitleResponse,
    SchemaRequest,
    ReadabilityRequest,
    ReadabilityResponse,
    CanonicalTagRequest,
    CanonicalTagResponse,
    HreflangRequest,
    HreflangResponse,
    FAQResponse,
    FAQRequest,
    RobotsTxtRequest,
    RobotsTxtResponse,
    GrammarCheckerRequest,
    GrammarCheckerResponse,
    IdeaGeneratorRequest,
    IdeaGeneratorResponse,
    HookGeneratorRequest,
    HookGeneratorResponse,
    SEOBlogTitleRequest,
    SEOBlogTitleResponse,
    ConclusionRequest,
    ConclusionResponse,
    KeywordDensityRequest,
    KeywordDensityResponse
)

from src.api.tool.schema.schema import QuestionRequest, QuestionResponse,MetaDescriptionRequest,MetaDescriptionResponse
# from src.api.tool.tools import generate_taglines
    
# from src.api.tool.schema.schema import (
#     QuestionRequest, 
#     QuestionResponse,
#     TagLineRequest,
    # TagLineResponse,
    # MetaDescriptionRequest,
    # MetaDescriptionResponse,
    # TitleRequest, 
    # TitleResponse,
    # SchemaRequest,
    # ReadabilityRequest,
    # ReadabilityResponse,
    # CanonicalTagRequest,validate_meta_description,
    # CanonicalTagResponse,
    # HreflangRequest,
    # HreflangResponse
# )


router = APIRouter(prefix='/tools', tags=['tools'])

@router.get("/")
def get_tools():
    return {"message": "tools"}

# Word Counter Endpoint
@router.post("/count_metrics", response_model=TextMetricsOutput)
async def get_metrics(input_data: TextInput):
    """
    API endpoint to receive text via POST request and return metrics.
    URL: POST /tools/count_metrics
    """
    try:
        metrics = count_text_metrics(input_data.text)
        return metrics
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Meta Description Generator Endpoint
@router.post("/meta-description/generate", response_model=MetaDescriptionResponse)
async def generate_meta_desc(request: MetaDescriptionRequest):
    """
    API endpoint to generate meta description.
    URL: POST /tools/meta-description/generate
    """
    try:
        meta_description = generate_meta_description(
            page_title=request.page_title,
            target_keywords=request.target_keywords
        )
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
    URL: POST /tools/title-tags/generate
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

# Schema Generator Endpoint
@router.post("/schema-generator", response_model=dict)
async def schema_generator(payload: SchemaRequest):
    """
    Generate Schema.org JSON-LD.
    URL: POST /tools/schema-generator
    """
    try:
        return build_schema(payload)
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Internal error while generating schema: {str(e)}"
        )

# Readability Checker Endpoint
@router.post("/readability-checker", response_model=ReadabilityResponse)
async def readability_checker(payload: ReadabilityRequest):
    """
    Analyze text readability.
    URL: POST /tools/readability-checker
    """
    try:
        return calculate_readability(payload.content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to calculate readability: {str(e)}")

# Canonical Tag Generator Endpoint
@router.post("/canonical-tag-generator", response_model=CanonicalTagResponse)
async def canonical_tag_generator(request: CanonicalTagRequest):
    """
    AI-powered Canonical Tag Generator.
    URL: POST /tools/canonical-tag-generator
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

# Questions generator route.
@router.post("/question-generator", response_model=QuestionResponse)
async def generate_questions_route(request: QuestionRequest):
    """
    AI-powered Google-compliant Hreflang Tag Generator.
    URL: POST /tools/hreflang-tag-generator
    """
    try:
        if not request.text.strip():
            raise HTTPException(status_code=400, detail="Input text cannot be empty")
            
        result = generate_questions(request.text)
        return {"questions": result}
    
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate questions: {str(e)}"
        )

# Link Checker Endpoint
@router.post("/link-checker", response_model=BrokenLinkResponse)
async def broken_link_checker_route(request: BrokenLinkRequest):
    """
    Check if a link is broken.
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

# Content Idea Generator Endpoint
@router.post("/content-idea-generator", response_model=IdeaGeneratorResponse)
def content_idea_generator(payload: IdeaGeneratorRequest):
    """
    Generate curated content ideas for various platforms.
    URL: POST /tools/content-idea-generator
    """
    try:
        return generate_content_ideas(payload)
    except Exception:
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail="Failed to generate content ideas"
        )

# Robots.txt Generator Endpoint
@router.post("/robots-txt/generate", response_model=RobotsTxtResponse, summary="Robots.txt Generator")
async def generate_robots_txt_route(request: RobotsTxtRequest):
    """
    Robots.txt Generator: API endpoint to generate a robots.txt file.
    URL: POST /tools/robots-txt/generate
    """
    try:
        robots_txt = generate_robots_txt(
            user_agent=request.user_agent,
            allow=request.allow,
            disallow=request.disallow,
            sitemap_url=str(request.sitemap_url) if request.sitemap_url else None
        )
        return RobotsTxtResponse(robots_txt=robots_txt)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate robots.txt file: {str(e)}"
        )

# Grammar Checker Endpoint
@router.post("/grammar-checker", response_model=GrammarCheckerResponse, summary="Grammar Checker")
async def grammar_checker_route(request: GrammarCheckerRequest):
    """
    Grammar Checker: Detects grammar, spelling, and punctuation issues.
    URL: POST /tools/grammar-checker
    """
    try:
        return grammar_checker(request.text)
    except ImportError as ie:
        raise HTTPException(status_code=500, detail=str(ie))
    except RuntimeError as re:
        raise HTTPException(status_code=500, detail=str(re))
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Grammar calculation failed: {str(e)}"
        )

# Hook Generater Endpoint
@router.post("/hook-generator", response_model=HookGeneratorResponse, summary="Hook Generater")
async def hook_generator_route(request: HookGeneratorRequest):
    """
    Hook Generater: Brainstorms attention grabbing hooks based on inputs.
    URL: POST /tools/hook-generator
    """
    try:
        return generate_hooks(request)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate hooks: {str(e)}"
        )

# Blog Topic Generater Endpoint
@router.post("/seo-blog-titles", response_model=SEOBlogTitleResponse, summary="Blog Topic Generater")
async def seo_blog_titles_route(request: SEOBlogTitleRequest):
    """
    Blog Topic Generater: Generates SEO-friendly blog titles based on a keyword.
    URL: POST /tools/seo-blog-titles
    """
    try:
        return generate_seo_blog_titles(request)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate SEO blog titles: {str(e)}"
        )

@router.post("/conclusion-generator", response_model=ConclusionResponse)
async def conclusion_generator(request: ConclusionRequest):
    """
    AI-powered Conclusion Generator.
    Generates a concise, human-like conclusion for articles, blogs, or reports.
    """
    try:
        conclusion_text = generate_conclusion(
            content=request.content,
            tone=request.tone,
            length=request.length
        )

        return ConclusionResponse(conclusion=conclusion_text)

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate conclusion: {str(e)}"
        )

# -----------------------------
# FAQ Generator Endpoint

@router.post("/faq/generate", response_model=FAQResponse)
def FAQGenerater(request: FAQRequest):
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

@router.post("/keyword_density_checker", response_model=KeywordDensityResponse)
def check_keyword_density(request: KeywordDensityRequest):
    try:
        return keyword_density_checker(
            content=request.content,
            keywords=request.keywords
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
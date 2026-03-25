from fastapi import HTTPException, APIRouter, Request
from typing import List
import traceback

from src.api.tool.tools import (
    build_schema,
    calculate_readability,
    generate_content_ideas,
    count_text_metrics,
    generate_meta_description,
    validate_meta_description,
    generate_title_tags,
    generate_canonical_tag,
    broken_link_checker,
    generate_robots_txt,
    grammar_checker,
    generate_hooks,
    generate_seo_blog_titles,
    generate_questions
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
    QuestionRequest,
    QuestionResponse,
)
from src.api.schema.response_schemas import SuccessResponse
from src.utils.response_utils import success

router = APIRouter(prefix='/tools', tags=['tools'])

@router.get("/")
def get_tools():
    return {"message": "tools"}

# Word Counter Endpoint
@router.post("/count_metrics", response_model=SuccessResponse[TextMetricsOutput])
async def get_metrics(input_data: TextInput, request: Request):
    """
    API endpoint to receive text via POST request and return metrics.
    URL: POST /tools/count_metrics
    """
    try:
        metrics = count_text_metrics(input_data.text)
        return success(data=metrics, request=request)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Meta Description Generator Endpoint
@router.post("/meta-description/generate", response_model=SuccessResponse[MetaDescriptionResponse])
async def generate_meta_desc(request_meta: MetaDescriptionRequest, request: Request):
    """
    API endpoint to generate meta description.
    URL: POST /tools/meta-description/generate
    """
    try:
        meta_description = await generate_meta_description(
            page_title=request_meta.page_title,
            target_keywords=request_meta.target_keywords
        )
        validation = validate_meta_description(meta_description)
        return success(
            data=MetaDescriptionResponse(
                meta_description=meta_description,
                validation=validation
            ),
            request=request
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate meta description: {str(e)}")

# Title Tag Generator Endpoint
        titles = await generate_title_tags(
            keyword=request_title.keyword,
            topic=request_title.topic,
            brand=request_title.brand,
            tone=request_title.tone
        )
        return success(data=TitleResponse(titles=titles), request=request)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate title tags: {str(e)}")

# Schema Generator Endpoint
@router.post("/schema-generator", response_model=SuccessResponse[dict])
async def schema_generator(payload: SchemaRequest, request: Request):
    """
    Generate Schema.org JSON-LD.
    URL: POST /tools/schema-generator
    """
    try:
        return success(data=build_schema(payload), request=request)
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Internal error while generating schema: {str(e)}"
        )

# Readability Checker Endpoint
@router.post("/readability-checker", response_model=SuccessResponse[ReadabilityResponse])
async def readability_checker(payload: ReadabilityRequest, request: Request):
    """
    Analyze text readability.
    URL: POST /tools/readability-checker
    """
    try:
        return success(data=calculate_readability(payload.content), request=request)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to calculate readability: {str(e)}")

# Canonical Tag Generator Endpoint
@router.post("/canonical-tag-generator", response_model=SuccessResponse[CanonicalTagResponse])
async def canonical_tag_generator(request_tag: CanonicalTagRequest, request: Request):
    """
    AI-powered Canonical Tag Generator.
    URL: POST /tools/canonical-tag-generator
    """
    try:
        data = await generate_canonical_tag(str(request_tag.url))
        return success(data=data, request=request)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate canonical tag: {str(e)}"
        )

# Question Generator Endpoint
@router.post("/question-generator", response_model=SuccessResponse[QuestionResponse])
async def generate_questions_route(request_q: QuestionRequest, request: Request):
    """
    AI-powered Question Generator.
    URL: POST /tools/question-generator
    """
    try:
        if not request_q.text.strip():
            raise HTTPException(status_code=400, detail="Input text cannot be empty")
            
        result = await generate_questions(request_q.text)
        return success(data={"questions": result}, request=request)
    
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate questions: {str(e)}"
        )

# Link Checker Endpoint
@router.post("/link-checker", response_model=SuccessResponse[BrokenLinkResponse])
async def broken_link_checker_route(request_link: BrokenLinkRequest, request: Request):
    """
    Check if a link is broken.
    URL: POST /tools/link-checker
    """
    try:
        result = await broken_link_checker(request_link.url)
        return success(data=BrokenLinkResponse(working=result), request=request)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to check link: {str(e)}"
        )

# Content Idea Generator Endpoint
@router.post("/content-idea-generator", response_model=SuccessResponse[IdeaGeneratorResponse])
async def content_idea_generator(payload: IdeaGeneratorRequest, request: Request):
    """
    Generate curated content ideas for various platforms.
    URL: POST /tools/content-idea-generator
    """
    try:
        data = await generate_content_ideas(payload)
        return success(data=data, request=request)
    except Exception:
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail="Failed to generate content ideas"
        )

# Robots.txt Generator Endpoint
@router.post("/robots-txt/generate", response_model=SuccessResponse[RobotsTxtResponse], summary="Robots.txt Generator")
async def generate_robots_txt_route(request_robots: RobotsTxtRequest, request: Request):
    """
    Robots.txt Generator: API endpoint to generate a robots.txt file.
    URL: POST /tools/robots-txt/generate
    """
    try:
        robots_txt = generate_robots_txt(
            user_agent=request_robots.user_agent,
            allow=request_robots.allow,
            disallow=request_robots.disallow,
            sitemap_url=str(request_robots.sitemap_url) if request_robots.sitemap_url else None
        )
        return success(data=RobotsTxtResponse(robots_txt=robots_txt), request=request)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate robots.txt file: {str(e)}"
        )

# Grammar Checker Endpoint
@router.post("/grammar-checker", response_model=SuccessResponse[GrammarCheckerResponse], summary="Grammar Checker")
async def grammar_checker_route(request_grammar: GrammarCheckerRequest, request: Request):
    """
    Grammar Checker: Detects grammar, spelling, and punctuation issues.
    URL: POST /tools/grammar-checker
    """
    try:
        return success(data=grammar_checker(request_grammar.text), request=request)
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
@router.post("/hook-generator", response_model=SuccessResponse[HookGeneratorResponse], summary="Hook Generater")
async def hook_generator_route(request_hook: HookGeneratorRequest, request: Request):
    """
    Hook Generater: Brainstorms attention grabbing hooks based on inputs.
    URL: POST /tools/hook-generator
    """
    try:
        data = await generate_hooks(request_hook)
        return success(data=data, request=request)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate hooks: {str(e)}"
        )

# Blog Topic Generater Endpoint
@router.post("/seo-blog-titles", response_model=SuccessResponse[SEOBlogTitleResponse], summary="Blog Topic Generater")
async def seo_blog_titles_route(request_seo: SEOBlogTitleRequest, request: Request):
    """
    Blog Topic Generater: Generates SEO-friendly blog titles based on a keyword.
    URL: POST /tools/seo-blog-titles
    """
    try:
        data = await generate_seo_blog_titles(request_seo)
        return success(data=data, request=request)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate SEO blog titles: {str(e)}"
        )

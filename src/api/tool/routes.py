import logging

from fastapi import APIRouter, Depends, HTTPException, Request

from src.api.schema.response_schemas import SuccessResponse
from src.api.tool.limits import bounded, free_tool_size
from src.api.tool.schema.schema import (
    BrokenLinkRequest,
    BrokenLinkResponse,
    CanonicalTagRequest,
    CanonicalTagResponse,
    GrammarCheckerRequest,
    GrammarCheckerResponse,
    HeadlineAnalyzerRequest,
    HeadlineAnalyzerResponse,
    HookGeneratorRequest,
    HookGeneratorResponse,
    HreflangRequest,
    HreflangResponse,
    IdeaGeneratorRequest,
    IdeaGeneratorResponse,
    KeywordDensityRequest,
    KeywordDensityResponse,
    MetaDescriptionRequest,
    MetaDescriptionResponse,
    OutlineGeneratorRequest,
    OutlineGeneratorResponse,
    ParagraphRewriterRequest,
    ParagraphRewriterResponse,
    QuestionRequest,
    QuestionResponse,
    ReadabilityRequest,
    ReadabilityResponse,
    RobotsTxtRequest,
    RobotsTxtResponse,
    SchemaRequest,
    SEOBlogTitleRequest,
    SEOBlogTitleResponse,
    SERPPreviewRequest,
    SERPPreviewResponse,
    SitemapGeneratorRequest,
    SitemapGeneratorResponse,
    TextInput,
    TextMetricsOutput,
    TitleRequest,
    TitleResponse,
)
from src.api.tool.tools import (
    analyze_headline,
    broken_link_checker,
    build_schema,
    calculate_keyword_density,
    calculate_readability,
    count_text_metrics,
    generate_canonical_tag,
    generate_content_ideas,
    generate_content_outline,
    generate_hooks,
    generate_hreflang_tags,
    generate_meta_description,
    generate_questions,
    generate_robots_txt,
    generate_seo_blog_titles,
    generate_serp_preview,
    generate_title_tags,
    generate_xml_sitemap,
    grammar_checker,
    rewrite_paragraph,
    validate_meta_description,
)
from src.flow.model.provider_outage import BUSY_MESSAGE, RETRY_AFTER_SECONDS, provider_outage
from src.utils.response_utils import success

logger = logging.getLogger(__name__)

FAILED_MESSAGE = "We couldn't complete this request right now. Please try again in a moment."


def _failed(exc: Exception, what: str) -> HTTPException:
    """A tool's failure: 503 with a Retry-After while the AI provider is unavailable (G75), else 500.
    A route's own HTTPException (a 400 for an empty input) goes out as it is."""
    if isinstance(exc, HTTPException):
        return exc
    outage = provider_outage(exc)
    if outage is not None:
        # The model's error hook alerts the team once an hour; every request needn't.
        logger.warning("%s: %s is unavailable (%s)", what, outage.provider, outage.kind)
        return HTTPException(
            status_code=503,
            detail=BUSY_MESSAGE,
            headers={"Retry-After": str(RETRY_AFTER_SECONDS)},
        )
    logger.error(what, exc_info=True)
    return HTTPException(status_code=500, detail=FAILED_MESSAGE)


# Public by decision (the rext.ai site's tool pages call it from the browser), bounded per visitor
# and per day: every route is @bounded, and a model tool's body is capped by free_tool_size.
router = APIRouter(prefix="/tools", tags=["tools"], dependencies=[Depends(free_tool_size)])


# Word Counter Endpoint
@router.post("/count_metrics", response_model=SuccessResponse[TextMetricsOutput])
@bounded
async def get_metrics(input_data: TextInput, request: Request):
    """
    API endpoint to receive text via POST request and return metrics.
    URL: POST /tools/count_metrics
    """
    try:
        metrics = count_text_metrics(input_data.text)
        return success(data=metrics, request=request)
    except Exception as exc:
        raise _failed(exc, "Error in count metrics tool") from exc


# Meta Description Generator Endpoint
@router.post("/meta-description/generate", response_model=SuccessResponse[MetaDescriptionResponse])
@bounded
async def generate_meta_desc(request_meta: MetaDescriptionRequest, request: Request):
    """
    API endpoint to generate meta description.
    URL: POST /tools/meta-description/generate
    """
    try:
        meta_description = await generate_meta_description(
            page_title=request_meta.page_title, target_keywords=request_meta.target_keywords
        )
        validation = validate_meta_description(meta_description)
        return success(
            data=MetaDescriptionResponse(meta_description=meta_description, validation=validation),
            request=request,
        )
    except Exception as exc:
        raise _failed(exc, "Failed to generate meta description") from exc


# Title Tag Generator Endpoint
@router.post("/title-tags", response_model=SuccessResponse[TitleResponse])
@bounded
async def generate_title_tags_route(request_title: TitleRequest, request: Request):
    """
    API endpoint to generate title tags.
    URL: POST /tools/title-tags
    """
    try:
        titles = await generate_title_tags(
            keyword=request_title.keyword,
            topic=request_title.topic,
            brand=request_title.brand,
            tone=request_title.tone,
        )
        return success(data=TitleResponse(titles=titles), request=request)
    except Exception as exc:
        raise _failed(exc, "Failed to generate title tags") from exc


# Schema Generator Endpoint
@router.post("/schema-generator", response_model=SuccessResponse[dict])
@bounded
async def schema_generator(payload: SchemaRequest, request: Request):
    """
    Generate Schema.org JSON-LD.
    URL: POST /tools/schema-generator
    """
    try:
        return success(data=build_schema(payload), request=request)
    except Exception as exc:
        raise _failed(exc, "Internal error while generating schema") from exc


# Readability Checker Endpoint
@router.post("/readability-checker", response_model=SuccessResponse[ReadabilityResponse])
@bounded
async def readability_checker(payload: ReadabilityRequest, request: Request):
    """
    Analyze text readability.
    URL: POST /tools/readability-checker
    """
    try:
        return success(data=calculate_readability(payload.content), request=request)
    except Exception as exc:
        raise _failed(exc, "Failed to calculate readability") from exc


# Canonical Tag Generator Endpoint
@router.post("/canonical-tag-generator", response_model=SuccessResponse[CanonicalTagResponse])
@bounded
async def canonical_tag_generator(request_tag: CanonicalTagRequest, request: Request):
    """
    Canonical Tag Generator.
    URL: POST /tools/canonical-tag-generator
    """
    try:
        data = await generate_canonical_tag(str(request_tag.url))
        return success(data=data, request=request)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as exc:
        raise _failed(exc, "Failed to generate canonical tag") from exc


# Question Generator Endpoint
@router.post("/question-generator", response_model=SuccessResponse[QuestionResponse])
@bounded
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

    except Exception as exc:
        raise _failed(exc, "Failed to generate questions") from exc


# Link Checker Endpoint
@router.post("/link-checker", response_model=SuccessResponse[BrokenLinkResponse])
@bounded
async def broken_link_checker_route(request_link: BrokenLinkRequest, request: Request):
    """
    Check if a link is broken.
    URL: POST /tools/link-checker
    """
    try:
        result = await broken_link_checker(str(request_link.url))
        return success(data=BrokenLinkResponse(working=result), request=request)
    except Exception as exc:
        raise _failed(exc, "Failed to check link") from exc


# Content Idea Generator Endpoint
@router.post("/content-idea-generator", response_model=SuccessResponse[IdeaGeneratorResponse])
@bounded
async def content_idea_generator(payload: IdeaGeneratorRequest, request: Request):
    """
    Generate curated content ideas for various platforms.
    URL: POST /tools/content-idea-generator
    """
    try:
        data = await generate_content_ideas(payload)
        return success(data=data, request=request)
    except Exception as exc:
        raise _failed(exc, "Failed to generate content ideas") from exc


# Robots.txt Generator Endpoint
@router.post(
    "/robots-txt/generate",
    response_model=SuccessResponse[RobotsTxtResponse],
    summary="Robots.txt Generator",
)
@bounded
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
            sitemap_url=str(request_robots.sitemap_url) if request_robots.sitemap_url else None,
        )
        return success(data=RobotsTxtResponse(robots_txt=robots_txt), request=request)
    except Exception as exc:
        raise _failed(exc, "Failed to generate robots.txt file") from exc


# Grammar Checker Endpoint
@router.post(
    "/grammar-checker",
    response_model=SuccessResponse[GrammarCheckerResponse],
    summary="Grammar Checker",
)
@bounded
async def grammar_checker_route(request_grammar: GrammarCheckerRequest, request: Request):
    """
    Grammar Checker: Detects grammar, spelling, and punctuation issues.
    URL: POST /tools/grammar-checker
    """
    try:
        data = await grammar_checker(request_grammar.text)
        return success(data=data, request=request)
    except Exception as exc:
        raise _failed(exc, "Grammar calculation failed") from exc


# Hook Generater Endpoint
@router.post(
    "/hook-generator",
    response_model=SuccessResponse[HookGeneratorResponse],
    summary="Hook Generater",
)
@bounded
async def hook_generator_route(request_hook: HookGeneratorRequest, request: Request):
    """
    Hook Generater: Brainstorms attention grabbing hooks based on inputs.
    URL: POST /tools/hook-generator
    """
    try:
        data = await generate_hooks(request_hook)
        return success(data=data, request=request)
    except Exception as exc:
        raise _failed(exc, "Failed to generate hooks") from exc


# Blog Topic Generater Endpoint
@router.post(
    "/seo-blog-titles",
    response_model=SuccessResponse[SEOBlogTitleResponse],
    summary="Blog Topic Generater",
)
@bounded
async def seo_blog_titles_route(request_seo: SEOBlogTitleRequest, request: Request):
    """
    Blog Topic Generater: Generates SEO-friendly blog titles based on a keyword.
    URL: POST /tools/seo-blog-titles
    """
    try:
        data = await generate_seo_blog_titles(request_seo)
        return success(data=data, request=request)
    except Exception as exc:
        raise _failed(exc, "Failed to generate SEO blog titles") from exc


# Content Outline Generator Endpoint
@router.post(
    "/outline-generator",
    response_model=SuccessResponse[OutlineGeneratorResponse],
    summary="Content Outline Generator",
)
@bounded
async def content_outline_generator_route(payload: OutlineGeneratorRequest, request: Request):
    """
    Content Outline Generator: Generates structured article outlines.
    URL: POST /tools/outline-generator
    """
    try:
        data = await generate_content_outline(payload)
        return success(data=data, request=request)
    except Exception as exc:
        raise _failed(exc, "Failed to generate content outline") from exc


# Headline Analyzer Endpoint
@router.post(
    "/headline-analyzer",
    response_model=SuccessResponse[HeadlineAnalyzerResponse],
    summary="Headline Analyzer",
)
@bounded
async def headline_analyzer_route(payload: HeadlineAnalyzerRequest, request: Request):
    """
    Headline Analyzer: Evaluates headline CTR, sentiment, and quality.
    URL: POST /tools/headline-analyzer
    """
    try:
        data = await analyze_headline(payload)
        return success(data=data, request=request)
    except Exception as exc:
        raise _failed(exc, "Failed to analyze headline") from exc


# Hreflang Tag Generator Endpoint
@router.post(
    "/hreflang-generator",
    response_model=SuccessResponse[HreflangResponse],
    summary="Hreflang Tag Generator",
)
@bounded
async def hreflang_generator_route(payload: HreflangRequest, request: Request):
    """
    Hreflang Tag Generator: Generates Google-compliant XML/HTML hreflang tags.
    URL: POST /tools/hreflang-generator
    """
    try:
        res = await generate_hreflang_tags(payload)
        return success(data=HreflangResponse(**res), request=request)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as exc:
        raise _failed(exc, "Failed to generate hreflang tags") from exc


# Keyword Density Checker Endpoint
@router.post(
    "/keyword-density",
    response_model=SuccessResponse[KeywordDensityResponse],
    summary="Keyword Density Checker",
)
@bounded
async def keyword_density_route(payload: KeywordDensityRequest, request: Request):
    """
    Keyword Density Checker: Analyzes text for n-gram frequencies and keyword density.
    URL: POST /tools/keyword-density
    """
    try:
        data = calculate_keyword_density(payload)
        return success(data=data, request=request)
    except Exception as exc:
        raise _failed(exc, "Failed to calculate keyword density") from exc


# Paragraph Rewriter Endpoint
@router.post(
    "/paragraph-rewriter",
    response_model=SuccessResponse[ParagraphRewriterResponse],
    summary="Paragraph Rewriter",
)
@bounded
async def paragraph_rewriter_route(payload: ParagraphRewriterRequest, request: Request):
    """
    Paragraph Rewriter: Rewrites paragraphs based on goal and tone.
    URL: POST /tools/paragraph-rewriter
    """
    try:
        data = await rewrite_paragraph(payload)
        return success(data=data, request=request)
    except Exception as exc:
        raise _failed(exc, "Failed to rewrite paragraph") from exc


# SERP Preview Tool Endpoint
@router.post(
    "/serp-preview",
    response_model=SuccessResponse[SERPPreviewResponse],
    summary="SERP Preview Tool",
)
@bounded
async def serp_preview_route(payload: SERPPreviewRequest, request: Request):
    """
    SERP Preview Tool: Calculates Google SERP snippet lengths and truncation warnings.
    URL: POST /tools/serp-preview
    """
    try:
        data = generate_serp_preview(payload)
        return success(data=data, request=request)
    except Exception as exc:
        raise _failed(exc, "Failed to generate SERP preview") from exc


# Sitemap Generator Endpoint
@router.post(
    "/sitemap-generator",
    response_model=SuccessResponse[SitemapGeneratorResponse],
    summary="Sitemap Generator",
)
@bounded
async def sitemap_generator_route(payload: SitemapGeneratorRequest, request: Request):
    """
    Sitemap Generator: Generates valid sitemap.xml strings from URL lists.
    URL: POST /tools/sitemap-generator
    """
    try:
        data = generate_xml_sitemap(payload)
        return success(data=data, request=request)
    except Exception as exc:
        raise _failed(exc, "Failed to generate sitemap") from exc

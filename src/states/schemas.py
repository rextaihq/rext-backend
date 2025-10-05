from typing import List, Optional
from pydantic import BaseModel, Field

# =========Topic Generation Schema=========
class BasicTopicScore(BaseModel):
    """Basic scoring structure for AI generation"""
    relevance: float = Field(..., ge=0, le=1, description="How relevant to the industry/domain")
    seo_potential: float = Field(..., ge=0, le=1, description="SEO ranking potential")
    trend_level: float = Field(..., ge=0, le=1, description="How trending/popular this topic is")
    uniqueness: float = Field(..., ge=0, le=1, description="How original compared to existing content")
    reader_interest: float = Field(..., ge=0, le=1, description="Engagement potential with readers")
    actionable_potential: float = Field(..., ge=0, le=1, description="How suitable for how-to/tutorial content")
    brand_alignment: float = Field(..., ge=0, le=1, description="How well it fits brand voice")
    controversy: float = Field(..., ge=0, le=1, description="Potential for debate/polarization (lower = safer)")

class BasicTopicGeneration(BaseModel):
    """Basic topic structure for AI generation before enrichment"""
    title: str = Field(..., description="Main headline for the content")
    angle: str = Field(..., description="Unique perspective or approach")
    description: str = Field(..., description="Detailed explanation of what the content will cover")
    channel_fit: List[str] = Field(..., description="Best platforms for this content")
    audience_fit: List[str] = Field(..., description="Target audience segments")
    why_it_works: str = Field(..., description="Justification for why this topic is valuable")
    tags: List[str] = Field(..., description="Categorization tags")
    scores: BasicTopicScore = Field(..., description="Basic scoring from AI generation")

class BasicTopicGenerationList(BaseModel):
    topics: List[BasicTopicGeneration]

class SaveTopicRequest(BaseModel):
    """Schema for topics being saved - includes basic topic data + suggested defaults from frontend"""
    id: str
    workspace_id: str
    title: str
    angle: str
    description: str
    channel_fit: List[str]
    audience_fit: List[str]
    why_it_works: str
    tags: List[str]
    scores: BasicTopicScore
    suggested_defaults: dict
    # Original input params for enrichment context
    input_params: Optional[dict] = None

class SaveTopicRequestList(BaseModel):
    topics: List[SaveTopicRequest]

class TopicScore(BaseModel):
    relevance: float = Field(..., ge=0, le=1, description="How relevant to the industry/domain")
    seo_potential: float = Field(..., ge=0, le=1, description="SEO ranking potential")
    trend_level: float = Field(..., ge=0, le=1, description="How trending/popular this topic is")
    uniqueness: float = Field(..., ge=0, le=1, description="How original compared to existing content")
    reader_interest: float = Field(..., ge=0, le=1, description="Engagement potential with readers")
    actionable_potential: float = Field(..., ge=0, le=1, description="How suitable for how-to/tutorial content")
    brand_alignment: float = Field(..., ge=0, le=1, description="How well it fits brand voice")
    controversy: float = Field(..., ge=0, le=1, description="Potential for debate/polarization (lower = safer)")

class SuggestedDefaults(BaseModel):
    platform: str = Field(..., description="Pre-filled platform choice")
    industry: str = Field(..., description="Pre-filled industry from topic generation input")
    audienceType: List[str] = Field(..., description="Suggested audience types based on industry")
    readingLevel: List[str] = Field(..., description="Complexity level suggestions")
    goals: List[str] = Field(..., description="Primary content goals this topic supports")
    tone: List[str] = Field(..., description="Recommended tone options")
    region: str = Field(..., description="Geographic focus suggestion")
    contentLength: str = Field(..., description="User-friendly length description")
    primaryKeywords: List[str] = Field(..., description="Main SEO targets")
    secondaryKeywords: List[str] = Field(..., description="Supporting keywords")
    includeTOC: bool = Field(..., description="Whether to include table of contents")
    includeSummary: bool = Field(..., description="Whether to include executive summary")
    includeKeyTakeaways: bool = Field(..., description="Whether to include key points section")
    includeCTABlock: bool = Field(..., description="Whether to include call-to-action")
    contentStyle: str = Field(..., description="User-friendly content type description")

class GoalAlignment(BaseModel):
    primary_goals: List[str] = Field(..., description="Goals this topic is perfect for")
    secondary_goals: List[str] = Field(..., description="Goals this topic can support")
    goal_difficulty: dict = Field(..., description="How hard it is to achieve each goal with this topic")

class ContentHooks(BaseModel):
    opening_angles: List[str] = Field(..., description="Compelling ways to start the article")
    key_questions: List[str] = Field(..., description="Important questions the content should answer")
    pain_points: List[str] = Field(..., description="Reader frustrations this content addresses")

class SEOOpportunities(BaseModel):
    featured_snippet_potential: str = Field(..., description="Likelihood of ranking in featured snippets")
    long_tail_keywords: List[str] = Field(..., description="Specific phrases to target")
    search_volume_estimate: str = Field(..., description="Expected search traffic potential")

class ContentGuidance(BaseModel):
    recommended_structure: str = Field(..., description="Best content format")
    research_complexity: str = Field(..., description="How much research needed")
    estimated_sections: List[str] = Field(..., description="Suggested content outline")
    content_hooks: ContentHooks = Field(..., description="Ready-to-use content elements")
    seo_opportunities: SEOOpportunities = Field(..., description="SEO optimization hints")

class AudienceFocus(BaseModel):
    tone_suggestions: List[str] = Field(..., description="Recommended tone for this audience")
    content_style: str = Field(..., description="Best style for this audience")
    reading_level: str = Field(..., description="Appropriate complexity level")
    emphasis: str = Field(..., description="What to highlight for this audience")

class AudienceInsights(BaseModel):
    small_business_focus: Optional[AudienceFocus] = Field(None, description="For small business owners")
    professional_focus: Optional[AudienceFocus] = Field(None, description="For technical professionals")

class InternalResearchConfig(BaseModel):
    enableSimilarArticles: bool = Field(..., description="Whether to fetch similar content")
    maxSimilarArticles: int = Field(..., description="How many similar articles to analyze")
    researchDepth: str = Field(..., description="Research depth level")
    includeCompetitorAnalysis: bool = Field(..., description="Whether to analyze competing content")
    searchQuerySeeds: List[str] = Field(..., description="Research query suggestions")
    dateRange: str = Field(..., description="How recent sources should be")
    sourcesAllowed: List[str] = Field(..., description="Types of sources to include")
    includeNews: bool = Field(..., description="Whether to include recent news")
    retrievalK: int = Field(..., description="Number of sources to retrieve for context")

class UserSettings(BaseModel):
    research_level: str = Field(..., description="Research complexity level")
    include_latest_info: bool = Field(..., description="Whether to include recent information")
    include_examples: bool = Field(..., description="Whether to include examples")
    fact_checking: str = Field(..., description="Fact checking level")
    content_freshness: str = Field(..., description="How recent content should be")
    include_statistics: bool = Field(..., description="Whether to include statistics")
    include_quotes: bool = Field(..., description="Whether to include quotes")
    competitor_analysis: bool = Field(..., description="Whether to analyze competitors")

class TopicGeneration(BaseModel):
    id: str = Field(..., description="Unique identifier for the topic")
    title: str = Field(..., description="Main headline for the content")
    angle: str = Field(..., description="Unique perspective or approach")
    description: str = Field(..., description="Detailed explanation of what the content will cover")
    channel_fit: List[str] = Field(..., description="Best platforms for this content")
    audience_fit: List[str] = Field(..., description="Target audience segments")
    why_it_works: str = Field(..., description="Justification for why this topic is valuable")
    tags: List[str] = Field(..., description="Categorization tags")
    scores: TopicScore = Field(..., description="Comprehensive scoring from evaluation system")
    suggested_defaults: SuggestedDefaults = Field(..., description="User-friendly defaults for content generation form")
    goal_alignment: GoalAlignment = Field(..., description="Shows which content goals this topic naturally supports")
    content_guidance: ContentGuidance = Field(..., description="Content creation guidance and structure recommendations")
    audience_insights: AudienceInsights = Field(..., description="Audience-specific adaptations")
    internal_research_config: InternalResearchConfig = Field(..., description="Backend research configuration")
    user_settings: UserSettings = Field(..., description="Simple user settings")

class TopicGenerationList(BaseModel):
    topics: List[TopicGeneration]


# ===== Blog Generation Schemas =====
class ImagePlaceholder(BaseModel):
    alt_text: str = Field(..., description="SEO-optimized alt text that accurately describes the image content.")
    suggested_prompt: Optional[str] = Field(None, description="AI-generated text prompt for designers.")


class Section(BaseModel):
    heading: str = Field(..., description="The title of the section (H2/H3).")
    content: str = Field(..., description="The body text in Markdown.")
    hyperlinks: List[str] = Field(default_factory=list, description="URLs referenced in this section.")


class BlogArticle(BaseModel):
    title: str
    meta_description: str
    keywords: List[str]
    introduction: str
    sections: List[Section]
    conclusion: str
    references: List[str] = []
    final_image: ImagePlaceholder


# ===== Evaluation Schema =====
class Evaluation(BaseModel):
    rating: int = Field(..., ge=0, le=10, description="Rating of the blog (0-10)")
    weight: int = Field(..., ge=0, le=10, description="Importance weight (0-10)")


# ===== Article Outline =====
class OutlineSection(BaseModel):
    heading: str
    bullet_points: List[str]


class ArticleOutline(BaseModel):
    title: str
    introduction: str
    sections: List[OutlineSection]
    conclusion: str


# ===== Query/Title Models =====
class RewriterTitle(BaseModel):
    refine_title: str = Field(..., description="Refined title for retrieval.")


class QueryDecomposer(BaseModel):
    compose_title: List[str] = Field(
        ..., description="List (max 5) of refined sub-queries for retrieval."
    )

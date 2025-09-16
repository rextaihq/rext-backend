"""
Topic Enrichment Service

This service takes basic topic generation output and enriches it with all the
structured data required by the return-response.md specification.
"""

from typing import List, Dict, Any
from src.states.schemas import (
    BasicTopicGeneration,
    BasicTopicScore,
    TopicGeneration,
    TopicScore,
    SuggestedDefaults,
    GoalAlignment,
    ContentGuidance,
    ContentHooks,
    SEOOpportunities,
    AudienceInsights,
    AudienceFocus,
    InternalResearchConfig,
    UserSettings
)
import uuid


class TopicEnrichmentService:
    """Service to enrich basic topic data with comprehensive structured information."""

    def __init__(self):
        self.platform_options = ["Website", "Social Media"]
        self.industry_options = [
            "Technology", "Healthcare", "Finance", "Education", "E-commerce",
            "Real Estate", "Food & Beverage", "Travel", "Fashion", "Automotive",
            "Entertainment", "Non-profit", "Government", "Consulting", "Manufacturing", "Other"
        ]
        self.audience_type_options = [
            "Consumers", "Businesses", "Enterprises", "Students", "Professionals",
            "Seniors", "Teens", "Parents", "Developers", "Marketers", "Designers",
            "Entrepreneurs", "Freelancers", "Decision Makers", "Investors"
        ]
        self.reading_level_options = ["Beginner", "Intermediate", "Advanced", "Expert"]
        self.goal_options = [
            "Educate", "Entertain", "Inspire", "Persuade", "Promote", "Drive SEO",
            "Thought Leadership", "Generate Leads", "Build Community", "Announce News"
        ]
        self.tone_options = [
            "Professional", "Casual", "Friendly", "Humorous", "Serious", "Technical",
            "Simple", "Inspirational", "Authoritative", "Conversational", "Formal",
            "Playful", "Urgent", "Empathetic"
        ]

    def enrich_topic(self, basic_topic: Dict[str, Any], input_params: Dict[str, Any]) -> TopicGeneration:
        """Enrich a basic topic with comprehensive structured data."""

        # Generate unique ID if not provided
        topic_id = f"topic_{str(uuid.uuid4())[:8]}"

        # Convert BasicTopicScore to full TopicScore object
        basic_scores = basic_topic.get("scores")
        if isinstance(basic_scores, dict):
            # Handle dict format (legacy)
            topic_scores = TopicScore(
                relevance=basic_scores.get("relevance", 0.8),
                seo_potential=basic_scores.get("seo_potential", 0.8),
                trend_level=basic_scores.get("trend_level", 0.8),
                uniqueness=basic_scores.get("uniqueness", 0.8),
                reader_interest=basic_scores.get("reader_interest", 0.8),
                actionable_potential=basic_scores.get("actionable_potential", 0.8),
                brand_alignment=basic_scores.get("brand_alignment", 0.8),
                controversy=basic_scores.get("controversy", 0.2)
            )
        else:
            # Handle BasicTopicScore object
            topic_scores = TopicScore(
                relevance=basic_scores.relevance,
                seo_potential=basic_scores.seo_potential,
                trend_level=basic_scores.trend_level,
                uniqueness=basic_scores.uniqueness,
                reader_interest=basic_scores.reader_interest,
                actionable_potential=basic_scores.actionable_potential,
                brand_alignment=basic_scores.brand_alignment,
                controversy=basic_scores.controversy
            )

        # Create suggested defaults based on input parameters and topic content
        suggested_defaults = self._create_suggested_defaults(basic_topic, input_params)

        # Create goal alignment based on topic characteristics
        goal_alignment = self._create_goal_alignment(basic_topic)

        # Create content guidance
        content_guidance = self._create_content_guidance(basic_topic)

        # Create audience insights
        audience_insights = self._create_audience_insights(basic_topic)

        # Create internal research config
        internal_research_config = self._create_internal_research_config(basic_topic)

        # Create user settings
        user_settings = self._create_user_settings()

        return TopicGeneration(
            id=topic_id,
            title=basic_topic["title"],
            angle=basic_topic["angle"],
            description=basic_topic.get("description", basic_topic["angle"]),
            channel_fit=basic_topic["channel_fit"],
            audience_fit=basic_topic["audience_fit"],
            why_it_works=basic_topic["why_it_works"],
            tags=basic_topic["tags"],
            scores=topic_scores,
            suggested_defaults=suggested_defaults,
            goal_alignment=goal_alignment,
            content_guidance=content_guidance,
            audience_insights=audience_insights,
            internal_research_config=internal_research_config,
            user_settings=user_settings
        )

    def _create_suggested_defaults(self, topic: Dict[str, Any], input_params: Dict[str, Any]) -> SuggestedDefaults:
        """Create suggested defaults based on topic and input parameters."""

        # Determine platform based on channel_fit
        platform = "Website" if "blog" in topic["channel_fit"] else "Social Media"

        # Use input industry or infer from topic
        industry = input_params.get("industry", "Technology")

        # Suggest audience types based on the topic's audience_fit
        audience_types = self._map_audience_fit_to_types(topic["audience_fit"])

        # Suggest reading level based on audience
        reading_levels = self._suggest_reading_levels(audience_types)

        # Suggest goals based on topic characteristics
        goals = self._suggest_goals(topic)

        # Suggest tone based on audience and industry
        tone = self._suggest_tone(audience_types, industry)

        # Generate keywords from title and tags
        primary_keywords = self._generate_primary_keywords(topic)
        secondary_keywords = self._generate_secondary_keywords(topic)

        return SuggestedDefaults(
            platform=platform,
            industry=industry,
            audienceType=audience_types,
            readingLevel=reading_levels,
            goals=goals,
            tone=tone,
            region="International",
            contentLength="Medium (1000-2500 words)",
            primaryKeywords=primary_keywords,
            secondaryKeywords=secondary_keywords,
            includeTOC=True,
            includeSummary=True,
            includeKeyTakeaways=True,
            includeCTABlock=True,
            contentStyle="Tutorial" if self._is_tutorial_topic(topic) else "Guide"
        )

    def _create_goal_alignment(self, topic: Dict[str, Any]) -> GoalAlignment:
        """Create goal alignment based on topic characteristics."""

        primary_goals = ["Educate"]
        secondary_goals = ["Drive SEO"]

        # Add goals based on topic content
        if any(word in topic["title"].lower() for word in ["how", "guide", "tutorial", "step"]):
            primary_goals.append("Drive SEO")

        if "blog" in topic["channel_fit"]:
            secondary_goals.append("Thought Leadership")

        if "social-media" in topic["channel_fit"]:
            secondary_goals.append("Build Community")

        goal_difficulty = {
            "Educate": "easy",
            "Drive SEO": "easy" if self._is_seo_friendly(topic) else "medium",
            "Persuade": "medium",
            "Entertain": "hard",
            "Thought Leadership": "medium",
            "Generate Leads": "medium"
        }

        return GoalAlignment(
            primary_goals=primary_goals,
            secondary_goals=secondary_goals,
            goal_difficulty=goal_difficulty
        )

    def _create_content_guidance(self, topic: Dict[str, Any]) -> ContentGuidance:
        """Create content guidance based on topic characteristics."""

        # Determine structure based on title and content
        structure = "tutorial" if self._is_tutorial_topic(topic) else "guide"

        # Determine research complexity
        research_complexity = "medium"
        if any(word in topic["title"].lower() for word in ["comparison", "vs", "best", "top"]):
            research_complexity = "hard"
        elif any(word in topic["title"].lower() for word in ["quick", "simple", "easy"]):
            research_complexity = "easy"

        # Generate content sections
        sections = self._generate_content_sections(topic)

        # Create content hooks
        hooks = self._create_content_hooks(topic)

        # Create SEO opportunities
        seo_opportunities = self._create_seo_opportunities(topic)

        return ContentGuidance(
            recommended_structure=structure,
            research_complexity=research_complexity,
            estimated_sections=sections,
            content_hooks=hooks,
            seo_opportunities=seo_opportunities
        )

    def _create_content_hooks(self, topic: Dict[str, Any]) -> ContentHooks:
        """Create content hooks based on topic."""

        # Generate opening angles based on topic
        opening_angles = [
            f"Discover how to {topic['title'].lower().replace('how to ', '')}",
            f"Transform your approach to {' '.join(topic['tags'][:2]).lower()}",
            f"Everything you need to know about {topic['title'].lower()}"
        ]

        # Generate key questions
        key_questions = [
            f"What are the best practices for {' '.join(topic['tags'][:2]).lower()}?",
            f"How do I get started with {topic['title'].lower()}?",
            f"What tools do I need for {' '.join(topic['tags'][:2]).lower()}?"
        ]

        # Generate pain points
        pain_points = [
            f"Struggling with {' '.join(topic['tags'][:2]).lower()} implementation",
            f"Lack of clear guidance on {topic['title'].lower()}",
            f"Time-consuming {' '.join(topic['tags'][:2]).lower()} processes"
        ]

        return ContentHooks(
            opening_angles=opening_angles,
            key_questions=key_questions,
            pain_points=pain_points
        )

    def _create_seo_opportunities(self, topic: Dict[str, Any]) -> SEOOpportunities:
        """Create SEO opportunities based on topic."""

        # Determine featured snippet potential
        snippet_potential = "high" if self._is_tutorial_topic(topic) else "medium"

        # Generate long-tail keywords
        long_tail_keywords = [
            f"how to {topic['title'].lower()}",
            f"best {' '.join(topic['tags'][:2]).lower()} guide",
            f"{topic['title'].lower()} tutorial"
        ]

        # Estimate search volume based on topic characteristics
        search_volume = "medium-high" if len(topic["audience_fit"]) > 2 else "medium"

        return SEOOpportunities(
            featured_snippet_potential=snippet_potential,
            long_tail_keywords=long_tail_keywords,
            search_volume_estimate=search_volume
        )

    def _create_audience_insights(self, topic: Dict[str, Any]) -> AudienceInsights:
        """Create audience insights based on topic."""

        small_business_focus = None
        professional_focus = None

        if "small-business-owners" in topic["audience_fit"] or "entrepreneurs" in topic["audience_fit"]:
            small_business_focus = AudienceFocus(
                tone_suggestions=["Friendly", "Simple"],
                content_style="step-by-step guide",
                reading_level="Beginner",
                emphasis="Cost-effectiveness and ease of use"
            )

        if "professionals" in topic["audience_fit"] or "developers" in topic["audience_fit"]:
            professional_focus = AudienceFocus(
                tone_suggestions=["Professional", "Technical"],
                content_style="comprehensive tutorial",
                reading_level="Intermediate",
                emphasis="Advanced features and ROI"
            )

        return AudienceInsights(
            small_business_focus=small_business_focus,
            professional_focus=professional_focus
        )

    def _create_internal_research_config(self, topic: Dict[str, Any]) -> InternalResearchConfig:
        """Create internal research configuration."""

        return InternalResearchConfig(
            enableSimilarArticles=True,
            maxSimilarArticles=4,
            researchDepth="Comprehensive",
            includeCompetitorAnalysis=True,
            searchQuerySeeds=self._generate_search_queries(topic),
            dateRange="6M",
            sourcesAllowed=["Website", "Blog", "News"],
            includeNews=True,
            retrievalK=10
        )

    def _create_user_settings(self) -> UserSettings:
        """Create default user settings."""

        return UserSettings(
            research_level="Comprehensive",
            include_latest_info=True,
            include_examples=True,
            fact_checking="Standard",
            content_freshness="Recent (6 months)",
            include_statistics=True,
            include_quotes=True,
            competitor_analysis=True
        )

    # Helper methods
    def _map_audience_fit_to_types(self, audience_fit: List[str]) -> List[str]:
        """Map audience_fit to audience types."""
        mapping = {
            "developers": "Developers",
            "marketers": "Marketers",
            "small-business-owners": "Businesses",
            "entrepreneurs": "Entrepreneurs",
            "professionals": "Professionals",
            "students": "Students",
            "consumers": "Consumers"
        }

        result = []
        for audience in audience_fit:
            if audience.lower() in mapping:
                result.append(mapping[audience.lower()])
            else:
                result.append("Professionals")  # default

        return list(set(result))[:3]  # max 3 unique items

    def _suggest_reading_levels(self, audience_types: List[str]) -> List[str]:
        """Suggest reading levels based on audience types."""
        if "Developers" in audience_types or "Professionals" in audience_types:
            return ["Intermediate", "Advanced"]
        elif "Students" in audience_types:
            return ["Beginner", "Intermediate"]
        else:
            return ["Beginner", "Intermediate"]

    def _suggest_goals(self, topic: Dict[str, Any]) -> List[str]:
        """Suggest goals based on topic characteristics."""
        goals = ["Educate"]

        if self._is_seo_friendly(topic):
            goals.append("Drive SEO")

        if "blog" in topic["channel_fit"]:
            goals.append("Thought Leadership")

        return goals

    def _suggest_tone(self, audience_types: List[str], industry: str) -> List[str]:
        """Suggest tone based on audience and industry."""
        if "Developers" in audience_types:
            return ["Technical", "Professional"]
        elif "Businesses" in audience_types:
            return ["Professional", "Friendly"]
        else:
            return ["Friendly", "Conversational"]

    def _generate_primary_keywords(self, topic: Dict[str, Any]) -> List[str]:
        """Generate primary keywords from topic."""
        return [
            topic["title"].lower(),
            f"{' '.join(topic['tags'][:2]).lower()}",
            f"{topic['title'].lower()} guide"
        ]

    def _generate_secondary_keywords(self, topic: Dict[str, Any]) -> List[str]:
        """Generate secondary keywords from topic."""
        return [
            f"{' '.join(topic['tags'][:2]).lower()} tips",
            f"best {' '.join(topic['tags'][:2]).lower()}",
            f"{' '.join(topic['tags'][:2]).lower()} tutorial"
        ]

    def _is_tutorial_topic(self, topic: Dict[str, Any]) -> bool:
        """Check if topic is tutorial-oriented."""
        tutorial_words = ["how", "guide", "tutorial", "step", "learn", "build", "create"]
        return any(word in topic["title"].lower() for word in tutorial_words)

    def _is_seo_friendly(self, topic: Dict[str, Any]) -> bool:
        """Check if topic is SEO-friendly."""
        seo_indicators = ["how", "best", "guide", "tutorial", "tips", "comparison"]
        return any(word in topic["title"].lower() for word in seo_indicators)

    def _generate_content_sections(self, topic: Dict[str, Any]) -> List[str]:
        """Generate estimated content sections."""
        if self._is_tutorial_topic(topic):
            return [
                f"Introduction to {' '.join(topic['tags'][:2])}",
                f"Getting Started with {topic['title']}",
                "Step-by-Step Implementation",
                "Best Practices and Tips",
                "Common Challenges and Solutions",
                "Conclusion and Next Steps"
            ]
        else:
            return [
                f"Overview of {' '.join(topic['tags'][:2])}",
                "Key Benefits and Features",
                "Implementation Considerations",
                "Best Practices",
                "Conclusion"
            ]

    def _generate_search_queries(self, topic: Dict[str, Any]) -> List[str]:
        """Generate search query seeds."""
        return [
            topic["title"].lower(),
            f"{' '.join(topic['tags'][:2]).lower()} guide",
            f"best {' '.join(topic['tags'][:2]).lower()}"
        ]
"""
Outline renderer — normalizes any content-type-specific outline dict
into a single RenderableOutline shape for generic frontend display.

Frontend renders one format regardless of schema_type.
Each block represents the primary structural content of the outline
(sections, steps, clusters, phases, etc.) — not metadata.
"""

from __future__ import annotations

from typing import Any

# ── field-name helpers ──────────────────────────────────────────────────────


def _label(key: str) -> str:
    return key.replace("_", " ").title()


# Fields used as a primary label for outline items (checked in order).
# Extend this when new schema types add distinct label-carrying fields.
_LABEL_FIELDS = (
    "title",
    "heading",
    "name",
    "cluster_name",
    "phase",
    "term",
    "metric_name",
    "feature",
    "use_case",
    "scenario",
    "category",
    "module",
    "section",
    "insight",
    "challenge",
    "objective",
    "service",
    "question",
    "decision",
    "step_number",
    # 2026 informational schema additions
    "module_name",  # Tutorial.Module
    "phase_name",  # Checklist.ChecklistPhase
    "category_name",  # ResourceList.ResourceCategory
    "finding",  # WhitePaper.Insight
    "risk",  # WhitePaper.Risk
    "mistake",  # Tutorial/Checklist mistake items
    "recommendation",  # WhitePaper.Recommendation
    "trend",  # WhitePaper.FutureTrend
    "task",  # Checklist.ChecklistItem
    "step",  # ProcessStep.step, TutorialStep.step (prevents label/point duplication)
    "item",  # generic single-item schemas
    "check",  # ValidationStep.check
    # Commercial schema label fields
    "benefit",  # BenefitItem.benefit (sales-page, landing-page, service-page, feature-overview)
    "factor",  # DecisionFactor.factor (comparison, buying-guide)
    "segment_name",  # BuyerSegment.segment_name (buying-guide)
    "segment",  # AudienceSegment.segment (brand-page)
    "group_name",  # BestPickGroup.group_name (product-roundup)
    "feature_name",  # FeatureEvaluation.feature_name (in-depth-review)
    "dimension",  # TradeOff.dimension (pros-cons)
    "criterion",  # ComparisonRow.criterion (buying-guide)
    # Transactional schema label fields
    "concern",  # Objection.concern (signup-page, service-page, demo-page)
    "objection",  # Objection.objection (sales-page, landing-page)
    # Navigational schema label fields
    "method_name",  # AuthMethod.method_name (login-guide)
    "action_name",  # SelfServiceAction.action_name (help-center)
    "channel",  # EscalationChannel.channel (help-center)
    "path",  # NavigationHub path items (brand-page)
)

# List fields whose contents are surfaced as bullet points.
_POINTS_FIELDS = (
    "key_points",
    "points",
    "actions",
    "tips",
    "questions",
    "items",
    "strengths",
    "weaknesses",
    "highlights",
    "requirements",
    "checks",
    "variations",
    "examples",
    "goals",
    "alternatives",
    "pros",
    "cons",
    "features",
    # 2026 informational schema additions
    "subtopics",  # PillarContent.ClusterTopic
    "benefits",  # WhitePaper.SolutionComponent / BenefitsSection wrapper
    "terms",  # Glossary.TermCluster — show term names as points
    "industry_impact",  # WhitePaper.ProblemStatement
    "business_impact",  # CaseStudy.ProblemStatement
    "key_decisions",  # CaseStudy.StrategySection (list of StrategyDecision dicts)
    # Commercial schema point fields
    "pain_points",  # ProblemSection.pain_points (sales-page, landing-page, service-page, demo-page)
    "key_features",  # Tool.key_features (best-tools), ProductItem.key_features (product-roundup)
    "best_for",  # Product.best_for, Tool.best_for, ProductOption.best_for
    "limitations",  # FeatureEvaluation.limitations (in-depth-review)
    "unique_selling_points",  # Differentiation.unique_selling_points (brand-page)
    "unique_advantages",  # Differentiation.unique_advantages (alternatives)
    "key_differences",  # Differentiation.key_differences, ComparisonSnapshot
    "steps_summary",  # MigrationInsight.steps_summary
    "user_goals",  # BuyerIntent.user_goals (buying-guide)
    "needs",  # BuyerSegment.needs, AudienceSegment.needs (brand-page)
    "criteria",  # SelectionCriteria.criteria (best-tools, product-roundup)
    # Transactional schema point fields
    "key_highlights",  # DemoExperience.key_highlights (demo-page)
    "onboarding_steps",  # PostSignupExperience.onboarding_steps (signup-page)
    "security_claims",  # TrustLayer.security_claims (signup-page)
    "guarantees",  # TrustSignals.guarantees (checkout-page, pricing-page)
    # Navigational schema point fields
    "journey_highlights",  # CompanyStory.journey_highlights, BrandStory.journey_highlights
    "offerings",  # ServicesSnapshot.offerings (about-us)
    "differentiators",  # ServicesSnapshot.differentiators
    "core_values",  # MissionVision.core_values (about-us)
    "values",  # ValuesSection.values (about-us, brand-page)
    "resolution_steps",  # IssueSolution.resolution_steps (help-center)
    "solution_steps",  # LoginIssue.solution_steps (login-guide)
    "competitive_advantages",  # Differentiation.competitive_advantages (brand-page)
    "primary_paths",  # NavigationHub.primary_paths (brand-page)
)

# Fields that carry enum/config values and should never be used as a label.
_SKIP_LABEL_FIELDS = {
    "heading_level",
    "type",
    "id",
    "level",
    "difficulty_level",
    "intent_type",
    "answer_format",
    "optional",
    "required",
    "resource_type",
    "credibility_score",
    "urgency_level",
    "importance",
    "skill_type",
    "relationship_type",
    # Commercial/transactional/navigational enum fields
    "rank",
    "weight",
    "fit_level",
    "impact_level",
    "severity",
    "overall_assessment",
    "recommendation_type",
    "value_for_money",
    "billing_cycle",
    "field_type",
    "method_type",
    "discount_type",
    "demo_type",
    "review_depth_level",
    "learning_curve",
    "access_method",
    "included",
    "is_popular",
}

# Direct fields that hold a short prose answer/description inside an item dict.
_ANSWER_PROSE_FIELDS = (
    "short_answer",
    "brief",
    "content",
    "text",
    "simple_definition",
    "definition",  # Glossary terms
    "description",  # generic — many schemas
    "quick_summary",
    "overview",
    "explanation",
    # Commercial/transactional/navigational prose fields
    "approach_summary",  # ServiceSolution.approach_summary (service-page)
    "solution_summary",  # SolutionSection.solution_summary (sales-page, landing-page)
    "core_benefit",  # ValueProposition.core_benefit (product-homepage)
    "unique_differentiation",  # ValueProposition.unique_differentiation (product-homepage)
    "problem_solved",  # ValueProposition.problem_solved (product-homepage)
    "value_proposition",  # BrandPositioning.value_proposition (brand-page)
    "origin_story",  # CompanyStory.origin_story (about-us)
    "real_world_usage",  # FeatureEvaluation.real_world_usage (in-depth-review)
    "reasoning",  # UseCaseComparison.reasoning, Recommendation.justification
    "justification",  # Recommendation.justification
    "ranking_reason",  # RankedTool.ranking_reason, RankedProduct.reason_for_rank
    "reason_for_rank",  # RankedProduct.reason_for_rank (product-roundup)
    "reason",  # UseCaseMatch.reason (alternatives, best-tools, buying-guide)
    "response",  # Objection.response, LoginError.resolution
    "mission",  # MissionVision.mission (about-us)
    "what_it_does",  # FeatureFunction.what_it_does (feature-overview)
    "how_it_works_summary",  # FeatureFunction.how_it_works_summary
)

# Wrapper keys whose value is a dict that may contain a prose field above.
_ANSWER_WRAPPER_KEYS = ("answer", "description", "explanation", "summary")

# Per content-type: ordered list of top-level keys that hold
# the primary structural content (what the article is actually made of).
# Keys are processed in order — earlier = higher priority in the approval UI.
_STRUCTURAL_KEYS: dict[str, list[str]] = {
    # ── Informational ──────────────────────────────────────────────────────────
    "blog": ["structure"],
    "faq": ["clusters"],
    "how-to-guide": ["steps"],
    "tutorial": ["modules", "steps"],
    "checklist": ["phases"],
    "explainer": ["progressive_explanation", "concept_breakdown", "how_it_works"],
    "glossary": ["clusters", "terms"],
    "pillar-content": ["cluster_architecture", "structure"],
    "resource-list": ["categories"],
    "white-paper": ["methodology", "analysis", "solution", "recommendations"],
    "case-study": [
        "problem",
        "goals",
        "strategy",
        "implementation",
        "results",
        "challenges",
        "insights",
    ],
    # ── Commercial ─────────────────────────────────────────────────────────────
    # comparison: show both product profiles, feature matrix, use-case winners,
    #   head-to-head verdict, pricing and decision framework
    "comparison": [
        "products",
        "feature_matrix",
        "use_cases",
        "head_to_head",
        "pricing",
        "decision_framework",
        "recommendations",
    ],
    # alternatives: list of competitors, per-competitor comparison matrices,
    #   use-case matching and who-should-choose-what guidance
    "alternatives": [
        "alternatives_list",
        "comparison_matrices",
        "use_cases",
        "decision_guide",
        "differentiation",
    ],
    # best-tools: ranked categories with tool profiles, use-case matching,
    #   decision guide and optional feature matrix
    "best-tools": [
        "rankings",
        "categories",
        "use_cases",
        "decision_guide",
        "comparison_matrix",
    ],
    # buying-guide: available product options, comparison matrix, buyer segments,
    #   decision weighting, use-case matching and common mistakes
    "buying-guide": [
        "product_options",
        "buyer_segments",
        "comparison_matrix",
        "decision_framework",
        "use_cases",
        "mistakes",
    ],
    # in-depth-review: product overview, feature-by-feature deep dive,
    #   usability analysis, pros/cons, use-case tests, limitations, final verdict
    "in-depth-review": [
        "overview",
        "features",
        "usability",
        "pros_cons",
        "use_cases",
        "limitations",
        "verdict",
    ],
    # product-roundup: best-pick groups (best overall / budget / premium),
    #   use-case matching, decision guide and comparison matrix
    "product-roundup": [
        "best_picks",
        "use_cases",
        "decision_guide",
        "comparison_matrix",
    ],
    # pros-cons: structured pros, structured cons, trade-off analysis,
    #   use-case fit, feature-impact mapping, final decision summary
    "pros-cons": [
        "pros",
        "cons",
        "tradeoffs",
        "use_cases",
        "feature_impact",
        "decision_summary",
    ],
    # ── Transactional ──────────────────────────────────────────────────────────
    # checkout-page: checkout flow type, order summary, payment methods, trust signals
    "checkout-page": ["checkout_flow", "order_summary", "payment", "trust"],
    # coupon-page: offer definition, coupon mechanics, redemption steps, trust/urgency
    "coupon-page": ["coupon_offer", "coupon_details", "redemption_flow", "trust_urgency"],
    # demo-page: demo experience type, walkthrough steps, value proof, objection handling
    "demo-page": ["demo_experience", "walkthrough", "value_proof", "objection_handling"],
    # landing-page: problem, solution, benefits, offer, objection handling
    "landing-page": ["problem", "solution", "benefits", "offer", "objection_handling"],
    # pricing-page: value positioning, plans, comparison table, billing options, objections
    "pricing-page": ["pricing_plans", "comparison_table", "billing_options", "objection_handling"],
    # sales-page: problem agitation, solution, offer, benefits, objection handling, urgency
    "sales-page": ["problem", "solution", "offer", "benefits", "objection_handling", "urgency"],
    # service-page: service overview, problem context, solution/process, benefits, pricing
    "service-page": ["service_overview", "problem_context", "solution", "benefits", "pricing"],
    # signup-page: value stack (why sign up), form fields, onboarding expectation, trust
    "signup-page": ["value_stack", "signup_form", "onboarding", "trust"],
    # ── Navigational ───────────────────────────────────────────────────────────
    # about-us: mission/vision, company story, services, credibility signals, team, values
    "about-us": [
        "mission_vision",
        "company_story",
        "services_snapshot",
        "credibility",
        "team",
        "values",
    ],
    # brand-page: brand positioning, story, product ecosystem,
    #   differentiation, navigation hub, audience map
    "brand-page": [
        "positioning",
        "story",
        "ecosystem",
        "differentiation",
        "navigation",
        "audience_map",
    ],
    # contact-us: intent routing (which team to contact), channels, form fields, SLA expectations
    "contact-us": ["routing", "channels", "form", "expectations"],
    # documentation: navigation tree, learning paths, guides, troubleshooting
    "documentation": ["navigation", "learning_paths", "guides", "troubleshooting"],
    # feature-overview: what it does, key benefits, use cases, how it works, integrations
    "feature-overview": ["function", "benefits", "use_cases", "how_it_works", "integrations"],
    # help-center: knowledge base categories, troubleshooting, learning paths, self-service, escalation
    "help-center": [
        "knowledge_base",
        "troubleshooting",
        "learning_paths",
        "self_service",
        "escalation",
    ],
    # login-guide: auth methods, modern auth (passkey/SSO), security, account recovery,
    #   error handling, troubleshooting
    "login-guide": [
        "authentication",
        "modern_auth",
        "security",
        "account_recovery",
        "error_handling",
        "troubleshooting",
    ],
    # product-homepage: value proposition, feature discovery, use cases,
    #   how it works (steps), activation flow
    "product-homepage": [
        "value_proposition",
        "features",
        "use_cases",
        "how_it_works",
        "activation_flow",
    ],
}

# Fields that are metadata / AI-internal / writing-guidance.
# These are never treated as structural blocks.
# Kept here primarily to protect the fallback scan from noise.
_META_KEYS = {
    # Core metadata — returned as flat top-level render fields
    "title",
    "slug_suggestion",
    "focus_keyphrase",
    "target_audience",
    "tone",
    "schema_type",
    "target_word_count",
    "rejected_reason",
    "status",
    "target_reading_time_minutes",
    "target_completion_time_minutes",
    "content_goal",
    "completion_goal",
    "success_metric",
    "success_definition",
    "comprehension_goal",
    "decision_time_target_seconds",
    "target_time_to_decision_seconds",
    # Hero — extracted separately as render.hero
    "hero",
    # SEO layers — exposed via focus_keyphrase + keywords_to_include
    "seo",
    "seo_plan",
    "keywords_to_include",
    # Writing-guidance and authority signals — used during generation, not approval
    "eeat",
    "engagement",
    "references",
    "cta",
    "social_proof",
    "transparency",
    "authority",
    "snippets",
    "coverage",
    "internal_links",
    # Internal AI / knowledge-graph layers
    "search_intent",
    "topic_cluster",
    "topic_authority",
    "entity_graph",
    "content_depth",
    "semantic_coverage",
    "cluster_heading_map",
    # Schema-specific writing-aid layers (not outline structure)
    "context",  # Explainer: concept context framing
    "analogies",  # Explainer: mental models for writing
    "related_concepts",  # Explainer: knowledge graph layer
    "media",  # Explainer / PillarContent: visual plan
    "misconceptions",  # Explainer / Glossary: correction layer
    "applications",  # Explainer: use-case writing hints
    "branching",  # HowToGuide: conditional logic paths
    "error_prevention",  # HowToGuide: failure prevention system
    "safety",  # HowToGuide: risk notes
    "validation",  # HowToGuide / Checklist: verification layer
    "user_context",  # HowToGuide: skill level metadata
    "dependencies",  # Checklist: task dependency graph
    "outcomes",  # Checklist: outcome mapping
    "progress",  # Checklist: progress tracker
    "priority",  # Checklist: priority tiers
    "practice",  # Tutorial: exercise system
    "mistakes",  # Tutorial: common mistakes (informational type only)
    "troubleshooting",  # Tutorial: debugging system (informational type only)
    "progress_tracking",  # Tutorial: checkpoint tracking
    "assessment",  # Tutorial: knowledge quiz
    "extensions",  # Tutorial: advanced learning paths
    "skill_context",  # Tutorial: skill-type metadata
    "related_questions",  # FAQ: query expansion layer
    "ux",  # FAQ / Glossary: UX config
    "domain_context",  # Glossary: domain framing
    "relationships",  # Glossary: term relationship map
    "cross_references",  # Glossary: cross-link system
    "background",  # WhitePaper: historical context
    "use_cases",  # WhitePaper: application section (informational only — see structural keys)
    "risks",  # WhitePaper: risk evaluation table (informational only)
    "visuals",  # WhitePaper / CaseStudy: data viz plan
    "glossary",  # WhitePaper: embedded term glossary
    "future_outlook",  # WhitePaper: trend forecasts
    "comparison",  # WhitePaper: option comparison table (informational only)
    "testimonials",  # CaseStudy: social proof quotes
    "applicability",  # CaseStudy: generalization layer
    "client",  # CaseStudy: shown via hero.description
    "summary",  # All types: AI-generated summary layer
    "user_journey",  # PillarContent: buyer journey mapping
    "learning_path",  # ResourceList: sequenced learning steps
    "learning_context",  # ResourceList: skill level framing
    "quality",  # ResourceList: curation quality signals
    "tagging",  # ResourceList: SEO tag system
    "comparisons",  # ResourceList: resource comparison objects
    "data_sources",  # Top-level in some schemas
    # ── Commercial optimization fields ──────────────────────────────────────────
    # surfaced as top-level render.conversion_goal instead of a block
    "conversion_goal",
    # CRO psychology signals — author guidance, not approval items
    "price_psychology_type",
    "guarantee_type",
    # Timing / speed optimization targets — internal UX metrics
    "decision_speed_goal_seconds",
    "decision_confidence_goal",
    "decision_clarity_goal",
    "decision_influence_goal",
    # ── Transactional optimization fields ───────────────────────────────────────
    "signup_strategy_type",  # SignupPage: internal PLG strategy type
    "activation_metric",  # SignupPage: internal activation event key
    "target_time_to_signup_seconds",
    "target_time_to_conversion_seconds",  # DemoPage
    "calendar_integration",  # DemoPage: booking config
    "lead_capture_fields",  # DemoPage: form fields for lead capture
    "lead_magnet",  # LandingPage / ServicePage: optional freebie
    "visual_direction",  # LandingPage: image/design hints for author
    "urgency_elements",  # ServicePage: scarcity copy hints
    "qualification",  # ServicePage: lead qualification (author guidance)
    "pricing_strategy_type",  # PricingPage: flat_rate / tiered / freemium etc.
    "currency",  # PricingPage: ISO currency (author reference)
    "abandoned_cart_recovery",  # CheckoutPage: retargeting config
    "coupon_field_enabled",  # CheckoutPage: UI config
    "tracking_events",  # CheckoutPage: analytics events
    "affiliate_disclosure",  # CouponPage: legal note (shown in blocks if needed)
    "supported_devices",  # CouponPage: technical detail
    "ui_microcopy",  # CouponPage: button/copy strings
    # ── Navigational optimization fields ────────────────────────────────────────
    "trust_intent_level",  # AboutUs: low/medium/high intent level
    "narrative_style",  # AboutUs: story-driven / fact-driven / hybrid
    "exploration_intent_level",  # BrandPage: curiosity / comparing / ready
    "brand_type",  # BrandPage: single_product / platform / etc.
    "product_adoption_goal",  # ProductHomepage: internal PLG goal string
    "time_to_first_value_seconds",  # ProductHomepage / FeatureOverview: UX metric
    "exploration_depth_target",  # ProductHomepage: low/medium/high
    "feature_adoption_stage",  # FeatureOverview: discovery/activation/retention
    "activation_goal",  # FeatureOverview: what user achieves first time
    "ai_support_assistant",  # HelpCenter: AI bot config
    "deflection_goal",  # HelpCenter: ticket-reduction target string
    "target_time_to_resolution_seconds",  # HelpCenter
    "interactive_docs_enabled",  # Documentation: playground config
    "ai_assistant_enabled",  # Documentation: AI search config
    "target_time_to_first_success_seconds",  # Documentation
    "auto_ticket_creation",  # ContactUs: form→ticket automation config
    "ai_response_suggestion",  # ContactUs: AI routing config
    "target_time_to_contact_seconds",  # ContactUs
    "contact_intent_types",  # ContactUs: free-text intent list (surfaced in routing block)
    "target_login_time_seconds",  # LoginGuide
    "failed_login_recovery_success_rate_goal",  # LoginGuide: internal SLA string
    "auth_methods_priority",  # LoginGuide: ordered list of auth methods (shown in auth block)
    "search",  # HelpCenter / Documentation: search system config
    "versioning",  # Documentation: version info (technical detail)
    "contribution",  # Documentation: contributor guide (technical detail)
    "update_info",  # BestTools: last-updated metadata
    "selection_criteria",  # BestTools: curation methodology (shown in rankings block)
    "selection_methodology",  # ProductRoundup: methodology (shown in best_picks block)
}


# ── hero extraction ─────────────────────────────────────────────────────────

# Extra description fields from each schema's hero sub-object,
# checked in order of information value for the approval screen.
_HERO_DESC_FIELDS = (
    # Informational hero descriptions
    "executive_summary",  # WhitePaper   — concise research summary
    "final_outcome",  # HowToGuide   — clear success state
    "final_skill_outcome",  # Tutorial     — skill the user gains
    "success_outcome",  # Checklist    — result after completion
    "simplified_definition",  # Explainer    — one-line concept explanation
    "authority_statement",  # PillarContent — why this is the definitive resource
    "curation_purpose",  # ResourceList  — gap the list fills
    "intent_summary",  # FAQ          — what problems these FAQs solve
    "purpose_statement",  # Glossary     — why the glossary exists
    "key_result",  # CaseStudy    — primary measurable outcome
    "key_takeaway",  # WhitePaper   — secondary insight
    "hook",  # Blog         — opening angle / hook
    # Commercial hero descriptions
    "verdict_preview",  # InDepthReview.ReviewHero — quick recommended/not verdict
    # Navigational hero descriptions
    "tagline",  # BrandPage.BrandHero — short brand positioning statement
    # Transactional / generic fallback
    "key_value_points",  # PricingPage.ValuePositioning — first bullet as description
)


def _resolve_hero(outline_dict: dict) -> dict:
    """Return a normalized {headline, subheadline, description} from any schema's hero.

    Falls back to schema-specific alternatives when there is no `hero` field:
    - PricingPage: uses `value_positioning` (same headline/subheadline shape)
    - CouponPage:  uses `coupon_offer` (title → headline, description → subheadline)
    """
    raw = outline_dict.get("hero")

    if not isinstance(raw, dict):
        # PricingPageOutline uses `value_positioning` as its hero equivalent
        vp = outline_dict.get("value_positioning")
        if isinstance(vp, dict):
            raw = vp
        else:
            # CouponPageOutline uses `coupon_offer` — map title/description manually
            co = outline_dict.get("coupon_offer")
            if isinstance(co, dict):
                return {
                    "headline": str(co.get("title", "") or "").strip(),
                    "subheadline": str(co.get("description", "") or "").strip(),
                    "description": "",
                }

    if not isinstance(raw, dict):
        return {"headline": "", "subheadline": "", "description": ""}

    headline = ""
    for k in ("headline", "title"):
        val = raw.get(k)
        if isinstance(val, str) and val.strip():
            headline = val.strip()
            break

    subheadline = ""
    for k in ("subheadline", "subtitle"):
        val = raw.get(k)
        if isinstance(val, str) and val.strip():
            subheadline = val.strip()
            break

    description = ""
    for k in _HERO_DESC_FIELDS:
        val = raw.get(k)
        if isinstance(val, str) and val.strip():
            description = val.strip()
            break
        # key_value_points is a list — take first item as description
        if k == "key_value_points" and isinstance(val, list) and val:
            first = str(val[0]).strip()
            if first:
                description = first
                break

    return {"headline": headline, "subheadline": subheadline, "description": description}


# ── metadata helpers ────────────────────────────────────────────────────────


def _resolve_focus_keyphrase(outline_dict: dict) -> str:
    """Get focus_keyphrase regardless of nesting (direct or under seo/seo_plan)."""
    direct = outline_dict.get("focus_keyphrase")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()
    for wrapper in ("seo", "seo_plan"):
        obj = outline_dict.get(wrapper)
        if isinstance(obj, dict):
            nested = obj.get("focus_keyphrase")
            if isinstance(nested, str) and nested.strip():
                return nested.strip()
    return ""


def _resolve_keywords(outline_dict: dict) -> list[str]:
    """Surface the primary keyword list regardless of per-type field name."""
    for key in (
        "keywords_to_include",
        "secondary_keywords",
        "focus_keywords",
        "semantic_keywords",
        "keywords",
    ):
        val = outline_dict.get(key)
        if isinstance(val, list) and val:
            return [str(k).strip() for k in val if k]
    for wrapper in ("seo", "seo_plan"):
        obj = outline_dict.get(wrapper)
        if isinstance(obj, dict):
            for key in (
                "secondary_keywords",
                "keywords_to_include",
                "focus_keywords",
                "semantic_keywords",
                "search_variants",
            ):
                val = obj.get(key)
                if isinstance(val, list) and val:
                    return [str(k).strip() for k in val if k]
    return []


def _resolve_content_goal(outline_dict: dict) -> str:
    """Resolve content_goal or completion_goal to a human-readable string."""
    for key in ("content_goal", "completion_goal"):
        val = outline_dict.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip().replace("_", " ").title()
    return ""


def _resolve_conversion_goal(outline_dict: dict) -> str:
    """Resolve conversion_goal for commercial and transactional schemas.

    Returns a human-readable string such as 'Start Trial' or 'Purchase'.
    Empty string for informational/navigational schemas that have no conversion_goal.
    """
    val = outline_dict.get("conversion_goal")
    if isinstance(val, str) and val.strip():
        return val.strip().replace("_", " ").title()
    return ""


def _resolve_reading_time(outline_dict: dict) -> int | None:
    """Return target reading or completion time in minutes, if present."""
    for key in ("target_reading_time_minutes", "target_completion_time_minutes"):
        val = outline_dict.get(key)
        if isinstance(val, int) and val > 0:
            return val
    return None


def _resolve_target_audience(outline_dict: dict) -> list[str]:
    val = outline_dict.get("target_audience")
    if isinstance(val, list):
        return [str(a).strip() for a in val if a]
    return []


# ── FAQ extraction ──────────────────────────────────────────────────────────


def _normalize_faq_list(raw: Any) -> list[dict]:
    """Normalize any schema's FAQ field value into [{"question", "answer"}, ...].

    Handles every shape seen across outline schemas:
    - FAQSection / ContactFAQ wrapper: {"faqs": [{"question", "answer"}, ...]}
    - Flat list of FAQItem-shaped dicts: [{"question", "answer"}, ...]
    - Flat list of bare question strings (e.g. PricingPage.faq): ["...", ...]
    """
    if isinstance(raw, dict):
        raw = raw.get("faqs")

    if not isinstance(raw, list):
        return []

    items: list[dict] = []
    for entry in raw:
        if isinstance(entry, dict):
            question = str(entry.get("question") or "").strip()
            answer = entry.get("answer")
            if isinstance(answer, dict):
                answer = answer.get("short_answer") or answer.get("text") or answer.get("summary")
            answer = str(answer or "").strip()
            if question:
                items.append({"question": question, "answer": answer})
        elif isinstance(entry, str) and entry.strip():
            items.append({"question": entry.strip(), "answer": ""})
    return items


def extract_outline_faqs(outline_dict: dict) -> list[dict]:
    """Return the outline's approved FAQ question/answer pairs, if any.

    Checks both field-name conventions used across schemas — `faqs` (required
    on most informational/commercial types) and `faq` (optional on most
    transactional/navigational types, singular) — and normalizes every known
    wrapper/list shape. Returns [] for schemas with no FAQ support (or, e.g.,
    Documentation.faq, which is a nav-link list rather than Q&A and has no
    "question" field so it never survives normalization).
    """
    if not isinstance(outline_dict, dict):
        return []
    for key in ("faqs", "faq"):
        items = _normalize_faq_list(outline_dict.get(key))
        if items:
            return items
    return []


# ── item extraction ─────────────────────────────────────────────────────────


def _prose_from_item(d: dict) -> str:
    """Extract a short answer/description string from a dict item.

    Handles both direct fields (short_answer, description, …) and one level of
    nesting such as FAQItem.answer.short_answer.
    """
    for key in _ANSWER_PROSE_FIELDS:
        val = d.get(key)
        if isinstance(val, str) and val.strip() and len(val) < 500:
            return val.strip()
    for wrapper in _ANSWER_WRAPPER_KEYS:
        val = d.get(wrapper)
        if isinstance(val, dict):
            for key in _ANSWER_PROSE_FIELDS:
                inner = val.get(key)
                if isinstance(inner, str) and inner.strip() and len(inner) < 500:
                    return inner.strip()
    return ""


def _primary_label(d: dict) -> str:
    for key in _LABEL_FIELDS:
        if key in d:
            val = d[key]
            if isinstance(val, (str, int)) and str(val).strip():
                return str(val).strip()
    for v in d.values():
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def _primary_points(d: dict) -> list[str]:
    for key in _POINTS_FIELDS:
        if key in d:
            val = d[key]
            if isinstance(val, list) and val:
                result = []
                for item in val:
                    if isinstance(item, str) and item.strip():
                        result.append(item.strip())
                    elif isinstance(item, dict):
                        lbl = _primary_label(item)
                        prose = _prose_from_item(item)
                        if lbl and prose:
                            result.append(f"{lbl} — {prose}")
                        elif lbl:
                            result.append(lbl)
                        elif prose:
                            result.append(prose)
                return result
    # fallback: short string fields that aren't label/skip fields
    result = []
    for k, v in d.items():
        if k in _SKIP_LABEL_FIELDS or k in _LABEL_FIELDS:
            continue
        if isinstance(v, str) and v.strip() and len(v) < 400:
            result.append(v.strip())
            if len(result) >= 3:
                break
    return result


def _items_from_list(lst: list) -> list[dict]:
    result = []
    for elem in lst:
        if isinstance(elem, dict):
            label = _primary_label(elem)
            points = _primary_points(elem)
            if label or points:
                result.append({"label": label, "points": points})
        elif isinstance(elem, str) and elem.strip():
            result.append({"label": elem.strip(), "points": []})
    return result


def _unwrap_nested_list(raw: dict) -> list | None:
    """
    If a dict wraps a single important list field, return that list.
    e.g. steps.steps → [Step], structure.sections → [Section],
         solution.components → [SolutionComponent],
         BenefitsSection.benefits → [BenefitItem]
    """
    nested_keys = (
        "sections",
        "steps",
        "items",
        "faqs",
        "goals",
        "clusters",
        "tools",
        "sources",
        "rows",
        "metrics",
        "errors",
        "testimonials",
        "challenges",
        "insights",
        "variations",
        "checks",
        "categories",
        "alternatives",
        "rankings",
        "pros",
        "cons",
        "recommendations",
        "phases",
        "modules",
        "terms",
        "resources",
        "products",
        # 2026 informational schema additions
        "components",  # SolutionFramework (white-paper), ConceptBreakdown (explainer)
        "layers",  # ProgressiveExplanation (explainer), ContentDepth (pillar)
        "key_decisions",  # StrategySection (case-study)
        "notes",  # SafetySection
        "rules",  # ValidationSection
        "mappings",  # OutcomeSection
        # Commercial schema nested lists
        "comparisons",  # UseCaseSection.comparisons (comparison)
        "matches",  # UseCaseSection.matches (alternatives, best-tools, buying-guide)
        "options",  # ProductOptions.options (buying-guide)
        "factors",  # DecisionFramework.factors (comparison, buying-guide)
        "groups",  # BestPickSection.groups (product-roundup)
        "features",  # FeatureSection.features (in-depth-review), FeatureBenefits
        "tests",  # UseCaseSection.tests (in-depth-review)
        "tradeoffs",  # TradeOffSection.tradeoffs (pros-cons)
        "fits",  # UseCaseSection.fits (pros-cons)
        "risks",  # RiskAnalysis.risks (pros-cons) — commercial type only
        "competitors",  # AlternativesList.competitors (alternatives)
        "ranked_tools",  # ToolRanking.ranked_tools (best-tools)
        # Transactional schema nested lists
        "benefits",  # BenefitsSection.benefits (sales-page, landing-page, service-page, feature-overview)
        "objections",  # ObjectionHandling.objections (many transactional schemas)
        "segments",  # BuyerSegments.segments (buying-guide), AudienceMap.segments (brand-page)
        # Navigational schema nested lists
        "common_issues",  # TroubleshootingSection.common_issues (help-center, login-guide)
        "paths",  # LearningPaths.paths (documentation, help-center)
        "methods",  # AuthenticationSystem.methods (login-guide)
        "actions",  # SelfServiceHub.actions (help-center)
        "channels",  # EscalationSystem.channels (help-center) — navigation type only
        "cases",  # UseCases.cases (feature-overview, product-homepage)
        "use_cases",  # UseCaseSection.use_cases (product-homepage)
    )
    for key in nested_keys:
        if key in raw and isinstance(raw[key], list):
            return raw[key]
    return None


def _extract_items(raw: Any) -> list[dict]:
    """
    Given any field value, return a list of {"label": str, "points": [str]} items.
    """
    if isinstance(raw, list):
        return _items_from_list(raw)

    if isinstance(raw, dict):
        # Try to unwrap a nested list first (e.g. BenefitsSection.benefits → [BenefitItem])
        inner = _unwrap_nested_list(raw)
        if inner is not None:
            return _items_from_list(inner)

        # Dict of named objects (e.g. products: {product_a: {...}, product_b: {...}})
        items = []
        for k, v in raw.items():
            if isinstance(v, dict):
                inner_label = _primary_label(v)
                full_label = f"{_label(k)}: {inner_label}" if inner_label else _label(k)
                points = _primary_points(v)
                items.append({"label": full_label, "points": points})
            elif isinstance(v, str) and v.strip():
                items.append({"label": _label(k), "points": [v.strip()]})
            elif isinstance(v, list) and v:
                # If any element is a dict, surface sub-items via _items_from_list.
                # This handles TeamSection.leadership, NavigationTree sub-sections, etc.
                if any(isinstance(i, dict) for i in v):
                    sub = _items_from_list(v)
                    if sub:
                        items.extend(sub)
                else:
                    flat = [str(i) for i in v if isinstance(i, str) and i]
                    if flat:
                        items.append({"label": _label(k), "points": flat[:5]})
        return items

    if isinstance(raw, str) and raw.strip():
        return [{"label": raw.strip(), "points": []}]

    return []


# ── public API ───────────────────────────────────────────────────────────────


def normalize_outline(outline_dict: dict, content_type: str) -> dict:
    """
    Convert any outline dict into a generic renderable shape for frontend display.

    Returns everything the user needs to review and approve an outline:
    editable metadata (title, slug, audience, tone, keyphrase, word count),
    the content hero/angle, structural blocks (sections/steps/products/etc.),
    supporting SEO keywords, and the strategic conversion or content goal.

    Internal AI fields — EEAT signals, engagement plans, entity graphs,
    snippet targets, optimization timing targets, writing-guidance layers —
    are intentionally excluded. They drive content generation but are not
    relevant during outline approval.

    Returns:
        {
            "title": str,
            "schema_type": str,           # human-readable content type label
            "slug_suggestion": str,       # editable URL slug
            "focus_keyphrase": str,
            "keywords_to_include": [str],
            "target_word_count": int,
            "target_audience": [str],     # who the content targets (editable)
            "tone": str,                  # writing tone (editable)
            "hero": {                     # article/page angle — key approval item
                "headline": str,
                "subheadline": str,
                "description": str,       # type-specific: verdict / outcome / tagline
            },
            "content_goal": str,          # informational: what the article achieves
            "conversion_goal": str,       # commercial/transactional: page conversion aim
            "reading_time": int | None,   # estimated minutes to read / complete
            "rejected_reason": str,
            "status": str,
            "blocks": [
                {
                    "heading": str,       # human label for this structural block
                    "items": [
                        {
                            "label": str,     # section/step/product/feature name
                            "points": [str],  # key points / features / actions
                        }
                    ]
                }
            ]
        }
    """
    from src.flow.model.structure.outlines import normalize_content_type

    ct = normalize_content_type(content_type)
    keys_to_try = _STRUCTURAL_KEYS.get(ct) or []

    blocks: list[dict] = []

    for key in keys_to_try:
        raw = outline_dict.get(key)
        if raw is None:
            continue
        items = _extract_items(raw)
        if items:
            blocks.append({"heading": _label(key), "items": items})

    # Fallback: scan all non-meta fields for any list/dict content
    if not blocks:
        for key, raw in outline_dict.items():
            if key in _META_KEYS:
                continue
            if isinstance(raw, (list, dict)):
                items = _extract_items(raw)
                if items:
                    blocks.append({"heading": _label(key), "items": items})
                    if len(blocks) >= 6:
                        break

    return {
        "title": outline_dict.get("title", ""),
        "schema_type": outline_dict.get("schema_type", ""),
        "slug_suggestion": outline_dict.get("slug_suggestion", ""),
        "focus_keyphrase": _resolve_focus_keyphrase(outline_dict),
        "keywords_to_include": _resolve_keywords(outline_dict),
        "target_word_count": outline_dict.get("target_word_count") or 0,
        "target_audience": _resolve_target_audience(outline_dict),
        "tone": outline_dict.get("tone", ""),
        "hero": _resolve_hero(outline_dict),
        "content_goal": _resolve_content_goal(outline_dict),
        "conversion_goal": _resolve_conversion_goal(outline_dict),
        "reading_time": _resolve_reading_time(outline_dict),
        "rejected_reason": outline_dict.get("rejected_reason", ""),
        "status": outline_dict.get("status", ""),
        "blocks": blocks,
        "faqs": extract_outline_faqs(outline_dict),
    }

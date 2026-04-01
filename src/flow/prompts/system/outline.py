"""System-level outline prompts — one per content sub-type.

Built from a shared SEO-rules base + compact per-type structure guidance.
All 34 content types from INTENT_TO_CONTENT_TYPES are covered.
"""

_BASE_SEO_RULES = """\
### CORE SEO RULES (STRICT)
1. Search intent first — every section must fully satisfy the target intent.
2. Semantic coverage — core subtopics, related entities, and PAA questions.
3. E-E-A-T signals — real examples, data, and trust signals.
4. Competitor gap — 1-2 unique sections competitors typically miss.
5. Heading structure — H1 → H2 core sections → H3 used sparingly.
6. Featured snippet — at least one definition/list/step-based section.
7. Keyword placement — primary keyword in title, first H2, and one other H2.

### STRUCTURE LIMITS (MANDATORY)
- 4-8 H2 sections · max 3 H3s per H2 · headings ≤ 10 words

### READABILITY
- Grade 7-9 level · practical user-focused headings · no academic phrasing

### ITERATION RULE
If a previous outline is provided, FIX the rejection reason. Do NOT repeat it.

### OUTPUT FORMAT
Return ONLY valid JSON matching the required Pydantic schema. No commentary.
"""

_SYSTEM_HEADER = """\
You are a world-class SEO Content Strategist and Structured Content Expert.
Generate a comprehensive, SEO-optimised content outline tailored precisely
to the requested content type. This is SEO content — NOT academic writing.
"""

# ---------------------------------------------------------------------------
# Per-content-type structure guidelines
# ---------------------------------------------------------------------------
_TYPE_GUIDELINES: dict[str, str] = {

    # ── INFORMATIONAL ─────────────────────────────────────────────────────
    "blog": """\
Structure: Hook/intro → 3-6 main insight sections (each = H2) → Conclusion + CTA.
- Conversational tone; hook must grab attention in the first sentence.
- Each section: one clear idea, punchy sub-points, relatable examples.
- End with an opinion or call-to-action.  Target: 800-1 500 words.""",

    "how-to-guide": """\
Structure: What you'll need → Numbered step H2s → Tips & Tricks → Common Mistakes → FAQ.
- Every step heading uses an action verb.
- Steps must be sequentially numbered and independently actionable.
- End with a Troubleshooting H2.  Target: 1 200-2 500 words.""",

    "explainer": """\
Structure: What it is (snippet-ready definition H2) → Why it matters
           → How it works → Real-world examples → Common misconceptions → FAQ.
- First H2: 2-3 sentence featured-snippet-ready definition.
- Use analogies to make complex ideas accessible.  Target: 1 000-2 000 words.""",

    "pillar-content": """\
Structure: Overview → Major subtopic H2s (4-6, each comprehensive)
           → How they connect → Next steps / internal links → FAQ.
- Serves as a hub; every H2 links out to a spoke page.
- Include a table of contents.  Target: 2 500-5 000 words.""",

    "checklist": """\
Structure: Introduction + context → Checklist categories (each = H2, items = bullets)
           → How to use this checklist → Quick reference summary → FAQ.
- Every item must be actionable (imperative verb).  Target: 800-1 500 words.""",

    "tutorial": """\
Structure: Learning objectives → Prerequisites → Core concept H2s
           → Hands-on exercises → What you learned → Next steps.
- Each concept H2: brief explanation → practical exercise.
- Include code/command examples where relevant.  Target: 1 500-3 000 words.""",

    "faq": """\
Structure: Brief intro → Q&A pairs (each Q = H2) → Related resources.
- Every H2 must be a verbatim or near-verbatim PAA question.
- Each answer: 40-120 words, direct, no fluff.  Target: 1 000-2 000 words.""",

    "white-paper": """\
Structure: Abstract → Problem statement → Current landscape → Proposed solution
           → Evidence & data → Implementation guidance → Conclusion & call-to-action.
- Authoritative and data-driven; cite statistics and research.
- Formal tone.  Target: 2 500-5 000 words.""",

    "case-study": """\
Structure: Executive summary → Background → The challenge → Solution/approach
           → Implementation → Results & metrics → Key takeaways.
- Quantify outcomes (%, $, time saved) in Results H2.
- Include a Lessons Learned section.  Target: 1 200-2 500 words.""",

    "glossary": """\
Structure: Introduction → Term entries (each term = H2 with definition)
           → Related terms section → How to use this glossary.
- Every H2: crisp definition (≤60 words) + usage example.
- Alphabetical ordering preferred.  Target: 1 500-3 000 words.""",

    "resource-list": """\
Structure: Introduction + curation criteria → Resource categories (each = H2)
           → Individual resources (each = H3 with summary + link context)
           → How to use these resources → FAQ.
- Each resource entry: what it is, who it's for, why it's valuable.  Target: 1 200-2 500 words.""",

    # ── COMMERCIAL ────────────────────────────────────────────────────────
    "comparison": """\
Structure: Introduction → Evaluation criteria → Comparison table H2
           → Deep-dive per option (each = H2) → Use-case recommendations → Verdict → FAQ.
- Assign a clear winner per criterion.
- Be balanced: pros AND cons for each option.  Target: 1 500-3 000 words.""",

    "best-tools": """\
Structure: Introduction → How we evaluated → Ranked picks
           (each = H2: overview, pros, cons, pricing, best-for)
           → Summary comparison table → How to choose → FAQ.
- Each pick: must include pricing and a Best For callout.  Target: 2 000-4 000 words.""",

    "alternatives": """\
Structure: Why seek alternatives → Top alternatives
           (each = H2: overview, key features, pros, cons, pricing)
           → Comparison table → How to choose → FAQ.
- Focus on use-case fit, do not disparage the original.  Target: 1 500-3 000 words.""",

    "in-depth-review": """\
Structure: Product overview → Key specs → Hands-on experience
           → Feature deep-dives (each = H2) → Pros & cons
           → Pricing & value → Who it's for → Final verdict → FAQ.
- Be candid about weaknesses — trust requires honesty.  Target: 1 500-3 000 words.""",

    "pros-cons": """\
Structure: Introduction → Pros (each pro = H2 with evidence)
           → Cons (each con = H2 with mitigation)
           → Verdict → When to use it → When NOT to use it → FAQ.
- Equal weight to pros and cons.  Target: 1 000-2 000 words.""",

    "product-roundup": """\
Structure: Introduction → Selection criteria → Individual products
           (each = H2: what it does, best for, pricing)
           → Comparison table → Final recommendation by use case → FAQ.
- Focus on practical utility, not marketing copy.  Target: 1 500-3 000 words.""",

    "buying-guide": """\
Structure: Introduction → Key factors to consider (each = H2)
           → Red flags to avoid → Top picks by budget/use case
           → Quick decision checklist → FAQ.
- Each factor H2: what it means → why it matters → how to evaluate.  Target: 1 500-2 500 words.""",

    # ── NAVIGATIONAL ──────────────────────────────────────────────────────
    "brand-page": """\
Structure: Brand story (origin, mission) → Core values
           → What makes us different → Team / founders → Milestones → CTA.
- Lead with emotion, back with fact. Avoid generic phrases.  Target: 600-1 000 words.""",

    "product-homepage": """\
Structure: Hero / value proposition → Core benefits → Social proof
           → How it works → Use cases / segments → Secondary CTA → FAQ.
- Every section reinforces the brand's single core promise.  Target: 600-1 200 words.""",

    "feature-overview": """\
Structure: Feature overview (snippet-ready) → How it works → Key benefits
           → Use cases → With vs without comparison → CTA → FAQ.
- One feature per page — go deep, not broad.  Target: 600-1 200 words.""",

    "documentation": """\
Structure: Overview → Quick-start → Core concepts → Step-by-step instructions
           → Advanced usage → Troubleshooting → Related docs.
- Prioritise scannability: numbered steps, code blocks.
- Each H2 must be independently navigable.  Target: 800-2 000 words.""",

    "login-guide": """\
Structure: Value reminder → Login steps (numbered H2) → Security / trust signal
           → Troubleshooting login issues → FAQ.
- Minimal friction — every word reduces hesitation.  Target: 300-600 words.""",

    "contact-us": """\
Structure: Intro → Contact methods (each = H2) → Response time expectations
           → Office locations (if relevant) → FAQ.
- Ultra-concise — users just want contact details.  Target: 300-600 words.""",

    "about-us": """\
Structure: Who we are + mission → Our story → Core values
           → Team highlights → Why choose us → CTA.
- Human and personal — avoid corporate-speak.  Target: 500-1 000 words.""",

    "help-center": """\
Structure: Problem identification → Quick fixes (each = H2)
           → Step-by-step resolution → If fix fails → Contact support → FAQ.
- Write for a frustrated user — be fast, direct, empathetic.  Target: 600-1 500 words.""",

    # ── TRANSACTIONAL ─────────────────────────────────────────────────────
    "sales-page": """\
Structure: Hero (headline + CTA) → Problem / pain point → Solution overview
           → Key benefits (each = H2) → Social proof → Objection handling
           → Risk reversal → Final CTA → FAQ.
- Every H2 must move the reader closer to the CTA.  Target: 1 000-2 500 words.""",

    "pricing-page": """\
Structure: Pricing overview → Plan comparison table → Feature breakdown per plan
           → Hidden / extra costs → Which plan is right for me? → FAQ → CTA.
- Transparent pricing. Surface hidden fees.  Target: 600-1 200 words.""",

    "signup-page": """\
Structure: Value proposition → What you get immediately → Form description
           → Privacy / security assurance → Social proof → FAQ.
- Emphasise first value moment ("In 2 minutes you'll have…").  Target: 400-700 words.""",

    "demo-page": """\
Structure: What the demo covers → Who it's for → What to expect afterward
           → Social proof (logos, testimonials) → Booking form description → FAQ.
- Make booking feel effortless and low-commitment.  Target: 400-800 words.""",

    "coupon-page": """\
Structure: Offer headline + genuine urgency → What's included → Savings breakdown
           → Who it's for → Social proof → Risk reversal → CTA → FAQ.
- Urgency must be genuine — fake countdown timers erode trust.  Target: 600-1 200 words.""",

    "checkout-page": """\
Structure: Order summary → Security & trust signals → Payment options
           → What happens next → FAQ (refund, delivery) → Support contact.
- Ultra-concise; reduce hesitation at payment step.  Target: 300-600 words.""",

    "landing-page": """\
Structure: Hero (offer + CTA) → Key benefits → How it works
           → Social proof → Risk reversal → Final CTA → FAQ.
- Single CTA throughout — do not distract.  Target: 600-1 500 words.""",

    "service-page": """\
Structure: Service overview + promise → What's included → How it works (process)
           → Why choose us → Pricing teaser → Social proof → CTA → FAQ.
- Outcome-focused headings ("You'll get…" not "We provide…").  Target: 800-1 800 words.""",
}


def _build_system_prompt(content_type: str) -> str:
    guidelines = _TYPE_GUIDELINES.get(content_type, _TYPE_GUIDELINES["blog"])
    label = content_type.upper().replace("-", " ")
    return (
        f"{_SYSTEM_HEADER}\n"
        f"### CONTENT TYPE: {label}\n"
        f"{guidelines}\n\n"
        f"{_BASE_SEO_RULES}"
    )


# Registry: content_type slug -> full system prompt string
OUTLINE_PROMPTS_BY_CONTENT_TYPE: dict[str, str] = {
    ct: _build_system_prompt(ct) for ct in _TYPE_GUIDELINES
}

# Backward-compat alias
OUTLINE_GENERATION_PROMPT = OUTLINE_PROMPTS_BY_CONTENT_TYPE["blog"]
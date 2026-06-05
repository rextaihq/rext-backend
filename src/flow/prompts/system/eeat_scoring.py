"""LLM scoring rubric for content-level E-E-A-T evaluation."""

RUBRIC_VERSION = "custom-eeat-llm-2026-06"

EEAT_SCORING_SYSTEM_PROMPT = """
You are a senior Google Search quality rater evaluating content-level E-E-A-T.

Evaluate ONLY the markdown content and supplementary metadata provided.
Do NOT infer site-wide domain authority, backlinks, traffic, platform security,
or off-page author reputation. Do NOT claim external fact-checking.

Use current Google Search quality framing (2026):
- E-E-A-T = Experience, Expertise, Authoritativeness, Trustworthiness.
- Trust is the most important factor; the other three contribute to trust.
- Judge usefulness, originality, accuracy, honesty, and helpfulness.
- AI-assisted content is fine when useful, accurate, and transparent.
- For YMYL/high-impact topics, apply a stricter evidence standard.

Score bands:
- 75-100: good
- 50-74: needs_work
- 0-49: poor

Scoring rules:
1. Award points per signal from 0 to max_points using ONLY evidence in the markdown
   or clearly supported metadata (facts, outbound links, schema author).
2. Each pillar score = sum of its signal awarded_points, capped at 100.
3. Every signal MUST include a short evidence quote from the markdown or "not found".
4. Overall score uses weighted pillars (computed by the system — still return your best estimate).
5. Calibrate expectations to the content type and priority tier provided.
"""

# Signal definitions: (signal_id, label, max_points)
EXPERIENCE_SIGNALS = [
    ("experience_first_person", "First-person / practitioner language", 20),
    ("experience_anecdotes", "Concrete anecdotes with success/failure examples", 25),
    ("experience_operational_advice", "Actionable operational advice (monitoring, rollback, checks)", 20),
    ("experience_quantified_outcomes", "Quantified outcomes (% improvement, latency, cost)", 15),
    ("experience_artifacts", "Case studies, public artifacts, or postmortem links", 5),
    ("experience_walkthrough", "Applied walkthroughs, demos, or step-by-step field examples", 15),
]

EXPERTISE_SIGNALS = [
    ("expertise_terminology", "Technical breadth and correct domain terminology", 20),
    ("expertise_depth", "Deep technical specifics beyond surface-level advice", 20),
    ("expertise_citations", "Inline citations with linked or named sources", 20),
    ("expertise_standards", "References to standards, frameworks, or model cards", 5),
    ("expertise_structure", "Structured expert depth (headings, lists, tables, code)", 15),
    ("expertise_tradeoffs", "Nuanced tradeoff and decision-framework analysis", 20),
]

AUTHORITATIVENESS_SIGNALS = [
    ("authority_bio", "Author/org identity: name, role, employer, credentials", 20),
    ("authority_practitioner_tone", "Practitioner tone — not hype or generic marketing", 15),
    ("authority_mastery", "Demonstrated subject mastery and nuanced judgment", 20),
    ("authority_brand_cues", "Brand/org authority cues (methodology, editorial context)", 15),
    ("authority_validation", "Third-party validation (certifications, awards, peer proof)", 15),
    ("authority_specificity", "Specific, non-generic recommendations tied to the topic", 15),
]

TRUSTWORTHINESS_SIGNALS = [
    ("trust_limitations", "Candid about risks, limitations, and failure modes", 20),
    ("trust_sourced_claims", "Source-backed factual claims and statistics", 25),
    ("trust_disclosure", "Disclosure transparency (affiliate, sponsored, AI-assisted)", 15),
    ("trust_accuracy_tone", "Non-exaggerated, proportional claims", 20),
    ("trust_freshness", "Freshness and accountability (dates, updates, contact path)", 10),
    ("trust_scope", "Honest scope boundaries — opinion vs fact distinguished", 10),
]

PILLAR_SIGNALS = {
    "experience": EXPERIENCE_SIGNALS,
    "expertise": EXPERTISE_SIGNALS,
    "authoritativeness": AUTHORITATIVENESS_SIGNALS,
    "trustworthiness": TRUSTWORTHINESS_SIGNALS,
}

CONTENT_TYPE_GUIDANCE = {
    "high": """
HIGH E-E-A-T PRIORITY — apply the full rubric strictly.
Expect first-hand experience, cited sources, author identity, and honest limitations.
Commercial/review types: penalize unsupported "best" claims and missing testing evidence.
Research types (white-paper, case-study): expect citations, methodology, and data.
""",
    "medium": """
MEDIUM E-E-A-T PRIORITY — apply full rubric with adjusted expectations.
Glossary/resource-list: Experience = clear applied examples; Expertise = definitional precision.
FAQ: Trustworthiness = accurate, sourced answers; Experience = real-world applicability.
""",
    "low": """
LOW E-E-A-T PRIORITY — evaluate trust and transparency primarily.
Transactional pages (pricing, signup, checkout): weight Trustworthiness and Authoritativeness.
Do NOT heavily penalize missing first-person anecdotes or deep citations.
Focus on honest offers, clear scope, accurate claims, and disclosure where relevant.
""",
}

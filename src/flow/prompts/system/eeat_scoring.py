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
- AI-assisted content is acceptable when useful, accurate, and transparent.
- For YMYL/high-impact topics, apply a stricter evidence standard.

Score bands:
- 75-100: good — strong content-level signals for the content type
- 50-74: needs_work — useful but missing notable E-E-A-T signals
- 0-49: poor — thin, generic, misleading, or clearly untrustworthy

Scoring rules:
1. Award points per signal from 0 to max_points using evidence in the markdown
   or clearly supported metadata (facts, outbound links, schema author).
2. Each pillar score = sum of its signal awarded_points, capped at 100.
3. Every signal MUST include a short evidence quote from the markdown/metadata
   or "not found".
4. Award PARTIAL credit when evidence is present but incomplete — do not use
   only 0 or max_points unless evidence is fully absent or fully strong.
5. Overall score is computed by the system from weighted pillars — still return
   your best estimate in the score field.
6. Calibrate to the content type and priority tier. Score what IS present, not
   what a perfect enterprise article with a full author page would have.

Content-level scope (critical — do not over-penalize):
- No explicit author bio block is required. Practitioner first-person voice,
  operational depth, and metadata schema author all count toward authority_bio.
- Inline hyperlinks, named sources, and metadata facts/outbound_links count as
  citations even without a formal bibliography section.
- First-person operational advice counts toward both Experience and Authority.
- Signals marked [optional] are not deficiencies when N/A for the content type;
  award 0 without dragging down the whole pillar when no substitute exists.

Calibration benchmarks (content-level only):
- Solid professional blog/how-to with practitioner voice, structure, caveats,
  and topic depth: typically more than 65 overall — NOT 30-50.
- Reserve scores below 50 for thin, generic, hype-heavy, or misleading content.
- Transactional pages (pricing, signup): more than 60 is typical when offers are clear
  and claims are honest, even without anecdotes or citations.

Confidence scoring (return in the confidence field, 0-100):
Rate how confident you are in this assessment:
- 80-95: Long, complete content; most signals have clear evidence
- 60-79: Adequate content; several signals have partial or inferred evidence
- 40-59: Short or sparse content; many signals are "not found"
- Below 40: Fragmentary input or contradictory evidence
Factors: content length, evidence coverage across signals, clarity of content
type expectations, and whether metadata supplements gaps in the markdown.
"""

# Signal definitions: (signal_id, label, max_points)
# Labels are concise; applicability is governed by the system prompt and tier guidance.

EXPERIENCE_SIGNALS = [
    ("experience_first_person", "First-person / practitioner language", 20),
    ("experience_anecdotes", "Concrete anecdotes or real-world scenarios", 25),
    ("experience_operational_advice", "Actionable operational advice (monitoring, rollback, checks)", 20),
    ("experience_quantified_outcomes", "Quantified outcomes (% improvement, latency, cost)", 15),
    ("experience_artifacts", "Case studies, artifacts, or postmortem references", 5),
    ("experience_walkthrough", "Applied walkthroughs, demos, or step-by-step examples", 15),
]

EXPERTISE_SIGNALS = [
    ("expertise_terminology", "Technical breadth and correct domain terminology", 20),
    ("expertise_depth", "Deep technical specifics beyond surface-level advice", 20),
    ("expertise_citations", "Inline citations, links, or named sources", 20),
    ("expertise_standards", "References to standards, frameworks, or model cards", 5),
    ("expertise_structure", "Structured expert depth (headings, lists, tables)", 15),
    ("expertise_tradeoffs", "Nuanced tradeoff and decision-framework analysis", 20),
]

AUTHORITATIVENESS_SIGNALS = [
    ("authority_practitioner_tone",      "Practitioner tone — not hype or generic marketing",              15),
    ("authority_mastery",                "Demonstrated subject mastery and nuanced judgment",               20),
    ("authority_brand_cues",             "Brand/org authority cues (methodology, editorial context)",       15),
    ("authority_specificity",            "Specific, non-generic recommendations tied to the topic",         15),
    ("authority_named_credentials",      "Named byline with role and org visible in content",               15),
    ("authority_author_bio_depth",       "Bio explains WHY the author is qualified (experience, domain)",   10),
    ("authority_methodology_transparency","Author explains HOW they know what they claim",                  10),
]


TRUSTWORTHINESS_SIGNALS = [
    ("trust_limitations",    "Candid about risks, limitations, and failure modes",              20),
    ("trust_sourced_claims", "Source-backed factual claims and statistics",                     25),
    ("trust_disclosure",     "Disclosure transparency (affiliate, sponsored, AI-assisted)",     15),
    ("trust_accuracy_tone",  "Non-exaggerated, proportional claims",                            20),
    ("trust_scope",          "Honest scope boundaries — opinion vs fact distinguished",         10),
    ("trust_author_identity","Named author with verifiable bio or credentials link",            10),
]


PILLAR_SIGNALS = {
    "experience": EXPERIENCE_SIGNALS,
    "expertise": EXPERTISE_SIGNALS,
    "authoritativeness": AUTHORITATIVENESS_SIGNALS,
    "trustworthiness": TRUSTWORTHINESS_SIGNALS,
}

CONTENT_TYPE_GUIDANCE = {
    "high": """
HIGH E-E-A-T PRIORITY — apply the full rubric with fair, content-level calibration.
Expect practitioner voice, topic depth, and honest limitations for editorial content.
Commercial/review types: penalize unsupported superlatives; reward specific testing detail.
Research types (white-paper, case-study): expect citations, methodology, and data.
Do NOT require a standalone author bio — sustained first-person expertise is sufficient.
A well-executed article of this type should typically score mor than 65, not below 50.
""",
    "medium": """
MEDIUM E-E-A-T PRIORITY — apply the full rubric with adjusted expectations.
Glossary/resource-list: Experience = applied examples; Expertise = definitional precision.
FAQ: Trustworthiness = accurate answers; Experience = real-world applicability.
Optional signals (artifacts, standards, third-party validation) may be N/A — do not over-penalize.
Typical well-written content:more than 60 overall.
""",
    "low": """
LOW E-E-A-T PRIORITY — evaluate trust and transparency primarily.
Transactional pages (pricing, signup, checkout): weight Trustworthiness and Authoritativeness.
Do NOT penalize missing first-person anecdotes, deep citations, or author bios.
Focus on honest offers, clear scope, accurate claims, and disclosure where relevant.
Typical well-written transactional content: more than 60 overall.
""",
}
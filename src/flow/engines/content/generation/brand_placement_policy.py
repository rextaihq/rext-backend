"""Product-led-marketing (brand promotion) placement policy, per content type.

Research-derived: a per-content-type intensity/placement/guardrail analysis
covering all 34 outline schemas (informational, commercial, navigational,
transactional). Governs WHERE and HOW an approved brand mention should be
woven into each content type — a blog post earns one soft mid-body mention;
a sales page can lead with it above the fold; a glossary should almost never
carry one at all.

Whether promotion happens is gated upstream by `outline.promote_brand`
(set at outline-review time) — this module only answers "given it's
approved, where does it belong for THIS content type." Even content types
whose natural intensity is effectively zero (glossary, documentation,
login-guide, help-center) get a `forced_fallback` — an explicitly approved
mention must never be silently dropped just because the format doesn't
naturally suit it; it gets placed the least-disruptive way that format allows.
"""

from __future__ import annotations

from typing import Literal

from typing_extensions import NotRequired, TypedDict

Intensity = Literal["none", "low", "moderate", "high", "maximal"]

# Fraction of the article's length within which the brand mention must
# appear, for prefers_top=True types. Strict "hero"/"above-the-fold" types
# (brand-page, sales-page, landing-page, comparison, alternatives, ...) use
# this tighter default.
DEFAULT_TOP_POSITION_MAX_FRACTION = 0.2
# A ranked-list format like best-tools/product-roundup can legitimately place
# the featured entry anywhere in the first half (after an intro/methodology
# section) without that being "buried" — the reported complaint was about
# being ranked LAST, not about a literal above-the-fold requirement, so this
# format gets a looser, first-half threshold instead.
RANKED_LIST_TOP_POSITION_MAX_FRACTION = 0.5


class BrandPlacementPolicy(TypedDict):
    intensity: Intensity
    placement: str        # WHERE — injected into the generation prompt verbatim
    guardrail: str         # constraint — injected into the generation prompt verbatim
    prefers_top: bool      # coarse signal consumed by check_brand_placement_policy
    forced_fallback: str   # used only when intensity == "none" but promote_brand is True anyway
    # Only set where it deviates from DEFAULT_TOP_POSITION_MAX_FRACTION —
    # read via .get(..., DEFAULT_TOP_POSITION_MAX_FRACTION), so most entries
    # can omit it.
    top_position_max_fraction: NotRequired[float]


_DEFAULT_POLICY: BrandPlacementPolicy = {
    "intensity": "low",
    "placement": "One natural mention in a body section that genuinely relates to the brand's core offering.",
    "guardrail": "Never in the introduction or as a closing sentence/CTA — keep it a soft, single aside.",
    "prefers_top": False,
    "forced_fallback": "",
}

BRAND_PLACEMENT_POLICY: dict[str, BrandPlacementPolicy] = {
    # ── Informational ────────────────────────────────────────────────────
    "blog": {
        "intensity": "low",
        "placement": "One example mid-body only, plus an optional soft mention in the closing line/CTA.",
        "guardrail": "Never in the introduction, in any H2/H3 heading, in the title, or in meta_description.",
        "prefers_top": False,
        "forced_fallback": "",
    },
    "how-to-guide": {
        "intensity": "low",
        "placement": "The product may BE the tool the walkthrough demonstrates (its UI shown in the step screenshots/descriptions).",
        "guardrail": "Disclose in the title/H1 that this walkthrough is tool-specific — do not frame it as neutral, tool-agnostic advice.",
        "prefers_top": False,
        "forced_fallback": "",
    },
    "explainer": {
        "intensity": "low",
        "placement": "At most one visually separated aside near the end, e.g. \"How [Brand] approaches this.\"",
        "guardrail": "Keep the core explanation itself brand-free — explainer content is prime AI-citation real estate, and a pitch inside the explanation undermines that.",
        "prefers_top": False,
        "forced_fallback": "",
    },
    "pillar-content": {
        "intensity": "low",
        "placement": "One \"tools/resources\" section near the end that links out to commercial cluster pages.",
        "guardrail": "Let the linked commercial pages carry the actual pitch — the pillar body itself should stay mostly brand-free.",
        "prefers_top": False,
        "forced_fallback": "",
    },
    "checklist": {
        "intensity": "low",
        "placement": "A single optional closing note, e.g. \"Automate this with [Brand].\"",
        "guardrail": "Every checklist item must still stand alone and be fully usable if the brand reference were stripped out.",
        "prefers_top": False,
        "forced_fallback": "",
    },
    "tutorial": {
        "intensity": "low",
        "placement": "Same pattern as How-To — the product is the tool being demonstrated throughout.",
        "guardrail": "The title must signal this is product-specific instruction, not generic, tool-agnostic advice.",
        "prefers_top": False,
        "forced_fallback": "",
    },
    "faq": {
        "intensity": "none",
        "placement": "Zero promotional content inside regular answers. The one acceptable exception: one FAQ entry may legitimately be phrased \"Does [Brand] do X?\" if it answers a real question a reader would ask.",
        "guardrail": "FAQ schema is machine-read verbatim by search engines — self-promotion inside a regular answer reads as spam and risks rich-result eligibility.",
        "prefers_top": False,
        "forced_fallback": "Add exactly one FAQ entry phrased as a genuine reader question about the brand, e.g. \"Does [Brand] do X?\" — do not insert promotion into any other answer.",
    },
    "white-paper": {
        "intensity": "moderate",
        "placement": "One dedicated \"solution/framework\" section near the end of the document.",
        "guardrail": "Lead with data, methodology, and named authorship first — the brand section comes only after the analysis has earned credibility.",
        "prefers_top": False,
        "forced_fallback": "",
    },
    "case-study": {
        "intensity": "high",
        "placement": "Throughout the piece, following the arc: problem -> product -> results -> customer quote.",
        "guardrail": "Pair every claim with a named customer and specific numbers — this is the one informational type actually built to be product-centered.",
        "prefers_top": True,
        "forced_fallback": "",
    },
    "glossary": {
        "intensity": "none",
        "placement": "No dedicated placement — glossary entries are reference material, not a promotional surface.",
        "guardrail": "Zero exceptions under normal circumstances; this is the worst possible place for product-led marketing.",
        "prefers_top": False,
        "forced_fallback": "If explicitly approved anyway, mention the brand only as one real-world example inside a single relevant term's definition, phrased neutrally and factually (e.g. \"for example, [Brand]\"), never promotionally, and nowhere else.",
    },
    "resource-list": {
        "intensity": "low",
        "placement": "The brand can be one honest entry in a genuinely comprehensive list.",
        "guardrail": "Do not silently rank it #1 — if it's included, state the list's selection criteria and apply them consistently.",
        "prefers_top": False,
        "forced_fallback": "",
    },

    # ── Commercial ────────────────────────────────────────────────────────
    "comparison": {
        "intensity": "high",
        "placement": "Name ALL products being compared — including [Brand] — right away in the introduction, not just the competitors. Also in a dedicated \"how [Brand] differs\" section, and in the closing recommendation.",
        "guardrail": "Include a visible disclosure line, honest cons for your own product, and a structured comparison table — not just a subjective pitch.",
        "prefers_top": True,
        "forced_fallback": "",
    },
    "best-tools": {
        "intensity": "high",
        "placement": "Your own entry can appear anywhere from the first ranked section onward, but must NOT be pushed to the last entry or past the article's midpoint. This promotion was explicitly approved specifically so the brand gets featured prominently; burying it as the final/lowest-ranked entry defeats the purpose. Also include a \"how we evaluated\" methodology section.",
        "guardrail": "Positioning it prominently does not excuse dishonesty — state the evaluation methodology explicitly and apply it consistently to every entry, including your own, not just competitors.",
        "prefers_top": True,
        "top_position_max_fraction": RANKED_LIST_TOP_POSITION_MAX_FRACTION,
        "forced_fallback": "",
    },
    "product-roundup": {
        "intensity": "high",
        "placement": "Same as Best-Tools — your own entry can appear anywhere from the first ranked section onward (e.g. as \"Best Overall\"), but must NOT be pushed to the last entry or past the article's midpoint, plus an evaluation-methodology section.",
        "guardrail": "Same disclosure requirement as Best-Tools — consistent criteria applied to every entry, including your own.",
        "prefers_top": True,
        "top_position_max_fraction": RANKED_LIST_TOP_POSITION_MAX_FRACTION,
        "forced_fallback": "",
    },
    "alternatives": {
        "intensity": "high",
        "placement": "In the introduction, as the featured/first alternative discussed. The reader's search intent here is already \"looking to switch\" — leading with [Brand] is the expected, natural pattern for this format, not something to downplay or hedge.",
        "guardrail": "Leading with it does not excuse dishonesty — still list genuine limitations for your own product, not just strengths.",
        "prefers_top": True,
        "forced_fallback": "",
    },
    "in-depth-review": {
        "intensity": "high",
        "placement": "Throughout the full review body — since the brand is the review's actual subject, it must be named from the opening paragraph onward, not introduced only partway through.",
        "guardrail": "If reviewing your own product, an upfront disclosure is essentially required, plus real, specific limitations — not just strengths.",
        "prefers_top": True,
        "forced_fallback": "",
    },
    "pros-cons": {
        "intensity": "high",
        "placement": "Naturally in the Pros section.",
        "guardrail": "The Cons section must list genuine drawbacks — this format only stays credible long-term if the cons are real.",
        "prefers_top": False,
        "forced_fallback": "",
    },
    "buying-guide": {
        "intensity": "moderate",
        "placement": "One \"what to look for\" criteria section (that happens to map to your features), plus a closing CTA.",
        "guardrail": "Keep the criteria list itself vendor-neutral in wording — let the reader connect the dots rather than stating it outright.",
        "prefers_top": False,
        "forced_fallback": "",
    },

    # ── Navigational ──────────────────────────────────────────────────────
    "brand-page": {
        "intensity": "maximal",
        "placement": "Hero section, value props, and CTAs throughout.",
        "guardrail": "Intent is already fully branded here — there is no need to \"earn\" the pitch as in other content types.",
        "prefers_top": True,
        "forced_fallback": "",
    },
    "product-homepage": {
        "intensity": "maximal",
        "placement": "Same as Brand Page — hero, value props, and CTAs throughout.",
        "guardrail": "Same as Brand Page.",
        "prefers_top": True,
        "forced_fallback": "",
    },
    "feature-overview": {
        "intensity": "high",
        "placement": "Feature framing throughout the piece, with a CTA at the close.",
        "guardrail": "Keep every feature claim specific and verifiable, not vague marketing language.",
        "prefers_top": True,
        "forced_fallback": "",
    },
    "documentation": {
        "intensity": "none",
        "placement": "No dedicated placement — this is support content in navigational clothing.",
        "guardrail": "A pitch in the middle of troubleshooting steps damages trust with existing customers who came here to solve a problem.",
        "prefers_top": False,
        "forced_fallback": "If explicitly approved anyway, add at most one low-key mention in a closing \"related resources\"/\"need more help\" note — never inside the actual troubleshooting/instructional steps.",
    },
    "login-guide": {
        "intensity": "none",
        "placement": "No dedicated placement — pure task-completion content.",
        "guardrail": "Same as Documentation — this is not a promotional surface.",
        "prefers_top": False,
        "forced_fallback": "If explicitly approved anyway, add at most one low-key mention in a closing note — never inside the actual login/auth steps.",
    },
    "help-center": {
        "intensity": "none",
        "placement": "No dedicated placement — pure task-completion content.",
        "guardrail": "Same as Documentation and Login Guide.",
        "prefers_top": False,
        "forced_fallback": "If explicitly approved anyway, add at most one low-key mention in a closing note — never inside the actual support/self-service steps.",
    },
    "contact-us": {
        "intensity": "low",
        "placement": "Minimal, functional copy only — if included at all, a brief line near the page's closing.",
        "guardrail": "Keep copy functional; this page's job is routing the visitor, not pitching them.",
        "prefers_top": False,
        "forced_fallback": "",
    },
    "about-us": {
        "intensity": "moderate",
        "placement": "Narrative/founder-story led — brand naturally threaded through the company story from early on.",
        "guardrail": "This is the best fit in this category for authentic, voice-driven storytelling — not a hard sell.",
        "prefers_top": True,
        "forced_fallback": "",
    },

    # ── Transactional ─────────────────────────────────────────────────────
    "sales-page": {
        "intensity": "maximal",
        "placement": "Above-the-fold value prop + CTA, objection-handling and social proof mid-page, and a final CTA.",
        "guardrail": "This structure is designed to saturate with product-led marketing — that's the format's job.",
        "prefers_top": True,
        "forced_fallback": "",
    },
    "pricing-page": {
        "intensity": "high",
        "placement": "Value justification woven into each pricing tier, plus an objection-handling FAQ near the bottom.",
        "guardrail": "Don't bury the actual pricing under narrative copy — value framing supports the numbers, it doesn't replace them.",
        "prefers_top": True,
        "forced_fallback": "",
    },
    "signup-page": {
        "intensity": "low",
        "placement": "Minimal persuasive copy; lead with trust signals (security badges, one short testimonial) over prose.",
        "guardrail": "Over-writing here hurts conversion — the goal is reducing friction, not adding narrative.",
        "prefers_top": False,
        "forced_fallback": "",
    },
    "demo-page": {
        "intensity": "moderate",
        "placement": "A value prop plus a clear \"what to expect\" section, in light copy.",
        "guardrail": "Same friction-reduction logic as Signup — don't over-narrate.",
        "prefers_top": True,
        "forced_fallback": "",
    },
    "coupon-page": {
        "intensity": "high",
        "placement": "Urgency/value framing, typically near the top.",
        "guardrail": "Keep it straightforward and short.",
        "prefers_top": True,
        "forced_fallback": "",
    },
    "checkout-page": {
        "intensity": "low",
        "placement": "Trust/security signals only.",
        "guardrail": "Zero persuasive copy — any added friction at checkout costs conversions directly.",
        "prefers_top": False,
        "forced_fallback": "",
    },
    "landing-page": {
        "intensity": "maximal",
        "placement": "Same pattern as Sales Page — above-the-fold value prop and CTA, carried through the page.",
        "guardrail": "Match the page's specific campaign angle — not a generic, one-size-fits-all pitch.",
        "prefers_top": True,
        "forced_fallback": "",
    },
    "service-page": {
        "intensity": "high",
        "placement": "A value prop plus a woven-in case-study/proof section.",
        "guardrail": "Slightly longer-form than Sales Page — let the proof section carry the trust weight, not just claims.",
        "prefers_top": True,
        "forced_fallback": "",
    },
}


def resolve_brand_placement_policy(content_type: str) -> BrandPlacementPolicy:
    """The full PLM placement policy for this content type.

    Defaults to a conservative low-intensity/body-only policy for any
    content type not explicitly covered above.
    """
    from src.flow.model.structure.outlines import normalize_content_type

    normalized = normalize_content_type(content_type)
    return BRAND_PLACEMENT_POLICY.get(normalized, _DEFAULT_POLICY)

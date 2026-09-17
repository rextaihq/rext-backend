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
#
# Deliberately NOT tied to DEFAULT_BODY_ATTENTION_MAX_FRACTION even when the two
# happen to share a number: this is a tolerance ceiling on a type that is already
# structurally slotted at rank 1 (see brand_slot.py), not an attention window on
# a body-led piece. They answer different questions and move independently.
RANKED_LIST_TOP_POSITION_MAX_FRACTION = 0.5

# Body-only types (blog, explainer, how-to, ...) get a POSITIVE attention
# window rather than the old purely-negative rule ("not in the intro, not in
# the last 10%"), which let a mention at the 85% mark pass silently. Anchored
# to reader-attention and AI-citation measurement — roughly three-quarters of
# viewing time falls within the first couple of screenfuls, and the bulk of
# generative-answer citations are drawn from the opening third of a page — but
# kept as a tunable policy field rather than a hardcoded constant, because that
# measurement is directional industry data rather than a fixed law.
#
# Set to the opening third, matching the citation measurement above. It was
# previously 0.5, which was looser than the evidence it cited: a first mention at
# the 45% mark passed while sitting outside the range readers and answer engines
# actually draw from.
DEFAULT_BODY_ATTENTION_MAX_FRACTION = 0.3

# Percentage form of the window above, for the PLACEMENT prose injected verbatim
# into the generation/humanize/persona prompts. Derived rather than written out,
# so the instruction the writer model is given can never drift from the threshold
# check_brand_placement_policy actually enforces — that drift is what turns a
# tightened window into silent extra repair loops.
_BODY_WINDOW_PCT = int(DEFAULT_BODY_ATTENTION_MAX_FRACTION * 100)

# NOTE: positional checks grade the FIRST appearance of the brand, not the most
# substantive one. The brand may legitimately recur through a piece; only the
# first mention has to land in the window, and the rest are woven in naturally.
# (A former PRIMARY_MENTION_MAX_FRACTION graded the most-substantive occurrence
# instead — removed, because it failed articles whose first mention was correctly
# placed simply for mentioning the brand again later.)


# HERO_ANCHORED_RATIONALE — why `hero_anchored` exists, and why a percentage
# window cannot replace it.
#
# The positional window above is measured as a character fraction of
# `introduction + body_markdown`. On a body-led page that is a fine proxy for
# "early". On a HERO-LED page it is not, because the hero is not at the start of
# that combined string — the introduction is, and the hero block opens
# body_markdown immediately after it.
#
# So the hero begins at roughly `len(introduction)` characters in, and the check
# only passes when `len(introduction) < 0.2 * (len(introduction) + len(body))`
# — i.e. when the body is more than four times the introduction. A landing page
# is 400-1200 words total and `BaseGeneratedContent.introduction` asks for three
# to four paragraphs (~220 words), so that inequality is routinely false: a
# landing page whose hero names the brand in its very FIRST sentence was being
# failed as "only appears later", while one that named the brand solely in the
# introduction and never in the hero passed. The grader was inverted relative to
# what the content type actually requires.
#
# Anchoring to structure instead removes the dependency on relative lengths
# entirely: the hero region is the introduction plus the body's opening section
# (the copy before the first H2), which is exactly the `hero` ContentBlock that
# structured generation emits — `ContentBlock.heading` is deliberately null for a
# hero, so it renders as unheaded opening copy. That definition also survives
# humanization's free-form rewrite, where block provenance is gone but the
# heading structure remains.


class BrandPlacementPolicy(TypedDict):
    intensity: Intensity
    placement: str  # WHERE — injected into the generation prompt verbatim
    guardrail: str  # constraint — injected into the generation prompt verbatim
    prefers_top: bool  # coarse signal consumed by check_brand_placement_policy
    forced_fallback: str  # used only when intensity == "none" but promote_brand is True anyway
    # Only set where it deviates from DEFAULT_TOP_POSITION_MAX_FRACTION —
    # read via .get(..., DEFAULT_TOP_POSITION_MAX_FRACTION), so most entries
    # can omit it.
    top_position_max_fraction: NotRequired[float]
    # Body-only counterpart, read via
    # .get(..., DEFAULT_BODY_ATTENTION_MAX_FRACTION). Set it per-type only where
    # a format genuinely earns a looser or tighter window than the default.
    body_attention_max_fraction: NotRequired[float]
    # Grade the first mention against the page's STRUCTURE — the introduction
    # plus the body's opening/hero section — instead of the character-percentage
    # window above. Opt-in per type, and only meaningful alongside
    # prefers_top=True. See HERO_ANCHORED_RATIONALE above for why the
    # percentage window cannot express "in the hero" on a hero-led page.
    hero_anchored: NotRequired[bool]


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
        "placement": f"One example in an EARLY body section — the first section that genuinely relates to the brand's offering, inside the first {_BODY_WINDOW_PCT}% of the article. An optional soft echo in the closing line/CTA is fine, but it does not replace the earlier mention.",
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
        "placement": f'At most one visually separated aside in an EARLY body section, inside the first {_BODY_WINDOW_PCT}% — placed immediately after the core concept has been defined, not saved for the end. e.g. "How [Brand] approaches this."',
        "guardrail": "Keep the explanatory prose itself brand-free — the aside must sit OUTSIDE it as a clearly separated block. Explainer content is prime AI-citation real estate, and a pitch woven into the explanation undermines that; placing it early is fine, blending it into the explanation is not.",
        "prefers_top": False,
        "forced_fallback": "",
    },
    "pillar-content": {
        "intensity": "low",
        "placement": f'One "tools/resources" callout in an EARLY body section, inside the first {_BODY_WINDOW_PCT}%, that names the brand and links out to the commercial cluster pages.',
        "guardrail": "Let the linked commercial pages carry the detailed pitch — the callout names the brand and links onward; the surrounding pillar body stays brand-free.",
        "prefers_top": False,
        "forced_fallback": "",
    },
    "checklist": {
        "intensity": "low",
        "placement": f'A single note attached to the FIRST checklist item the brand genuinely automates, inside the first {_BODY_WINDOW_PCT}% of the list — e.g. "Automate this with [Brand]." Not a closing note appended after the list.',
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
        "placement": 'Zero promotional content inside regular answers. The one acceptable exception: one FAQ entry may legitimately be phrased "Does [Brand] do X?" if it answers a real question a reader would ask.',
        "guardrail": "FAQ schema is machine-read verbatim by search engines — self-promotion inside a regular answer reads as spam and risks rich-result eligibility.",
        "prefers_top": False,
        "forced_fallback": 'Add exactly one FAQ entry phrased as a genuine reader question about the brand, e.g. "Does [Brand] do X?" — do not insert promotion into any other answer.',
    },
    "white-paper": {
        "intensity": "moderate",
        "placement": f'One dedicated "solution/framework" section inside the first {_BODY_WINDOW_PCT}% of the document, immediately after the problem statement and methodology are established.',
        "guardrail": f"Establish the problem framing, data and named authorship BEFORE the brand section — but within the opening {_BODY_WINDOW_PCT}%, not deferred to the end. Credibility is earned by what precedes the section, not by how late it appears.",
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
        "forced_fallback": 'If explicitly approved anyway, mention the brand only as one real-world example inside a single relevant term\'s definition, phrased neutrally and factually (e.g. "for example, [Brand]"), never promotionally, and nowhere else.',
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
        "placement": 'Name ALL products being compared — including [Brand] — right away in the introduction, not just the competitors. Also in a dedicated "how [Brand] differs" section, and in the closing recommendation.',
        "guardrail": "Include a visible disclosure line, honest cons for your own product, and a structured comparison table — not just a subjective pitch.",
        "prefers_top": True,
        "forced_fallback": "",
    },
    "best-tools": {
        "intensity": "high",
        "placement": 'Your own entry can appear anywhere from the first ranked section onward, but must NOT be pushed to the last entry or past the article\'s midpoint. This promotion was explicitly approved specifically so the brand gets featured prominently; burying it as the final/lowest-ranked entry defeats the purpose. Also include a "how we evaluated" methodology section.',
        "guardrail": "Positioning it prominently does not excuse dishonesty — state the evaluation methodology explicitly and apply it consistently to every entry, including your own, not just competitors.",
        "prefers_top": True,
        "top_position_max_fraction": RANKED_LIST_TOP_POSITION_MAX_FRACTION,
        "forced_fallback": "",
    },
    "product-roundup": {
        "intensity": "high",
        "placement": 'Same as Best-Tools — your own entry can appear anywhere from the first ranked section onward (e.g. as "Best Overall"), but must NOT be pushed to the last entry or past the article\'s midpoint, plus an evaluation-methodology section.',
        "guardrail": "Same disclosure requirement as Best-Tools — consistent criteria applied to every entry, including your own.",
        "prefers_top": True,
        "top_position_max_fraction": RANKED_LIST_TOP_POSITION_MAX_FRACTION,
        "forced_fallback": "",
    },
    "alternatives": {
        "intensity": "high",
        "placement": 'In the introduction, as the featured/first alternative discussed. The reader\'s search intent here is already "looking to switch" — leading with [Brand] is the expected, natural pattern for this format, not something to downplay or hedge.',
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
        "placement": f'One "what to look for" criteria section inside the first {_BODY_WINDOW_PCT}% (whose criteria happen to map to your features), plus an optional closing CTA. The criteria section carries the mention — the CTA is not a substitute for it.',
        "guardrail": "Keep the criteria list itself vendor-neutral in wording — let the reader connect the dots rather than stating it outright.",
        "prefers_top": False,
        "forced_fallback": "",
    },
    # ── Navigational ──────────────────────────────────────────────────────
    "brand-page": {
        "intensity": "maximal",
        "placement": "Hero section, value props, and CTAs throughout.",
        "guardrail": 'Intent is already fully branded here — there is no need to "earn" the pitch as in other content types.',
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
        "forced_fallback": 'If explicitly approved anyway, add at most one low-key mention in a closing "related resources"/"need more help" note — never inside the actual troubleshooting/instructional steps.',
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
        "placement": "Minimal, functional copy only — if included at all, one brief line in the page's opening block, not appended at the bottom.",
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
        "placement": 'A value prop plus a clear "what to expect" section, in light copy.',
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
        "placement": (
            "In the HERO itself — the opening block, before the first section heading. Name the brand "
            "explicitly in the hero's first sentence or two, as part of the above-the-fold value prop and "
            "CTA, then carry it through the page. A later section is not a substitute for the hero."
        ),
        "guardrail": "Match the page's specific campaign angle — not a generic, one-size-fits-all pitch.",
        "prefers_top": True,
        # The hero is this format's entire point, so placement is graded against
        # the hero block rather than a character-percentage window that a long
        # introduction pushes the hero out of. See HERO_ANCHORED_RATIONALE above.
        "hero_anchored": True,
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


def resolve_placement_instruction(policy: BrandPlacementPolicy) -> tuple[str, bool]:
    """(the placement text that applies, whether it is the forced fallback).

    A content type whose natural intensity is "none" (glossary, documentation,
    login-guide, help-center, faq) carries a `forced_fallback` for the case where
    the user approved a mention anyway — an explicitly approved mention must
    never be silently dropped just because the format doesn't suit it, it gets
    placed the least-disruptive way that format allows.

    Choosing between the two is a property of the policy, so it lives here rather
    than being re-decided by each consumer. Both the generation prompt
    (content_generation.py) and the schema directive (brand_schema_context.py)
    call this, so they cannot state different placements for the same article.
    """
    if policy["intensity"] == "none" and policy.get("forced_fallback"):
        return policy["forced_fallback"], True
    return policy["placement"], False


# Where brand_slot.apply_brand_slot_to_outline has already placed the brand for
# each featured-candidate content type, phrased so the writer model recognises it
# in the Structural Plan it was handed.
#
# These used to be loose labels ("the compared Products list", "the Alternatives
# list") describing containers that did not exist in the shape claimed:
# AlternativesOutline.alternatives_list.competitors is the COMPETITOR set, where
# filing our own product would be semantically wrong, and ComparisonOutline.products
# was a two-field {product_a, product_b} struct rather than a list you could insert
# at the front of. The model was being told to perform an edit the schema could not
# express, so it fell back to mentioning the brand wherever felt natural, which is
# the drift this whole module exists to stop. Each entry now names the real field
# and the real operation. (Comparison's products field is a genuine 2-4 item list
# as of the name-keyed schema migration, so its anchor finally matches the others.)
_BRAND_SLOT_LABEL = {
    # Both ranked-list types also carry a feature-comparison table whose product
    # list is generated BEFORE the promotion is approved. Ranking the brand #1
    # while publishing a comparison table it is absent from undoes the ranking —
    # on a commercial-intent page the table is what readers actually compare on,
    # so the anchor has to name it explicitly alongside the ranking.
    "best-tools": (
        "the FIRST entry of the Rankings list (rank 1), the FIRST column of the "
        "feature-comparison table, and the decision guide, pricing insights, use-case "
        "matches and tool categories — every comparison table rendered in the article must "
        "include a row/column for it, not only the competitors"
    ),
    "product-roundup": (
        "the FIRST entry of the first Best-Picks group (rank 1) and the FIRST column of the "
        "feature-comparison table — every comparison table rendered in the article must "
        "include a row/column for it, not only the competitors"
    ),
    "comparison": (
        "the FIRST entry of the compared Products list, plus the FIRST column of the "
        "feature-comparison table, the pricing comparison and the recommendations — the brand "
        "is one of the products being compared, so every table, verdict and recommendation "
        "must reference it by name alongside the competitors, not only the hero"
    ),
    "alternatives": (
        "the positioning statement and the hero/opening, as the featured alternative — NOT as "
        "an entry in the competitors list"
    ),
}


def build_brand_structural_injection(
    content_type: str,
    brand_name: str,
    policy: BrandPlacementPolicy | None = None,
) -> str:
    """A concrete structural anchor for WHERE to place/move the brand mention —
    not just descriptive PLACEMENT prose, which a model can satisfy narratively
    (generic value-prop copy) without ever naming the brand where it matters.

    Single source of truth, reused everywhere a placement instruction is
    injected — content generation (content_generation.py, persona_middleware.py),
    the humanize rewrite pass, and the targeted-repair prompt (repair_content.py)
    — so all four stages agree on the same concrete anchor instead of drifting
    across independently-worded prose.

    Featured-candidate commercial types (best-tools, comparison, ...) point at
    the concrete outline field brand_slot.py already wrote the brand into. Any
    other `prefers_top` type (landing-page, sales-page, brand-page, ...) gets a
    generic but concrete anchor: name the brand inside the opening/hero section
    itself, within the policy's top-position window. Non-`prefers_top` types
    return "" — their placement is carried by the outline slot plus the
    positional check, so a second prose-level anchor here would only
    double-instruct.

    Phrased as "honour the position the plan already gives it" rather than the
    old "the plan doesn't include the brand, add it": since promote_brand now
    reserves a real slot at approval time, telling the model to invent one
    contradicts the Structural Plan in front of it.
    """
    from src.flow.model.structure.outlines import normalize_content_type

    normalized = normalize_content_type(content_type)

    slot_label = _BRAND_SLOT_LABEL.get(normalized)
    if slot_label:
        return (
            f"\nSTRUCTURAL REQUIREMENT: the Structural Plan above already places {brand_name} at "
            f"{slot_label}. Write it there. Do not demote it to a later entry, do not drop it to the end "
            f"of the list, and do not satisfy this by mentioning {brand_name} only in prose elsewhere "
            f"while writing something else into that slot.\n"
        )

    resolved_policy = policy or BRAND_PLACEMENT_POLICY.get(normalized, _DEFAULT_POLICY)
    if not resolved_policy.get("prefers_top"):
        return ""

    # Hero-anchored types are GRADED against the hero block, not a percentage, so
    # the anchor must name the hero rather than quote a percentage the checker no
    # longer enforces. Quoting "the first 20%" here is what let the model satisfy
    # the instruction by opening the INTRODUCTION with the brand and leaving the
    # hero itself brand-free.
    if resolved_policy.get("hero_anchored"):
        return (
            f"\nSTRUCTURAL EDIT REQUIRED: {brand_name} must be named explicitly inside the HERO — the "
            f"opening block of the page, the copy that runs BEFORE the first section heading. The "
            f"Structural Plan above already carries {brand_name} in the hero; write it there. Generic "
            f"value-prop language that never says the name does not satisfy this, and naming it only in a "
            f"later section does not either. If {brand_name} is currently named only further down the page, "
            f"MOVE that naming into the hero copy (don't just add a second, later mention) — the hero must "
            f'say "{brand_name}" by name.\n'
        )

    max_fraction = resolved_policy.get(
        "top_position_max_fraction", DEFAULT_TOP_POSITION_MAX_FRACTION
    )
    pct = int(max_fraction * 100)
    return (
        f"\nSTRUCTURAL EDIT REQUIRED: {brand_name} must be named explicitly within the first {pct}% of the "
        f"article — inside the opening/hero section itself, not just implied by generic value-prop language "
        f"that never says the name. If {brand_name} is currently only named later in the piece, MOVE that "
        f"naming into the opening section (don't just add a second, later mention) — the opening section must "
        f'say "{brand_name}" by name.\n'
    )

"""Deterministic quality gate: LangGraph nodes, not agent middleware.

validate_content / final_validate_content run outside create_content_agent()
entirely, so the gate is always enforced by LangGraph routing rather than
something the writer agent could choose to skip. Every check here is plain
string/regex/structural logic — no LLM calls, milliseconds — because the goal
is to catch "wrong" (fabricated citation, mismatched URL, bolted-on mention)
in addition to "missing," using exact-match against real ground truth rather
than semantic judgment. See the plan's "Guarantees and limits" section for
what is and isn't achievable this way.
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Callable

from src.flow.engines.content.generation.humanize_content import (
    repair_missing_brand_mention,
)
from src.flow.engines.content.generation.requirements_spec import (
    RequirementsSpec,
    build_requirements_spec,
)
from src.flow.engines.content.generation.word_count_utils import compute_word_target_band
from src.flow.model.structure.contents import get_generated_content_model
from src.flow.states.content import ContentValidation, ValidationCheckResult
from src.flow.states.rext import REXT

logger = logging.getLogger(__name__)

# Shared across both this module's gave_up computation and repair_content.py's
# loop bound. 2, not 1: brand-placement-policy is now a blocking check (moving
# an existing mention to the top of the article is a bigger structural edit
# than most other repairs), so a single attempt gives it too little room —
# revisit downward only if production repair-success-rate data supports it.
MAX_REPAIR_ATTEMPTS = 2

# ── text-matching helpers ────────────────────────────────────────────────────

_MD_LINK_RE = re.compile(r'\[([^\]]*)\]\((https?://[^)\s]+)\)')
_WORD_RE = re.compile(r"[a-zA-Z0-9']+")
_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "of", "to", "in", "on", "for", "with",
    "is", "are", "was", "were", "this", "that", "it", "as", "by", "at", "be",
    "from", "your", "you", "we", "our", "will", "can", "has", "have", "not",
}


def _combined_text(final_content: dict) -> str:
    return f"{final_content.get('introduction') or ''}\n\n{final_content.get('body_markdown') or ''}"


def _mention_present(text: str, name: str) -> bool:
    return bool(name) and name.strip().lower() in (text or "").lower()


def _find_markdown_links(text: str) -> list[tuple[str, str]]:
    return [(m.group(1), m.group(2)) for m in _MD_LINK_RE.finditer(text)]


def _tokenize(text: str) -> set[str]:
    return {w for w in _WORD_RE.findall((text or "").lower()) if len(w) > 2 and w not in _STOPWORDS}


def _word_overlap_ratio(a: str, b: str) -> float:
    """Cheap bag-of-words overlap, 0..1 — a proxy for topical relevance, not exact meaning."""
    ta, tb = _tokenize(a), _tokenize(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / min(len(ta), len(tb))


def _sentence_containing(text: str, needle: str) -> str:
    idx = text.find(needle)
    if idx == -1:
        return ""
    start_candidates = [p for p in (text.rfind('\n', 0, idx), text.rfind('. ', 0, idx)) if p != -1]
    start = max(start_candidates) + 1 if start_candidates else 0
    end_candidates = [p for p in (text.find('\n', idx), text.find('. ', idx)) if p != -1]
    end = min(end_candidates) if end_candidates else len(text)
    return text[start:end].strip()


def _is_bare_line(text: str, needle: str, max_words: int = 8) -> bool:
    """True if `needle`'s only appearance is an isolated, mostly-empty line.

    This is the exact shape produced by BaseGeneratedContent's
    enforce_internal_links_in_body auto-append fallback (a bare
    "[anchor](url)" line with nothing else) — and functionally identical to a
    writer dropping a raw mention/link at the end instead of weaving it in,
    whichever produced it.
    """
    for line in text.splitlines():
        stripped = line.strip()
        if needle in stripped:
            without_md = _MD_LINK_RE.sub(r'\1', stripped)
            if len(without_md.split()) <= max_words:
                return True
    return False


_REFERENCES_HEADING_RE = re.compile(
    r'^#{1,3}\s*(sources?|references?|further reading|citations?|works cited|resources)\b',
    re.IGNORECASE,
)


def _preceded_by_references_heading(text: str, needle: str) -> bool:
    """True if the line containing `needle` sits under a labeled Sources/
    References heading — the one case where a bare link line is an idiomatic
    bibliography entry rather than a lazy bolt-on dump (see
    evidence_placement_policy.py's "inline_or_references" content types).

    Walks back to the nearest heading of ANY level (not just the first
    non-blank line) — a multi-entry list under one heading has only its
    first line immediately below that heading; later entries sit below
    another list line, so the search must skip past those to find the
    section heading they're actually under.
    """
    lines = text.splitlines()
    idx = next((i for i, line in enumerate(lines) if needle in line), None)
    if idx is None:
        return False
    for j in range(idx - 1, -1, -1):
        stripped = lines[j].strip()
        if stripped.startswith('#'):
            return bool(_REFERENCES_HEADING_RE.match(stripped))
    return False


def _pass(name: str, detail: str) -> ValidationCheckResult:
    return {"name": name, "passed": True, "severity": "blocking", "detail": detail}


def _fail(name: str, severity: str, detail: str) -> ValidationCheckResult:
    return {"name": name, "passed": False, "severity": severity, "detail": detail}


# ── individual checks ────────────────────────────────────────────────────────

def check_word_count_band(final_content: dict, spec: RequirementsSpec) -> ValidationCheckResult:
    target = spec.get("target_word_count") or 0
    if not target:
        return _pass("word_count_band", "No target word count in outline; skipping.")
    total_words = len(_combined_text(final_content).split())
    min_words, max_words = compute_word_target_band(target)
    if min_words <= total_words <= max_words:
        return _pass("word_count_band", f"{total_words} words within target band {min_words}-{max_words}.")
    return _fail(
        "word_count_band", "blocking",
        f"{total_words} words outside target band {min_words}-{max_words}.",
    )


def check_keyword_presence(final_content: dict, spec: RequirementsSpec) -> ValidationCheckResult:
    keyword = (spec.get("target_keyword") or "").strip()
    if not keyword:
        return _pass("keyword_presence", "No target keyword in outline; skipping.")
    text = _combined_text(final_content)
    if keyword.lower() in text.lower():
        return _pass("keyword_presence", f"Target keyword '{keyword}' present.")
    return _fail("keyword_presence", "blocking", f"Target keyword '{keyword}' not found anywhere in the content.")


def check_required_sections(final_content: dict, spec: RequirementsSpec) -> ValidationCheckResult:
    expected = spec.get("expected_sections") or []
    if not expected:
        return _pass("required_sections", "No section requirements extracted from outline; skipping.")
    body = final_content.get("body_markdown") or ""
    headings = [h.strip().lower() for h in re.findall(r'^#{2,3}\s+(.+)$', body, flags=re.MULTILINE)]
    missing = []
    for label in expected:
        label_l = label.strip().lower()
        if any(label_l in h or h in label_l or _word_overlap_ratio(label_l, h) >= 0.4 for h in headings):
            continue
        missing.append(label)
    if not missing:
        return _pass("required_sections", f"All {len(expected)} expected section(s) found.")
    # Fuzzy label-to-heading matching means this is inherently approximate
    # (see requirements_spec._expected_sections) — a minority miss is treated
    # as a warning rather than blocking to avoid false-positive repair loops.
    coverage = 1 - (len(missing) / len(expected))
    severity = "blocking" if coverage < 0.7 else "warning"
    return _fail(
        "required_sections", severity,
        f"Missing {len(missing)}/{len(expected)} expected section(s): {', '.join(missing[:5])}",
    )


def check_brand_presence(final_content: dict, spec: RequirementsSpec) -> ValidationCheckResult:
    brand = spec.get("brand_context")
    if not brand:
        return _pass("brand_presence", "No approved brand promotion for this article; skipping.")
    text = _combined_text(final_content)
    if _mention_present(text, brand["brand_name"]):
        return _pass("brand_presence", f"Brand '{brand['brand_name']}' is mentioned.")
    return _fail("brand_presence", "blocking", f"Approved brand mention '{brand['brand_name']}' is missing entirely.")


def check_brand_url_accuracy(final_content: dict, spec: RequirementsSpec) -> ValidationCheckResult:
    brand = spec.get("brand_context")
    if not brand or not brand.get("brand_url"):
        return _pass("brand_url_accuracy", "No approved brand URL to verify; skipping.")
    text = _combined_text(final_content)
    brand_url = brand["brand_url"]
    brand_name = brand["brand_name"]
    idx = text.lower().find(brand_name.lower())
    if idx == -1:
        return _pass("brand_url_accuracy", "Brand not mentioned (caught by brand_presence); skipping.")
    # Sentence-scoped, not a fixed char window — a fixed window can grab a
    # link from an adjacent, unrelated sentence/line and misattribute it.
    sentence = _sentence_containing(text, text[idx: idx + len(brand_name)])
    links_in_sentence = _find_markdown_links(sentence) if sentence else []
    if any(url == brand_url for _, url in links_in_sentence):
        return _pass("brand_url_accuracy", "Brand mention is correctly hyperlinked to the approved URL.")
    if links_in_sentence:
        wrong = links_in_sentence[0][1]
        return _fail(
            "brand_url_accuracy", "blocking",
            f"Brand mention is hyperlinked to '{wrong}', not the approved '{brand_url}'.",
        )
    return _fail("brand_url_accuracy", "blocking", f"Brand mention has no hyperlink; expected '{brand_url}'.")


def check_brand_placement(final_content: dict, spec: RequirementsSpec) -> ValidationCheckResult:
    brand = spec.get("brand_context")
    if not brand:
        return _pass("brand_placement", "No approved brand promotion; skipping.")
    text = _combined_text(final_content)
    if not _mention_present(text, brand["brand_name"]):
        return _pass("brand_placement", "Brand not mentioned (caught by brand_presence); skipping.")
    if _is_bare_line(text, brand["brand_name"], max_words=6):
        return _fail(
            "brand_placement", "warning",
            "Brand mention appears bolted onto its own line, not woven into a sentence.",
        )
    return _pass("brand_placement", "Brand mention is embedded in prose.")


def check_brand_placement_policy(final_content: dict, spec: RequirementsSpec) -> ValidationCheckResult:
    """Content-type-aware positional check — see brand_placement_policy.py.

    Severity is asymmetric, not uniformly soft: for `prefers_top` content
    types (landing-page, sales-page, best-tools, comparison, ...) the user
    has explicitly and repeatedly confirmed top/early placement is a hard
    requirement, not a style preference — a promoted brand buried after the
    midpoint defeats the entire point of approving the promotion. That case
    is `blocking`, so it actually reaches repair_content's failed_checks (a
    `warning` here is invisible to the repair loop, which only acts on
    blocking failures — this was the exact bug that let it through silently).
    The reverse case (a `body_only` type where the mention leaked into the
    introduction) stays a softer `warning` — a blog opening with a product
    pitch is a stylistic misstep, not a broken promotion. Content types whose
    natural intensity is "none" (glossary, documentation, login-guide,
    help-center, faq) skip the positional check entirely — for those, mere
    presence (already covered by check_brand_presence, via forced_fallback in
    the prompt) is what matters, not whether it's early or late.
    """
    brand = spec.get("brand_context")
    if not brand:
        return _pass("brand_placement_policy", "No approved brand promotion; skipping.")
    full_policy = spec.get("brand_placement_policy") or {}
    if full_policy.get("intensity") == "none":
        return _pass(
            "brand_placement_policy",
            "This content type has no natural PLM placement — position isn't checked, only presence.",
        )
    policy = spec.get("brand_placement", "body_only")
    intro = final_content.get("introduction") or ""
    body = final_content.get("body_markdown") or ""
    combined = f"{intro}\n\n{body}"
    if not _mention_present(combined, brand["brand_name"]):
        return _pass("brand_placement_policy", "Brand not mentioned (caught by brand_presence); skipping.")

    if policy == "hero":
        # Graduated threshold, not one-size-fits-all: strict hero/above-the-fold
        # types (brand-page, sales-page, comparison, ...) need the mention very
        # early; a ranked-list format (best-tools, product-roundup) can
        # legitimately place its featured entry anywhere in the first half —
        # the actual complaint there was about being ranked LAST, not about a
        # literal above-the-fold requirement. See brand_placement_policy.py.
        max_fraction = full_policy.get("top_position_max_fraction", 0.2)
        cutoff_chars = max(200, int(len(body) * max_fraction))
        early_window = intro + body[:cutoff_chars]
        if _mention_present(early_window, brand["brand_name"]):
            return _pass("brand_placement_policy", "Brand mention appears near the top, as expected for this content type.")
        pct = int(max_fraction * 100)
        return _fail(
            "brand_placement_policy", "blocking",
            f"This content type requires '{brand['brand_name']}' within the first {pct}% of the article "
            f"(hero/intro/top-ranked position), but it only appears later — move the existing mention up, "
            f"don't just add a second one at the top.",
        )

    if _mention_present(intro, brand["brand_name"]):
        return _fail(
            "brand_placement_policy", "warning",
            f"Brand mention appears in the introduction; for this content type it should stay in a body "
            f"section — opening an otherwise-independent article with a product pitch reads as an ad.",
        )
    return _pass("brand_placement_policy", "Brand mention correctly kept out of the introduction for this content type.")


_SHALLOW_MENTION_MIN_WORDS = 12  # minimum words in the text surrounding the mention
_SHALLOW_MENTION_OVERLAP_THRESHOLD = 0.08


def check_brand_integration_depth(final_content: dict, spec: RequirementsSpec) -> ValidationCheckResult:
    """Naming the brand is not the same as promoting it — this catches a bare
    name-drop with no attached value/benefit, as distinct from correct
    placement (check_brand_placement_policy) or a wrong URL
    (check_brand_url_accuracy). Best-effort/heuristic (word-overlap against
    the approved About/selling-position text as a proxy for "specific claim
    attached"), so it can't verify true persuasive quality — but blocking for
    high/maximal-intensity types, since those formats exist specifically to
    carry real marketing copy, not just a namecheck; low/moderate types stay
    a warning, where a brief clause genuinely is sufficient.
    """
    brand = spec.get("brand_context")
    if not brand:
        return _pass("brand_integration_depth", "No approved brand promotion; skipping.")
    full_policy = spec.get("brand_placement_policy") or {}
    if full_policy.get("intensity") == "none":
        return _pass("brand_integration_depth", "This content type has no natural PLM depth requirement; skipping.")
    text = _combined_text(final_content)
    if not _mention_present(text, brand["brand_name"]):
        return _pass("brand_integration_depth", "Brand not mentioned (caught by brand_presence); skipping.")

    # The SENTENCE the mention lives in, not a fixed character radius — a
    # fixed window lets unrelated surrounding prose pad the word count
    # without the mention itself carrying any substance.
    sentence = _sentence_containing(text, brand["brand_name"])
    sentence_word_count = len(_MD_LINK_RE.sub(r'\1', sentence).split())

    about_and_selling = f"{brand.get('about', '')} {brand.get('selling_position', '')}".strip()
    overlap = _word_overlap_ratio(about_and_selling, sentence) if about_and_selling else 1.0  # nothing to compare against

    if sentence_word_count < _SHALLOW_MENTION_MIN_WORDS or overlap < _SHALLOW_MENTION_OVERLAP_THRESHOLD:
        severity = "blocking" if full_policy.get("intensity") in ("high", "maximal") else "warning"
        return _fail(
            "brand_integration_depth", severity,
            f"Brand mention reads like a bare name-drop with no specific benefit/value attached nearby — "
            f"attach a concrete claim from the approved About/selling-position text, not just the name.",
        )
    return _pass("brand_integration_depth", "Brand mention is backed by specific, substantive context.")


# Confusable technology-stack term pairs — swapping one for the other in a
# brand mention produces a concretely wrong factual claim (e.g. a brand built
# on Next.js gets described as "built on React.js"). Each element is the set
# of surface forms for one side of the pair.
_TECH_CONFUSION_PAIRS = (
    ({"next.js", "nextjs"}, {"react.js", "reactjs"}),
    ({"vue.js", "vuejs"}, {"react.js", "reactjs"}),
    ({"angular.js", "angularjs"}, {"react.js", "reactjs"}),
    ({"nuxt.js", "nuxtjs"}, {"next.js", "nextjs"}),
    ({"gatsby", "gatsbyjs"}, {"next.js", "nextjs"}),
    ({"remix", "remix.js"}, {"next.js", "nextjs"}),
    ({"wordpress"}, {"webflow"}),
    ({"shopify"}, {"woocommerce"}),
    ({"laravel"}, {"django"}),
    ({"ruby on rails", "rails"}, {"django"}),
)


def check_brand_factual_grounding(final_content: dict, spec: RequirementsSpec) -> ValidationCheckResult:
    """Catches a specific, concrete hallucination: the brand mention naming a
    technology that contradicts the approved about/selling_position text
    (e.g. "built on React.js" when the approved brand info says Next.js).

    Curated confusion-pair list, not a general fact-checker — deliberately
    conservative (skips if the brand's own text mentions both sides, treating
    that as a legitimate dual-stack claim rather than a contradiction) to
    avoid false-blocking a correct, more detailed brand description.
    """
    brand = spec.get("brand_context")
    if not brand:
        return _pass("brand_factual_grounding", "No approved brand promotion; skipping.")
    about_text = f"{brand.get('about', '')} {brand.get('selling_position', '')}".lower()
    text = _combined_text(final_content)
    idx = text.lower().find(brand["brand_name"].lower())
    if idx == -1:
        return _pass("brand_factual_grounding", "Brand not mentioned (caught by brand_presence); skipping.")
    sentence = (_sentence_containing(text, text[idx: idx + len(brand["brand_name"])]) or "").lower()
    if not sentence:
        return _pass("brand_factual_grounding", "Could not isolate the brand-mention sentence; skipping.")

    for group_a, group_b in _TECH_CONFUSION_PAIRS:
        a_in_about = any(t in about_text for t in group_a)
        b_in_about = any(t in about_text for t in group_b)
        if a_in_about == b_in_about:
            continue  # neither present, or both present (legitimate dual-stack) — not a contradiction
        approved, conflicting = (group_a, group_b) if a_in_about else (group_b, group_a)
        hit = next((t for t in conflicting if t in sentence), None)
        if hit:
            return _fail(
                "brand_factual_grounding", "blocking",
                f"Brand mention says '{hit}', but the approved brand info specifies "
                f"'{next(t for t in approved if t in about_text)}' — this contradicts the approved facts.",
            )
    return _pass("brand_factual_grounding", "No contradicting technology term found near the brand mention.")


_NEGATIVE_CONTEXT_WORDS = (
    "avoid", "worse", "worst", "bad", "don't use", "never use", "poor",
    "fails", "broken", "scam", "overpriced", "disappointing", "instead of",
)


def check_brand_context_heuristic(final_content: dict, spec: RequirementsSpec) -> ValidationCheckResult:
    """Best-effort only — a deterministic check cannot reliably judge tone.

    See the plan's "Guarantees and limits": this reduces risk, it does not
    eliminate it, and is always a warning, never blocking.
    """
    brand = spec.get("brand_context")
    if not brand:
        return _pass("brand_context_heuristic", "No approved brand promotion; skipping.")
    text = _combined_text(final_content)
    idx = text.lower().find(brand["brand_name"].lower())
    if idx == -1:
        return _pass("brand_context_heuristic", "Brand not mentioned; skipping.")
    window = text[max(0, idx - 120): idx + 120].lower()
    hits = [w for w in _NEGATIVE_CONTEXT_WORDS if w in window]
    if hits:
        return _fail(
            "brand_context_heuristic", "warning",
            f"Negative-sounding word(s) near brand mention: {', '.join(hits)} — verify tone manually.",
        )
    return _pass("brand_context_heuristic", "No negative-tone signal near brand mention.")


# Below this relevance threshold, skipping an approved link is treated as
# acceptable (the writer had good reason not to force it in) rather than a
# failure — matches "an irrelevant link might be skipped in rare cases."
_LINK_RELEVANCE_THRESHOLD = 0.15
_LINK_PLACEMENT_THRESHOLD = 0.10


def check_internal_links_integration(final_content: dict, spec: RequirementsSpec) -> ValidationCheckResult:
    approved = spec.get("approved_internal_links") or []
    if not approved:
        return _pass("internal_links_integration", "No approved internal links; skipping.")

    combined = _combined_text(final_content)
    url_set = {u for _, u in _find_markdown_links(combined)}

    missing_relevant: list[str] = []
    missing_irrelevant: list[str] = []
    bolted_on: list[str] = []
    misplaced: list[str] = []

    for lnk in approved:
        if not isinstance(lnk, dict):
            continue
        url = (lnk.get("url") or "").strip()
        if not url:
            continue
        anchor_context = f"{lnk.get('title', '')} {lnk.get('anchor_text', '')} {lnk.get('context', '')}".strip()
        relevance = _word_overlap_ratio(anchor_context, combined) if anchor_context else 0.0

        if url not in url_set:
            (missing_relevant if relevance >= _LINK_RELEVANCE_THRESHOLD else missing_irrelevant).append(url)
            continue

        # Present — but is it woven in, or just an isolated line? Wrong-URL
        # substitution is already caught above (exact match against url_set),
        # so from here on we're only distinguishing HOW a present link landed.
        if _is_bare_line(combined, url):
            if relevance >= _LINK_RELEVANCE_THRESHOLD:
                bolted_on.append(url)
            continue

        sentence = _sentence_containing(combined, url)
        if anchor_context and sentence and _word_overlap_ratio(anchor_context, sentence) < _LINK_PLACEMENT_THRESHOLD:
            misplaced.append(url)

    if missing_relevant or bolted_on:
        parts = []
        if missing_relevant:
            parts.append(f"{len(missing_relevant)} relevant approved link(s) never embedded: {', '.join(missing_relevant[:3])}")
        if bolted_on:
            parts.append(f"{len(bolted_on)} link(s) only present as a bolted-on line, not woven in: {', '.join(bolted_on[:3])}")
        return _fail("internal_links_integration", "blocking", "; ".join(parts))

    if missing_irrelevant or misplaced:
        parts = []
        if missing_irrelevant:
            parts.append(f"{len(missing_irrelevant)} approved link(s) skipped, low topical overlap (acceptable): {', '.join(missing_irrelevant[:3])}")
        if misplaced:
            parts.append(f"{len(misplaced)} link(s) present but possibly misplaced (low overlap with surrounding sentence): {', '.join(misplaced[:3])}")
        return _fail("internal_links_integration", "warning", "; ".join(parts))

    return _pass("internal_links_integration", f"All {len(approved)} approved internal link(s) naturally integrated.")


_FACT_FIDELITY_THRESHOLD = 0.15


def check_facts_and_external_links_integration(
    final_content: dict, spec: RequirementsSpec, searched_results: list[dict],
) -> ValidationCheckResult:
    facts = [f for f in (final_content.get("facts") or []) if isinstance(f, dict)]
    outbound_links = [l for l in (final_content.get("outbound_links") or []) if isinstance(l, dict)]
    sourced_facts = [f for f in facts if (f.get("source_url") or "").strip()]

    if not sourced_facts and not outbound_links:
        return _pass("facts_and_external_links", "No sourced facts or outbound links to verify; skipping.")

    if not searched_results:
        # No search-tool ground truth captured this run — degrade to a
        # warning rather than blocking every article with citations, since a
        # plumbing gap here (not a real hallucination) shouldn't hard-fail
        # generation. Still surfaced for visibility.
        return _fail(
            "facts_and_external_links", "warning",
            "Article cites source(s) but no search_tool results were captured this run — provenance unverifiable.",
        )

    searched_urls = {r.get("url") for r in searched_results if r.get("url")}
    snippet_by_url = {r.get("url"): r.get("snippet", "") for r in searched_results if r.get("url")}
    combined = _combined_text(final_content)

    evidence_policy = spec.get("evidence_placement") or {}
    citation_style = evidence_policy.get("citation_style", "inline_only")
    max_recommended = evidence_policy.get("max_recommended_citations", 6)

    fabricated: list[str] = []
    # "not_integrated" covers TWO distinct-but-equally-bad failure modes:
    # the citation never appears at all, OR it only appears as an isolated
    # markdown-link line (a bolted-on dump, typically 2-3 links tacked onto
    # the end) rather than woven into the sentence that makes its claim —
    # the exact reported bug. Both mean "not naturally integrated."
    not_integrated: list[str] = []
    low_fidelity: list[str] = []
    real_urls: list[str] = []

    def _is_bolted_on(url: str) -> bool:
        """Present as an inline hyperlink, but only as an isolated dump line —
        not woven into a sentence. A labeled references section is the one
        idiomatic exception, for content types whose style allows it."""
        if not _is_bare_line(combined, url):
            return False
        is_labeled_reference = (
            citation_style == "inline_or_references"
            and _preceded_by_references_heading(combined, url)
        )
        return not is_labeled_reference

    def _check_fact(source_url: str, fact_text: str) -> None:
        if source_url not in searched_urls:
            fabricated.append(source_url)
            return
        real_urls.append(source_url)
        # A fact's own TEXT is what must appear — facts are cited stats, not
        # every one needs to become a clickable link (that's outbound_links'
        # job). Word-overlap covers a close paraphrase, not just an exact quote.
        text_present = bool(fact_text) and (
            fact_text in combined or _word_overlap_ratio(fact_text, combined) >= 0.2
        )
        if fact_text and not text_present:
            not_integrated.append(source_url)
            return
        # If the source is ALSO hyperlinked somewhere, that hyperlink must not
        # itself be a bolted-on dump line (a fact can carry both a stated
        # stat AND a citation link).
        if source_url in combined and _is_bolted_on(source_url):
            not_integrated.append(source_url)
            return
        if fact_text:
            snippet = snippet_by_url.get(source_url, "")
            if snippet and _word_overlap_ratio(fact_text, snippet) < _FACT_FIDELITY_THRESHOLD:
                low_fidelity.append(source_url)

    def _check_outbound_link(url: str) -> None:
        """Outbound links ARE meant to be actual inline hyperlinks (see Link's
        docstring) — this is where the reported bug lives: 2-3 links dumped
        as a bare trailing list instead of woven into a sentence."""
        if url not in searched_urls:
            fabricated.append(url)
            return
        real_urls.append(url)
        if url not in combined:
            not_integrated.append(url)
            return
        if _is_bolted_on(url):
            not_integrated.append(url)

    for fact in sourced_facts:
        _check_fact(fact["source_url"].strip(), (fact.get("text") or "").strip())

    for lnk in outbound_links:
        url = (lnk.get("url") or "").strip()
        if url:
            _check_outbound_link(url)

    fabricated = list(dict.fromkeys(fabricated))
    not_integrated = list(dict.fromkeys(not_integrated))
    low_fidelity = list(dict.fromkeys(low_fidelity))
    real_urls = list(dict.fromkeys(real_urls))

    if fabricated:
        return _fail(
            "facts_and_external_links", "blocking",
            f"{len(fabricated)} citation(s) not traceable to any search_tool result — likely fabricated: {', '.join(fabricated[:3])}",
        )
    if not_integrated:
        return _fail(
            "facts_and_external_links", "blocking",
            f"{len(not_integrated)} sourced fact(s)/link(s) never woven into the prose "
            f"(missing entirely, or only present as a bolted-on trailing link): {', '.join(not_integrated[:3])}",
        )
    if len(real_urls) > max_recommended:
        return _fail(
            "facts_and_external_links", "warning",
            f"{len(real_urls)} external citations is more than recommended ({max_recommended}) for this "
            f"content type — consider trimming to the strongest few.",
        )
    if low_fidelity:
        return _fail(
            "facts_and_external_links", "warning",
            f"{len(low_fidelity)} fact(s) wording doesn't clearly match its cited source: {', '.join(low_fidelity[:3])}",
        )
    return _pass("facts_and_external_links", "All sourced facts/links trace to real search results and appear naturally in the article.")


def check_cta_presence(final_content: dict, spec: RequirementsSpec) -> ValidationCheckResult:
    if not spec.get("cta_required"):
        return _pass("cta_presence", "This content type/outline has no declared CTA requirement; skipping.")
    cta = final_content.get("cta")
    cta_text = (cta.get("text") or "").strip() if isinstance(cta, dict) else ""
    if not cta_text:
        expected = (spec.get("outline_cta") or {}).get("text", "")
        return _fail(
            "cta_presence", "blocking",
            f"Outline declares a CTA ('{expected}') but the generated content has no cta field populated.",
        )
    if cta_text.lower() in _combined_text(final_content).lower():
        return _pass("cta_presence", f"CTA '{cta_text}' is populated and integrated into the content.")
    return _fail(
        "cta_presence", "blocking",
        f"cta.text ('{cta_text}') was populated but never appears in body_markdown/introduction.",
    )


# ── check registry + orchestration ──────────────────────────────────────────

CheckFn = Callable[[dict, RequirementsSpec], ValidationCheckResult]

CHECK_REGISTRY: list[CheckFn] = [
    check_word_count_band,
    check_keyword_presence,
    check_required_sections,
    check_brand_presence,
    check_brand_url_accuracy,
    check_brand_placement,
    check_brand_placement_policy,
    check_brand_integration_depth,
    check_brand_factual_grounding,
    check_brand_context_heuristic,
    check_internal_links_integration,
    check_cta_presence,
]

# Lightweight subset re-checked after humanization — only what humanization's
# free-form rewrite could plausibly damage. No LLM, no full suite, no EEAT.
FINAL_VALIDATE_CHECKS: list[CheckFn] = [
    check_word_count_band,
    check_keyword_presence,
    check_brand_presence,
    check_brand_url_accuracy,
    check_brand_placement,
    check_brand_factual_grounding,
]


def run_checks(
    final_content: dict, spec: RequirementsSpec, searched_results: list[dict],
) -> tuple[list[ValidationCheckResult], list[ValidationCheckResult]]:
    """Returns (failed_blocking, warnings)."""
    results = [fn(final_content, spec) for fn in CHECK_REGISTRY]
    results.append(check_facts_and_external_links_integration(final_content, spec, searched_results))
    failed_blocking = [r for r in results if not r["passed"] and r["severity"] == "blocking"]
    warnings = [r for r in results if not r["passed"] and r["severity"] == "warning"]
    return failed_blocking, warnings


async def validate_content(state: REXT) -> dict:
    """Deterministic pre-humanize gate. Runs before humanize_content ever fires."""
    content_state = state.get("content") or {}
    final_content = content_state.get("final_content") or {}
    outline = content_state.get("outline") or {}
    content_type = content_state.get("content_type", "")
    searched_results = (content_state.get("generation_meta") or {}).get("searched_results") or []
    review = content_state.get("review") or {}

    spec = build_requirements_spec(outline, content_type)
    failed_blocking, warnings = run_checks(final_content, spec, searched_results)
    passed = not failed_blocking

    repair_attempts = review.get("repair_attempts", 0)
    gave_up = (not passed) and repair_attempts >= MAX_REPAIR_ATTEMPTS
    run_id = (review.get("validation") or {}).get("validation_run_id") or str(uuid.uuid4())

    validation_result: ContentValidation = {
        "passed": passed,
        "gave_up": gave_up,
        "failed_checks": failed_blocking,
        "warnings": warnings,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "stage": "pre_repair",
        "validation_run_id": run_id,
    }

    logger.info(
        "validate_content: content_type=%s passed=%s gave_up=%s failed=%s repair_attempts=%s run_id=%s",
        content_type, passed, gave_up, [c["name"] for c in failed_blocking], repair_attempts, run_id,
    )

    return {
        "content": {
            **content_state,
            "review": {**review, "validation": validation_result},
        }
    }


async def final_validate_content(state: REXT) -> dict:
    """Lightweight post-humanize re-check — no LLM, no full suite, no EEAT.

    Only exists to catch humanization's free-form rewrite damaging a check
    that already passed. Auto-fixes a broken brand mention using the same
    narrow, tone-preserving repair humanize_content already relies on;
    anything else caught here is logged, not silently patched.
    """
    content_state = state.get("content") or {}
    final_content = content_state.get("final_content") or {}
    outline = content_state.get("outline") or {}
    content_type = content_state.get("content_type", "")
    review = content_state.get("review") or {}

    spec = build_requirements_spec(outline, content_type)
    checks = [fn(final_content, spec) for fn in FINAL_VALIDATE_CHECKS]

    brand_failed = any(
        c["name"] in ("brand_presence", "brand_url_accuracy") and not c["passed"] for c in checks
    )
    if brand_failed and spec.get("brand_context"):
        schema = get_generated_content_model(content_type)
        if schema is not None:
            repaired = await repair_missing_brand_mention(
                payload=dict(final_content), brand_context=spec["brand_context"], schema=schema,
            )
            if repaired:
                final_content = repaired
                checks = [
                    fn(final_content, spec) for fn in FINAL_VALIDATE_CHECKS
                ]
                logger.info("final_validate_content: brand mention auto-repaired.")

    failed_blocking = [c for c in checks if not c["passed"] and c["severity"] == "blocking"]
    warnings = [c for c in checks if not c["passed"] and c["severity"] == "warning"]
    passed = not failed_blocking

    result: ContentValidation = {
        "passed": passed,
        "gave_up": not passed,  # no further repair loop exists after humanization
        "failed_checks": failed_blocking,
        "warnings": warnings,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "stage": "post_humanize",
        "validation_run_id": (review.get("validation") or {}).get("validation_run_id") or str(uuid.uuid4()),
    }

    logger.info(
        "final_validate_content: content_type=%s passed=%s failed=%s",
        content_type, passed, [c["name"] for c in failed_blocking],
    )

    return {
        "content": {
            **content_state,
            "final_content": final_content,
            "review": {**review, "final_validation": result},
        }
    }

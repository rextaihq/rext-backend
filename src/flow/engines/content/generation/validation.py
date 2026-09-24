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
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Optional

from src.flow.engines.content.generation.brand_placement_policy import (
    DEFAULT_BODY_ATTENTION_MAX_FRACTION,
    DEFAULT_TOP_POSITION_MAX_FRACTION,
)
from src.flow.engines.content.generation.claim_integrity import (
    describe_unsupported_claims,
    find_unsupported_claims,
)
from src.flow.engines.content.generation.focus_keyword import resolve_focus_keyword
from src.flow.engines.content.generation.keyword_density import (
    analyze_keyword_density,
    count_keyphrase_occurrences,
)
from src.flow.engines.content.generation.link_integrity import (
    LinkRecord,
    dedupe_records,
    describe_link,
    extract_content_links,
    normalize_url,
    present_urls,
    restore_lost_links,
)
from src.flow.engines.content.generation.onpage_seo import (
    META_DESCRIPTION_MAX_CHARS,
    META_DESCRIPTION_MIN_CHARS,
    enforce_onpage_seo,
)
from src.flow.engines.content.generation.repair_content import (
    HUMANIZATION_OWNED_CHECKS,
    enforce_subheadings_for_spec,
    run_targeted_repair,
)
from src.flow.engines.content.generation.requirements_spec import (
    RequirementsSpec,
    build_requirements_spec,
)
from src.flow.engines.content.generation.seo_title_rules import contains_keyphrase
from src.flow.engines.content.generation.structured_body import STRUCTURED_BLOCKS_KEY
from src.flow.engines.content.generation.subheading_seo import (
    describe_keyphrase_issue,
    describe_length_issue,
    subheading_report,
)
from src.flow.engines.content.generation.title_subject import find_subject_mismatch
from src.flow.engines.content.generation.word_count_utils import compute_word_target_band
from src.flow.model.structure.outlines.product_names import find_placeholder_names_in_text
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

_MD_LINK_RE = re.compile(r"\[([^\]]*)\]\((https?://[^)\s]+)\)")
_WORD_RE = re.compile(r"[a-zA-Z0-9']+")
_STOPWORDS = {
    "the",
    "a",
    "an",
    "and",
    "or",
    "but",
    "of",
    "to",
    "in",
    "on",
    "for",
    "with",
    "is",
    "are",
    "was",
    "were",
    "this",
    "that",
    "it",
    "as",
    "by",
    "at",
    "be",
    "from",
    "your",
    "you",
    "we",
    "our",
    "will",
    "can",
    "has",
    "have",
    "not",
}


def _combined_text(final_content: dict) -> str:
    return (
        f"{final_content.get('introduction') or ''}\n\n{final_content.get('body_markdown') or ''}"
    )


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


def _coverage_ratio(needle: str, haystack: str) -> float:
    """Fraction of `needle`'s distinctive words that appear in `haystack`.

    Directional, unlike _word_overlap_ratio, which divides by min(len(a),
    len(b)) — that normalization compares a short string against a long one and
    reports the SHORT one's saturation, so a hero sharing only generic topic
    words ("saas", "solutions", "2026") with a whole article scored the same as
    a hero that was genuinely reproduced. Asking "how much of the hero is
    actually here" is the question that distinguishes them.
    """
    nt = _tokenize(needle)
    if not nt:
        return 0.0
    return len(nt & _tokenize(haystack)) / len(nt)


# Fraction of an expected section label's words that must appear in a heading.
_HEADING_MATCH_MIN_COVERAGE = 0.6

# How much of the body counts as "the opening" for hero verification, with a
# 400-char floor so short articles are not graded on a sliver.
_HERO_WINDOW_FRACTION = 0.2
# Fraction of the approved hero's wording that must survive into that opening.
# Forgiving enough for a rewrite — the writer is expected to rework hero copy
# into prose, not paste it — but above the level generic topic-word overlap
# reaches on its own (measured at ~0.27 on an article with no hero at all).
_HERO_MIN_COVERAGE = 0.5


def _heading_matches(label_l: str, heading_l: str) -> bool:
    """Whether an article heading satisfies an expected outline label.

    Token-based, not substring. `"solution" in "buy saas solutions online"` is
    True as raw text, which let one unrelated keyword heading satisfy a required
    "Solution" section and mask its absence entirely.
    """
    label_tokens, heading_tokens = _tokenize(label_l), _tokenize(heading_l)
    if not label_tokens or not heading_tokens:
        return False
    if label_tokens <= heading_tokens:
        return True
    return len(label_tokens & heading_tokens) / len(label_tokens) >= _HEADING_MATCH_MIN_COVERAGE


def _sentence_at(text: str, idx: int) -> str:
    """The sentence/line surrounding character offset `idx`."""
    start_candidates = [p for p in (text.rfind("\n", 0, idx), text.rfind(". ", 0, idx)) if p != -1]
    start = max(start_candidates) + 1 if start_candidates else 0
    end_candidates = [p for p in (text.find("\n", idx), text.find(". ", idx)) if p != -1]
    end = min(end_candidates) if end_candidates else len(text)
    return text[start:end].strip()


def _sentence_containing(text: str, needle: str) -> str:
    idx = text.find(needle)
    if idx == -1:
        return ""
    return _sentence_at(text, idx)


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
            without_md = _MD_LINK_RE.sub(r"\1", stripped)
            if len(without_md.split()) <= max_words:
                return True
    return False


# Last 10% of body_markdown counts as "the closing section". A mention whose
# FIRST occurrence falls in here is bolted onto the closing paragraph/CTA rather
# than woven into the body proper — a repeat that also appears earlier is a
# different, higher-intensity pattern, not this "buried in the last scrap"
# failure, which is why the test reads the first occurrence rather than any.
_CLOSING_TAIL_FRACTION = 0.1


_REFERENCES_HEADING_RE = re.compile(
    r"^#{1,3}\s*(sources?|references?|further reading|citations?|works cited|resources)\b",
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
        if stripped.startswith("#"):
            return bool(_REFERENCES_HEADING_RE.match(stripped))
    return False


# An H2 that opens a body section. Exactly level two: `blocks_to_body_markdown`
# emits one "## <heading>" per structured block, and an H3 is a subsection
# INSIDE a block, not a new one.
_BODY_SECTION_HEADING_RE = re.compile(r"^##(?!#)\s*\S", re.MULTILINE)


def _opening_section_end(body: str) -> int:
    """Char offset at which the body's opening (hero) section ends.

    For a hero-led page this is the hero block. `ContentBlock.heading` is
    deliberately null for a hero — emitting "## Hero" as a visible heading is a
    defect the schema explicitly warns against — so the hero normally renders as
    unheaded copy before the first "## ...", and the opening section is simply
    everything up to that heading.

    The model does sometimes give the hero a heading anyway. When the body opens
    with a heading, that heading belongs to the opening section itself, so the
    section runs to the NEXT one — otherwise a hero that merely carried a title
    would collapse to a zero-length region and fail every article that has one.

    Offsets are in the same space as `BrandOccurrence.offset`, so callers must
    pass the text they measured occurrences in (see `_normalize_for_mentions`).
    """
    starts = [m.start() for m in _BODY_SECTION_HEADING_RE.finditer(body or "")]
    if not starts:
        return len(body or "")
    if not (body or "")[: starts[0]].strip():
        return starts[1] if len(starts) > 1 else len(body or "")
    return starts[0]


# ── brand occurrence model ───────────────────────────────────────────────────
# Position and depth must be judged about the SAME, well-defined, reader-visible
# mention. Before this existed the three brand checks each answered "where is the
# brand" differently — the hero branch took ANY occurrence in the early window,
# _is_closing_mention took the FIRST, and integration-depth graded the FIRST
# occurrence's sentence. Nothing tied them together, so a filler name-drop at 15%
# plus the real value-prop at 80% satisfied the position check AND got graded for
# depth on the filler. "Present but weak" was unreachable by any check.

_BARE_URL_RE = re.compile(r"https?://\S+")


@dataclass(frozen=True)
class BrandOccurrence:
    offset: int  # char offset within the normalized text
    position_fraction: float  # offset / len(normalized text), 0..1
    text_length: int  # len(normalized text), for absolute-char thresholds
    sentence: str  # the sentence the mention sits in
    substance_score: float  # overlap RATIO, for the depth threshold
    # Absolute count of shared tokens, used to RANK occurrences against each
    # other. The ratio can't do that job: _word_overlap_ratio normalizes by
    # min(len(a), len(b)), so a bare "Acme." scores a perfect 1.0 — its single
    # token is fully contained in the about text — and would outrank the real
    # value-prop sentence it's supposed to lose to.
    overlap_tokens: int


def _strip_references_section(text: str) -> str:
    """Drop everything under a Sources/References heading.

    A brand name sitting in a bibliography entry is not a promotional mention —
    counting it lets an article "mention" the brand somewhere no reader reads it.
    Resets at the next heading of any level, since that ends the section.
    """
    out: list[str] = []
    in_refs = False
    for line in (text or "").splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            in_refs = bool(_REFERENCES_HEADING_RE.match(stripped))
        if not in_refs:
            out.append(line)
    return "\n".join(out)


def _normalize_for_mentions(text: str) -> str:
    """Reader-visible prose only.

    Link URLs are stripped but their anchor text kept, so `[Acme](https://acme.com)`
    is ONE mention rather than two, and a bare reference URL that merely contains
    the brand's domain is none at all. Without this a brand present only in a URL
    slug passes the positional window while being invisible on the page.
    """
    without_refs = _strip_references_section(text)
    anchors_only = _MD_LINK_RE.sub(r"\1", without_refs)
    return _BARE_URL_RE.sub("", anchors_only)


def _brand_mention_re(brand_name: str) -> Optional[re.Pattern]:
    """Case-insensitive, boundary-anchored matcher for one brand name.

    Lookarounds rather than `\\b` because brand names legitimately end in
    non-word characters ("Next.js"), where `\\b` asserts the wrong thing.
    """
    name = (brand_name or "").strip()
    if not name:
        return None
    return re.compile(
        r"(?<![0-9A-Za-z])" + re.escape(name) + r"(?![0-9A-Za-z])",
        re.IGNORECASE,
    )


def _brand_occurrences(
    text: str,
    brand_name: str,
    about_and_selling: str = "",
) -> list[BrandOccurrence]:
    """Every reader-visible mention of `brand_name`, in document order.

    Fractions are relative to the NORMALIZED text, so callers must compare them
    against each other rather than against raw-markdown offsets.
    """
    pattern = _brand_mention_re(brand_name)
    if pattern is None:
        return []
    normalized = _normalize_for_mentions(text)
    if not normalized:
        return []
    length = len(normalized)
    target_tokens = _tokenize(about_and_selling) if about_and_selling else set()
    occurrences = []
    for match in pattern.finditer(normalized):
        sentence = _sentence_at(normalized, match.start())
        occurrences.append(
            BrandOccurrence(
                offset=match.start(),
                position_fraction=match.start() / length if length else 0.0,
                text_length=length,
                sentence=sentence,
                substance_score=(
                    _word_overlap_ratio(about_and_selling, sentence)
                    if about_and_selling
                    else 1.0  # nothing to compare against
                ),
                overlap_tokens=len(target_tokens & _tokenize(sentence)),
            )
        )
    return occurrences


def _primary_occurrence(occurrences: list[BrandOccurrence]) -> Optional[BrandOccurrence]:
    """The mention that actually carries the promotion.

    Ranked by absolute shared-token count, so the sentence saying the most about
    the brand wins over a bare name-drop. Ties resolve to the earliest, which
    `max` gives for free since `occurrences` is already in document order. Both
    the positional check and the depth check grade THIS occurrence, so they can
    never disagree about which mention they mean.
    """
    if not occurrences:
        return None
    return max(occurrences, key=lambda o: o.overlap_tokens)


def _about_and_selling(brand: dict) -> str:
    return f"{brand.get('about', '')} {brand.get('selling_position', '')}".strip()


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
        return _pass(
            "word_count_band", f"{total_words} words within target band {min_words}-{max_words}."
        )
    return _fail(
        "word_count_band",
        "blocking",
        f"{total_words} words outside target band {min_words}-{max_words}.",
    )


def check_keyword_presence(final_content: dict, spec: RequirementsSpec) -> ValidationCheckResult:
    """The focus keyphrase appears at least once, as an exact word sequence.

    Word-sequence matching rather than the previous `keyword.lower() in
    text.lower()` substring test: a substring test passes on "crm" buried
    inside "crms" or inside a URL slug, which meant an article could satisfy
    this check without the phrase ever being readable in the copy.
    """
    keyword = (spec.get("target_keyword") or "").strip()
    if not keyword:
        return _pass("keyword_presence", "No target keyword in outline; skipping.")
    occurrences = count_keyphrase_occurrences(_combined_text(final_content), keyword)
    if occurrences:
        return _pass("keyword_presence", f"Focus keyphrase '{keyword}' present ({occurrences}x).")
    return _fail(
        "keyword_presence",
        "blocking",
        f"Focus keyphrase '{keyword}' not found anywhere in the content.",
    )


def check_keyword_density(final_content: dict, spec: RequirementsSpec) -> ValidationCheckResult:
    """Focus-keyphrase density sits inside a band derived from the FINAL length.

    Separate from keyword_presence on purpose: presence answers "is the article
    about this phrase at all", density answers "is it weighted like it is".
    A 3,000-word article that names its focus keyphrase once passes presence
    and is still, to a search engine, not about that phrase.

    Blocking in both directions. Too low is the reported bug; too high is the
    failure mode a naive "add more occurrences" fix produces, and shipping
    keyword-stuffed copy is worse than shipping thin copy. Both route into the
    existing bounded repair loop rather than hard-stopping the run.

    Title and meta description contribute occurrences but not word count -- see
    analyze_keyword_density -- because they are keyphrase-bearing SEO surfaces
    rather than body prose the reader has to get through.
    """
    keyword = (spec.get("target_keyword") or "").strip()
    if not keyword:
        return _pass("keyword_density", "No target keyword in outline; skipping.")

    report = analyze_keyword_density(
        text=_combined_text(final_content),
        keyphrase=keyword,
        content_type=spec.get("content_type") or "",
        extra_text="\n".join(
            str(final_content.get(field) or "")
            for field in ("title", "meta_title", "meta_description")
        ),
    )

    if report["status"] in ("ok", "not_applicable"):
        return _pass("keyword_density", report["detail"])
    return _fail("keyword_density", "blocking", report["detail"])


def check_selected_title_preserved(
    final_content: dict, spec: RequirementsSpec
) -> ValidationCheckResult:
    """The article's title is EXACTLY the title the user selected.

    topic_generation is the only stage permitted to author or repair a title;
    from the moment the user picks one it is read-only. Generation, repair and
    humanization all return the full schema and can therefore quietly reword it,
    which is how a user-selected title used to end up replaced by a model's
    "improved" variant in the finished article.

    Blocking, but in practice never reaches the repair loop: enforce_onpage_seo
    reverts the title deterministically in the same node that changed it. This
    check exists so a revert that somehow did not happen is visible instead of
    silent.
    """
    selected = spec.get("selected_title") or ""
    if not selected:
        return _pass("selected_title_preserved", "No user-selected title in spec; skipping.")

    # Exact comparison on BOTH title fields: the editor saves `meta_title`
    # alongside `title`, so either one drifting is a changed title.
    for field in ("title", "meta_title"):
        actual = final_content.get(field)
        if actual != selected:
            return _fail(
                "selected_title_preserved",
                "blocking",
                f"`{field}` was changed after selection. Expected the user-selected title "
                f"{selected!r} but found {actual!r}. Restore the user-selected title verbatim.",
            )

    return _pass("selected_title_preserved", "Title matches the user-selected title exactly.")


def check_focus_keyphrase_in_title(
    final_content: dict, spec: RequirementsSpec
) -> ValidationCheckResult:
    """The exact focus keyphrase appears in the final title."""
    keyword = (spec.get("target_keyword") or "").strip()
    if not keyword:
        return _pass("focus_keyphrase_in_title", "No target keyword in outline; skipping.")

    title = final_content.get("title") or ""
    if contains_keyphrase(title, keyword):
        return _pass("focus_keyphrase_in_title", f"Focus keyphrase {keyword!r} present in title.")

    return _fail(
        "focus_keyphrase_in_title",
        "blocking",
        f"Focus keyphrase {keyword!r} is missing from the title {title!r}.",
    )


def check_meta_description_present(
    final_content: dict, spec: RequirementsSpec
) -> ValidationCheckResult:
    """A meta description exists at all.

    It was ``Optional[str] = None`` on the generated-content schema with no
    check anywhere, so an article could -- and did -- ship with none, and
    persistence silently stored an empty string for it.
    """
    meta_description = (final_content.get("meta_description") or "").strip()
    if meta_description:
        return _pass(
            "meta_description_present",
            f"Meta description present ({len(meta_description)} characters).",
        )

    return _fail(
        "meta_description_present",
        "blocking",
        f"Meta description is missing. Write a {META_DESCRIPTION_MIN_CHARS}-"
        f"{META_DESCRIPTION_MAX_CHARS} character meta description containing the exact focus "
        "keyphrase and ending with a call to action.",
    )


def check_meta_description_length(
    final_content: dict, spec: RequirementsSpec
) -> ValidationCheckResult:
    """The meta description never exceeds Yoast's 156-character limit.

    Blocking above the ceiling. In practice enforce_onpage_seo shortens an
    over-long description in the same node that produced it, so this documents
    what ships. Below the 120-character floor is only a warning: a short but
    accurate description is not worth a full repair loop.
    """
    meta_description = (final_content.get("meta_description") or "").strip()
    if not meta_description:
        return _pass(
            "meta_description_length", "No meta description to check (reported separately)."
        )

    length = len(meta_description)
    if length > META_DESCRIPTION_MAX_CHARS:
        return _fail(
            "meta_description_length",
            "blocking",
            f"Meta description is {length} characters; the maximum is {META_DESCRIPTION_MAX_CHARS}. "
            "Rewrite it as a complete, shorter description that keeps the exact focus keyphrase.",
        )
    if length < META_DESCRIPTION_MIN_CHARS:
        return _fail(
            "meta_description_length",
            "warning",
            f"Meta description is {length} characters; aim for {META_DESCRIPTION_MIN_CHARS}-"
            f"{META_DESCRIPTION_MAX_CHARS}.",
        )
    return _pass("meta_description_length", f"Meta description length {length} is within range.")


def check_subheading_keyphrase(
    final_content: dict, spec: RequirementsSpec
) -> ValidationCheckResult:
    """30%-75% of H2/H3 subheadings reflect the focus keyphrase (Yoast semantics).

    See subheading_seo for the matching rule. Blocking in both directions: too
    few is the reported Yoast failure, too many is keyword stuffing.
    """
    keyword = (spec.get("target_keyword") or "").strip()
    if not keyword:
        return _pass("subheading_keyphrase", "No target keyword in outline; skipping.")

    report = subheading_report(
        final_content.get("body_markdown") or "",
        keyword,
        spec.get("content_type") or "",
        spec.get("keyphrase_synonyms") or [],
    )
    analysis = report["keyphrase"]
    if analysis["status"] == "not_applicable":
        return _pass(
            "subheading_keyphrase",
            f"Keyphrase-in-subheadings not applicable ({analysis['reason']}).",
        )
    if analysis["status"] == "ok":
        return _pass(
            "subheading_keyphrase",
            f"{analysis['matching']}/{analysis['total']} H2/H3 subheadings reflect the focus keyphrase.",
        )
    return _fail("subheading_keyphrase", "blocking", describe_keyphrase_issue(analysis, keyword))


def check_subheading_length(final_content: dict, spec: RequirementsSpec) -> ValidationCheckResult:
    """Every H2/H3 subheading is inside its length range (see subheading_seo)."""
    report = subheading_report(
        final_content.get("body_markdown") or "",
        "",
        spec.get("content_type") or "",
    )
    violations = report["length_violations"]
    if not violations:
        return _pass(
            "subheading_length",
            f"All {len(report['headings'])} H2/H3 subheadings are within length range.",
        )
    return _fail("subheading_length", "blocking", describe_length_issue(violations))


def check_focus_keyphrase_in_meta_description(
    final_content: dict, spec: RequirementsSpec
) -> ValidationCheckResult:
    """The exact focus keyphrase appears in the meta description."""
    keyword = (spec.get("target_keyword") or "").strip()
    if not keyword:
        return _pass(
            "focus_keyphrase_in_meta_description", "No target keyword in outline; skipping."
        )

    meta_description = (final_content.get("meta_description") or "").strip()
    if not meta_description:
        # Reported by check_meta_description_present; not double-counted here.
        return _pass(
            "focus_keyphrase_in_meta_description",
            "No meta description to check (reported separately).",
        )

    if contains_keyphrase(meta_description, keyword):
        return _pass(
            "focus_keyphrase_in_meta_description",
            f"Focus keyphrase {keyword!r} present in meta description.",
        )

    return _fail(
        "focus_keyphrase_in_meta_description",
        "blocking",
        f"Focus keyphrase {keyword!r} is missing from the meta description.",
    )


def check_focus_keyphrase_in_introduction(
    final_content: dict, spec: RequirementsSpec
) -> ValidationCheckResult:
    """The exact focus keyphrase appears in the introduction."""
    keyword = (spec.get("target_keyword") or "").strip()
    if not keyword:
        return _pass("focus_keyphrase_in_introduction", "No target keyword in outline; skipping.")

    introduction = (final_content.get("introduction") or "").strip()
    if not introduction:
        return _fail(
            "focus_keyphrase_in_introduction",
            "blocking",
            "Introduction is missing, so the focus keyphrase cannot appear in it.",
        )

    if contains_keyphrase(introduction, keyword):
        return _pass(
            "focus_keyphrase_in_introduction",
            f"Focus keyphrase {keyword!r} present in the introduction.",
        )

    return _fail(
        "focus_keyphrase_in_introduction",
        "blocking",
        f"Focus keyphrase {keyword!r} is missing from the introduction. It must appear "
        "in the opening paragraphs, ideally in the first sentence.",
    )


def check_title_subject_alignment(
    final_content: dict, spec: RequirementsSpec
) -> ValidationCheckResult:
    """The body delivers the subject the title promises.

    Pins the reported defect where a title comparing AGENCIES shipped with a
    body comparing TOOLS. Every other check passed on that article: the
    keyphrase was present, the length was right, the sections existed. Only the
    entity class disagreed, and nothing compared it.

    Deliberately narrow -- see title_subject.find_subject_mismatch. A title that
    names no entity class (most how-to and explainer titles) is skipped rather
    than guessed at.
    """
    title = (final_content.get("title") or spec.get("selected_title") or "").strip()
    if not title:
        return _pass("title_subject_alignment", "No title to check; skipping.")

    mismatch = find_subject_mismatch(title, _combined_text(final_content))
    if mismatch is None:
        return _pass("title_subject_alignment", "Body subject matches the title's subject.")

    promised = mismatch["promised_class"]
    dominant = mismatch["dominant_class"]

    if mismatch["reason"] == "absent":
        detail = (
            f"The title is about {promised!r}, but the article barely mentions it "
            f"({mismatch['promised_count']} occurrence(s))."
        )
    else:
        detail = (
            f"The title is about {promised!r} ({mismatch['promised_count']} occurrence(s)), "
            f"but the article is written about {dominant!r} instead "
            f"({mismatch['dominant_count']} occurrence(s))."
        )

    if dominant:
        detail += (
            f" Rewrite the article to be about {promised!r} -- every comparison, list "
            f"entry, recommendation and example must be {promised!r}, not {dominant!r}. "
            "Do not change the title."
        )
    else:
        detail += (
            f" Rewrite the article to be about {promised!r} as the title promises. "
            "Do not change the title."
        )

    return _fail("title_subject_alignment", "blocking", detail)


def check_required_sections(final_content: dict, spec: RequirementsSpec) -> ValidationCheckResult:
    expected = spec.get("expected_sections") or []
    if not expected:
        return _pass(
            "required_sections", "No section requirements extracted from outline; skipping."
        )
    # When generation was structured, each section was a required Pydantic field
    # and its presence is already guaranteed — the model could not have returned
    # an object missing one. Heading matching would actively MISREPORT here,
    # because expected_sections holds schema labels ("Problem", "Objection
    # Handling") while a structured block's heading is deliberately reader-facing
    # ("Buying Without Clarity"); emitting the field name as a heading is the
    # defect ContentBlock.heading exists to prevent. Verify the blocks that were
    # actually written instead, and only fall through to heading matching when
    # this payload did not come from structured generation.
    written_blocks = final_content.get(STRUCTURED_BLOCKS_KEY)
    if isinstance(written_blocks, list):
        return _pass(
            "required_sections",
            f"Structured generation produced {len(written_blocks)} approved section(s); "
            f"presence is guaranteed by the content schema rather than heading matching.",
        )

    body = final_content.get("body_markdown") or ""
    headings = [h.strip().lower() for h in re.findall(r"^#{2,3}\s+(.+)$", body, flags=re.MULTILINE)]
    missing = []
    for label in expected:
        label_l = label.strip().lower()
        if any(_heading_matches(label_l, h) for h in headings):
            continue
        missing.append(label)
    if not missing:
        return _pass("required_sections", f"All {len(expected)} expected section(s) found.")

    # A missing REQUIRED block blocks regardless of overall coverage. A flat
    # percentage cannot tell "the optional FAQ block didn't make it" from "the
    # article has no Solution section at all" — a landing page that dropped its
    # Problem section scored 5/6 (83%) and shipped on a warning nobody reads.
    # `required` here means the schema field is non-Optional, so the content
    # type itself declares the section mandatory.
    required = {r.strip().lower() for r in (spec.get("required_sections") or [])}
    missing_required = [m for m in missing if m.strip().lower() in required]
    if missing_required:
        return _fail(
            "required_sections",
            "blocking",
            f"Missing {len(missing_required)} REQUIRED section(s) this content type declares "
            f"mandatory: {', '.join(missing_required[:5])}. "
            f"({len(missing)}/{len(expected)} expected section(s) missing overall.)",
        )

    # Only optional blocks are absent. Fuzzy label-to-heading matching is
    # inherently approximate, so a minority miss here stays a warning rather
    # than driving a repair loop against a section the schema never required.
    coverage = 1 - (len(missing) / len(expected))
    severity = "blocking" if coverage < 0.7 else "warning"
    return _fail(
        "required_sections",
        severity,
        f"Missing {len(missing)}/{len(expected)} expected section(s): {', '.join(missing[:5])}",
    )


def check_hero_presence(final_content: dict, spec: RequirementsSpec) -> ValidationCheckResult:
    """Verify the approved hero survived into the article — by CONTENT, not label.

    `hero` sits in outline_structure's _NON_HEADING_BLOCKS because no article
    contains a literal "## Hero" heading, so requiring that label would fail
    everything. The side effect was that a missing hero became structurally
    invisible: check_required_sections could not see it, and the model could
    drop the block with nothing noticing. That is exactly how a landing page
    shipped with keyword headings and no hero — which in turn left an approved
    brand mention with no above-the-fold slot, so it slid to the last line and
    repair had nowhere to move it to.

    Matching is token overlap against the hero's own headline/subheadline rather
    than an exact string, because the writer is expected to rewrite hero copy
    into flowing prose, not paste it verbatim.
    """
    hero = spec.get("hero_context")
    if not hero:
        return _pass("hero_presence", "This content type/outline declares no hero; skipping.")

    # When generation was structured, `hero` was a REQUIRED Pydantic field — the
    # model could not have returned an object without it, so its presence is
    # already guaranteed and this heuristic can only misreport.
    #
    # And it did: the writer is asked to turn the approved hero into natural
    # prose rather than paste it, so a correctly-written hero scores far below
    # the token-coverage threshold (measured at 0.18 against a 0.5 bar). That
    # produced a BLOCKING "hero missing" on articles whose hero was present,
    # which repair then burned both attempts failing to fix because there was
    # nothing to fix. Trust the schema, exactly as check_required_sections does.
    written_blocks = final_content.get(STRUCTURED_BLOCKS_KEY)
    if isinstance(written_blocks, list) and "hero" in written_blocks:
        return _pass(
            "hero_presence",
            "Hero was generated as a required section of the structured content schema.",
        )

    hero_text = f"{hero.get('headline', '')} {hero.get('subheadline', '')}".strip()
    if not _tokenize(hero_text):
        return _pass("hero_presence", "Approved hero carries no distinctive wording to verify.")

    # The hero's job is to open the page, so only the opening counts: the title,
    # the introduction, and the first slice of the body.
    title = final_content.get("title") or ""
    intro = final_content.get("introduction") or ""
    body = final_content.get("body_markdown") or ""
    opening = f"{title}\n{intro}\n{body[: max(400, int(len(body) * _HERO_WINDOW_FRACTION))]}"

    if _coverage_ratio(hero_text, opening) >= _HERO_MIN_COVERAGE:
        return _pass(
            "hero_presence", "The approved hero's message is present in the article's opening."
        )

    severity = "blocking" if spec.get("hero_required") else "warning"
    return _fail(
        "hero_presence",
        severity,
        f"The approved hero does not appear in the article's opening — its headline/subheadline "
        f'("{hero_text[:70]}") is not reflected in the title, introduction or first section. '
        f"Open the article with the approved hero rather than starting straight into body sections.",
    )


def check_brand_presence(final_content: dict, spec: RequirementsSpec) -> ValidationCheckResult:
    brand = spec.get("brand_context")
    if not brand:
        return _pass("brand_presence", "No approved brand promotion for this article; skipping.")
    text = _combined_text(final_content)
    if _mention_present(text, brand["brand_name"]):
        return _pass("brand_presence", f"Brand '{brand['brand_name']}' is mentioned.")
    return _fail(
        "brand_presence",
        "blocking",
        f"Approved brand mention '{brand['brand_name']}' is missing entirely.",
    )


def check_brand_url_accuracy(final_content: dict, spec: RequirementsSpec) -> ValidationCheckResult:
    brand = spec.get("brand_context")
    if not brand or not brand.get("brand_url"):
        return _pass("brand_url_accuracy", "No approved brand URL to verify; skipping.")
    text = _combined_text(final_content)
    brand_url = brand["brand_url"]
    brand_name = brand["brand_name"]
    idx = text.lower().find(brand_name.lower())
    if idx == -1:
        return _pass(
            "brand_url_accuracy", "Brand not mentioned (caught by brand_presence); skipping."
        )
    # Sentence-scoped, not a fixed char window — a fixed window can grab a
    # link from an adjacent, unrelated sentence/line and misattribute it.
    sentence = _sentence_containing(text, text[idx : idx + len(brand_name)])
    links_in_sentence = _find_markdown_links(sentence) if sentence else []
    if any(url == brand_url for _, url in links_in_sentence):
        return _pass(
            "brand_url_accuracy", "Brand mention is correctly hyperlinked to the approved URL."
        )
    if links_in_sentence:
        wrong = links_in_sentence[0][1]
        return _fail(
            "brand_url_accuracy",
            "blocking",
            f"Brand mention is hyperlinked to '{wrong}', not the approved '{brand_url}'.",
        )
    return _fail(
        "brand_url_accuracy", "blocking", f"Brand mention has no hyperlink; expected '{brand_url}'."
    )


def check_brand_placement(final_content: dict, spec: RequirementsSpec) -> ValidationCheckResult:
    brand = spec.get("brand_context")
    if not brand:
        return _pass("brand_placement", "No approved brand promotion; skipping.")
    text = _combined_text(final_content)
    if not _mention_present(text, brand["brand_name"]):
        return _pass("brand_placement", "Brand not mentioned (caught by brand_presence); skipping.")
    if _is_bare_line(text, brand["brand_name"], max_words=6):
        return _fail(
            "brand_placement",
            "warning",
            "Brand mention appears bolted onto its own line, not woven into a sentence.",
        )
    return _pass("brand_placement", "Brand mention is embedded in prose.")


def check_brand_placement_policy(
    final_content: dict, spec: RequirementsSpec
) -> ValidationCheckResult:
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
    brand_name = brand["brand_name"]
    about_selling = _about_and_selling(brand)

    # Reader-visible mentions only, so a brand that appears solely inside a link
    # URL or a bibliography entry is correctly treated as absent here rather than
    # silently satisfying the positional window.
    intro_occurrences = _brand_occurrences(intro, brand_name, about_selling)
    body_occurrences = _brand_occurrences(body, brand_name, about_selling)
    if not intro_occurrences and not body_occurrences:
        return _pass(
            "brand_placement_policy", "Brand not mentioned (caught by brand_presence); skipping."
        )

    if policy == "hero":
        # Hero-anchored types (landing-page) are graded against the page's
        # STRUCTURE — the introduction plus the body's opening/hero section —
        # instead of the character-percentage window below, which cannot express
        # "in the hero" on a hero-led page: the hero opens body_markdown, so it
        # starts roughly len(introduction) characters into the combined text and
        # falls outside a 20% window on any landing page whose body is not more
        # than four times its introduction. See HERO_ANCHORED_RATIONALE in
        # brand_placement_policy.py.
        #
        # The hero block itself is what has to carry the mention — an
        # `introduction` mention does NOT substitute for it. On a landing page
        # the hero is the conversion surface the promotion was approved for, and
        # "brand named in the intro, hero left brand-free" is precisely the
        # reported "brand is in the wrong place" defect. A mention in the intro
        # is not PENALISED (it sits above the hero, so it cannot be "buried") —
        # it just does not satisfy the requirement on its own.
        if full_policy.get("hero_anchored"):
            hero_end = _opening_section_end(_normalize_for_mentions(body))
            if body_occurrences and body_occurrences[0].offset < hero_end:
                return _pass(
                    "brand_placement_policy",
                    f"'{brand_name}' is named in the hero/opening section, as this content type requires.",
                )
            where = (
                "only in the introduction, leaving the hero itself brand-free"
                if intro_occurrences
                else "only further down the page"
            )
            return _fail(
                "brand_placement_policy",
                "blocking",
                f"This content type requires '{brand_name}' in the HERO — the opening block of the page, "
                f"the copy before the first section heading — but it appears {where}. Name '{brand_name}' "
                f"in the hero copy itself; a mention anywhere else does not substitute for it.",
            )

        # Measured over intro+body as one document rather than intro-counts-
        # wholesale plus a body offset. The split version misgraded the good
        # case: a substantive mention in the INTRO with an incidental one late
        # in the body made the late one "primary" and failed an article that had
        # done exactly the right thing.
        #
        # Graduated threshold, not one-size-fits-all: strict hero/above-the-fold
        # types (brand-page, sales-page, comparison, ...) need the mention very
        # early; a ranked-list format (best-tools, product-roundup) can
        # legitimately place its featured entry anywhere in the first half —
        # the actual complaint there was about being ranked LAST, not about a
        # literal above-the-fold requirement. See brand_placement_policy.py.
        max_fraction = full_policy.get(
            "top_position_max_fraction",
            DEFAULT_TOP_POSITION_MAX_FRACTION,
        )
        combined_occurrences = _brand_occurrences(
            f"{intro}\n\n{body}",
            brand_name,
            about_selling,
        )
        in_window = any(
            o.offset < max(200, int(o.text_length * max_fraction)) for o in combined_occurrences
        )
        pct = int(max_fraction * 100)
        if not in_window:
            return _fail(
                "brand_placement_policy",
                "blocking",
                f"This content type requires '{brand_name}' within the first {pct}% of the article "
                f"(hero/intro/top-ranked position), but it only appears later — move the existing mention up, "
                f"don't just add a second one at the top.",
            )
        # Position is judged on the FIRST appearance only. A brand legitimately
        # recurs through a hero-led page, and those later mentions are not a
        # defect to grade — once the first one lands in the window, the rest can
        # be woven in wherever they read naturally.
        return _pass(
            "brand_placement_policy",
            "Brand mention appears near the top, as expected for this content type.",
        )

    if intro_occurrences:
        return _fail(
            "brand_placement_policy",
            "warning",
            "Brand mention appears in the introduction; for this content type it should stay in a body "
            "section — opening an otherwise-independent article with a product pitch reads as an ad.",
        )

    if not body_occurrences:
        # Intro-only mention, which the warning above already returned on —
        # defensive, guards the indexed reads below.
        return _pass("brand_placement_policy", "No body mention to grade positionally.")

    # Position is judged on the FIRST appearance only. The brand may legitimately
    # recur later in the piece; those repeats are woven in naturally and are not
    # graded. What matters is that the reader meets the brand somewhere they
    # actually read.
    first = body_occurrences[0]

    # Checked BEFORE the general window below: a mention at 95% trips both, and
    # "it's bolted onto the closing paragraph" is the more specific and more
    # actionable message of the two.
    #
    # Blocking at every promoting intensity, not just moderate/high. An approved
    # promotion buried in the final scrap of the article is a failed promotion
    # regardless of how soft the format is, and `warning` severity is invisible
    # to repair_content — which only acts on blocking failures — so the softer
    # treatment meant these were never repaired at all.
    if first.position_fraction >= (1 - _CLOSING_TAIL_FRACTION):
        return _fail(
            "brand_placement_policy",
            "blocking",
            f"'{brand_name}' only appears in the article's closing section — this content type's "
            f"guardrail calls for a genuine mid-body mention, not a mention bolted onto the closing "
            f"paragraph/CTA. Move it into an earlier body section.",
        )

    # Positive attention window, graded on the FIRST appearance. The old rule was
    # purely negative — not in the intro, not in the last 10% — so a mention at
    # the 85% mark passed silently even though most readers never reach it
    # (roughly three-quarters of viewing time falls in the first couple of
    # screenfuls). The window (30% by default) is the hard ceiling, not the
    # target: earlier is better. Only the FIRST mention is graded against it —
    # later ones recur freely and are never penalised.
    max_fraction = full_policy.get(
        "body_attention_max_fraction", DEFAULT_BODY_ATTENTION_MAX_FRACTION
    )
    if first.position_fraction > max_fraction:
        pct = int(max_fraction * 100)
        return _fail(
            "brand_placement_policy",
            "blocking",
            f"'{brand_name}' first appears at {int(first.position_fraction * 100)}% through the body, past "
            f"the first {pct}% where readers actually are. Move that first mention into an earlier body "
            f"section — later mentions are fine, but the first one must land early.",
        )

    return _pass(
        "brand_placement_policy",
        "Brand mention sits in an early body section, out of the introduction and the closing section.",
    )


_SHALLOW_MENTION_MIN_WORDS = 12  # minimum words in the text surrounding the mention
_SHALLOW_MENTION_OVERLAP_THRESHOLD = 0.08


def check_brand_integration_depth(
    final_content: dict, spec: RequirementsSpec
) -> ValidationCheckResult:
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
        return _pass(
            "brand_integration_depth",
            "This content type has no natural PLM depth requirement; skipping.",
        )
    text = _combined_text(final_content)
    about_and_selling = _about_and_selling(brand)
    occurrences = _brand_occurrences(text, brand["brand_name"], about_and_selling)
    if not occurrences:
        return _pass(
            "brand_integration_depth", "Brand not mentioned (caught by brand_presence); skipping."
        )

    # Grade the PRIMARY occurrence — the most substantive one — rather than
    # whichever happened to come first. Reading the first occurrence meant an
    # early throwaway name-drop masked a genuinely strong mention later in the
    # piece (and vice versa), and did so via a case-SENSITIVE `str.find` that
    # returned an empty sentence whenever the article wrote the name in a
    # different case than the outline did, failing this check spuriously.
    # check_brand_placement_policy grades the same occurrence, so the two can
    # never disagree about which mention they are talking about.
    primary = _primary_occurrence(occurrences)
    sentence = primary.sentence
    sentence_word_count = len(sentence.split())
    overlap = primary.substance_score

    if (
        sentence_word_count < _SHALLOW_MENTION_MIN_WORDS
        or overlap < _SHALLOW_MENTION_OVERLAP_THRESHOLD
    ):
        # Blocking at every promoting intensity, not just high/maximal. The
        # `intensity == "none"` case already returned above, so reaching here
        # means the brand IS meant to be promoted in this article, and a bare
        # name-drop fails that regardless of how soft the format is. Warnings
        # never reach repair_content — it acts only on blocking failures — so
        # under the old rule a shallow mention in a blog, explainer, how-to,
        # checklist, white-paper or buying-guide (12 of the 13 body-led types)
        # was correctly POSITIONED and then shipped with no substance attached.
        # That is the "present but poorly integrated" failure this check exists
        # to catch, and it was unreachable.
        return _fail(
            "brand_integration_depth",
            "blocking",
            "Brand mention reads like a bare name-drop with no specific benefit/value attached nearby — "
            "attach a concrete claim from the approved About/selling-position text, not just the name.",
        )
    return _pass(
        "brand_integration_depth", "Brand mention is backed by specific, substantive context."
    )


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


def check_brand_factual_grounding(
    final_content: dict, spec: RequirementsSpec
) -> ValidationCheckResult:
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
        return _pass(
            "brand_factual_grounding", "Brand not mentioned (caught by brand_presence); skipping."
        )
    sentence = (
        _sentence_containing(text, text[idx : idx + len(brand["brand_name"])]) or ""
    ).lower()
    if not sentence:
        return _pass(
            "brand_factual_grounding", "Could not isolate the brand-mention sentence; skipping."
        )

    for group_a, group_b in _TECH_CONFUSION_PAIRS:
        a_in_about = any(t in about_text for t in group_a)
        b_in_about = any(t in about_text for t in group_b)
        if a_in_about == b_in_about:
            continue  # neither present, or both present (legitimate dual-stack) — not a contradiction
        approved, conflicting = (group_a, group_b) if a_in_about else (group_b, group_a)
        hit = next((t for t in conflicting if t in sentence), None)
        if hit:
            return _fail(
                "brand_factual_grounding",
                "blocking",
                f"Brand mention says '{hit}', but the approved brand info specifies "
                f"'{next(t for t in approved if t in about_text)}' — this contradicts the approved facts.",
            )
    return _pass(
        "brand_factual_grounding", "No contradicting technology term found near the brand mention."
    )


_NEGATIVE_CONTEXT_WORDS = (
    "avoid",
    "worse",
    "worst",
    "bad",
    "don't use",
    "never use",
    "poor",
    "fails",
    "broken",
    "scam",
    "overpriced",
    "disappointing",
    "instead of",
)


def check_brand_context_heuristic(
    final_content: dict, spec: RequirementsSpec
) -> ValidationCheckResult:
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
    window = text[max(0, idx - 120) : idx + 120].lower()
    hits = [w for w in _NEGATIVE_CONTEXT_WORDS if w in window]
    if hits:
        return _fail(
            "brand_context_heuristic",
            "warning",
            f"Negative-sounding word(s) near brand mention: {', '.join(hits)} — verify tone manually.",
        )
    return _pass("brand_context_heuristic", "No negative-tone signal near brand mention.")


# Below this relevance threshold, skipping an approved link is treated as
# acceptable (the writer had good reason not to force it in) rather than a
# failure — matches "an irrelevant link might be skipped in rare cases."
_LINK_RELEVANCE_THRESHOLD = 0.15
_LINK_PLACEMENT_THRESHOLD = 0.10


def check_internal_links_integration(
    final_content: dict, spec: RequirementsSpec
) -> ValidationCheckResult:
    approved = spec.get("approved_internal_links") or []
    if not approved:
        return _pass("internal_links_integration", "No approved internal links; skipping.")

    combined = _combined_text(final_content)
    url_set = {normalize_url(u) for _, u in _find_markdown_links(combined)}

    labels: dict[str, str] = {}
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
        anchor_context = (
            f"{lnk.get('title', '')} {lnk.get('anchor_text', '')} {lnk.get('context', '')}".strip()
        )
        relevance = _word_overlap_ratio(anchor_context, combined) if anchor_context else 0.0
        suggested_anchor = (lnk.get("anchor_text") or lnk.get("title") or "").strip()
        labels[url] = f'{url} (topic: "{suggested_anchor}")' if suggested_anchor else url

        if normalize_url(url) not in url_set:
            (
                missing_relevant if relevance >= _LINK_RELEVANCE_THRESHOLD else missing_irrelevant
            ).append(url)
            continue

        # Present — but is it woven in, or just an isolated line? Wrong-URL
        # substitution is already caught above (exact match against url_set),
        # so from here on we're only distinguishing HOW a present link landed.
        if _is_bare_line(combined, url):
            if relevance >= _LINK_RELEVANCE_THRESHOLD:
                bolted_on.append(url)
            continue

        sentence = _sentence_containing(combined, url)
        if (
            anchor_context
            and sentence
            and _word_overlap_ratio(anchor_context, sentence) < _LINK_PLACEMENT_THRESHOLD
        ):
            misplaced.append(url)

    # Every offending URL is listed, with the topic it should be anchored on. The
    # detail is the repair model's instruction: truncating it to three URLs meant a
    # fourth missing link could only be fixed by a second repair round.
    if missing_relevant or bolted_on:
        parts = []
        if missing_relevant:
            parts.append(
                f"{len(missing_relevant)} relevant approved link(s) never embedded: "
                f"{_join_limited([labels[u] for u in missing_relevant])}"
            )
        if bolted_on:
            parts.append(
                f"{len(bolted_on)} link(s) only present as a bolted-on line, not woven in: "
                f"{_join_limited([labels[u] for u in bolted_on])}"
            )
        return _fail("internal_links_integration", "blocking", "; ".join(parts))

    if missing_irrelevant or misplaced:
        parts = []
        if missing_irrelevant:
            parts.append(
                f"{len(missing_irrelevant)} approved link(s) skipped, low topical overlap (acceptable): {', '.join(missing_irrelevant[:3])}"
            )
        if misplaced:
            parts.append(
                f"{len(misplaced)} link(s) present but possibly misplaced (low overlap with surrounding sentence): {', '.join(misplaced[:3])}"
            )
        return _fail("internal_links_integration", "warning", "; ".join(parts))

    return _pass(
        "internal_links_integration",
        f"All {len(approved)} approved internal link(s) naturally integrated.",
    )


_DETAIL_LIST_LIMIT = 12


def _join_limited(items: list[str], limit: int = _DETAIL_LIST_LIMIT) -> str:
    shown = "; ".join(items[:limit])
    return f"{shown}; (+{len(items) - limit} more)" if len(items) > limit else shown


def protected_links(
    final_content: dict,
    spec: RequirementsSpec,
    searched_results: Optional[list[dict]] = None,
    candidates: Optional[list[LinkRecord]] = None,
) -> list[LinkRecord]:
    """Inline links in this article that no later stage may silently remove.

    Uses the same ground truth the link checks already grade against, so a link
    is protected only when it is VALID and RELEVANT:

    * an approved internal link whose topic overlaps the article (the same
      relevance bar check_internal_links_integration applies),
    * a citation whose URL came back from the writer's own search_tool calls,
    * the approved brand URL.

    Anything else — an unverified or fabricated URL, a low-relevance internal
    link — is deliberately not protected, so repair can still remove it.

    ``candidates`` classifies the given records instead of the article's own
    links — used for links the writer produced that never reached the article
    (see structured_body.UNPLACED_LINKS_KEY).
    """
    combined = _combined_text(final_content)
    internal: set[str] = set()
    for lnk in spec.get("approved_internal_links") or []:
        if not isinstance(lnk, dict) or not (lnk.get("url") or "").strip():
            continue
        context = f"{lnk.get('title', '')} {lnk.get('anchor_text', '')} {lnk.get('context', '')}"
        if (
            not context.strip()
            or _word_overlap_ratio(context, combined) >= _LINK_RELEVANCE_THRESHOLD
        ):
            internal.add(normalize_url(lnk["url"]))
    verified = {normalize_url(r.get("url") or "") for r in (searched_results or []) if r.get("url")}
    brand_url = normalize_url((spec.get("brand_context") or {}).get("brand_url") or "")

    records: list[LinkRecord] = []
    source = candidates if candidates is not None else extract_content_links(final_content)
    for record in dedupe_records(source):
        key = normalize_url(record["url"])
        if key in internal:
            kind = "internal"
        elif brand_url and key == brand_url:
            kind = "brand"
        elif key in verified:
            kind = "citation"
        else:
            continue
        records.append({**record, "kind": kind})
    return records


def merge_link_inventory(*groups: Optional[list[dict]]) -> list[dict]:
    """Union of inventories, one record per URL; the earliest record keeps its placement."""
    return dedupe_records(record for group in groups for record in (group or []))


def check_links_preserved(final_content: dict, spec: RequirementsSpec) -> ValidationCheckResult:
    """Every protected link the article has carried is still linked.

    The other link checks grade the article against the OUTLINE (was an approved
    link embedded?) and against the cited-facts LIST. Neither can see a valid link
    that a rewrite simply dropped: an outbound citation removed by humanization
    passed every check, and a link lost when structured generation discarded the
    model's own body_markdown was indistinguishable from one never written.

    This compares against `link_inventory` — the protected links recorded by each
    prose-rewriting stage — and names every lost link with its anchor text and
    original sentence, which is exactly what a repair needs to put it back.
    """
    inventory = dedupe_records(spec.get("link_inventory") or [])
    if not inventory:
        return _pass("links_preserved", "No protected inline links recorded; skipping.")
    present = present_urls(final_content)
    lost = [r for r in inventory if normalize_url(r.get("url", "")) not in present]
    if not lost:
        return _pass("links_preserved", f"All {len(inventory)} protected link(s) present.")
    return _fail(
        "links_preserved",
        "blocking",
        f"{len(lost)} valid link(s) were removed from the article and must be restored in "
        f"place: {_join_limited([describe_link(r) for r in lost])}",
    )


_FACT_FIDELITY_THRESHOLD = 0.15


def check_facts_and_external_links_integration(
    final_content: dict,
    spec: RequirementsSpec,
    searched_results: list[dict],
) -> ValidationCheckResult:
    facts = [f for f in (final_content.get("facts") or []) if isinstance(f, dict)]
    outbound_links = [
        link for link in (final_content.get("outbound_links") or []) if isinstance(link, dict)
    ]
    sourced_facts = [f for f in facts if (f.get("source_url") or "").strip()]

    if not sourced_facts and not outbound_links:
        return _pass(
            "facts_and_external_links", "No sourced facts or outbound links to verify; skipping."
        )

    if not searched_results:
        # No search-tool ground truth captured this run — degrade to a
        # warning rather than blocking every article with citations, since a
        # plumbing gap here (not a real hallucination) shouldn't hard-fail
        # generation. Still surfaced for visibility.
        return _fail(
            "facts_and_external_links",
            "warning",
            "Article cites source(s) but no search_tool results were captured this run — provenance unverifiable.",
        )

    # Matched on the normalized URL: a trailing slash, #fragment or utm_ tag on a
    # real search result is the same source, and reading it as "fabricated" made
    # repair delete a valid, verified citation.
    searched_urls = {normalize_url(r.get("url")) for r in searched_results if r.get("url")}
    snippet_by_url = {
        normalize_url(r.get("url")): r.get("snippet", "") for r in searched_results if r.get("url")
    }
    linked_urls = present_urls(final_content)
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
        if normalize_url(source_url) not in searched_urls:
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
            snippet = snippet_by_url.get(normalize_url(source_url), "")
            if snippet and _word_overlap_ratio(fact_text, snippet) < _FACT_FIDELITY_THRESHOLD:
                low_fidelity.append(source_url)

    def _check_outbound_link(url: str) -> None:
        """Outbound links ARE meant to be actual inline hyperlinks (see Link's
        docstring) — this is where the reported bug lives: 2-3 links dumped
        as a bare trailing list instead of woven into a sentence."""
        if normalize_url(url) not in searched_urls:
            fabricated.append(url)
            return
        real_urls.append(url)
        if url not in combined and normalize_url(url) not in linked_urls:
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
            "facts_and_external_links",
            "blocking",
            f"{len(fabricated)} citation(s) not traceable to any search_tool result — likely fabricated: {_join_limited(fabricated)}",
        )
    if not_integrated:
        return _fail(
            "facts_and_external_links",
            "blocking",
            f"{len(not_integrated)} sourced fact(s)/link(s) never woven into the prose "
            f"(missing entirely, or only present as a bolted-on trailing link): {_join_limited(not_integrated)}",
        )
    if len(real_urls) > max_recommended:
        return _fail(
            "facts_and_external_links",
            "warning",
            f"{len(real_urls)} external citations is more than recommended ({max_recommended}) for this "
            f"content type — consider trimming to the strongest few.",
        )
    if low_fidelity:
        return _fail(
            "facts_and_external_links",
            "warning",
            f"{len(low_fidelity)} fact(s) wording doesn't clearly match its cited source: {', '.join(low_fidelity[:3])}",
        )
    return _pass(
        "facts_and_external_links",
        "All sourced facts/links trace to real search results and appear naturally in the article.",
    )


def check_cta_presence(final_content: dict, spec: RequirementsSpec) -> ValidationCheckResult:
    if not spec.get("cta_required"):
        return _pass(
            "cta_presence", "This content type/outline has no declared CTA requirement; skipping."
        )
    cta = final_content.get("cta")
    cta_text = (cta.get("text") or "").strip() if isinstance(cta, dict) else ""
    if not cta_text:
        expected = (spec.get("outline_cta") or {}).get("text", "")
        return _fail(
            "cta_presence",
            "blocking",
            f"Outline declares a CTA ('{expected}') but the generated content has no cta field populated.",
        )
    if cta_text.lower() in _combined_text(final_content).lower():
        return _pass(
            "cta_presence", f"CTA '{cta_text}' is populated and integrated into the content."
        )
    return _fail(
        "cta_presence",
        "blocking",
        f"cta.text ('{cta_text}') was populated but never appears in body_markdown/introduction.",
    )


def check_placeholder_product_names(
    final_content: dict, spec: RequirementsSpec
) -> ValidationCheckResult:
    """Report invented stand-in competitors ("Agency A", "Tool 1") in the article.

    These come from a comparison-style outline generated with no real product
    names available, and they make the page worthless: it compares companies
    that do not exist. The structural fixes live upstream — the outline prompt
    now receives the workspace's real brand and competitor names, and
    `brand_slot` treats a placeholder-named product as a free slot rather than a
    competitor to protect — so by the time an article reaches here a placeholder
    means those upstream guards were bypassed or insufficient.

    Deliberately a WARNING rather than blocking. Every other failed check routes
    into a repair pass, but repair cannot fix this one: the real name is not
    knowable from the article, so a repair prompt would only swap an obvious
    fabrication for a plausible-looking one. Surfacing it for a human is the
    honest outcome.
    """
    names = find_placeholder_names_in_text(_combined_text(final_content))
    if not names:
        return _pass("placeholder_product_names", "No placeholder product names found.")
    return _fail(
        "placeholder_product_names",
        "warning",
        f"Article names {len(names)} placeholder product(s) instead of real ones: "
        f"{', '.join(names[:5])}. The comparison should name real, specific products — "
        f"regenerate the outline with real competitor names rather than renaming these.",
    )


def check_unsupported_claims(final_content: dict, spec: RequirementsSpec) -> ValidationCheckResult:
    """Prices, figures, versions/dates, invented experience, absolute verdicts,
    competitor weaknesses and brand capabilities that no evidence supports.

    check_facts_and_external_links_integration only sees claims the writer
    declared in `facts`; this reads the prose itself, so an undeclared guess
    (an outdated competitor price, "we tested all five", "the clear winner")
    can no longer pass by simply not being listed. Evidence comes from
    spec["claim_evidence"] — the real search results, the approved brand info
    and the author profile — and the rules are identical for every content
    type (claim_integrity.py).

    Blocking: repair removes or softens each flagged claim in place. Brand
    promotion itself is untouched — only the unsupported specifics inside it,
    so qualified positioning ("a strong fit for teams that...") survives.
    """
    text = "\n".join(
        str(final_content.get(field) or "")
        for field in ("meta_description", "introduction", "body_markdown")
    )
    claims = find_unsupported_claims(text, spec.get("claim_evidence") or {})
    if not claims:
        return _pass(
            "unsupported_claims",
            "Every price, figure, version, verdict and product claim checked is backed by evidence.",
        )
    return _fail("unsupported_claims", "blocking", describe_unsupported_claims(claims))


# ── check registry + orchestration ──────────────────────────────────────────

CheckFn = Callable[[dict, RequirementsSpec], ValidationCheckResult]

CHECK_REGISTRY: list[CheckFn] = [
    check_word_count_band,
    # Content-level on-page SEO: the title the user locked in, the exact focus
    # keyphrase on every keyphrase-bearing surface, and the body actually being
    # about what the title promises.
    check_selected_title_preserved,
    check_focus_keyphrase_in_title,
    check_meta_description_present,
    check_meta_description_length,
    check_focus_keyphrase_in_meta_description,
    check_focus_keyphrase_in_introduction,
    check_title_subject_alignment,
    check_keyword_presence,
    check_keyword_density,
    # H2/H3 subheadings: Yoast's keyphrase-in-subheadings distribution and a
    # length range. Repaired by a headings-only rewrite (see repair_content),
    # never by a full-article repair.
    check_subheading_keyphrase,
    check_subheading_length,
    check_required_sections,
    check_hero_presence,
    check_brand_presence,
    check_brand_url_accuracy,
    check_brand_placement,
    check_brand_placement_policy,
    check_brand_integration_depth,
    check_brand_factual_grounding,
    check_brand_context_heuristic,
    check_internal_links_integration,
    check_links_preserved,
    check_cta_presence,
    check_placeholder_product_names,
    check_unsupported_claims,
]

# Lightweight subset re-checked after humanization — only what humanization's
# free-form rewrite could plausibly damage. No LLM, no full suite, no EEAT.
FINAL_VALIDATE_CHECKS: list[CheckFn] = [
    check_word_count_band,
    # Humanization rewrites the introduction and body wholesale and returns the
    # full schema, so every one of these can regress here even though it passed
    # pre-humanize.
    check_selected_title_preserved,
    check_focus_keyphrase_in_title,
    check_meta_description_present,
    check_meta_description_length,
    check_focus_keyphrase_in_meta_description,
    check_focus_keyphrase_in_introduction,
    check_title_subject_alignment,
    check_keyword_presence,
    # Humanization may reword headings while "improving the flow".
    check_subheading_keyphrase,
    check_subheading_length,
    # Humanization rewrites the introduction and body wholesale and may trim or
    # expand by hundreds of words -- both move density directly, and a rewrite
    # that "improves the flow" by swapping the exact phrase for a synonym is the
    # single most likely way a compliant draft turns non-compliant here.
    check_keyword_density,
    check_brand_presence,
    check_brand_url_accuracy,
    check_brand_placement,
    # Humanization is a free-form rewrite: it can move an approved mention out
    # of its hero/attention slot, or dilute real value-prop copy down to a bare
    # namecheck. Both were previously invisible here — position and depth were
    # verified pre-humanize and then never re-checked — so a compliant draft
    # could ship non-compliant.
    check_brand_placement_policy,
    check_brand_integration_depth,
    check_brand_factual_grounding,
    # Humanization is told to add voice, not facts — but it is a free-form
    # rewrite with no access to the evidence, so a new figure, anecdote or
    # verdict it introduces is re-checked here before the article ships.
    check_unsupported_claims,
    # Humanization is told to keep every link, but nothing verified it: a
    # dropped verified citation previously shipped with zero failed checks.
    check_links_preserved,
]

# Link-loss regressions worth one targeted repair pass after humanization. The
# check detail carries each lost link's anchor and original sentence, so the
# repair can put it back where it was.
_FINAL_REPAIRABLE_LINK_CHECKS = ("links_preserved",)

# Factual-claim checks worth one targeted repair pass after humanization. Needs
# no brand_context: an unsupported price or invented anecdote is repairable in
# any content type.
_FINAL_REPAIRABLE_CLAIM_CHECKS = ("unsupported_claims",)

# Brand checks whose failure at the post-humanize stage is worth one targeted
# repair pass. Previously only presence/URL were routed, so a placement or depth
# regression introduced by humanization was logged and shipped.
_FINAL_REPAIRABLE_BRAND_CHECKS = (
    "brand_presence",
    "brand_url_accuracy",
    "brand_placement_policy",
    "brand_integration_depth",
)

# Focus-keyphrase checks worth one targeted repair pass after humanization, for
# the same reason the brand ones are: humanization is a free-form rewrite that
# can drop or dilute the exact phrase, and there is no repair loop after this
# node, so a regression detected here would otherwise just be logged and
# shipped. Unlike the brand set these need no brand_context to be repairable.
_FINAL_REPAIRABLE_KEYWORD_CHECKS = (
    "keyword_presence",
    "keyword_density",
    "focus_keyphrase_in_introduction",
    "title_subject_alignment",
)


def measured_density_report(final_content: dict, spec: RequirementsSpec) -> Optional[dict]:
    """The density report for this article, or None when no keyword applies.

    Exposed so downstream nodes (on-page scoring, persistence) report the same
    deterministically measured number the gate enforced, instead of the
    LLM-self-reported `keyphrase_density` field that nothing verified.
    """
    keyword = (spec.get("target_keyword") or "").strip()
    if not keyword:
        return None
    return dict(
        analyze_keyword_density(
            text=_combined_text(final_content),
            keyphrase=keyword,
            content_type=spec.get("content_type") or "",
            extra_text="\n".join(
                str(final_content.get(field) or "")
                for field in ("title", "meta_title", "meta_description")
            ),
        )
    )


def apply_density_report(final_content: dict, spec: RequirementsSpec) -> dict:
    """Return `final_content` with the measured density written onto it.

    `keyphrase_density` already existed on every generated-content schema as a
    model-populated float; this overwrites that guess with the measured value so
    persistence and the UI agree with the gate.
    """
    report = measured_density_report(final_content, spec)
    if report is None:
        return final_content
    return {
        **final_content,
        "keyphrase_density": report["density"],
        "keyword_density_report": report,
    }


def restore_links_for_spec(final_content: dict, spec: RequirementsSpec, *, stage: str) -> dict:
    """``final_content`` with every re-anchorable lost protected link put back in place."""
    inventory = spec.get("link_inventory") or []
    if not inventory or not final_content:
        return final_content
    restored_content, restored, missing = restore_lost_links(final_content, inventory)
    if restored or missing:
        logger.info(
            "%s: link restoration restored=%s still_missing=%s",
            stage,
            [r.get("url") for r in restored],
            [r.get("url") for r in missing],
        )
    return restored_content


def run_checks(
    final_content: dict,
    spec: RequirementsSpec,
    searched_results: list[dict],
) -> tuple[list[ValidationCheckResult], list[ValidationCheckResult]]:
    """Returns (failed_blocking, warnings)."""
    results = [fn(final_content, spec) for fn in CHECK_REGISTRY]
    results.append(
        check_facts_and_external_links_integration(final_content, spec, searched_results)
    )
    failed_blocking = [r for r in results if not r["passed"] and r["severity"] == "blocking"]
    warnings = [r for r in results if not r["passed"] and r["severity"] == "warning"]
    return failed_blocking, warnings


async def validate_content(state: REXT) -> dict:
    """Deterministic pre-humanize gate. Runs before humanize_content ever fires."""
    content_state = state.get("content") or {}
    final_content = content_state.get("final_content") or {}
    outline = content_state.get("outline") or {}
    content_type = content_state.get("content_type", "")
    generation_meta = content_state.get("generation_meta") or {}
    searched_results = generation_meta.get("searched_results") or []
    review = content_state.get("review") or {}

    # The keyword resolved from state wins over whatever the outline carries:
    # generate_outline pins them to the same value, but resolving here as well
    # means a run whose outline predates pinning is still graded against the
    # user's own query rather than a model-invented substitute.
    spec = build_requirements_spec(
        outline,
        content_type,
        resolve_focus_keyword(state),
        content_state.get("selected_topic") or "",
        generation_meta=generation_meta,
    )
    # A protected link that is no longer linked but whose anchor text (or the
    # sentence that replaced its sentence) is still there is put back in place
    # deterministically — no model call is needed to re-wrap an anchor.
    final_content = restore_links_for_spec(final_content, spec, stage="validate_content")
    final_content = apply_density_report(final_content, spec)
    failed_blocking, warnings = run_checks(final_content, spec, searched_results)
    passed = not failed_blocking

    # Word count is owned by humanization, which already rewrites the whole
    # article with an explicit expand/trim instruction. A failure it owns is
    # recorded, but never routes to the repair model on its own: repair is a
    # minimal-edit pass, and asking it to add or cut hundreds of words is both
    # the wrong tool and a reliable way to break checks that already passed.
    repairable = [c for c in failed_blocking if c["name"] not in HUMANIZATION_OWNED_CHECKS]
    deferred = [c for c in failed_blocking if c["name"] in HUMANIZATION_OWNED_CHECKS]
    repair_required = bool(repairable)

    repair_attempts = review.get("repair_attempts", 0)
    gave_up = repair_required and repair_attempts >= MAX_REPAIR_ATTEMPTS
    run_id = (review.get("validation") or {}).get("validation_run_id") or str(uuid.uuid4())

    validation_result: ContentValidation = {
        "passed": passed,
        "repair_required": repair_required,
        "gave_up": gave_up,
        "failed_checks": failed_blocking,
        "deferred_checks": deferred,
        "warnings": warnings,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "stage": "pre_repair",
        "validation_run_id": run_id,
    }

    logger.info(
        "validate_content: content_type=%s passed=%s repair_required=%s gave_up=%s failed=%s "
        "deferred_to_humanize=%s repair_attempts=%s run_id=%s",
        content_type,
        passed,
        repair_required,
        gave_up,
        [c["name"] for c in repairable],
        [c["name"] for c in deferred],
        repair_attempts,
        run_id,
    )

    return {
        "content": {
            **content_state,
            "final_content": final_content,
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
    generation_meta = content_state.get("generation_meta") or {}

    spec = build_requirements_spec(
        outline,
        content_type,
        resolve_focus_keyword(state),
        content_state.get("selected_topic") or "",
        generation_meta=generation_meta,
    )
    # Last chance to hold the content-level on-page SEO invariants: this is the
    # final node that can mutate final_content before review and persistence.
    # Everything it fixes (the user-selected title, a missing or keyphrase-less
    # meta description, a keyphrase-less introduction) is deterministic, so it
    # runs BEFORE the checks — the report then describes what actually ships.
    final_content = enforce_onpage_seo(
        final_content,
        selected_title=spec.get("selected_title") or "",
        focus_keyphrase=spec.get("target_keyword") or "",
        stage="final_validate_content",
    )
    # Humanization can reword H2/H3 headings; repair them with the headings-only
    # pass before measuring. No model call when the headings already comply,
    # and never raises.
    final_content = await enforce_subheadings_for_spec(
        final_content, spec, stage="final_validate_content"
    )
    final_content = restore_links_for_spec(final_content, spec, stage="final_validate_content")
    final_content = apply_density_report(final_content, spec)
    checks = [fn(final_content, spec) for fn in FINAL_VALIDATE_CHECKS]

    # Brand and focus-keyphrase regressions are repaired in ONE pass rather than
    # two sequential model calls: they are both "humanization rewrote something
    # that had to survive", and fixing them separately risks the second pass
    # undoing the first.
    failed_brand_checks = [
        c for c in checks if c["name"] in _FINAL_REPAIRABLE_BRAND_CHECKS and not c["passed"]
    ]
    if not spec.get("brand_context"):
        failed_brand_checks = []
    failed_keyword_checks = [
        c for c in checks if c["name"] in _FINAL_REPAIRABLE_KEYWORD_CHECKS and not c["passed"]
    ]
    failed_claim_checks = [
        c for c in checks if c["name"] in _FINAL_REPAIRABLE_CLAIM_CHECKS and not c["passed"]
    ]
    failed_link_checks = [
        c for c in checks if c["name"] in _FINAL_REPAIRABLE_LINK_CHECKS and not c["passed"]
    ]
    repairable = (
        failed_brand_checks + failed_keyword_checks + failed_claim_checks + failed_link_checks
    )
    if repairable:
        repaired = await run_targeted_repair(
            final_content=dict(final_content),
            content_type=content_type,
            failed_checks=repairable,
            brand_context=spec.get("brand_context"),
            searched_results=generation_meta.get("searched_results") or [],
            focus_keyword=spec.get("target_keyword") or "",
            selected_title=spec.get("selected_title") or "",
            article_stage="post-humanization (tone finalized — preserve it)",
            protected=merge_link_inventory(
                spec.get("link_inventory"),
                protected_links(final_content, spec, generation_meta.get("searched_results") or []),
            ),
        )
        if repaired is not None:
            repaired = apply_density_report(repaired, spec)
            recheck = [fn(repaired, spec) for fn in FINAL_VALIDATE_CHECKS]
            # Only accept the repair when it did not make things worse overall.
            # A post-humanize repair has no loop behind it to catch a regression,
            # so a pass that fixes density while breaking the word-count band
            # must not be allowed to stand.
            # "Not worse" means no previously passing check now fails — a pure
            # failure COUNT would accept trading a density failure for a
            # word-count failure.
            failed_before = {c["name"] for c in checks if not c["passed"]}
            failed_after = {c["name"] for c in recheck if not c["passed"]}
            if failed_after <= failed_before:
                final_content = repaired
                checks = recheck
                logger.info(
                    "final_validate_content: auto-repaired %s",
                    [c["name"] for c in repairable],
                )
            else:
                logger.warning(
                    "final_validate_content: repair of %s regressed other checks — discarded.",
                    [c["name"] for c in repairable],
                )

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
        "validation_run_id": (review.get("validation") or {}).get("validation_run_id")
        or str(uuid.uuid4()),
    }

    logger.info(
        "final_validate_content: content_type=%s passed=%s failed=%s",
        content_type,
        passed,
        [c["name"] for c in failed_blocking],
    )

    return {
        "content": {
            **content_state,
            "final_content": final_content,
            "review": {**review, "final_validation": result},
        }
    }

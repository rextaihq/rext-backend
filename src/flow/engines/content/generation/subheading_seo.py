"""H2/H3 subheading SEO rules: keyphrase distribution and heading length.

The single source of truth for what a compliant set of subheadings looks like,
shared by the generation prompt, the content schema, validation and repair —
for all 34 content types, because every one of them reaches the same
``body_markdown`` (``blocks_to_body_markdown`` renders each structured block as
``## heading``, and the writer adds ``###`` subsections inside a block).

Two rules, both measured on the H2 and H3 headings of ``body_markdown``:

1. **Keyphrase in subheadings** — mirrors Yoast's "Keyphrase in subheadings"
   assessment. A heading *reflects* the focus keyphrase when it contains MORE
   THAN HALF of the keyphrase's content words (function words such as "for",
   "the", "to" ignored), in any order. Yoast is green when 30%-75% of H2/H3
   subheadings reflect it (a lone subheading that reflects it is also green).
   Below 30% is the reported defect; above 75% is keyword stuffing, so the rule
   is enforced in both directions.

   Because matching is by content words rather than the exact phrase, a long
   keyphrase ("best crm software for small business teams") is satisfied by a
   natural heading carrying its core words ("Choosing CRM Software for Small
   Teams"), so nothing ever needs the full phrase forced into a heading. When a
   keyphrase is so long that even its minimum matching words cannot fit inside
   the H2 limit, the rule is reported as not applicable instead of failed.

   Explicit synonyms are accepted where a caller supplies them (see
   ``RequirementsSpec.keyphrase_synonyms``) — Yoast Premium credits synonyms
   entered in its synonyms field the same way.

2. **Heading length** — H2/H3 headings must be neither stubs ("Pricing",
   "FAQs") nor paragraph-length. Question headings get a longer ceiling because
   a real "People Also Ask" question is reader-first and naturally longer.

Repair is layered and fail-safe:

* an LLM rewrites ONLY the offending heading lines (never prose) — the cheapest,
  least destructive edit that can preserve meaning, which a deterministic
  rewrite cannot;
* every proposed rewrite is validated deterministically (length, no brand name
  introduced, no "Keyphrase: ..." prefix/suffix insertion, no keyphrase
  repetition, meaning overlap with the original) and applied greedily only if
  it makes no measured rule worse — including keyphrase density;
* over-long headings can additionally be shortened deterministically at a
  clause boundary; short headings and missing keyphrases are never "fixed" by
  padding or appending words, because that is exactly the artificial insertion
  this module exists to avoid;
* any exception returns the content unchanged.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from typing import Awaitable, Callable, Iterable, Optional, Sequence

from pydantic import BaseModel, Field

from src.flow.engines.content.generation.keyword_density import (
    analyze_keyword_density,
    tokenize_words,
)
from src.flow.engines.content.generation.seo_title_rules import contains_keyphrase

logger = logging.getLogger(__name__)

# ── rules ────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class HeadingLengthRule:
    min_chars: int
    max_chars: int
    min_words: int
    max_words: int


# H2: a section title. 20 characters / 3 words is the smallest that still says
# what the section is about ("Pricing" and "How It Works" do not); 70 characters
# is where a heading starts wrapping to a second line on desktop.
H2_LENGTH_RULE = HeadingLengthRule(min_chars=20, max_chars=70, min_words=3, max_words=12)
# H3: a subsection under an already-specific H2, so it may be shorter.
H3_LENGTH_RULE = HeadingLengthRule(min_chars=12, max_chars=70, min_words=2, max_words=12)
# Question headings (FAQ, "People Also Ask" style) are allowed to run longer —
# shortening a real search question to fit 70 characters makes it worse.
QUESTION_MAX_CHARS = 90
QUESTION_MAX_WORDS = 16

# Content types whose H3s are legitimately a bare term: a glossary entry is the
# term itself ("CRM", "Churn Rate"), and forcing it to 12 characters would
# rename the entry. Their H2 rule is unchanged.
_TERM_H3_CONTENT_TYPES = frozenset({"glossary"})
_TERM_H3_LENGTH_RULE = HeadingLengthRule(min_chars=2, max_chars=70, min_words=1, max_words=12)

# Yoast "Keyphrase in subheadings" boundaries (inclusive), as integer ratios so
# ceil/floor are exact: 30% and 75%.
_KEYPHRASE_MIN_NUM, _KEYPHRASE_MIN_DEN = 3, 10
_KEYPHRASE_MAX_NUM, _KEYPHRASE_MAX_DEN = 3, 4

# English function words ignored when matching a keyphrase to a heading — the
# same idea as Yoast's function-word list: "for" and "the" are not what makes a
# heading about "crm software for startups".
FUNCTION_WORDS = frozenset(
    """
    a about above after again against all am an and any are as at be because been
    before being below between both but by can could did do does doing down during
    each few for from further had has have having he her here hers him his how i if
    in into is it its itself just me more most my no nor not now of off on once only
    or other our ours out over own same she should so some such than that the their
    theirs them then there these they this those through to too under until up very
    was we were what when where which while who whom why will with would you your
    yours vs versus
    """.split()
)

# ── heading extraction ───────────────────────────────────────────────────────

_HEADING_LINE_RE = re.compile(r"^(#{2,3})[ \t]+(.+?)[ \t]*#*[ \t]*$")
_FENCE_RE = re.compile(r"^\s*(```|~~~)")
_MD_LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_MD_EMPHASIS_RE = re.compile(r"[*_`~]+")
_WHITESPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class Subheading:
    level: int  # 2 or 3
    text: str  # reader-visible text, markdown stripped
    raw: str  # heading text exactly as written after the hashes
    line_index: int  # index into body_markdown.splitlines()


def clean_heading_text(raw: str) -> str:
    text = _MD_LINK_RE.sub(r"\1", raw or "")
    text = _MD_EMPHASIS_RE.sub("", text)
    return _WHITESPACE_RE.sub(" ", text).strip()


def extract_subheadings(markdown: Optional[str]) -> list[Subheading]:
    """H2 and H3 headings in document order, ignoring fenced code blocks."""
    headings: list[Subheading] = []
    in_fence = False
    for index, line in enumerate((markdown or "").splitlines()):
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        match = _HEADING_LINE_RE.match(line)
        if not match:
            continue
        text = clean_heading_text(match.group(2))
        if not text:
            continue
        headings.append(
            Subheading(
                level=len(match.group(1)),
                text=text,
                raw=match.group(2),
                line_index=index,
            )
        )
    return headings


# ── keyphrase matching ───────────────────────────────────────────────────────


def _tokens(text: str) -> list[str]:
    # Same tokenizer the density check uses, so a heading and the body agree on
    # what counts as a keyphrase word.
    return tokenize_words(text)


def keyphrase_content_words(keyphrase: str) -> list[str]:
    """The words of ``keyphrase`` that carry meaning, de-duplicated, in order.

    Falls back to every word when the keyphrase is made only of function words
    ("how to"), so such a keyphrase is still matchable.
    """
    words = _tokens(keyphrase)
    content = [w for w in words if w not in FUNCTION_WORDS] or words
    return list(dict.fromkeys(content))


def _required_matches(word_count: int) -> int:
    """More than half, i.e. Yoast's ``percentWordMatches > 50``."""
    return word_count // 2 + 1


def phrase_reflected_in_heading(heading: str, phrase: str) -> bool:
    words = keyphrase_content_words(phrase)
    if not words:
        return False
    heading_words = set(_tokens(heading))
    matched = sum(1 for w in words if w in heading_words)
    return matched >= _required_matches(len(words))


def heading_reflects_keyphrase(heading: str, keyphrase: str, synonyms: Iterable[str] = ()) -> bool:
    """Whether ``heading`` reflects the keyphrase or one of its synonyms."""
    if phrase_reflected_in_heading(heading, keyphrase):
        return True
    return any(s and phrase_reflected_in_heading(heading, s) for s in synonyms)


def keyphrase_fits_in_heading(keyphrase: str) -> bool:
    """Whether a heading can reflect the keyphrase inside the H2 length limit.

    Uses the SHORTEST words that would satisfy the match, so this only returns
    False for keyphrases that genuinely cannot fit — not for merely long ones.
    """
    words = keyphrase_content_words(keyphrase)
    if not words:
        return False
    needed = _required_matches(len(words))
    shortest = sorted(words, key=len)[:needed]
    return (
        needed <= H2_LENGTH_RULE.max_words and len(" ".join(shortest)) <= H2_LENGTH_RULE.max_chars
    )


def keyphrase_heading_bounds(total: int) -> tuple[int, int]:
    """(minimum, maximum) number of H2/H3 headings that should reflect the keyphrase."""
    if total <= 0:
        return 0, 0
    if total == 1:
        return 1, 1
    minimum = -(-_KEYPHRASE_MIN_NUM * total // _KEYPHRASE_MIN_DEN)  # ceil
    maximum = _KEYPHRASE_MAX_NUM * total // _KEYPHRASE_MAX_DEN  # floor
    return minimum, max(maximum, minimum)


def analyze_subheading_keyphrase(
    headings: Sequence[Subheading],
    keyphrase: str,
    synonyms: Iterable[str] = (),
) -> dict:
    """Keyphrase distribution across H2/H3 headings, Yoast-style.

    ``status`` is "ok", "too_low", "too_high" or "not_applicable" (no keyphrase,
    no subheadings, or a keyphrase that cannot fit a heading).
    """
    synonyms = [s for s in synonyms if s and s.strip()]
    total = len(headings)
    base = {"total": total, "matching": 0, "matching_indexes": [], "min": 0, "max": 0}
    if not (keyphrase or "").strip():
        return {**base, "status": "not_applicable", "reason": "no_keyphrase"}
    if total == 0:
        return {**base, "status": "not_applicable", "reason": "no_subheadings"}
    if not keyphrase_fits_in_heading(keyphrase):
        return {**base, "status": "not_applicable", "reason": "keyphrase_too_long_for_heading"}

    matching_indexes = [
        i for i, h in enumerate(headings) if heading_reflects_keyphrase(h.text, keyphrase, synonyms)
    ]
    minimum, maximum = keyphrase_heading_bounds(total)
    matching = len(matching_indexes)
    status = "too_low" if matching < minimum else "too_high" if matching > maximum else "ok"
    return {
        "total": total,
        "matching": matching,
        "matching_indexes": matching_indexes,
        "min": minimum,
        "max": maximum,
        "status": status,
        "reason": "",
    }


# ── heading length ───────────────────────────────────────────────────────────


def _normalize_type(content_type: str) -> str:
    try:
        from src.flow.model.structure.outlines import normalize_content_type

        return normalize_content_type(content_type or "")
    except Exception:
        return (content_type or "").strip().lower()


def heading_length_rule(level: int, text: str = "", content_type: str = "") -> HeadingLengthRule:
    if level == 3 and _normalize_type(content_type) in _TERM_H3_CONTENT_TYPES:
        rule = _TERM_H3_LENGTH_RULE
    else:
        rule = H2_LENGTH_RULE if level == 2 else H3_LENGTH_RULE
    if text.rstrip().endswith("?"):
        rule = HeadingLengthRule(
            min_chars=rule.min_chars,
            max_chars=max(rule.max_chars, QUESTION_MAX_CHARS),
            min_words=rule.min_words,
            max_words=max(rule.max_words, QUESTION_MAX_WORDS),
        )
    return rule


def heading_length_issue(level: int, text: str, content_type: str = "") -> Optional[str]:
    """ "too_short", "too_long" or None."""
    rule = heading_length_rule(level, text, content_type)
    chars = len(text)
    words = len(text.split())
    if chars < rule.min_chars or words < rule.min_words:
        return "too_short"
    if chars > rule.max_chars or words > rule.max_words:
        return "too_long"
    return None


def heading_length_violations(headings: Sequence[Subheading], content_type: str = "") -> list[dict]:
    violations = []
    for index, heading in enumerate(headings):
        issue = heading_length_issue(heading.level, heading.text, content_type)
        if issue:
            rule = heading_length_rule(heading.level, heading.text, content_type)
            violations.append(
                {
                    "index": index,
                    "level": heading.level,
                    "text": heading.text,
                    "issue": issue,
                    "chars": len(heading.text),
                    "words": len(heading.text.split()),
                    "min_chars": rule.min_chars,
                    "max_chars": rule.max_chars,
                }
            )
    return violations


# ── prompt / schema guidance ─────────────────────────────────────────────────


def describe_heading_length_rules() -> str:
    return (
        f"H2 headings: {H2_LENGTH_RULE.min_chars}-{H2_LENGTH_RULE.max_chars} characters and "
        f"{H2_LENGTH_RULE.min_words}-{H2_LENGTH_RULE.max_words} words. "
        f"H3 headings: {H3_LENGTH_RULE.min_chars}-{H3_LENGTH_RULE.max_chars} characters and "
        f"{H3_LENGTH_RULE.min_words}-{H3_LENGTH_RULE.max_words} words. "
        f"Question headings may run to {QUESTION_MAX_CHARS} characters. "
        "Vary heading lengths naturally within those ranges — never make them all the same length, "
        "and never use a one- or two-word stub such as 'Pricing', 'Overview' or 'FAQs'."
    )


def build_subheading_prompt_instruction(keyphrase: str, synonyms: Iterable[str] = ()) -> str:
    """Up-front H2/H3 instruction, generated from the same rules validation enforces."""
    keyphrase = (keyphrase or "").strip()
    lines = ["\nSUBHEADINGS (H2/H3) - SEO RULES:", f"- Length: {describe_heading_length_rules()}"]
    if keyphrase:
        core = keyphrase_content_words(keyphrase)
        needed = _required_matches(len(core)) if core else 0
        lines.append(
            f'- Reflect the focus keyphrase "{keyphrase}" in roughly 30-75% of all H2/H3 headings '
            "(aim for about half; never every heading). A heading reflects it when it naturally uses "
            f"at least {needed} of its core words ({', '.join(core)}), in any natural word order."
        )
        synonyms = [s.strip() for s in synonyms if s and s.strip()]
        if synonyms:
            lines.append(f"- These synonyms count too: {', '.join(synonyms)}.")
        if len(core) > 3 or len(keyphrase) > 35:
            lines.append(
                "- The keyphrase is long: do not repeat the full phrase in headings. Use its core words "
                "in a heading that reads naturally."
            )
        lines.append(
            "- Put it only in headings whose section is genuinely about it. Never bolt it on "
            "('Keyphrase: ...', '... - Keyphrase', '... for Keyphrase'), never repeat it within one "
            "heading, and never put a brand name into a heading to make room."
        )
    lines.append(
        "- Keep every heading reader-first: it must describe exactly what its section covers."
    )
    return "\n".join(lines) + "\n"


# ── validation results ───────────────────────────────────────────────────────


def subheading_report(
    body_markdown: str,
    keyphrase: str,
    content_type: str = "",
    synonyms: Iterable[str] = (),
) -> dict:
    headings = extract_subheadings(body_markdown)
    return {
        "headings": headings,
        "keyphrase": analyze_subheading_keyphrase(headings, keyphrase, synonyms),
        "length_violations": heading_length_violations(headings, content_type),
    }


def describe_keyphrase_issue(analysis: dict, keyphrase: str) -> str:
    total, matching = analysis["total"], analysis["matching"]
    core = ", ".join(keyphrase_content_words(keyphrase))
    if analysis["status"] == "too_low":
        return (
            f"Only {matching} of {total} H2/H3 subheadings reflect the focus keyphrase {keyphrase!r} "
            f"(need {analysis['min']}-{analysis['max']}). Rework {analysis['min'] - matching} more "
            f"heading(s) whose sections are genuinely about it to naturally use its core words ({core}). "
            "Edit headings only; do not bolt the keyphrase on as a prefix or suffix."
        )
    return (
        f"{matching} of {total} H2/H3 subheadings reflect the focus keyphrase {keyphrase!r} "
        f"(allowed {analysis['min']}-{analysis['max']}) — that reads as keyword stuffing. Rephrase "
        f"{matching - analysis['max']} of them to describe their section without it."
    )


def describe_length_issue(violations: Sequence[dict]) -> str:
    parts = []
    for v in violations[:6]:
        parts.append(
            f"H{v['level']} {v['text']!r} is {v['issue'].replace('_', ' ')} "
            f"({v['chars']} chars; allowed {v['min_chars']}-{v['max_chars']})"
        )
    more = f" (+{len(violations) - 6} more)" if len(violations) > 6 else ""
    return (
        "Subheading length out of range: "
        + "; ".join(parts)
        + more
        + ". Rewrite only those headings, preserving their meaning."
    )


# ── repair ───────────────────────────────────────────────────────────────────


class HeadingRewrite(BaseModel):
    index: int = Field(description="The number of the heading being rewritten, from the list.")
    heading: str = Field(description="The new heading text only — no '#' markers.")


class HeadingRewritePlan(BaseModel):
    rewrites: list[HeadingRewrite] = Field(
        default_factory=list,
        description="Only the headings you changed. Omit headings that need no change.",
    )


RewriteFn = Callable[[dict], Awaitable[list[dict]]]

_HEADING_REWRITE_SYSTEM_PROMPT = """
You are an SEO editor fixing ONLY the H2/H3 subheadings of a finished article. You never touch body copy.

Rules:
- Rewrite only the headings listed under TASKS. Return nothing for any other heading.
- A rewritten heading must describe exactly what its section covers (see each section's excerpt). Keep its meaning and search intent.
- Respect the length rule given for each heading, and vary lengths naturally.
- When a task asks you to reflect the focus keyphrase, pick headings whose section is genuinely about it and weave its core words into natural wording (any natural order is fine). Never bolt it on as a prefix or suffix ("Keyphrase: ...", "... - Keyphrase"), never repeat it within one heading, and never produce an awkward keyword-stuffed heading.
- When a task asks you to reduce keyphrase use, rephrase those headings to describe their section without the keyphrase words.
- Never add a brand or product name that the original heading did not contain. Never invent facts, numbers or years.
- Question headings may stay questions. Keep the heading's language.
""".strip()


def _section_excerpts(
    body_markdown: str, headings: Sequence[Subheading], limit: int = 220
) -> list[str]:
    lines = body_markdown.splitlines()
    excerpts = []
    for position, heading in enumerate(headings):
        end = headings[position + 1].line_index if position + 1 < len(headings) else len(lines)
        text = " ".join(
            line.strip() for line in lines[heading.line_index + 1 : end] if line.strip()
        )
        excerpts.append(text[:limit])
    return excerpts


def _build_rewrite_request(
    body_markdown: str,
    headings: Sequence[Subheading],
    analysis: dict,
    length_violations: Sequence[dict],
    keyphrase: str,
    content_type: str,
    synonyms: Sequence[str],
) -> dict:
    excerpts = _section_excerpts(body_markdown, headings)
    flagged = {v["index"]: v for v in length_violations}
    listing = []
    for i, heading in enumerate(headings):
        rule = heading_length_rule(heading.level, heading.text, content_type)
        flags = []
        if i in flagged:
            flags.append(flagged[i]["issue"].upper())
        if i in analysis.get("matching_indexes", []):
            flags.append("REFLECTS_KEYPHRASE")
        listing.append(
            f"{i}. H{heading.level} [{len(heading.text)} chars; allowed "
            f"{rule.min_chars}-{rule.max_chars}] {' '.join(flags)}\n"
            f"   heading: {heading.text}\n   section excerpt: {excerpts[i]}"
        )

    tasks = []
    if length_violations:
        tasks.append(
            "Fix the length of every heading flagged TOO_SHORT or TOO_LONG, keeping its meaning."
        )
    if analysis.get("status") == "too_low":
        core = keyphrase_content_words(keyphrase)
        tasks.append(
            f"Make {analysis['min'] - analysis['matching']} more heading(s) (at most "
            f"{analysis['max'] - analysis['matching']}) reflect the focus keyphrase "
            f"{keyphrase!r} by naturally using at least "
            f"{_required_matches(len(core))} of its core words "
            f"({', '.join(core)}). Choose headings not flagged "
            "REFLECTS_KEYPHRASE whose sections are genuinely about it."
        )
    elif analysis.get("status") == "too_high":
        tasks.append(
            f"Rephrase {analysis['matching'] - analysis['max']} heading(s) flagged "
            "REFLECTS_KEYPHRASE so they no longer use the keyphrase words, keeping their meaning."
        )
    if synonyms:
        tasks.append(f"Accepted keyphrase synonyms: {', '.join(synonyms)}.")

    return {
        "system": _HEADING_REWRITE_SYSTEM_PROMPT,
        "human": (
            f"Content type: {content_type or 'article'}\n"
            f"Focus keyphrase: {keyphrase or '(none)'}\n\n"
            "TASKS:\n- " + "\n- ".join(tasks) + "\n\nHEADINGS:\n" + "\n".join(listing)
        ),
    }


async def _llm_rewrite(request: dict) -> list[dict]:
    from langchain_core.messages import HumanMessage, SystemMessage

    from src.flow.model.llm_manager import load_model

    model = load_model(max_tokens=2048, temperature=0.4).with_structured_output(HeadingRewritePlan)
    plan = await model.ainvoke(
        [SystemMessage(content=request["system"]), HumanMessage(content=request["human"])]
    )
    if isinstance(plan, HeadingRewritePlan):
        return [r.model_dump() for r in plan.rewrites]
    if isinstance(plan, dict):
        return list(plan.get("rewrites") or [])
    return []


def _escape(phrase: str) -> str:
    return r"\s+".join(re.escape(w) for w in phrase.split())


def _is_bolted_on(heading: str, keyphrase: str) -> bool:
    """A "Keyphrase: ..." / "... - Keyphrase" style insertion."""
    if not keyphrase.strip():
        return False
    kp = _escape(keyphrase.strip())
    prefix = re.compile(rf"^\s*{kp}\s*[:|–—-]\s+", re.IGNORECASE)
    suffix = re.compile(rf"\s(?:[:|–—-]|\()\s*{kp}\s*\)?\s*$", re.IGNORECASE)
    return bool(prefix.search(heading) or suffix.search(heading))


def _keyphrase_repeated(heading: str, keyphrase: str) -> bool:
    if not keyphrase.strip():
        return False
    return len(re.findall(rf"\b{_escape(keyphrase.strip())}\b", heading, re.IGNORECASE)) > 1


def _clean_candidate(text: str) -> str:
    text = (text or "").strip().splitlines()[0] if (text or "").strip() else ""
    text = re.sub(r"^#+\s*", "", text)
    text = clean_heading_text(text).strip(" \"'“”")
    return text.rstrip(".:;,")


def _meaning_preserved(original: str, candidate: str, keyphrase: str) -> bool:
    """The rewrite keeps at least one of the original's own content words.

    Keyphrase words are excluded from the overlap, so a rewrite cannot "keep
    its meaning" merely by sharing the words it was asked to add. Headings with
    one content word or fewer ("FAQs", "Pricing") are exempt: rewriting a stub
    necessarily introduces new words.
    """
    kp_words = set(keyphrase_content_words(keyphrase)) if keyphrase else set()
    own = {w for w in _tokens(original) if w not in FUNCTION_WORDS and w not in kp_words}
    if len(own) <= 1:
        return True
    return bool(own & set(_tokens(candidate)))


def validate_heading_rewrite(
    original: Subheading,
    candidate_text: str,
    *,
    keyphrase: str,
    content_type: str = "",
    brand_name: str = "",
) -> Optional[str]:
    """The cleaned rewrite when it is acceptable on its own, else None."""
    candidate = _clean_candidate(candidate_text)
    if not candidate or candidate == original.text:
        return None
    if heading_length_issue(original.level, candidate, content_type):
        return None
    if (
        brand_name
        and contains_keyphrase(candidate, brand_name)
        and not contains_keyphrase(original.text, brand_name)
    ):
        return None
    if _is_bolted_on(candidate, keyphrase) and not _is_bolted_on(original.text, keyphrase):
        return None
    if _keyphrase_repeated(candidate, keyphrase):
        return None
    if not _meaning_preserved(original.text, candidate, keyphrase):
        return None
    return candidate


_CLAUSE_SPLIT_RE = re.compile(r"\s*(?::|\s[–—-]|\s\||\()\s*")


def deterministic_shorten_heading(
    heading: Subheading, keyphrase: str = "", content_type: str = ""
) -> Optional[str]:
    """Shorten an over-long heading to its leading clause, when that clause stands alone.

    "Choosing CRM Software: What Small Teams Should Compare Before Signing a
    Contract" -> "Choosing CRM Software". Only removes words; never adds any.
    """
    if heading_length_issue(heading.level, heading.text, content_type) != "too_long":
        return None
    parts = [p.strip(" )") for p in _CLAUSE_SPLIT_RE.split(heading.text) if p.strip(" )")]
    if len(parts) < 2:
        return None
    candidate = parts[0]
    if heading_length_issue(heading.level, candidate, content_type):
        return None
    if (
        keyphrase
        and heading_reflects_keyphrase(heading.text, keyphrase)
        and not (heading_reflects_keyphrase(candidate, keyphrase))
    ):
        return None
    return candidate


def _replace_heading_lines(
    body_markdown: str, replacements: dict[int, tuple[Subheading, str]]
) -> str:
    lines = body_markdown.splitlines()
    for line_index, (heading, new_text) in replacements.items():
        lines[line_index] = f"{'#' * heading.level} {new_text}"
    rebuilt = "\n".join(lines)
    if body_markdown.endswith("\n"):
        rebuilt += "\n"
    return rebuilt


def _unmatched_sections(headings: Sequence[Subheading], expected_sections: Sequence[str]) -> int:
    """Expected outline labels no heading covers (>=60% of the label's content words).

    Guards the outline structure: a heading rewrite that stops matching the
    section label the outline approved is rejected even if it helps SEO.
    """
    if not expected_sections:
        return 0
    heading_sets = [set(_tokens(h.text)) for h in headings]
    missing = 0
    for label in expected_sections:
        words = {w for w in _tokens(label) if w not in FUNCTION_WORDS} or set(_tokens(label))
        if not words:
            continue
        if not any(len(words & hs) / len(words) >= 0.6 for hs in heading_sets):
            missing += 1
    return missing


def _score(
    body_markdown: str,
    introduction: str,
    keyphrase: str,
    content_type: str,
    synonyms: Sequence[str],
    extra_text: str,
    expected_sections: Sequence[str] = (),
) -> tuple[int, int, int, int]:
    """(length violations, keyphrase distance, density failure, unmatched outline sections)."""
    report = subheading_report(body_markdown, keyphrase, content_type, synonyms)
    analysis = report["keyphrase"]
    distance = 0
    if analysis["status"] == "too_low":
        distance = analysis["min"] - analysis["matching"]
    elif analysis["status"] == "too_high":
        distance = analysis["matching"] - analysis["max"]
    density_failure = 0
    if keyphrase:
        density = analyze_keyword_density(
            text=f"{introduction}\n\n{body_markdown}",
            keyphrase=keyphrase,
            content_type=content_type,
            extra_text=extra_text,
        )
        density_failure = 0 if density["status"] in ("ok", "not_applicable") else 1
    return (
        len(report["length_violations"]),
        distance,
        density_failure,
        _unmatched_sections(report["headings"], expected_sections),
    )


def _no_worse(new: tuple[int, ...], old: tuple[int, ...]) -> bool:
    return all(n <= o for n, o in zip(new, old)) and new != old


async def enforce_subheading_seo(
    final_content: dict,
    *,
    focus_keyphrase: str,
    content_type: str = "",
    synonyms: Sequence[str] = (),
    brand_name: str = "",
    expected_sections: Sequence[str] = (),
    stage: str = "",
    rewrite_fn: Optional[RewriteFn] = None,
    use_llm: bool = True,
    timeout_seconds: float = 60.0,
) -> dict:
    """Return ``final_content`` with H2/H3 subheadings repaired where possible.

    A compliant article is returned as-is with no model call. Otherwise the
    offending headings are rewritten (LLM) or shortened (deterministic), and a
    change is kept only when it makes no measured rule worse — heading length,
    keyphrase distribution, keyphrase density, or coverage of the outline's
    expected section labels. Never raises: any failure returns the content
    unchanged, so a heading problem can never break generation.
    """
    if not isinstance(final_content, dict) or not final_content:
        return final_content
    try:
        return await _enforce_subheading_seo(
            final_content,
            focus_keyphrase=(focus_keyphrase or "").strip(),
            content_type=content_type,
            synonyms=[s.strip() for s in synonyms if s and s.strip()],
            brand_name=(brand_name or "").strip(),
            expected_sections=[s for s in expected_sections if s and str(s).strip()],
            stage=stage or "unknown",
            rewrite_fn=rewrite_fn,
            use_llm=use_llm,
            timeout_seconds=timeout_seconds,
        )
    except Exception:
        logger.exception(
            "enforce_subheading_seo[%s]: heading repair failed; keeping headings unchanged.",
            stage or "unknown",
        )
        return final_content


async def _enforce_subheading_seo(
    final_content: dict,
    *,
    focus_keyphrase: str,
    content_type: str,
    synonyms: list[str],
    brand_name: str,
    expected_sections: list[str],
    stage: str,
    rewrite_fn: Optional[RewriteFn],
    use_llm: bool,
    timeout_seconds: float,
) -> dict:
    body = final_content.get("body_markdown") or ""
    if not body.strip():
        return final_content
    introduction = final_content.get("introduction") or ""
    extra_text = "\n".join(
        str(final_content.get(f) or "") for f in ("title", "meta_title", "meta_description")
    )

    report = subheading_report(body, focus_keyphrase, content_type, synonyms)
    headings: list[Subheading] = report["headings"]
    analysis = report["keyphrase"]
    violations = report["length_violations"]
    if not headings or (not violations and analysis["status"] in ("ok", "not_applicable")):
        return final_content

    candidates: list[tuple[int, str]] = []
    if use_llm:
        request = _build_rewrite_request(
            body, headings, analysis, violations, focus_keyphrase, content_type, synonyms
        )
        try:
            proposed = await asyncio.wait_for(
                (rewrite_fn or _llm_rewrite)(request), timeout=timeout_seconds
            )
        except Exception:
            logger.warning(
                "enforce_subheading_seo[%s]: heading rewrite call failed; using deterministic "
                "fallback only.",
                stage,
                exc_info=True,
            )
            proposed = []
        seen: set[int] = set()
        for item in proposed or []:
            try:
                index = int(item.get("index"))
            except (TypeError, ValueError, AttributeError):
                continue
            if index in seen or not 0 <= index < len(headings):
                continue
            accepted = validate_heading_rewrite(
                headings[index],
                str(item.get("heading") or ""),
                keyphrase=focus_keyphrase,
                content_type=content_type,
                brand_name=brand_name,
            )
            if accepted:
                seen.add(index)
                candidates.append((index, accepted))

    covered = {i for i, _ in candidates}
    for violation in violations:
        if violation["issue"] != "too_long" or violation["index"] in covered:
            continue
        shortened = deterministic_shorten_heading(
            headings[violation["index"]], focus_keyphrase, content_type
        )
        if shortened:
            candidates.append((violation["index"], shortened))

    current_body = body
    current_score = _score(
        body, introduction, focus_keyphrase, content_type, synonyms, extra_text, expected_sections
    )
    applied: dict[int, tuple[Subheading, str]] = {}
    for index, new_text in candidates:
        heading = headings[index]
        trial = {**applied, heading.line_index: (heading, new_text)}
        trial_body = _replace_heading_lines(body, trial)
        trial_score = _score(
            trial_body,
            introduction,
            focus_keyphrase,
            content_type,
            synonyms,
            extra_text,
            expected_sections,
        )
        if _no_worse(trial_score, current_score):
            applied, current_body, current_score = trial, trial_body, trial_score

    if not applied:
        logger.info(
            "enforce_subheading_seo[%s]: no acceptable heading rewrite (length_violations=%d, "
            "keyphrase_status=%s).",
            stage,
            len(violations),
            analysis["status"],
        )
        return final_content

    logger.info(
        "enforce_subheading_seo[%s]: rewrote %d heading(s): %s",
        stage,
        len(applied),
        [(h.text, new) for h, new in applied.values()],
    )
    return {**final_content, "body_markdown": current_body}

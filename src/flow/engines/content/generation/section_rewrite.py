"""The rewrite, one section at a time (rext-control#787).

Asked to rewrite a whole article "at about 1,500 words", the rewrite's model writes to a length
of its own: a draft that was right at 1,493 words came back at 2,019, and six wordings of the
length instruction, a hard rule first in its standing instructions and a word limit per section
all left that as it was. Asked to rewrite one section of 180 words, it comes back within a few
words of what it is told. So the article is split at its H2s, each part goes to the same model
with the same standing instructions and its own length, all at once, and the parts are put
back in their order. On the same draft: 1,431 and 1,466 words, in a third of the time.

Nothing here trusts the model with the article's shape:

* a part's H2 line is put back as it was drafted, whatever came back;
* a part that comes back with another H2 in it, empty, without a link or an image it had,
  with the brand named more or less often than it was (or parted from its link), or outside
  what it was asked for by more than the guard allows, is kept as it was drafted;
* links, the brand's place and the page's SEO fields are checked afterwards by the code that
  checked the whole-article rewrite (humanize_content).
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from typing import Any, Optional

from src.flow.engines.content.generation.keyword_density import (
    analyze_keyword_density,
    count_keyphrase_occurrences,
    resolve_density_policy,
    strip_markdown_noise,
    tokenize_words,
)
from src.flow.engines.content.generation.subheading_seo import extract_subheadings
from src.flow.engines.content.generation.validation import (
    _brand_occurrences,
    _keyword_appears,
    check_brand_url_accuracy,
)
from src.flow.engines.content.generation.word_count_utils import compute_word_target_band
from src.flow.model.runaway import ainvoke_watched

logger = logging.getLogger(__name__)

# What a part is asked for, as a share of the length wanted from it. The model comes back about
# an eighth over the middle of the range it is given (measured on staging drafts: told 90 to
# 110% of a section it returned 112 to 118%; told 78 to 92% it returned 96 to 98% in all), so
# the range is stated that much lower. The guard below is what holds; this is what makes it rare.
STATED_SHARE = 0.87
STATED_SPREAD = 0.07
# Asked to cut, it cuts less than it is told: a part asked for 82% of its words came back at
# 92%. A part that has to come down is told lower still.
STATED_SHARE_TO_CUT = 0.78
# A part back at more than this share of the length wanted from it, or less than the other, is
# kept as drafted: the first is how an article left its range, the second is lost substance.
MOST_SHARE = 1.2
LEAST_SHARE = 0.6
# Shorter than this, a part is left as it is: an image and its caption, a one-line lead-in.
MIN_WORDS_TO_REWRITE = 40
# A section longer than this is rewritten one H3 at a time when it has them: a list article's
# one long H2 (1,522 words on staging) was told its length and came back longer, as a whole
# article does.
LONG_SECTION_WORDS = 400
# Calls at once. A pillar page has twenty sections and more.
MAX_AT_ONCE = 8

INTRODUCTION = "introduction"
OPENING = "opening"
SECTION = "section"

_FENCE = re.compile(r"^\s*```[a-zA-Z]*\s*\n(.*)\n\s*```\s*$", re.DOTALL)
# Where a markdown link or an image embed points.
_TARGET = re.compile(r"\]\(\s*<?([^)\s>]+)")


def _targets(text: str) -> set[str]:
    return {target.rstrip("/") for target in _TARGET.findall(text or "")}


@dataclass(frozen=True)
class Part:
    """One part of the article as it is rewritten: the introduction, what the body opens with
    before its first H2, or an H2 with everything under it."""

    kind: str
    # The part's own heading line ("## …", or "### …" for one H3 of a long section); empty for
    # the two parts that have none.
    heading: str
    text: str

    @property
    def level(self) -> int:
        return len(self.heading) - len(self.heading.lstrip("#"))

    @property
    def title(self) -> str:
        return self.heading.lstrip("#").strip()


def words(text: str) -> int:
    return len((text or "").split())


def split_article(introduction: str, body_markdown: str) -> list[Part]:
    """The article's parts in order. H2s are found as the subheading parser finds them, so a
    line of a fenced example that looks like one starts no part."""
    parts: list[Part] = []
    if (introduction or "").strip():
        parts.append(Part(INTRODUCTION, "", introduction.strip()))
    lines = (body_markdown or "").splitlines()
    starts = [h.line_index for h in extract_subheadings(body_markdown or "") if h.level == 2]
    if not starts:
        if (body_markdown or "").strip():
            parts.append(Part(OPENING, "", body_markdown.strip()))
        return parts
    opening = "\n".join(lines[: starts[0]]).strip()
    if opening:
        parts.append(Part(OPENING, "", opening))
    for start, end in zip(starts, [*starts[1:], len(lines)], strict=True):
        parts.extend(_section_parts(lines[start:end]))
    return parts


def _section_parts(lines: list[str]) -> list[Part]:
    """One H2 with everything under it: one part, or, when it is long and has H3s, its lead-in
    and one part for each H3."""
    text = "\n".join(lines).strip()
    whole = Part(SECTION, lines[0].strip(), text)
    if words(text) <= LONG_SECTION_WORDS:
        return [whole]
    block = text.splitlines()
    starts = [h.line_index for h in extract_subheadings(text) if h.level == 3]
    if len(starts) < 2:
        return [whole]
    parts = [Part(SECTION, block[0].strip(), "\n".join(block[: starts[0]]).strip())]
    for start, end in zip(starts, [*starts[1:], len(block)], strict=True):
        parts.append(Part(SECTION, block[start].strip(), "\n".join(block[start:end]).strip()))
    return parts


def join_article(parts: list[Part]) -> tuple[str, str]:
    """(introduction, body_markdown) from the parts, in their order."""
    introduction = "\n\n".join(part.text for part in parts if part.kind == INTRODUCTION)
    body = "\n\n".join(part.text for part in parts if part.kind != INTRODUCTION)
    return introduction, body


def wanted_scale(total_words: int, word_target: int) -> float:
    """How the article's length should change through the rewrite, as a share of what it has.

    Inside the range it is checked against: none. Outside it, either way: to the target
    itself, since aiming at the range's edge, or halfway to it, ended a few words outside. No
    further than a quarter either way: a rewrite is not the place to write, or to cut, a third
    of an article.
    """
    if total_words <= 0 or not word_target:
        return 1.0
    low, high = compute_word_target_band(word_target)
    if low <= total_words <= high:
        return 1.0
    return min(1.25, max(0.75, word_target / total_words))


def stated_range(wanted: float, cutting: bool = False) -> tuple[int, int]:
    """The range a part is told, for the length wanted from it (see STATED_SHARE), lower when
    the part has to come down from what it has."""
    share = STATED_SHARE_TO_CUT if cutting else STATED_SHARE
    return (
        max(1, round(wanted * (share - STATED_SPREAD))),
        max(2, round(wanted * (share + STATED_SPREAD))),
    )


def _plain_text(answer: Any) -> str:
    content = getattr(answer, "content", answer)
    if isinstance(content, list):
        content = "".join(
            piece.get("text", "") if isinstance(piece, dict) else str(piece) for piece in content
        )
    text = str(content or "").strip()
    fenced = _FENCE.match(text)
    return fenced.group(1).strip() if fenced else text


def _mentions(text: str, name: str) -> int:
    """How often a reader sees the name in the text, as the article's brand checks count it."""
    return len(_brand_occurrences(text, name)) if name else 0


def _brand_linked(text: str, brand: dict[str, str]) -> bool:
    """Whether the brand's first mention in the text stands with the brand's link, as the
    article's check of it reads (brand_url_accuracy); true of a text that does not name it."""
    return bool(
        check_brand_url_accuracy({"body_markdown": text}, {"brand_context": brand})["passed"]
    )


def judge(
    part: Part,
    rewritten: str,
    wanted: float,
    *,
    brand: dict[str, str] | None = None,
    excluded: dict[str, str] | None = None,
) -> tuple[Optional[str], str]:
    """(the rewritten part as it goes into the article, "") or (None, why the part is kept as
    drafted).

    The part's own heading line is the drafted one whatever came back: a heading is the
    outline's, and the checks on headings ran before the rewrite. No heading of its level or
    above may have been added: that is a new section."""
    text = (rewritten or "").strip()
    if not text:
        return None, "came back empty"
    found = extract_subheadings(text)
    if part.kind == SECTION:
        level = part.level
        own = [h for h in found if h.level == level]
        if len(own) > 1 or any(h.level < level for h in found):
            return None, "a heading was added"
        lines = text.splitlines()
        if own:
            lines[own[0].line_index] = part.heading
            # Nothing may stand before a part's own heading.
            text = "\n".join(lines[own[0].line_index :]).strip()
        else:
            text = f"{part.heading}\n\n{text}"
    elif any(h.level == 2 for h in found):
        # The introduction and the opening have no H2: one that appeared is a new section.
        return None, "a heading was added"
    count, drafted = words(text), words(part.text)
    # Too long is longer than the guard allows and longer than the part was: a part that had
    # to come down and came back no longer than it was drafted does the length no harm, and
    # kept as drafted it would stand a third over what was wanted of it.
    if count > wanted * MOST_SHARE and count > drafted:
        return None, f"too long ({count} words for {round(wanted)} wanted)"
    if count < wanted * LEAST_SHARE:
        return None, f"too short ({count} words for {round(wanted)} wanted)"
    # A link or an image the part had and its rewrite has not: put back afterwards it would
    # land at the article's end, on a line of its own, and fail the check on woven-in links.
    if _targets(part.text) - _targets(text):
        return None, "a link or an image was lost"
    # The brand is named where the writer and its checks put it, as often as the user chose
    # (a Subtle article names it once): a mention added or dropped, or parted from its link,
    # is a rewrite that cannot be used.
    name = ((brand or {}).get("brand_name") or "").strip()
    if name:
        if _mentions(text, name) != _mentions(part.text, name):
            return None, "the brand's mentions changed"
        if (
            (brand or {}).get("brand_url")
            and _brand_linked(part.text, brand)
            and not _brand_linked(text, brand)
        ):
            return None, "the brand's mention lost its link"
    barred = ((excluded or {}).get("brand_name") or "").strip()
    if barred and _mentions(text, barred) > _mentions(part.text, barred):
        return None, "a brand the article leaves out was named"
    return text, ""


def accept(
    part: Part,
    rewritten: str,
    wanted: float,
    *,
    brand: dict[str, str] | None = None,
    excluded: dict[str, str] | None = None,
) -> Optional[str]:
    """The rewritten part as it goes into the article, or None to keep the part as drafted."""
    return judge(part, rewritten, wanted, brand=brand, excluded=excluded)[0]


def _uses(text: str, focus: str) -> tuple[int, int]:
    """(uses of the keyphrase in the part's text, uses in its heading lines)."""
    in_headings = sum(
        count_keyphrase_occurrences(line, focus)
        for line in text.splitlines()
        if line.lstrip().startswith("#")
    )
    return count_keyphrase_occurrences(text, focus) - in_headings, in_headings


def keyphrase_plan(
    parts: list[Part], focus_keyphrase: str, content_type: str, scale: float
) -> dict[int, int]:
    """How often each part's text is to use the keyphrase: as often as it does, moved by one
    in a part or two when the article's count would otherwise leave the range its length allows.

    That range goes with the article's length. A draft with exactly the least it needed is one
    short when the rewrite adds fifty words (a how-to on staging: three uses at 1,984 words,
    still three at 2,083, and the density check failed), so the plan is made for the length
    wanted, and keeps one above the least where the range has room.
    """
    focus = (focus_keyphrase or "").strip()
    if not focus or not parts:
        return {}
    report = analyze_keyword_density(
        text="\n\n".join(part.text for part in parts), keyphrase=focus, content_type=content_type
    )
    policy = resolve_density_policy(
        round(report["word_count"] * scale),
        content_type,
        len(tokenize_words(strip_markdown_noise(focus))) or 1,
    )
    least, most = policy["min_occurrences"], policy["max_occurrences"]
    current = report["occurrences"]
    wanted = min(max(current, min(least + 1, most)), most)
    plan = {index: _uses(part.text, focus)[0] for index, part in enumerate(parts)}
    rewritten = [i for i, part in enumerate(parts) if words(part.text) >= MIN_WORDS_TO_REWRITE]
    # One more in the longest parts, where a use reads least forced; one fewer in the parts
    # that have the most.
    for index in sorted(rewritten, key=lambda i: -words(parts[i].text))[: max(0, wanted - current)]:
        plan[index] += 1
    for index in sorted(rewritten, key=lambda i: -plan[i])[: max(0, current - wanted)]:
        if plan[index] > 0:
            plan[index] -= 1
    return plan


# Phrases one part is asked to bring in. More than this in one part reads forced.
MOST_NEW_PHRASES = 2


def secondary_plan(parts: list[Part], secondary_keywords: list[str] | None) -> dict[int, list[str]]:
    """Which part is asked to bring in each secondary keyword the draft does not have.

    Told the whole article's keywords ("each at least once"), the whole-article rewrite put in
    the ones the draft had missed. Each part is told only what it holds, so a missed one would
    stay missed: it is given to the section whose words are nearest to it (the most of the
    phrase's words already there; the longer section on a tie). One to a section before a
    second to any, and two at most: a section asked for two on a replay grew past its length
    and was kept as drafted, both phrases with it.
    """
    article = "\n\n".join(part.text for part in parts)
    missing = [
        keyword.strip()
        for keyword in secondary_keywords or []
        if isinstance(keyword, str) and keyword.strip() and not _keyword_appears(article, keyword)
    ]
    sections = [
        index
        for index, part in enumerate(parts)
        if part.kind == SECTION and words(part.text) >= MIN_WORDS_TO_REWRITE
    ]
    if not missing or not sections:
        return {}
    in_part = {i: set(tokenize_words(strip_markdown_noise(parts[i].text))) for i in sections}
    plan: dict[int, list[str]] = {}
    for keyword in missing:
        wanted = set(tokenize_words(strip_markdown_noise(keyword)))
        fewest = min(len(plan.get(i, [])) for i in sections)
        if fewest >= MOST_NEW_PHRASES:
            break
        free = [i for i in sections if len(plan.get(i, [])) == fewest]
        best = max(free, key=lambda i: (len(wanted & in_part[i]), words(parts[i].text), -i))
        plan.setdefault(best, []).append(keyword)
    return plan


def keyword_lines(
    text: str,
    focus_keyphrase: str,
    secondary_keywords: list[str] | None,
    wanted_uses: int | None = None,
    new_phrases: list[str] | None = None,
) -> str:
    """What a part is told about the keywords: the uses its text is to have (``wanted_uses``,
    from `keyphrase_plan`; the uses it has when none is given), the secondary keywords it
    holds, and the ones it is to bring in (``new_phrases``, from `secondary_plan`)."""
    lines = []
    focus = (focus_keyphrase or "").strip()
    if focus:
        # A heading's use is not the text's: counted together, a section whose heading holds
        # the phrase was given one more in its text ("keep it once" read as once in the prose).
        in_text, in_headings = _uses(text, focus)
        wanted = in_text if wanted_uses is None else wanted_uses
        heading_note = (
            " (its heading has the phrase too, and stays as it is; that use is not counted here)"
            if in_headings
            else ""
        )
        has = (
            f'- The exact phrase "{focus}" appears {in_text} time(s) in this part\'s text'
            if in_text
            else f'- The phrase "{focus}" is not in this part\'s text'
        ) + heading_note
        if wanted == in_text:
            lines.append(
                f"{has}. Keep it exactly {in_text} time(s) in the text, word for word: vary the "
                "sentences around it, never the phrase."
                if in_text
                else f"{has}. Do not add it."
            )
        elif wanted > in_text:
            lines.append(
                f"{has}. The article needs it once more: use it exactly {wanted} time(s) in the "
                "text, word for word, the new one in a sentence where it reads naturally."
            )
        else:
            lines.append(
                f"{has}. The article has it too often: use it exactly {wanted} time(s) in the "
                "text, and say the same thing in plain words where one is dropped."
            )
    lowered = text.lower()
    kept = [
        keyword.strip()
        for keyword in secondary_keywords or []
        if isinstance(keyword, str) and keyword.strip() and keyword.strip().lower() in lowered
    ]
    if kept:
        lines.append(f"- Keep each of these phrases as written, at least once: {', '.join(kept)}.")
    if new_phrases:
        quoted = ", ".join(f'"{phrase}"' for phrase in new_phrases)
        lines.append(
            f"- The article does not use {quoted} yet. Use "
            + ("it" if len(new_phrases) == 1 else "each")
            + " once in this part, word for word, in a sentence where it reads naturally."
        )
    return "\n".join(lines)


def brand_lines(
    text: str,
    *,
    brand_context: dict[str, str] | None,
    excluded_brand: dict[str, str] | None,
) -> str:
    """What a part is told about the brand. Where the mention belongs was settled by the writer
    and its checks; a part keeps the mentions it has and brings in none."""
    if excluded_brand and excluded_brand.get("brand_name"):
        return (
            f'- Do not name "{excluded_brand["brand_name"]}" or link to its site. If this part '
            "names it, rewrite that sentence without it. The article's other links stay."
        )
    name = ((brand_context or {}).get("brand_name") or "").strip()
    if not name:
        return ""
    uses = len(
        re.findall(r"(?<![0-9A-Za-z])" + re.escape(name) + r"(?![0-9A-Za-z])", text, re.IGNORECASE)
    )
    if not uses:
        return f'- This part does not name "{name}". Do not bring it in.'
    url = ((brand_context or {}).get("brand_url") or "").strip()
    link = f" Its link ({url}) stays on the brand's name." if url and url in text else ""
    return (
        f'- This part names "{name}" {uses} time(s). Keep each mention in the sentence it is in, '
        f"as a real benefit or use and never a bare name; add no other.{link}"
    )


async def rewrite_parts(
    parts: list[Part],
    *,
    model: Any,
    messages_for: Any,
    word_target: int,
    brand: dict[str, str] | None = None,
    excluded: dict[str, str] | None = None,
) -> tuple[list[Part], dict[str, int]]:
    """Every part rewritten at once, each kept as drafted when its rewrite cannot be used.

    ``messages_for(part, index, low, high)`` gives the model's messages for one part. Returns
    the parts in their order and the counts (parts, rewritten, kept as drafted, words before
    and after).
    """
    total = sum(words(part.text) for part in parts)
    scale = wanted_scale(total, word_target)
    gate = asyncio.Semaphore(MAX_AT_ONCE)

    async def one(index: int, part: Part) -> Part:
        count = words(part.text)
        if count < MIN_WORDS_TO_REWRITE:
            return part
        wanted = count * scale
        low, high = stated_range(wanted, cutting=scale < 1)
        try:
            async with gate:
                answer = await ainvoke_watched(
                    model, messages_for(part, index, low, high), stage="humanize"
                )
        except Exception as error:  # noqa: BLE001 - one part's failure keeps that part's draft
            logger.warning(
                "section rewrite: part %s failed (%s); kept as drafted",
                index + 1,
                type(error).__name__,
            )
            return part
        accepted, why = judge(part, _plain_text(answer), wanted, brand=brand, excluded=excluded)
        if accepted is None:
            logger.info("section rewrite: part %s kept as drafted: %s", index + 1, why)
            return part
        return Part(part.kind, part.heading, accepted)

    rewritten = list(await asyncio.gather(*(one(i, part) for i, part in enumerate(parts))))
    changed = sum(1 for before, after in zip(parts, rewritten, strict=True) if after is not before)
    return rewritten, {
        "parts": len(parts),
        "rewritten": changed,
        "kept": len(parts) - changed,
        "words_before": total,
        "words_after": sum(words(part.text) for part in rewritten),
    }

"""Inline-link bookkeeping shared by every stage that rewrites article prose.

Links are lost between generation and the final article in more than one place:
structured generation discards the prose the model wrote into `body_markdown`,
and repair and humanization are free-form rewrites that can drop an inline
link while "improving" a sentence. Each stage previously had its own partial
safety net (an internal-link auto-append in the Pydantic model, a brand-URL
check), and none covered a verified citation.

This module is the one text-level implementation of "which links does this
article carry, and put a lost one back where it was". It is deliberately
policy-free: WHICH links are worth protecting (approved internal links, verified
citations, the approved brand URL) is decided in validation.py next to the
checks that already own those rules, so an irrelevant or unverified link is
never preserved just because it existed.

Restoration is placement-preserving by design. A lost link is re-attached to
its original anchor text, or to the closest phrase in the sentence that
replaced its original sentence. It is never appended as a bare trailing line —
that is the exact shape the integration checks reject as bolted-on, which is
how the old auto-append fallback produced a second repair round by itself.
"""

from __future__ import annotations

import re
from typing import Iterable, Optional, TypedDict
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# Markdown inline link, not preceded by "!" (which makes it an image embed).
MD_LINK_RE = re.compile(r"(?<!!)\[([^\]]*)\]\((https?://[^)\s]+)\)")
_IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_INLINE_CODE_RE = re.compile(r"`[^`\n]*`")
_BARE_URL_RE = re.compile(r"https?://\S+")
_HEADING_LINE_RE = re.compile(r"^\s{0,3}#{1,6}\s.*$", re.MULTILINE)
_H2_H3_RE = re.compile(r"^\s{0,3}#{2,3}\s+(.+?)\s*#*\s*$", re.MULTILINE)
_SENTENCE_BOUNDARY_RE = re.compile(r"(?<=[.!?])\s+|\n+")
_WORD_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9'’-]*")

_TRACKING_PARAM_PREFIXES = ("utm_",)
_TRACKING_PARAMS = {"gclid", "fbclid", "mc_cid", "mc_eid", "ref"}

_EDGE_STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "of", "to", "in", "on", "for", "with", "at", "by",
    "from", "as", "is", "are", "was", "were", "be", "this", "that", "these", "those", "it",
    "its", "your", "our", "their", "you", "we", "they", "how", "what", "why", "when",
}  # fmt: skip

# Minimum share of the original sentence's words a candidate sentence must share
# before a lost link may be re-attached to it. Below this, the sentence is about
# something else and attaching the link there would misplace it.
_MIN_SENTENCE_SIMILARITY = 0.35
_MAX_FUZZY_ANCHOR_WORDS = 8

LINK_FIELDS = ("introduction", "body_markdown")


class LinkRecord(TypedDict, total=False):
    url: str
    anchor_text: str
    # The sentence the link sat in, with markdown links reduced to their anchor
    # text — both the placement reference for restoration and the context a
    # repair prompt needs to put a link back where it belonged.
    sentence: str
    # The H2/H3 the link sat under ("" for the introduction or pre-heading copy).
    section: str
    field: str
    # "internal" | "citation" | "brand" — assigned by the policy layer.
    kind: str


def normalize_url(url: str) -> str:
    """Comparison key for a URL: case-insensitive host, no fragment, no tracking params.

    Two spellings of the same page must not read as "the link was removed" — a
    trailing slash or a `#section` anchor is not a different source.
    """
    raw = (url or "").strip()
    if not raw:
        return ""
    try:
        parts = urlsplit(raw)
    except ValueError:
        return raw.rstrip("/").lower()
    query = urlencode(
        [
            (k, v)
            for k, v in parse_qsl(parts.query, keep_blank_values=True)
            if k.lower() not in _TRACKING_PARAMS
            and not k.lower().startswith(_TRACKING_PARAM_PREFIXES)
        ]
    )
    path = parts.path.rstrip("/")
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, query, ""))


def _plain(text: str) -> str:
    """Markdown links reduced to their anchor text, images removed."""
    return MD_LINK_RE.sub(r"\1", _IMAGE_RE.sub("", text or ""))


def _words(text: str) -> list[str]:
    return [w.lower() for w in _WORD_RE.findall(text or "")]


def _sentence_spans(text: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    start = 0
    for match in _SENTENCE_BOUNDARY_RE.finditer(text):
        if match.start() > start:
            spans.append((start, match.start()))
        start = match.end()
    if start < len(text):
        spans.append((start, len(text)))
    return spans


def _section_at(text: str, index: int) -> str:
    heading = ""
    for match in _H2_H3_RE.finditer(text):
        if match.start() > index:
            break
        heading = match.group(1).strip()
    return heading


def extract_links(text: str, field: str = "") -> list[LinkRecord]:
    """Every inline markdown link in ``text``, with its sentence and section."""
    records: list[LinkRecord] = []
    spans = _sentence_spans(text or "")
    for match in MD_LINK_RE.finditer(text or ""):
        sentence = ""
        for start, end in spans:
            if start <= match.start() < end:
                sentence = _plain(text[start:end]).strip()
                break
        records.append(
            LinkRecord(
                url=match.group(2),
                anchor_text=match.group(1).strip(),
                sentence=sentence,
                section=_section_at(text, match.start()),
                field=field,
            )
        )
    return records


def extract_content_links(content: dict, fields: Iterable[str] = LINK_FIELDS) -> list[LinkRecord]:
    records: list[LinkRecord] = []
    for field in fields:
        records.extend(extract_links(str((content or {}).get(field) or ""), field))
    return records


def present_urls(content: dict, fields: Iterable[str] = LINK_FIELDS) -> set[str]:
    """Normalized URLs linked anywhere in the given prose fields."""
    return {normalize_url(r["url"]) for r in extract_content_links(content, fields)}


def dedupe_records(records: Iterable[LinkRecord]) -> list[LinkRecord]:
    """One record per normalized URL, first occurrence wins (it carries the placement)."""
    seen: set[str] = set()
    out: list[LinkRecord] = []
    for record in records:
        key = normalize_url(record.get("url", ""))
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(record)
    return out


def _blocked_spans(text: str) -> list[tuple[int, int]]:
    """Regions a link may not be inserted into: existing links, images, code, headings, URLs."""
    spans: list[tuple[int, int]] = []
    for pattern in (MD_LINK_RE, _IMAGE_RE, _INLINE_CODE_RE, _HEADING_LINE_RE, _BARE_URL_RE):
        spans.extend((m.start(), m.end()) for m in pattern.finditer(text))
    return spans


def _is_free(spans: list[tuple[int, int]], start: int, end: int) -> bool:
    return all(end <= s or start >= e for s, e in spans)


def _phrase_pattern(words: list[str]) -> re.Pattern:
    joined = r"[\s\-–—,]+".join(re.escape(w) for w in words)
    return re.compile(rf"(?<![A-Za-z0-9]){joined}(?![A-Za-z0-9])", re.IGNORECASE)


def _find_free(text: str, pattern: re.Pattern, lo: int = 0, hi: Optional[int] = None):
    blocked = _blocked_spans(text)
    hi = len(text) if hi is None else hi
    for match in pattern.finditer(text, lo, hi):
        if _is_free(blocked, match.start(), match.end()):
            return match
    return None


def _similarity(a: str, b: str) -> float:
    wa, wb = set(_words(a)) - _EDGE_STOPWORDS, set(_words(b)) - _EDGE_STOPWORDS
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa)


def _trim_edges(words: list[str]) -> list[str]:
    while words and words[0].lower() in _EDGE_STOPWORDS:
        words = words[1:]
    while words and words[-1].lower() in _EDGE_STOPWORDS:
        words = words[:-1]
    return words


def _best_shared_phrase(reference: str, sentence: str) -> Optional[list[str]]:
    """Longest run of words (2..8, not stopword-edged) shared by both texts, in order."""
    ref = _WORD_RE.findall(reference or "")
    target = {w.lower() for w in _WORD_RE.findall(sentence or "")}
    best: Optional[list[str]] = None
    for size in range(min(_MAX_FUZZY_ANCHOR_WORDS, len(ref)), 1, -1):
        for i in range(len(ref) - size + 1):
            candidate = _trim_edges(ref[i : i + size])
            if len(candidate) < 2 or not all(w.lower() in target for w in candidate):
                continue
            if _phrase_pattern(candidate).search(sentence):
                if best is None or len(candidate) > len(best):
                    best = candidate
        if best is not None:
            return best
    return None


def _wrap(text: str, start: int, end: int, url: str) -> str:
    return f"{text[:start]}[{text[start:end]}]({url}){text[end:]}"


def _section_bounds(text: str, section: str) -> Optional[tuple[int, int]]:
    if not section:
        return None
    headings = list(_H2_H3_RE.finditer(text))
    for i, match in enumerate(headings):
        if match.group(1).strip().lower() == section.strip().lower():
            end = headings[i + 1].start() if i + 1 < len(headings) else len(text)
            return match.end(), end
    return None


def _restore_one(text: str, record: LinkRecord) -> Optional[str]:
    url = record.get("url") or ""
    anchor_words = _WORD_RE.findall(record.get("anchor_text") or "")
    bounds = _section_bounds(text, record.get("section") or "")

    # 1. The original anchor text survived — re-link it, preferring its old section.
    if anchor_words:
        pattern = _phrase_pattern(anchor_words)
        for lo, hi in ([bounds] if bounds else []) + [(0, len(text))]:
            match = _find_free(text, pattern, lo, hi)
            if match:
                return _wrap(text, match.start(), match.end(), url)

    # 2. The sentence was reworded — find the sentence that replaced it and link the
    #    phrase it shares with the old anchor (or, failing that, the old sentence).
    original = record.get("sentence") or ""
    if not original:
        return None
    blocked = _blocked_spans(text)
    best: Optional[tuple[float, int, int]] = None
    for start, end in _sentence_spans(text):
        if not _is_free(blocked, start, start + 1) and not _is_free(blocked, end - 1, end):
            continue
        score = _similarity(original, text[start:end])
        if bounds and bounds[0] <= start < bounds[1]:
            score += 0.05
        if score >= _MIN_SENTENCE_SIMILARITY and (best is None or score > best[0]):
            best = (score, start, end)
    if best is None:
        return None
    _, start, end = best
    sentence = text[start:end]
    for reference in (record.get("anchor_text") or "", original):
        phrase = _best_shared_phrase(reference, _plain(sentence))
        if not phrase:
            continue
        match = _find_free(text, _phrase_pattern(phrase), start, end)
        if match:
            return _wrap(text, match.start(), match.end(), url)
    return None


def restore_lost_links(
    content: dict,
    records: Iterable[LinkRecord],
    fields: Iterable[str] = LINK_FIELDS,
) -> tuple[dict, list[LinkRecord], list[LinkRecord]]:
    """Re-attach every record whose URL is no longer linked in ``content``.

    Returns ``(content, restored, still_missing)``. ``content`` is a new dict when
    anything changed; the input is never mutated. A record is only restored into
    the field it came from when that field still exists, otherwise into the
    first field that yields a placement.
    """
    fields = tuple(fields)
    updated = dict(content or {})
    present = present_urls(updated, fields)
    restored: list[LinkRecord] = []
    missing: list[LinkRecord] = []
    for record in dedupe_records(records):
        key = normalize_url(record.get("url", ""))
        if not key or key in present:
            continue
        preferred = [record.get("field")] if record.get("field") in fields else []
        placed = False
        for field in preferred + [f for f in fields if f not in preferred]:
            text = updated.get(field)
            if not isinstance(text, str) or not text.strip():
                continue
            new_text = _restore_one(text, record)
            if new_text is not None:
                updated[field] = new_text
                present.add(key)
                restored.append(record)
                placed = True
                break
        if not placed:
            missing.append(record)
    return updated, restored, missing


LINK_LIST_FIELDS = ("internal_links", "outbound_links")


def reconcile_link_lists(before: dict, after: dict) -> dict:
    """``after`` with its `internal_links`/`outbound_links` lists matched to its prose.

    A repair or humanization pass echoes these lists back and can shorten or pad
    them independently of the prose. Two failure modes follow:

    * an entry the pass dropped from the list vanishes from every check that reads
      the list, even though the link is still in the article;
    * an entry whose link is no longer in the prose makes the model validator
      (`enforce_internal_links_in_body`) append it as a bare trailing line — the
      shape check_internal_links_integration rejects as bolted-on, which forced a
      second repair round on its own.

    So the result is the union of both lists, limited to URLs actually linked in
    the prose. A protected link that was dropped is restored into the prose
    BEFORE this runs; an unprotected (unverified, irrelevant) one is allowed to go.
    """
    updated = dict(after or {})
    linked = present_urls(updated)
    for field in LINK_LIST_FIELDS:
        merged: dict[str, dict] = {}
        for entry in list((before or {}).get(field) or []) + list(updated.get(field) or []):
            if not isinstance(entry, dict):
                continue
            key = normalize_url(entry.get("url") or "")
            if not key or key not in linked:
                continue
            merged[key] = {**merged.get(key, {}), **{k: v for k, v in entry.items() if v}}
        if merged or updated.get(field):
            updated[field] = list(merged.values())
    return updated


def describe_link(record: LinkRecord, max_sentence_chars: int = 220) -> str:
    """One-line human description of a link and where it belonged, for repair prompts."""
    sentence = (record.get("sentence") or "").strip()
    if len(sentence) > max_sentence_chars:
        sentence = sentence[: max_sentence_chars - 1].rstrip() + "…"
    where = (
        f' under "{record["section"]}"'
        if record.get("section")
        else (" in the introduction" if record.get("field") == "introduction" else "")
    )
    line = f"[{record.get('anchor_text') or record.get('url')}]({record.get('url')}){where}"
    if sentence:
        line += f' — original sentence: "{sentence}"'
    return line

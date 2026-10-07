"""Deterministic SEO title rules — the single source of truth for what makes a
title valid, shared by topic generation, content generation and validation.

Two requirements are treated as hard, not advisory:

1. The title contains the EXACT focus keyphrase the user entered.
2. The title is 50-59 characters inclusive, or up to the keyphrase plus 20 characters
   for a long keyphrase, never over 75 (``title_max_chars``).

The LLM is instructed to satisfy both (see prompts + the SEOTopic schema), but
an instruction is not a guarantee, so everything here is deterministic and
runs after the model. Nothing in this module invents facts, numbers, dates,
brands or claims — a deterministic repair may only re-arrange the title's own
words, add the user's own keyphrase, or append a neutral, claim-free qualifier
from a fixed ladder.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Optional

TITLE_MIN_CHARS = 50
TITLE_MAX_CHARS = 59
# A long keyphrase (5-8 words, as SEO users type them) leaves 59 characters almost no room
# beside it, so its titles may run to the keyphrase plus this much, up to the ceiling. Search
# engines truncate a long title in their results; they don't reject it (G69, rext-control #585).
TITLE_ROOM_BESIDE_KEYPHRASE = 20
TITLE_MAX_CHARS_CEILING = 75

# Claim-free qualifiers used only to lift a too-short title into range. None of
# these assert a fact, a ranking, a date or a superlative, so appending one can
# never make a title untrue — which is the reason the list is fixed rather than
# model-generated.
_NEUTRAL_SUFFIXES: tuple[str, ...] = (
    ": A Complete Guide",
    ": What You Need to Know",
    ": A Practical Guide",
    ": Everything Explained",
    ": A Detailed Overview",
    ": A Step-by-Step Guide",
    ": Key Things to Know",
    " Explained in Plain English",
    ": A Complete Guide for Beginners",
)

# Neutral lead-ins, tried (empty first) only when a suffix alone cannot reach
# the minimum. Same rule as the suffixes: no facts, rankings or superlatives.
_NEUTRAL_PREFIXES: tuple[str, ...] = (
    "",
    "Understanding ",
    "A Closer Look at ",
    "A Practical Guide to ",
)

_WHITESPACE_RE = re.compile(r"\s+")
# Scripts written without spaces between words (Thai, Lao, Myanmar, Khmer, kana including the
# halfwidth forms, CJK ideographs and the iteration marks 々 〆 〇, with the supplementary
# ideographic planes 2 and 3): no space
# marks where their words begin and end, so a phrase's edge in one of them needs no space beside
# it, and a character of one beside a phrase is a boundary in itself.
_UNSPACED_SCRIPT_RE = re.compile(
    "[\u0e00-\u0eff\u1000-\u109f\u1780-\u17ff\u3005-\u3007\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff"
    "\uf900-\ufaff\uff66-\uff9f\U00020000-\U0003ffff]"
)
_SPACE_BESIDE_UNSPACED_RE = re.compile(
    rf"(?<={_UNSPACED_SCRIPT_RE.pattern}) | (?={_UNSPACED_SCRIPT_RE.pattern})"
)
_SURROUNDING_QUOTES = "\"'`“”‘’ "


def _nfc(text: Any) -> str:
    """One spelling per character: an accent typed as a separate mark (NFD) is the same
    letter as its precomposed form (NFC), and counts as one character."""
    return unicodedata.normalize("NFC", str(text or ""))


def _capitalized(word: str) -> str:
    """The word with a capital first letter, unless that capital would match differently: German
    ß is SS, and the Turkish dotless ı is I, which lowercases to a dotted i."""
    capital = word[:1].upper() + word[1:]
    return capital if _normalize_for_match(capital) == _normalize_for_match(word) else word


def normalize_title(title: Any) -> str:
    """Whitespace/quote (and NFC) normalization only — never changes meaning."""
    if not title:
        return ""
    text = _WHITESPACE_RE.sub(" ", _nfc(title).strip())
    return text.strip(_SURROUNDING_QUOTES).strip()


def _normalize_for_match(text: Any) -> str:
    """Lowercase, punctuation-flattened form used for keyphrase containment (G69b).

    Padded with spaces so a containment test is implicitly word-boundary
    aware: "seo agency" must not match inside "seo agencyx".
    """
    # Letters, marks and digits of every script are kept (an accented letter, Arabic, Cyrillic,
    # Devanagari's vowel signs); punctuation, symbols, separators and the underscore become spaces.
    # Lowercased, not casefolded: casefolding makes different words equal ("Maße" and "Masse").
    # A capital dotted İ lowercases to "i" plus a combining dot that no lowercase i carries, so
    # the dot goes: Turkish "İstanbul" is "istanbul" in lowercase. A capital Σ lowercases to the
    # final ς at a word's end, which a user types as σ: both are σ. The Armenian ligature և is
    # եւ, as its capital ԵՒ lowercases.
    # Lowercasing can leave a letter and its accent apart ("J̌" is "ǰ"): NFC again after it.
    lowered = _nfc(_nfc(text).lower()).replace("i\u0307", "i").replace("ς", "σ").replace("և", "եւ")
    kept: list[str] = []
    base_flattened = False
    for char in lowered:
        category = unicodedata.category(char)
        if category == "Cf" and char != "\u200b":
            # Invisible inside a word (a soft hyphen, a zero-width joiner): not a word break. The
            # zero-width space is one, and is flattened below.
            continue
        if category[0] == "M":
            # A mark goes with the character it sits on: an emoji's variation selector is not
            # kept once the emoji is flattened, or every emoji would match every other.
            if not base_flattened:
                kept.append(char)
            continue
        base_flattened = char == "_" or category[0] in "PSZC"
        kept.append(" " if base_flattened else char)
    # Beside a script written without spaces, a space (or the punctuation it replaced: "生成AI・
    # ツール") is no word break, so it goes in both the phrase and the text.
    spaced = " ".join("".join(kept).split())
    return f" {_SPACE_BESIDE_UNSPACED_RE.sub('', spaced)} "


def contains_keyphrase(text: Any, keyphrase: Any) -> bool:
    """True when ``text`` contains the exact keyphrase as a whole-word run.

    Tolerant of casing, punctuation and whitespace differences only — a
    reordered or partial keyphrase does NOT count, because the user's
    requirement is the exact phrase.
    """
    phrase = _normalize_for_match(keyphrase).strip()
    if not phrase:
        return False
    haystack = _normalize_for_match(text)  # padded with a space at each end
    start = haystack.find(phrase)
    while start != -1:
        end = start + len(phrase)
        if _at_boundary(phrase[0], haystack[start - 1]) and _at_boundary(phrase[-1], haystack[end]):
            return True
        start = haystack.find(phrase, start + 1)
    return False


def _at_boundary(edge: str, beside: str) -> bool:
    """Whether a phrase's edge character ends a word against the character beside it.

    Each edge is judged on its own, so a mixed phrase ("AIツール") still needs its Latin edge
    to end a word ("XAIツール" doesn't hold it). An edge in a script without spaces needs no
    space; neither does any edge beside such a character ("最佳seo工具" holds "seo").
    """
    return (
        beside == " "
        or bool(_UNSPACED_SCRIPT_RE.match(edge))
        or bool(_UNSPACED_SCRIPT_RE.match(beside))
    )


def title_max_chars(keyphrase: Any = "") -> int:
    """The longest a title for this keyphrase may be.

    TITLE_MAX_CHARS, or the keyphrase plus TITLE_ROOM_BESIDE_KEYPHRASE when that is more,
    never over TITLE_MAX_CHARS_CEILING. A short keyphrase keeps 59.
    """
    # Measured as keyphrase_fits_a_title measures it, so a keyword the gate lets through is
    # never given a smaller limit than the gate assumed.
    length = len(_normalize_for_match(keyphrase).strip()) if keyphrase else 0
    return min(TITLE_MAX_CHARS_CEILING, max(TITLE_MAX_CHARS, length + TITLE_ROOM_BESIDE_KEYPHRASE))


def keyphrase_fits_a_title(keyphrase: Any) -> bool:
    """False when the keyphrase alone is longer than any title may be.

    Every title must contain the keyphrase and stay within TITLE_MAX_CHARS_CEILING,
    so such a keyphrase can produce no title at all: the keyword gate does not
    charge for titles then, and the topic step ends the run without a model call.
    It is measured as contains_keyphrase matches it (case, quotes and other
    punctuation flattened), so a keyword some title could hold is never refused.
    """
    return len(_normalize_for_match(keyphrase).strip()) <= TITLE_MAX_CHARS_CEILING


def title_violations(title: Any, keyphrase: Any = "") -> list[str]:
    """Machine-readable reasons ``title`` is not publishable. Empty == valid."""
    cleaned = normalize_title(title)
    reasons: list[str] = []

    if not cleaned:
        return ["empty_title"]

    length = len(cleaned)
    if length < TITLE_MIN_CHARS:
        reasons.append(f"too_short:{length}")
    elif length > title_max_chars(keyphrase):
        reasons.append(f"too_long:{length}")

    if keyphrase and not contains_keyphrase(cleaned, keyphrase):
        reasons.append("missing_focus_keyphrase")

    return reasons


def title_is_valid(title: Any, keyphrase: Any = "") -> bool:
    return not title_violations(title, keyphrase)


_TRAILING_PUNCTUATION = " ,;:-–—"
# Words a trimmed title must not end on: a trim that stops just after one leaves the phrase
# hanging ("Innovations in AI content writing tools for agencies in", G69a). Not "is", "are",
# "this", "these" or "those": they can close a clause ("Who We Are", "Why You Need This"). "that"
# can too, so it dangles only when the trim cut more than a time ("Tools That [Save Time]", but
# "Needs That [Today]").
_DANGLING_END_WORDS = frozenset(
    {
        "a", "an", "the", "and", "or", "but", "nor", "&", "via", "per", "than", "vs", "versus",
        "your", "our", "their", "its", "my",
    }
)  # fmt: skip


def _verb_forms(verb: str) -> set[str]:
    """A regular verb's written forms ("rely": relies, relied, relying), for the table below."""
    past = f"{verb}d" if verb.endswith("e") else f"{verb}ed"
    # "care": caring, but "agree": agreeing.
    progressive = (
        f"{verb[:-1]}ing" if verb.endswith("e") and not verb.endswith("ee") else f"{verb}ing"
    )
    forms = {verb, f"{verb}s", past, progressive}
    if re.search(r"[^aeiou][aeiou][^aeiouwxy]$", verb):  # commit: committed, committing
        forms |= {f"{verb}{verb[-1]}ed", f"{verb}{verb[-1]}ing"}
    if verb.endswith("y") and verb[-2:-1] not in ("a", "e", "i", "o", "u"):
        forms |= {f"{verb[:-1]}ies", f"{verb[:-1]}ied"}
    if verb.endswith(("s", "sh", "ch", "x", "o")):  # go: goes
        forms.add(f"{verb}es")
    return forms


# A preposition left at the end once a trim cut its object dangles too ("for agencies in"), but
# not after a verb that needs it ("Businesses Depend On", "What to Look For"): each preposition,
# with the verbs it completes at a title's end. Verbs that are mostly nouns ("plan", "search",
# "work") are left out, so "Your Marketing Plan for" is still tidied.
_PREPOSITION_AFTER_VERB: dict[str, frozenset[str]] = {
    preposition: frozenset(form for verb in verbs for form in _verb_forms(verb))
    for preposition, verbs in {
        "on": ("rely", "depend", "count", "focus", "build", "built", "bet", "insist"),
        "for": ("look", "ask", "pay", "paid", "wait", "prepare", "apply", "use", "know", "known"),
        "about": ("care", "talk", "think", "thought", "worry", "know", "known", "learn", "hear", "heard"),
        "by": ("swear", "swore", "sworn", "stand", "stood", "live"),
        "with": ("deal", "dealt", "agree", "cope"),
        "in": ("believe", "invest", "specialize", "specialise", "sign", "log", "opt"),
        "of": ("make", "made", "consist", "approve"),
        "to": ("listen", "switch", "migrate", "stick", "commit", "subscribe", "turn", "talk", "reach", "go", "relate", "respond"),
        "at": ("look", "aim"),
        "as": ("know", "known", "serve"),
        "from": ("benefit", "choose"),
        "into": ("look", "dig", "dive", "tap"),
        "over": ("think", "thought", "argue", "fight"),
        "under": ("fall", "fell", "fallen"),
        "onto": ("hold", "held", "latch"),
        "without": ("live", "do", "go"),
        "through": ("go", "get", "walk", "talk", "think", "break"),
        "after": ("look", "take", "go"),
        "across": ("come", "run"),
        "around": ("look", "get", "work", "shop"),
        "against": ("go", "stand", "fight"),
        "beyond": ("go", "look"),
        "behind": ("stand", "fall", "leave"),
        "upon": ("rely", "depend", "call"),
        "before": (),
        "during": (),
        "between": (),
        "within": (),
        "among": (),
        "toward": (),
        "towards": (),
        "until": (),
        "despite": (),
    }.items()
}  # fmt: skip


# Words that follow a preposition without being its object ("Turns To Today", "Sign Up Now"),
# and the time phrases that do the same ("Catch Up On This Year").
_TIME_ADVERBS = frozenset(
    {"today", "now", "tonight", "tomorrow", "again", "instead", "first", "fast", "soon", "anyway"}
)
_TIME_PHRASE_STARTS = frozenset({"this", "next", "last", "every"})
_TIME_NOUNS = frozenset(
    {
        "year", "month", "week", "weekend", "season", "quarter", "time", "spring", "summer",
        "fall", "autumn", "winter",
    }
)  # fmt: skip
# Particles a verb takes before its preposition ("Catch Up On", "Fall Back On"). Not before "of"
# or "to", which make compound prepositions of them ("Out Of", "Up To 50%").
_PARTICLES = frozenset({"up", "out", "down", "back", "off", "away", "along", "ahead"})
# The verbs those particles make phrasal verbs of; a particle after anything else is part of a
# noun ("Round Up For Teams" lost its object).
_PHRASAL_VERBS = frozenset(
    form
    for verb in (
        "catch", "fall", "look", "sign", "keep", "cut", "set", "follow", "show", "end", "give",
        "come", "stand", "check", "reach", "figure", "find", "work", "carry", "go", "get", "turn",
        "line", "team", "build", "open", "sum", "log", "opt", "speak", "think", "start", "hold",
        "put", "take", "bring", "call", "pick", "run", "sort", "point", "back", "clean", "move",
    )
    for form in _verb_forms(verb)
)  # fmt: skip


def _bare(word: str) -> str:
    return word.lower().strip(_TRAILING_PUNCTUATION)


def _ends_dangling(words: list[str], kept: int) -> bool:
    """Whether the title cut to its first ``kept`` words (a trim's result) ends on a word left
    hanging."""
    last = _bare(words[kept - 1])
    if last in _DANGLING_END_WORDS:
        return True
    following = _bare(words[kept]) if kept < len(words) else ""
    # What the trim cut, all of it: only a time ("Today", "This Year") leaves a word whole;
    # "for Today and Tomorrow" was the preposition's object.
    removed = [word for word in (_bare(word) for word in words[kept:]) if word]
    only_time_cut = (
        not removed
        or (len(removed) == 1 and removed[0] in _TIME_ADVERBS)
        or (len(removed) == 2 and removed[0] in _TIME_PHRASE_STARTS and removed[1] in _TIME_NOUNS)
    )
    if last == "that":
        return not only_time_cut
    if last not in _PREPOSITION_AFTER_VERB:
        return False
    # A preposition that ended a clause, or stood before another one or an adverb of time, had
    # no object for the trim to cut ("Rely On: A Guide", "Fall Back On in 2026", "Turns To
    # Today"). One before a conjunction may share the object that follows it ("for and by
    # Industry Experts"), so a conjunction proves nothing.
    if (
        words[kept - 1][-1] in _TRAILING_PUNCTUATION
        or only_time_cut
        or following in _PREPOSITION_AFTER_VERB
    ):
        return False
    verb = _bare(words[kept - 2]) if kept > 1 else ""
    before_particle = _bare(words[kept - 3]) if kept > 2 else ""
    if verb in _PARTICLES and before_particle in _PHRASAL_VERBS and last not in ("of", "to"):
        return False
    return verb not in _PREPOSITION_AFTER_VERB[last]


def _trim_to_max(title: str, keyphrase: str, tidy_end: bool = True) -> str:
    """Drop trailing words until the title fits, never cutting the keyphrase; with
    ``tidy_end``, never stop on a dangling word either."""
    words = title.split()
    max_chars = title_max_chars(keyphrase)

    def first(count: int) -> str:
        return " ".join(words[:count]).rstrip(_TRAILING_PUNCTUATION)

    def can_cut_to(count: int) -> bool:
        # Never trim away the user's keyphrase to satisfy the length rule.
        return not keyphrase or contains_keyphrase(first(count), keyphrase)

    kept = len(words)
    while kept > 1 and len(first(kept)) > max_chars and can_cut_to(kept - 1):
        kept -= 1
    if tidy_end and kept < len(words):
        # A trim that stopped after "in", "for" or "the" drops it too; the minimum, if it is
        # missed now, is met by the claim-free padding.
        while kept > 1 and _ends_dangling(words, kept) and can_cut_to(kept - 1):
            kept -= 1
    return first(kept)


def _pad_to_min(title: str, max_chars: int = TITLE_MAX_CHARS) -> str:
    """Lift a too-short title into range with claim-free qualifiers.

    One suffix first; a very short title (~20 chars) cannot reach the minimum
    with a single suffix, so a neutral lead-in is then combined with one.
    """
    base = title.rstrip(" ,;:-–—")
    for prefix in _NEUTRAL_PREFIXES:
        for suffix in _NEUTRAL_SUFFIXES:
            candidate = f"{prefix}{base}{suffix}"
            if TITLE_MIN_CHARS <= len(candidate) <= max_chars:
                return candidate
    return title


def repair_title(title: Any, keyphrase: Any = "") -> Optional[str]:
    """Best-effort deterministic repair. Returns None when it cannot comply.

    Applied only as the last net, after the LLM repair pass has already been
    given a chance — see ``topic_generation._repair_invalid_titles``. Returning
    None is meaningful: the caller keeps the previous valid value rather than
    showing the user something that breaks the rule.
    """
    cleaned = normalize_title(title)
    keyphrase = normalize_title(keyphrase)

    if not cleaned and not keyphrase:
        return None

    # Missing keyphrase: lead with it, which is also the placement SEO wants.
    if keyphrase and not contains_keyphrase(cleaned, keyphrase):
        # Capitalized for display only; matching is case-insensitive, so the
        # title still contains the user's exact phrase.
        lead = " ".join(_capitalized(word) for word in keyphrase.split())
        cleaned = f"{lead}: {cleaned}" if cleaned else lead

    if len(cleaned) > title_max_chars(keyphrase):
        tidy = _trim_to_max(cleaned, keyphrase)
        if len(tidy) < TITLE_MIN_CHARS:
            tidy = _pad_to_min(tidy, title_max_chars(keyphrase))
        # The tidy ending, when it still makes a valid title; otherwise the plain trim, so a
        # title is never lost for the sake of its last word.
        cleaned = (
            tidy
            if title_is_valid(tidy, keyphrase)
            else _trim_to_max(cleaned, keyphrase, tidy_end=False)
        )

    if len(cleaned) < TITLE_MIN_CHARS:
        cleaned = _pad_to_min(cleaned, title_max_chars(keyphrase))

    return cleaned if title_is_valid(cleaned, keyphrase) else None


def keyphrase_title(keyphrase: Any) -> Optional[str]:
    """The keyphrase itself as a title, when no generated title survives (G69).

    Title-cased for display (matching is case-insensitive, so it still holds the exact
    phrase), and lifted to the minimum length with a claim-free qualifier as any repair is.
    None when even that breaks the rules (a keyphrase whose punctuation takes it over the
    limit, or one no qualifier lifts to the minimum): an invalid title is never offered.
    """
    keyphrase = normalize_title(keyphrase)
    if not keyphrase:
        return None
    title = " ".join(_capitalized(word) for word in keyphrase.split())
    return repair_title(title, keyphrase)


# NOTE: resolving WHICH keyphrase to enforce is not this module's job — that
# is ``focus_keyword.resolve_focus_keyword``, the single authority chain shared
# by outline, generation, repair and validation. This module only answers
# "given a keyphrase, is this title compliant, and can it be repaired".

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
from typing import Any, Iterable, Optional

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

# Short endings for a title left a few characters under the minimum once its filler word is
# gone ("...Benefits Of Standing Desks Today" is 48 without it). The same rule as the suffixes
# above: no facts, rankings or superlatives. After a title that already holds a colon only the
# ones without one are tried.
# The article types whose title may end ": A Guide" or " Explained": the ones that explain or
# guide. A landing page, a comparison or a list promises something else, and so does a title
# for a search that wants to buy or to find a site.
GUIDE_LIKE_CONTENT_TYPES = frozenset(
    {"article", "blog", "how-to-guide", "explainer", "tutorial", "pillar-content"}
)


def takes_a_guide_ending(content_type: Any, intent: Any) -> bool:
    """Whether a title for this article type and search intent may be lifted with a short
    ending that promises a guide or an explanation."""
    return (
        str(content_type or "").strip().lower() in GUIDE_LIKE_CONTENT_TYPES
        and str(intent or "").strip().lower() == "informational"
    )


_SHORT_NEUTRAL_SUFFIXES: tuple[str, ...] = (
    ": A Guide",
    " Explained",
    ": The Basics",
    ": An Overview",
    ": A Short Guide",
)

# Neutral lead-ins, tried (empty first) only when a suffix alone cannot reach
# the minimum. Same rule as the suffixes: no facts, rankings or superlatives.
_NEUTRAL_PREFIXES: tuple[str, ...] = (
    "",
    "Understanding ",
    "A Closer Look at ",
    "A Practical Guide to ",
)

# The same for the scripts with a range of their own, in the title's own language (G69c): no
# English is added to them. Lead-ins, then suffixes, tried as the English ones are.
_LOCAL_PADDING: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "zh-Hans": (
        ("", "了解", "一文读懂"),
        ("：概述", "：基本概念", "：定义、用途与选择要点", "：基本概念、常见用途与选择方法"),
    ),
    "zh-Hant": (
        ("", "了解", "一文讀懂"),
        ("：概述", "：基本概念", "：定義、用途與選擇要點", "：基本概念、常見用途與選擇方法"),
    ),
    # A title in Han characters alone, with no sign of its language: qualifiers whose every
    # character is written the same in simplified and traditional Chinese and in Japanese. The
    # longest lifts even a one-character keyphrase to the minimum, so the last-resort title
    # never fails for want of padding.
    "han": (
        ("",),
        (
            "：概要",
            "：基本概念",
            "：基本概念、用途、使用方法",
            "：基本概念、目的、用途、使用方法、重要性",
        ),
    ),
    "ja": (
        ("", "基礎から学ぶ"),
        ("：概要", "：基本ガイド", "：入門ガイド", "の基本：意味・使い方・選び方"),
    ),
    "ko": (
        ("", "한눈에 보는 "),
        (" | 개요", " | 기본 가이드", " | 입문 가이드", " | 의미, 활용법, 선택 기준"),
    ),
    "th": (
        ("", "ทำความรู้จัก"),
        (" | ภาพรวม", " | ความรู้พื้นฐาน", " | คู่มือเบื้องต้น", " | ความหมาย การใช้งาน และวิธีเลือก"),
    ),
}
# Characters written only in Traditional Chinese, only in Simplified Chinese, or only in
# Japanese (its own simplified forms), to tell which language a Han-only title is in. None is
# shared with another of the three; a title with no such character gets the neutral qualifiers.
_TRADITIONAL_ONLY = frozenset("們這與體學實點擇對說讀麼來將當從應發關會營銷產圖戲匯賣價處")
_SIMPLIFIED_ONLY = frozenset(
    "们这个为实选择导对开关时说读义么从还进电动应发现机种类语叶书车门马鱼鸟长东网软处务价优买卖"
    "荐营销产业热题视频图戏页评测词"
)
_JAPANESE_ONLY = frozenset("観気広歩楽図駅売発対総経済読続験検権県辺変転伝")

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
        flat = _flattened(char)
        base_flattened = flat == " "
        kept.append(flat)
    # Beside a script written without spaces, a space (or the punctuation it replaced: "生成AI・
    # ツール") is no word break, so it goes in both the phrase and the text.
    spaced = " ".join("".join(kept).split())
    return f" {_SPACE_BESIDE_UNSPACED_RE.sub('', spaced)} "


def _flattened(char: str) -> str:
    """A space for punctuation, a symbol, a separator, a control character or the underscore."""
    return " " if char == "_" or unicodedata.category(char)[0] in "PSZC" else char


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


# A title is measured by how wide it is on a results page, not by its code points (G69c,
# rext-control #610): a character of an East Asian wide script takes the room of two Latin
# letters, and a combining mark (Thai's vowel and tone marks) or an invisible format character
# none. For Latin text the width is the length, so the Latin rule is as it was.
_THAI_RE = re.compile("[\u0e00-\u0e7f]")
_KANA_RE = re.compile("[\u3040-\u30ff\uff66-\uff9f]")
_HANGUL_RE = re.compile("[\u1100-\u11ff\u3130-\u318f\uac00-\ud7af]")
# Each script family's range, inclusive, in width: (minimum, maximum, the ceiling a long
# keyphrase may take it to). About 600 pixels in search results hold 30 CJK characters, or 55
# Thai ones, and SEO guidance for those languages agrees (the research on rext-control #610).
_TITLE_RANGES: dict[str, tuple[int, int, int]] = {
    "narrow": (TITLE_MIN_CHARS, TITLE_MAX_CHARS, TITLE_MAX_CHARS_CEILING),
    "cjk": (40, 60, 64),
    "thai": (38, 55, 60),
}


def _is_wide(char: str) -> bool:
    return unicodedata.east_asian_width(char) in ("W", "F")


def title_width(text: Any) -> int:
    """How wide a title is, in Latin letters: 2 for a wide character, 0 for a mark or an
    invisible format character, 1 for anything else."""
    return sum(
        0 if unicodedata.category(char) in ("Mn", "Me", "Cf") else 2 if _is_wide(char) else 1
        for char in _nfc(text)
    )


def _title_family(text: Any) -> str:
    """ "cjk" when wide characters take a third of the text's letter width, "thai" when Thai
    letters are a third of its letters, else "narrow" (Latin, Cyrillic, Arabic and the like)."""
    letters = [char for char in _nfc(text) if unicodedata.category(char)[0] in "LN"]
    if not letters:
        return "narrow"
    wide = sum(2 for char in letters if _is_wide(char))
    if wide * 3 >= wide + sum(1 for char in letters if not _is_wide(char)):
        return "cjk"
    if sum(1 for char in letters if _THAI_RE.match(char)) * 3 >= len(letters):
        return "thai"
    return "narrow"


def title_range(title: Any = "", keyphrase: Any = "") -> tuple[int, int]:
    """The widths a title may have, inclusive: its script family's range, with room beside a
    long keyphrase up to the family's ceiling. Without a title, the keyphrase's family decides."""
    low, high, ceiling = _TITLE_RANGES[_title_family(title or keyphrase)]
    # Measured as keyphrase_fits_a_title measures it, so a keyword the gate lets through is
    # never given a smaller limit than the gate assumed.
    keyphrase_width = _matched_width(keyphrase) if keyphrase else 0
    return low, min(ceiling, max(high, keyphrase_width + TITLE_ROOM_BESIDE_KEYPHRASE))


def _matched_width(keyphrase: Any) -> int:
    """The keyphrase's width as matching reads it (punctuation flattened), but with the Armenian
    ligature և as the one character it takes in a title, not the two it is matched as."""
    return title_width(_normalize_for_match(keyphrase).strip()) - _nfc(keyphrase).count("և")


def title_length_terms(keyphrase: Any = "") -> tuple[int, int, str]:
    """The range a prompt states for this keyphrase's titles, in the characters a writer counts,
    and how to count them: a Chinese, Japanese or Korean title's range is half its width."""
    low, high = title_range("", keyphrase)
    family = _title_family(keyphrase)
    if family == "cjk":
        return (
            low // 2,
            high // 2,
            "Count each Chinese, Japanese or Korean character, and each full-width punctuation "
            "mark (such as ：、。), as one, and a Latin letter, digit, space or half-width "
            "punctuation mark as half of one.",
        )
    if family == "thai":
        return low, high, "Thai vowel and tone marks written above or below a letter don't count."
    cjk_low, cjk_high, _ = _TITLE_RANGES["cjk"]
    thai_low, thai_high, _ = _TITLE_RANGES["thai"]
    return (
        low,
        high,
        "Count spaces and punctuation as characters. A title written in Chinese, Japanese or "
        f"Korean is {cjk_low // 2}-{cjk_high // 2} of those characters instead (a Latin letter, "
        f"digit or space counting half), and one in Thai {thai_low}-{thai_high} characters.",
    )


def title_max_chars(keyphrase: Any = "") -> int:
    """The widest a title for this keyphrase may be (TITLE_MAX_CHARS for a short Latin one)."""
    return title_range("", keyphrase)[1]


def keyphrase_fits_a_title(keyphrase: Any) -> bool:
    """False when the keyphrase alone is wider than any title may be.

    Every title must contain the keyphrase and stay within its family's ceiling, so such a
    keyphrase can produce no title at all: the keyword gate does not charge for titles then,
    and the topic step ends the run without a model call. It is measured as contains_keyphrase
    matches it (case, quotes and other punctuation flattened), so a keyword some title could
    hold is never refused.
    """
    ceiling = _TITLE_RANGES[_title_family(keyphrase)][2]
    return _matched_width(keyphrase) <= ceiling


def title_violations(title: Any, keyphrase: Any = "") -> list[str]:
    """Machine-readable reasons ``title`` is not publishable. Empty == valid."""
    cleaned = normalize_title(title)
    reasons: list[str] = []

    if not cleaned:
        return ["empty_title"]

    width = title_width(cleaned)
    low, high = title_range(cleaned, keyphrase)
    if width < low:
        reasons.append(f"too_short:{width}")
    elif width > high:
        reasons.append(f"too_long:{width}")

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
        # A modal whose verb, or a conjunction whose clause, was cut ("What Marketing Can",
        # "Works Because"). Not "may", "will" or "though": a month, a noun, a clause's end.
        "can", "could", "would", "should", "might", "must", "shall", "because", "although",
        "unless", "whether", "if",
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
    {
        "today", "now", "tonight", "tomorrow", "again", "instead", "first", "fast", "soon",
        "anyway", "online", "offline", "here", "there", "everywhere", "anywhere", "locally",
        "globally", "worldwide", "abroad", "together", "alone", "quickly", "easily",
        "ultimately", "finally", "really", "actually", "too", "also", "ever", "yet", "already",
    }
)  # fmt: skip
_TIME_PHRASE_STARTS = frozenset({"this", "next", "last", "every"})
# Prepositions that take a time as their object, and the times that can be one.
_TIME_OBJECT_PREPOSITIONS = frozenset(
    {"for", "until", "till", "since", "by", "before", "after", "from", "during"}
)
_TIME_WORDS = frozenset({"today", "now", "tonight", "tomorrow", "soon"})
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
    # What the trim cut, all of it: only a time ("Today", "This Year") leaves a word whole;
    # "for Today and Tomorrow" was the preposition's object.
    removed = [word for word in (_bare(word) for word in words[kept:]) if word]
    only_time_cut = (
        not removed
        or (len(removed) == 1 and removed[0] in _TIME_ADVERBS)
        or (len(removed) == 2 and removed[0] in _TIME_PHRASE_STARTS and removed[1] in _TIME_NOUNS)
    )
    if last == "that":
        # "Needs That: Guide" ended a clause on it, as "Needs That Today" did.
        return not (only_time_cut or words[kept - 1][-1] in _TRAILING_PUNCTUATION)
    if last not in _PREPOSITION_AFTER_VERB:
        return False
    # A preposition that ended a clause, or stood before another one or an adverb of time, had
    # no object for the trim to cut ("Rely On: A Guide", "Fall Back On in 2026", "Turns To
    # Today"). One before a conjunction may share the object that follows it ("for and by
    # Industry Experts"), so a conjunction proves nothing.
    # "for", "until" or "since" take a time as their object ("Guide for [Today]"): a time cut
    # after one of them cut its object; after the others it didn't ("Turns To [Today]").
    time_was_object = last in _TIME_OBJECT_PREPOSITIONS and (
        (len(removed) == 1 and removed[0] in _TIME_WORDS)
        or (len(removed) == 2 and removed[0] in _TIME_PHRASE_STARTS)
    )
    # A preposition before another one is no proof it had no object: "in [under 10 Minutes]"
    # nests the second in the first's object. "Rely On in 2026" is kept by its verb.
    if words[kept - 1][-1] in _TRAILING_PUNCTUATION or (only_time_cut and not time_was_object):
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
    max_width = title_range(title, keyphrase)[1]

    def first(count: int) -> str:
        return " ".join(words[:count]).rstrip(_TRAILING_PUNCTUATION)

    def can_cut_to(count: int) -> bool:
        # Never trim away the user's keyphrase to satisfy the length rule.
        return not keyphrase or contains_keyphrase(first(count), keyphrase)

    kept = len(words)
    while kept > 1 and title_width(first(kept)) > max_width and can_cut_to(kept - 1):
        kept -= 1
    if tidy_end and kept < len(words):
        # A trim that stopped after "in", "for" or "the" drops it too; the minimum, if it is
        # missed now, is met by the claim-free padding.
        while kept > 1 and _ends_dangling(words, kept) and can_cut_to(kept - 1):
            kept -= 1
    return first(kept)


def _local_language(title: str) -> Optional[str]:
    """The language of a title in a script with a range of its own, for its qualifiers."""
    family = _title_family(title)
    if family == "thai":
        return "th"
    if family != "cjk":
        return None
    if _KANA_RE.search(title) or any(char in _JAPANESE_ONLY for char in title):
        return "ja"
    if _HANGUL_RE.search(title):
        return "ko"
    traditional = sum(char in _TRADITIONAL_ONLY for char in title)
    simplified = sum(char in _SIMPLIFIED_ONLY for char in title)
    if traditional > simplified:
        return "zh-Hant"
    return "zh-Hans" if simplified > traditional else "han"


# ── How a title ends (G65, rext-control #560) ──────────────────────────────────────────────
#
# No part of validity: a title the customer wrote or picked is never refused for how it ends.
# The title step asks these of what the model wrote, and sends a weak ending to the repair.

# Last words that would fit any title: what a model reaches the minimum length with
# ("...Best Practices Now", "...at Work Today", "...How Does It Work Easily?").
_FILLER_END_WORDS = frozenset(
    {"now", "today", "here", "easily", "effectively", "efficiently", "successfully"}
)
_FILLER_END_PHRASES = frozenset({("for", "you"), ("right", "now")})
# Words "for you" completes ("Which Plan Is Right for You", "Guides Made for You"): no filler
# after them, nor after a regular participle ("Designed for You", "Tailored for You").
_COMPLETED_BY_FOR_YOU = frozenset(
    {
        "right", "best", "good", "better", "enough", "work", "works", "working", "fit", "fits",
        "mean", "means", "matter", "matters", "made", "built", "written", "chosen", "meant",
        "done", "ready",
    }
)  # fmt: skip
# Prepositions that need an object, so a title that ends on one was cut short ("...Grow Over
# Time With"). Only those that are never an adverb or a particle: "Look Around", "Start Over"
# and "What Lies Beyond" end whole. A verb that takes the preposition may end on it ("What to
# Look For"), and a question asked with what, who, which or where strands one by nature ("Who
# Is This Guide For?").
_OBJECT_PREPOSITIONS = frozenset(
    {
        "with", "for", "of", "to", "at", "from", "by", "into", "onto", "upon", "as", "during",
        "between", "among", "toward", "towards", "until", "despite", "against", "in", "on",
        "about",
    }
)  # fmt: skip
_STRANDING_QUESTION_WORDS = frozenset({"what", "who", "whom", "which", "where"})
# Verbs that end a whole title on a preposition or a particle, besides the trim's table ("Tools
# Your Whole Team Can Work With", "Where Readers Sign In", "What Is Going On"). For titles
# nobody cut: the trim's table leaves out "work" and its like, which are nouns as often, so
# that "Your Team's Work With" is still tidied after a cut.
_ENDS_ON_ITS_PREPOSITION: dict[str, frozenset[str]] = {
    preposition: frozenset(form for verb in verbs for form in _verb_forms(verb))
    for preposition, verbs in {
        "with": ("work", "start", "begin", "began", "live", "go", "went", "come", "stay", "play", "partner", "compete", "comply", "experiment", "struggle", "connect"),
        "for": ("care", "hope", "watch", "stand", "stood", "qualify", "account", "budget", "save", "shop", "settle", "aim", "plan", "search", "work", "go", "fall", "opt", "vote"),
        "in": ("check", "plug", "join", "move", "cash", "tune", "fill", "step", "chip", "lock", "live", "work", "zoom", "dial", "weigh", "trade", "settle", "get", "come", "let"),
        "on": ("turn", "go", "going", "carry", "hold", "move", "log", "hang", "catch", "switch", "take", "try", "work", "save", "pass", "live", "sign", "come", "get"),
        "about": ("ask", "write", "read", "go", "bring", "come", "forget", "dream", "complain"),
        "to": ("look", "get", "come", "refer", "apply", "belong", "adapt", "aspire", "agree", "object", "amount", "contribute", "lead"),
        "from": ("learn", "start", "come", "hear", "heard", "borrow", "buy", "order", "work", "save", "stay"),
        "at": ("work", "arrive", "stay", "start", "excel", "stop", "laugh"),
        "of": ("think", "thought", "take", "took", "dream", "hear", "heard", "let", "beware"),
        "by": ("go", "come", "get", "pass", "drop", "abide"),
        "into": ("get", "turn", "run", "break", "grow", "buy", "fall", "move", "come", "go"),
        "against": ("protect", "guard", "compete", "decide"),
    }.items()
}  # fmt: skip
_SPACE_BEFORE_PUNCTUATION_RE = re.compile(r"\s+(?=[?!.,;:]+(?:\s|$))")
# Words a whole title doesn't end on ("...Examples to Enhance Your"): the trim's list without
# the modals, which close a clause in a title nobody cut ("Yes, You Can").
_UNFINISHED_END_WORDS = _DANGLING_END_WORDS - {
    "can", "could", "would", "should", "might", "must", "shall",
}  # fmt: skip
_WORD_EDGES = _TRAILING_PUNCTUATION + "?!.\"'“”‘’()"


def _plain_words(title: str) -> list[str]:
    """The title's words in lowercase without their punctuation; a mark that stands alone
    ("Today ?") is no word."""
    return [word for word in (raw.lower().strip(_WORD_EDGES) for raw in title.split()) if word]


def _closed_up(title: Any) -> str:
    """The normalized title with no space before a closing mark ("Today ?" is "Today?")."""
    return _SPACE_BEFORE_PUNCTUATION_RE.sub("", normalize_title(title))


def _balanced(title: str) -> bool:
    """Whether every bracket and quotation mark that opens also closes. A single closing mark
    is an apostrophe as often ("Beginner’s"), so only an opening one without its closing one
    counts against the title."""
    pairs = (("(", ")"), ("[", "]"), ("“", "”"))
    if not all(title.count(opening) == title.count(closing) for opening, closing in pairs):
        return False
    if title.count('"') % 2 or title.count("‘") > title.count("’"):
        return False
    opening_straight = len(re.findall(r"(?:^|\s)'(?=\S)", title))
    closing_straight = len(re.findall(r"(?<=\S)'(?=$|\s|[?!.,;:])", title))
    return opening_straight <= closing_straight


def _completes_for_you(word: str) -> bool:
    return word in _COMPLETED_BY_FOR_YOU or (len(word) > 4 and word.endswith("ed"))


def _preposition_left_hanging(title: str, words: list[str]) -> bool:
    """Whether the title's last word is a preposition whose object is missing."""
    last = words[-1]
    if last not in _OBJECT_PREPOSITIONS:
        return False
    # The clause the title ends in: "What Is X? Five Examples to Compare With" asks nothing
    # with its last words.
    clauses = [clause for clause in re.split(r"[:?!|—–]", title) if clause.strip()]
    clause = _plain_words(clauses[-1]) if clauses else words
    # ...and within it, the part after its last "and", "or" or "but": in "What It Is and How
    # Your Savings Grow With" the question word asks about the first half only.
    joins = [index for index, word in enumerate(clause) if word in ("and", "or", "but")]
    if _STRANDING_QUESTION_WORDS.intersection(clause[joins[-1] + 1 :] if joins else clause):
        return False
    before = words[-2]
    if before in ("and", "or"):  # a pair that shares its object elsewhere, or none
        return False
    if before in _PREPOSITION_AFTER_VERB.get(last, ()) or before in _ENDS_ON_ITS_PREPOSITION.get(
        last, ()
    ):
        return False
    phrasal = before in _PARTICLES and len(words) > 2 and words[-3] in _PHRASAL_VERBS
    return not (phrasal and last not in ("of", "to"))


def title_ending_problem(title: Any, keyphrase: Any = "") -> Optional[str]:
    """Why the title's ending is weak: "unfinished:your" for a word left hanging, "filler:now"
    for words that would fit any title. None for an ending that is fine, for one that is the
    keyphrase's own last words, and for a title of one word."""
    cleaned = _closed_up(title)
    words = _plain_words(cleaned)
    if len(words) < 2:
        return None
    # The keyphrase as the title matcher reads it: "start-today" ends "...You Can Start Today".
    own = _normalize_for_match(keyphrase).split()
    if own and _normalize_for_match(cleaned).split()[-len(own) :] == own:
        return None
    last = words[-1]
    if last in _UNFINISHED_END_WORDS or _preposition_left_hanging(cleaned, words):
        return f"unfinished:{last}"
    pair = (words[-2], last)
    if pair in _FILLER_END_PHRASES:
        if pair == ("for", "you") and len(words) > 2 and _completes_for_you(words[-3]):
            return None
        return f"filler:{' '.join(pair)}"
    return f"filler:{last}" if last in _FILLER_END_WORDS else None


def without_filler_ending(title: Any, keyphrase: Any = "", lift: bool = False) -> Optional[str]:
    """The title without its one filler word, when what is left is a valid title that ends
    well ("...Understanding Best Practices Now"). Left a few characters under the minimum, it
    is lifted with a short neutral ending where one fits ("...Standing Desks: A Guide"), with
    ``lift`` only: those endings promise a guide or an explanation, so the caller says whether
    the article is one. None when neither gives a title that stands: the ending then has to
    be written anew, which is the repair's work."""
    cleaned = _closed_up(title)
    problem = title_ending_problem(cleaned, keyphrase) or ""
    if not problem.startswith("filler:") or " " in problem:
        return None
    words = cleaned.split()
    asks = words[-1].rstrip("\"'”’)").endswith("?")
    shorter = " ".join(words[:-1]).rstrip(_TRAILING_PUNCTUATION) + ("?" if asks else "")
    # The word closed a bracket or a quotation that opened before it ("(Start Here)", "‘Why
    # They Matter Today’").
    if _ends_dangling(words, len(words) - 1) or not _balanced(shorter):
        return None
    candidates = [shorter]
    # A question keeps its mark at the end, as does a clause that closed on a mark of its own
    # ("...How Does It Work? Today"), and the other scripts have padding of their own.
    if lift and not asks and shorter[-1:] not in "?!." and not _local_language(shorter):
        known = shorter.lower()
        candidates += [
            f"{shorter}{suffix}"
            for suffix in _SHORT_NEUTRAL_SUFFIXES
            if not (suffix.startswith(":") and ":" in shorter)
            and suffix.strip(" :").split()[-1].lower()[:6] not in known
        ]
    for candidate in candidates:
        if title_is_valid(candidate, keyphrase) and not title_ending_problem(candidate, keyphrase):
            return candidate
    return None


def _pad_to_min(title: str, keyphrase: str = "") -> str:
    """Lift a too-short title into range with claim-free qualifiers.

    One suffix first; a very short title (~20 chars) cannot reach the minimum
    with a single suffix, so a neutral lead-in is then combined with one. A
    Chinese, Japanese, Korean or Thai title gets one qualifier in its own
    language, or none.
    """
    base = title.rstrip(" ,;:-–—：")
    low, high = title_range(title, keyphrase)
    language = _local_language(title)
    prefixes, suffixes = (
        _LOCAL_PADDING[language] if language else (_NEUTRAL_PREFIXES, _NEUTRAL_SUFFIXES)
    )
    for candidate in (f"{prefix}{base}{suffix}" for prefix in prefixes for suffix in suffixes):
        if low <= title_width(candidate) <= high:
            return candidate
    return title


# The keyphrase's case (G49, rext-control #463). Matching ignores case, so a title may write the
# user's "seo agency for small business" as "SEO Agency for Small Business": only the letters'
# case changes, never a word.

# Short words a Title Case title keeps in lowercase unless they open it.
_TITLE_CASE_SMALL_WORDS = frozenset(
    {
        "a", "an", "the", "and", "or", "but", "nor", "for", "of", "in", "on", "at", "to", "by",
        "with", "from", "into", "onto", "as", "vs", "via", "per", "than",
    }
)  # fmt: skip
# Acronyms SEO users type in lowercase; written in capitals in any title ("kpis" is "KPIs").
# Not "it" or "us", which are words too.
_ACRONYMS = frozenset(
    {
        "seo", "sem", "ppc", "ai", "crm", "erp", "saas", "b2b", "b2c", "d2c", "roi", "kpi", "api",
        "ui", "ux", "cms", "faq", "diy", "usa", "uk", "eu", "gdpr", "hipaa", "vpn", "sql", "css",
        "html", "php", "aws", "iot", "ar", "vr", "nft", "ctr", "cpc", "cpm", "cpa", "smb",
        "llc", "pdf", "url", "hr", "pr", "llm", "gpt", "ecom",
    }
)  # fmt: skip
_ACRONYM_SPELLINGS = {"saas": "SaaS", "ecom": "eCom"}
_WORD_EDGE_PUNCTUATION = "\"'`“”‘’()[]{}.,;:!?"
_SENTENCE_BREAKS = (":", "?", "!", ".", "|", "-", "–", "—")


def _same_length_case(word: str, cased: str) -> str:
    """``cased`` when it changes only the case of ``word``'s letters, else ``word``: "ß" upper is
    "SS", which would change a title's length."""
    return cased if len(cased) == len(word) and cased.lower() == word.lower() else word


def _acronym(word: str) -> Optional[str]:
    """The written form of an acronym the user typed in lowercase, or None."""
    low = word.lower()
    if low in _ACRONYMS:
        return _ACRONYM_SPELLINGS.get(low, low.upper())
    if low.endswith("s") and low[:-1] in _ACRONYMS and len(low) > 2:  # "kpis": KPIs
        return f"{_ACRONYM_SPELLINGS.get(low[:-1], low[:-1].upper())}s"
    return None


def _phrase_spans(title: str, keyphrase: str, ignore_case: bool) -> list[tuple[int, int]]:
    """Where the keyphrase is written in the title letter for letter, at the word boundaries
    contains_keyphrase accepts: "seo" in "最佳seo工具" is a word."""
    spans = []
    for match in re.finditer(re.escape(keyphrase), title, re.IGNORECASE if ignore_case else 0):
        start, end = match.span()
        before = title[start - 1] if start else " "
        after = title[end] if end < len(title) else " "
        if _at_boundary(keyphrase[0], _flattened(before)) and _at_boundary(
            keyphrase[-1], _flattened(after)
        ):
            spans.append((start, end))
    return spans


def _opens_at(title: str, start: int) -> bool:
    """Whether the word at ``start`` opens the title or a clause after a break (": ", " - ")."""
    before = title[:start].rstrip()
    return not before or before.endswith(_SENTENCE_BREAKS)


def _title_style(title: str, skip: tuple[int, int]) -> Optional[str]:
    """How the title's own words, outside the keyphrase, are cased: "title" or "sentence".

    None when no word decides it. Opening words, short words, acronyms and words with a capital
    inside ("YouTube") don't count.
    """
    votes = []
    for match in re.finditer(r"\S+", title):
        if skip[0] <= match.start() < skip[1]:
            continue
        word = match.group().strip(_WORD_EDGE_PUNCTUATION)
        if (
            not word[:1].isalpha()
            or word[:1].lower() == word[:1].upper()
            or _opens_at(title, match.start())
            or word.lower() in _TITLE_CASE_SMALL_WORDS
            or any(char.isupper() for char in word[1:])
        ):
            continue
        votes.append(word[:1].isupper())
    if not votes:
        return None
    # Names keep their capitals in a sentence-case title ("…work with Google, Microsoft and
    # Apple today"), while a Title Case title leaves almost nothing in lowercase: Title Case only
    # when its capitals outnumber its lowercase words more than three to one.
    capitals = sum(votes)
    return "title" if capitals > 3 * (len(votes) - capitals) else "sentence"


def keyphrase_spellings(titles: Iterable[Any], keyphrase: Any) -> dict[int, str]:
    """How the keyphrase's words are spelled, by position, where their case is not a matter of
    style.

    The user's own capitals come first ("London", "SEO"), then what the titles show: a capital
    inside a word ("SaaS", "iPhone"), or a capitalized word in the middle of a sentence-case
    title (a name). By position, so "it" and "IT" in one keyphrase keep their own spellings.
    """
    keyphrase = normalize_title(keyphrase)
    spellings: dict[int, str] = {}
    for title in titles:
        title = normalize_title(title)
        for start, end in _phrase_spans(title, keyphrase, ignore_case=True):
            style = _title_style(title, (start, end))
            for index, match in enumerate(re.finditer(r"\S+", title[start:end])):
                word = match.group()
                if any(char.isupper() for char in word[1:]) or (
                    style == "sentence"
                    and word[:1].isupper()
                    and not _opens_at(title, start + match.start())
                ):
                    spellings.setdefault(index, word)
    for index, word in enumerate(keyphrase.split(" ")):
        if word != word.lower():
            spellings[index] = word
    return spellings


def _cased_keyphrase(
    keyphrase: str, style: Optional[str], opens: bool, spellings: dict[int, str]
) -> str:
    words = []
    for index, word in enumerate(keyphrase.split(" ")):
        if index in spellings:
            words.append(_same_length_case(word, spellings[index]))
            continue
        # Each part of a joined word on its own: "seo-friendly" is "SEO-Friendly" in Title Case,
        # "seo's" is "SEO's"; nothing after an apostrophe is capitalized ("Don't").
        parts = re.split(r"(\W+)", word)
        for part_index in range(0, len(parts), 2):
            part = parts[part_index]
            acronym = _acronym(part)
            after_apostrophe = part_index > 0 and parts[part_index - 1] in ("'", "’")
            if acronym:
                parts[part_index] = _same_length_case(part, acronym)
            elif not after_apostrophe and (
                (index == 0 and part_index == 0 and opens)
                or (style == "title" and part.lower() not in _TITLE_CASE_SMALL_WORDS)
            ):
                parts[part_index] = _capitalized(part)
        words.append("".join(parts))
    return " ".join(words)


def display_keyphrase(keyphrase: Any) -> str:
    """The keyphrase in Title Case, as a title's opening words ("seo agency" is "SEO Agency")."""
    keyphrase = normalize_title(keyphrase)
    return _cased_keyphrase(keyphrase, "title", True, keyphrase_spellings([], keyphrase))


def recase_keyphrase(title: Any, keyphrase: Any, spellings: Optional[dict[int, str]] = None) -> str:
    """The title with the keyphrase written in the title's case, where it was copied as typed.

    "Find the Best seo agency for small business in 2026" becomes "Find the Best SEO Agency for
    Small Business in 2026"; in a sentence-case title only acronyms, names and an opening word
    change. A keyphrase the title already writes another way is left as written, and so is a
    title whose case can't be told.
    """
    title = normalize_title(title)
    keyphrase = normalize_title(keyphrase)
    if not keyphrase or keyphrase.lower() == keyphrase.upper():  # no letters with a case
        return title
    if spellings is None:
        spellings = keyphrase_spellings([title], keyphrase)
    for start, end in _phrase_spans(title, keyphrase, ignore_case=False):
        opens = _opens_at(title, start)
        style = _title_style(title, (start, end))
        if style is None and not opens:
            continue
        cased = _cased_keyphrase(keyphrase, style, opens, spellings)
        title = f"{title[:start]}{cased}{title[end:]}"
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
        lead = display_keyphrase(keyphrase)
        separator = "：" if _title_family(f"{lead}{cleaned}") == "cjk" else ": "
        cleaned = f"{lead}{separator}{cleaned}" if cleaned else lead

    low, high = title_range(cleaned, keyphrase)
    if title_width(cleaned) > high:
        tidy = _trim_to_max(cleaned, keyphrase)
        if title_width(tidy) < low:
            tidy = _pad_to_min(tidy, keyphrase)
        # The tidy ending, when it still makes a valid title; otherwise the plain trim, so a
        # title is never lost for the sake of its last word.
        cleaned = (
            tidy
            if title_is_valid(tidy, keyphrase)
            else _trim_to_max(cleaned, keyphrase, tidy_end=False)
        )

    if title_width(cleaned) < title_range(cleaned, keyphrase)[0]:
        cleaned = _pad_to_min(cleaned, keyphrase)

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
    return repair_title(display_keyphrase(keyphrase), keyphrase)


# NOTE: resolving WHICH keyphrase to enforce is not this module's job — that
# is ``focus_keyword.resolve_focus_keyword``, the single authority chain shared
# by outline, generation, repair and validation. This module only answers
# "given a keyphrase, is this title compliant, and can it be repaired".

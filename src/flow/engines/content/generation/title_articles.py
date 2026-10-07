"""
"a" or "an" by the sound of the next word, in an English title (G65).

The model now and then writes "How to Create a Effective Content Brief", and the checks on a
title's length and keyphrase pass it. This puts the article right: "an" before a vowel sound
("an effective", "an hour", "an SEO brief", "an 8-step plan"), "a" before a consonant sound
("a unique", "a one-page", "a URL").

A wrong change is worse than the slip it fixes, so it changes only what it's sure of, and leaves:
- a title that doesn't read as English, where "a" and "an" are other words (Spanish "viajar a
  Europa", German "Briefe an Kunden");
- a capital "A" inside a title, which may be a letter ("Point A", "Plan A", "Vitamin A"): only an
  article at the start of the title or of a clause, or a lowercase one, is changed;
- an acronym said either as letters or as a word ("REST", "FAQ"), a year-like number ("1800s"),
  and a next word that starts with neither a letter nor a digit;
- the user's own keyphrase (in `fix_title_articles`).
"""

import re
import unicodedata

from src.flow.engines.content.generation.seo_title_rules import contains_keyphrase
from src.flow.model.structure.topics import SEOTopics

# Words that mark a title as English, besides "a" and "an" themselves.
_ENGLISH = {
    "the", "to", "for", "how", "of", "and", "with", "your", "you", "in", "on", "is", "are",
    "what", "why", "when", "best", "guide", "tips", "ways", "from", "by", "that", "this", "it",
    "or", "vs", "can", "should", "will", "my", "our", "into", "without", "about", "more", "than",
    "using", "step", "steps", "complete", "ultimate", "beginners",
}  # fmt: skip
# Words of the other languages that write "a" or "an" as a word of their own, and are no English
# words: one of them means the title isn't English.
_OTHER = {
    "de", "del", "la", "el", "los", "las", "para", "por", "como", "cómo", "qué", "que", "con",
    "una", "y", "en", "al", "der", "und", "für", "mit", "ein", "eine", "einen", "zu", "im", "von",
    "bei", "auf", "zum", "zur", "les", "des", "du", "pour", "avec", "et", "une", "au", "aux",
    "sur", "dans", "à", "dos", "em", "uma", "um", "ao", "aos", "na", "nas", "nos", "às", "il",
    "di", "della", "delle", "degli", "gli", "het", "een", "voor", "och", "dla", "jak", "oraz",
    "się", "jest", "czy",
}  # fmt: skip
# Common English title words that other languages don't borrow ("SEO" and "marketing" they do):
# two of them make a title English when it has none of the function words above.
_ENGLISH_TITLE_WORDS = {
    "content", "strategy", "plan", "planning", "template", "templates", "checklist", "tools",
    "tool", "ideas", "examples", "business", "small", "teams", "team", "website", "growth",
    "customer", "customers", "free", "build", "create", "write", "writing", "make", "start",
    "choose", "improve", "rank", "search", "keyword", "keywords", "traffic", "page", "pages",
    "framework", "blueprint", "playbook", "explained", "review", "reviews", "benefits",
    "mistakes", "way", "effective", "simple", "easy", "new", "brief", "post", "posts",
}  # fmt: skip
# Words an article never comes before, so the "a" in front of them is a letter ("a to z").
_NOT_AFTER_AN_ARTICLE = {
    "to", "or", "and", "vs", "versus", "through", "&", "is", "isn't", "was", "are", "were", "has",
    "had", "does", "did", "will", "can", "of", "in", "on", "at", "as", "if", "into", "onto",
    "over", "a", "an",
}  # fmt: skip
# Before these, a capital letter starts a clause, so a capital "A" there is an article.
_CLAUSE_ENDS = (":", "?", "!", "-", "–", "—", "|")
# Vowel letters with a consonant sound: "a usage", "a European", "a one-page".
_YOU_SOUND = ("use", "usa", "usu", "uti", "ura", "ure", "uri", "uro", "ubiq", "ukr", "eu", "ewe")
# "uni" is "you-ni" in these ("a unique", "a unimodal") and "un-i" in the negations ("an
# unindexed", "an uninstall"); any other "uni" word is unsure, and left.
_UNI_YOU = (
    "unique", "unit", "union", "univers", "unicorn", "uniform", "unif", "unilat", "unidirect",
    "unimod", "unison", "unix", "unicode", "unicycl", "unisex",
)  # fmt: skip
_UN_I = (
    "unident", "unidea", "unimp", "unimag", "unindex", "unins", "uninf", "unint", "unini", "uninv",
    "uninh", "unissu", "uniron", "unimm", "unitem",
)  # fmt: skip
# More words whose "u" says "you": "a utensil", "a unanimous".
_U_YOU = ("unanim", "utens", "utop", "uter", "ukul", "ubiq")
# Silent h: "an hour", "an honest". Said either way by dialect ("an herb" in America): left.
_SILENT_H = ("hour", "honest", "honor", "honour", "heir")
_EITHER_H = ("herb", "homage", "historic", "humble")
# Letters whose names start with a vowel sound: "an X-ray", "an F grade" (but "a U-turn").
_VOWEL_SOUND_NAMES = set("AEFHILMNORSX")
# An acronym starting with one of these consonants is "an" only when it's said letter by letter,
# which these are.
_SAID_AS_LETTERS = {
    "SEO", "SEM", "SMS", "SSL", "SSD", "SLA", "SMB", "SME", "SDK", "SUV", "SVG", "HR", "HTML",
    "HTTP", "HTTPS", "HVAC", "LLM", "LMS", "MBA", "MVP", "MRR", "NFT", "NPS", "RFP", "ROI", "RSS",
    "XML", "FTP", "FBA", "ERP", "EV", "SKU", "SSO", "MFA", "HD", "LED", "NGO", "MP3", "MP4",
}  # fmt: skip
# Acronyms starting with U said as letters ("a URL"), not as a word.
_U_AS_LETTERS = {"URL", "UX", "UI", "USB", "USP", "UK", "US", "UTM", "UGC"}

_LEADING = "\"'“‘(["
_TRAILING = ".,:;!?)]\"'”’"


def _is_english(words: list[str]) -> bool:
    lowered = {word.strip(_LEADING + _TRAILING).lower() for word in words}
    if lowered & _OTHER:
        return False
    if lowered & _ENGLISH:
        return True
    return len(lowered & _ENGLISH_TITLE_WORDS) >= 2


def _base_letter(char: str) -> str | None:
    """The Latin letter under an accent ("É" is "E"), or None for any other character."""
    base = unicodedata.normalize("NFD", char)[0]
    return base if base.isascii() and base.isalpha() else None


def _number_takes_an(digits: str) -> bool | None:
    if digits.startswith("8"):
        return True
    if digits[:2] in ("11", "18"):
        # "eleven", "eighteen", "eleven thousand"; a four-digit one may be a year ("1800s").
        return None if len(digits) == 4 else len(digits) % 3 == 2
    return False


def _acronym_takes_an(letters: str) -> bool | None:
    first = letters[0]
    if first in "AEIO":
        return True
    if first == "U":
        return False if letters in _U_AS_LETTERS else None
    if first in "FHLMNRSX":
        return True if letters in _SAID_AS_LETTERS else None
    return False


def _an_before(word: str) -> bool | None:
    """True when the word takes "an", False when "a", None when it isn't clear."""
    head = re.split(r"[-–/]", word.lstrip(_LEADING), maxsplit=1)[0].rstrip(_TRAILING)
    head = re.sub(r"['’]s$", "", head)  # "URL's" is read as "URL"
    if not head:
        return None
    if head[0] in "0123456789":
        return _number_takes_an(re.match(r"[0-9]+", head.replace(",", "")).group(0))
    first = _base_letter(head[0])
    if first is None:
        return None
    letters = "".join(_base_letter(char) or "" for char in head)
    if len(head) == 1:
        return first.upper() in _VOWEL_SOUND_NAMES
    lower = letters.lower()
    # "URLs", "APIs": an acronym's plural.
    acronym = letters[:-1] if re.fullmatch(r"[A-Z]{2,}s", letters) else letters
    # An all-caps word is a word, not letters, when it's one of the words below: "A ONE-PAGE",
    # "A EUROPEAN", "AN HOURLY" (but "an EU", "a URL").
    caps_word = lower in ("one", "once") or (
        len(lower) >= 5
        and lower.startswith((*_YOU_SOUND, *_UNI_YOU, *_UN_I, *_SILENT_H, *_EITHER_H))
    )
    if len(acronym) >= 2 and acronym.isupper() and not caps_word:
        return _acronym_takes_an(acronym)
    if lower.startswith(_SILENT_H):
        return True
    if lower.startswith(_EITHER_H):
        return None
    if (
        lower == "one"
        or lower.startswith(("one-", "once"))
        or re.match(r"one[a-z]", lower)
        and not lower.startswith("oner")
    ):
        return False
    if lower.startswith("uni"):
        return True if lower.startswith(_UN_I) else False if lower.startswith(_UNI_YOU) else None
    if lower.startswith(_YOU_SOUND) or lower.startswith(_U_YOU):
        return False
    if (
        lower.startswith("u")
        and not lower.startswith("un")
        and re.match(r"u[^aeiou][aeiouy]", lower)
    ):
        return None  # "u", one consonant, a vowel: "you" as often as not (utensil, uber)
    return first.lower() in "aeiou"


def _as(article: str, an: bool) -> str:
    """The article in the form it should take, in the case it was written in."""
    want = "an" if an else "a"
    if article.isupper() and len(article) > 1:
        return want.upper()
    if article[0].isupper():
        return want.capitalize()
    return want


def _changes(title: str) -> list[tuple[int, str]]:
    """Where an article disagrees with the next word: (index in the title's pieces, the article
    as it should read, its punctuation kept)."""
    pieces = re.split(r"(\s+)", title)
    tokens = [index for index, piece in enumerate(pieces) if piece and not piece.isspace()]
    if not _is_english([pieces[index] for index in tokens]):
        return []
    changes = []
    for position, index in enumerate(tokens[:-1]):
        token = pieces[index]
        opening = token[: len(token) - len(token.lstrip(_LEADING))]
        article = token[len(opening) :]
        if article.lower() not in ("a", "an"):
            continue
        previous = pieces[tokens[position - 1]] if position else ""
        starts_clause = not previous or previous.endswith(_CLAUSE_ENDS) or bool(opening)
        if article[0].isupper() and not starts_clause:
            continue  # "Point A", "Plan A": a capital A inside a title may be a letter
        after = pieces[tokens[position + 1]]
        if after.lower().strip(_TRAILING) in _NOT_AFTER_AN_ARTICLE:
            continue
        an = _an_before(after)
        if an is not None and _as(article, an) != article:
            changes.append((index, opening + _as(article, an)))
    return changes


def _apply(title: str, changes: list[tuple[int, str]]) -> str:
    pieces = re.split(r"(\s+)", title)
    for index, replacement in changes:
        pieces[index] = replacement
    return "".join(pieces)


def fix_indefinite_articles(title: str) -> str:
    """The title with each "a" or "an" agreeing with the next word's sound, where that's sure."""
    return _apply(title, _changes(title))


def fix_title_articles(parsed: SEOTopics, keyphrase: str) -> SEOTopics:
    """Each title's articles by the next word's sound. A change that would take out the keyphrase
    the title carries is left out (a user's own "a" stays as they wrote it); the others are made."""
    for topic in parsed.topics:
        kept: list[tuple[int, str]] = []
        carries = contains_keyphrase(topic.title, keyphrase)
        for change in _changes(topic.title):
            if not carries or contains_keyphrase(_apply(topic.title, [*kept, change]), keyphrase):
                kept.append(change)
        fixed = _apply(topic.title, kept)
        # Two options that differed only by an article would become one twice over: the second
        # keeps its own wording rather than showing the same title as another option.
        if not any(other is not topic and other.title == fixed for other in parsed.topics):
            topic.title = fixed
    return parsed

"""
"a" or "an" by the sound of the next word, in an English title (G65).

The model now and then writes "How to Create a Effective Content Brief", and the checks on a
title's length and keyphrase pass it. This puts the article right: "an" before a vowel sound
("an effective", "an hour", "an SEO brief", "an 8-step plan"), "a" before a consonant sound
("a unique", "a one-page", "a URL").

It stays out of what it can't be sure of:
- a title that doesn't read as English, where "a" and "an" are other words (Spanish "viajar a
  Europa", German "Briefe an Kunden");
- a letter rather than an article ("Plan A", "Vitamin A Explained", "The A to Z of SEO");
- an acronym said as a word, or said both ways ("a FAQ" and "an FAQ" are both in use);
- a next word that starts with neither a letter nor a digit.
"""

import re

from src.flow.engines.content.generation.seo_title_rules import contains_keyphrase
from src.flow.model.structure.topics import SEOTopics

# Words that mark a title as English, besides "a" and "an" themselves.
_ENGLISH = {
    "the", "to", "for", "how", "of", "and", "with", "your", "you", "in", "on", "is", "are",
    "what", "why", "when", "best", "guide", "tips", "ways", "from", "by", "that", "this", "it",
    "or", "vs", "can", "should", "will", "my", "our", "into", "without", "about", "more", "than",
    "using", "step", "steps", "complete", "ultimate", "beginners",
}  # fmt: skip
# Words that mark another language that writes "a" or "an" as a word of its own.
_OTHER = {
    "de", "del", "la", "el", "los", "las", "para", "por", "como", "cómo", "qué", "que", "con",
    "una", "der", "und", "für", "mit", "ein", "eine", "einen", "les", "des", "du", "pour",
    "avec", "et", "une", "dos", "em", "uma", "um", "het", "een", "voor", "och",
}  # fmt: skip
# Before a letter, "A" names it: "Plan A", "Vitamin A", "Grade A".
_LETTER_LABELS = {
    "plan", "vitamin", "type", "grade", "class", "option", "section", "part", "exhibit", "side",
    "group", "level", "tier", "phase", "model", "series", "version", "category", "size", "team",
    "block", "row", "column", "zone", "gate", "schedule", "form", "appendix", "figure", "table",
    "item", "variant", "scenario", "track", "mode", "step", "list", "route", "line",
}  # fmt: skip
# Words an article never comes before, so the "a" in front of them is a letter: "A to Z",
# "Plan A or B", "Why A Is Better".
_NOT_AFTER_AN_ARTICLE = {
    "to", "or", "and", "vs", "versus", "through", "&", "is", "isn't", "was", "are", "were", "has",
    "had", "does", "did", "will", "can", "of", "in", "on", "at", "as", "if", "into", "onto",
    "over", "a", "an",
}  # fmt: skip
# Words starting with a vowel letter and a consonant sound: "a unique", "a European", "a one-page".
_YOU_SOUND = (
    "uni",
    "use",
    "usa",
    "usu",
    "uti",
    "ura",
    "ure",
    "uri",
    "uro",
    "ubiq",
    "ukr",
    "eu",
    "ewe",
)
_YOU_SOUND_EXCEPT = ("unin", "unim", "unid")  # "an uninstall", "an unimportant", "an unidentified"
_ONE_SOUND = ("one", "once")
# Words starting with a silent h: "an hour", "an honest".
_SILENT_H = ("hour", "honest", "honor", "honour", "heir")
# Letters whose names start with a vowel sound: "an SEO", "an HR", "an LLM", "an MBA".
_VOWEL_SOUND_LETTERS = set("AEFHILMNORSX")
# Acronyms said as words, or said both ways: left as written.
_UNSURE_ACRONYMS = {
    "FAQ",
    "FAQS",
    "SQL",
    "NASA",
    "NATO",
    "SCUBA",
    "FIFA",
    "SIM",
    "SAT",
    "MOOC",
    "HIPAA",
}

_WORD = re.compile(r"\S+")
_LEADING = re.compile(r"^[\"'“‘(\[«]+")


def _is_english(words: list[str]) -> bool:
    lowered = {word.strip(".,:;!?()[]\"'“”‘’").lower() for word in words}
    return bool(lowered & _ENGLISH) and not lowered & _OTHER


def _an_before(word: str) -> bool | None:
    """True when the word takes "an", False when "a", None when it isn't clear."""
    word = _LEADING.sub("", word)
    if not word:
        return None
    head = re.split(r"[-–/]", word, maxsplit=1)[0].rstrip(".,:;!?)]\"'”’")
    if not head:
        return None
    if head[0].isdigit():
        digits = re.sub(r"[,.].*$", "", head.replace(",", ""))
        digits = re.match(r"\d+", digits).group(0)
        if digits.startswith("8"):
            return True
        return digits[:2] in ("11", "18") and len(digits) % 3 == 2
    if not head[0].isalpha():
        return None
    letters = re.sub(r"[^A-Za-z]", "", head)
    if len(head) == 1 or (len(letters) >= 2 and letters.isupper()):
        # A letter or an acronym, said letter by letter.
        if letters.upper() in _UNSURE_ACRONYMS:
            return None
        return head[0].upper() in _VOWEL_SOUND_LETTERS
    lower = head.lower()
    if lower.startswith(_SILENT_H):
        return True
    if lower == "one" or lower.startswith(_ONE_SOUND) and not lower.startswith("oner"):
        return False
    if lower.startswith(_YOU_SOUND) and not lower.startswith(_YOU_SOUND_EXCEPT):
        return False
    return lower[0] in "aeiou"


def _as(article: str, an: bool) -> str:
    """The article in the form it should take, in the case it was written in."""
    want = "an" if an else "a"
    if article.isupper() and len(article) > 1:
        return want.upper()
    if article[0].isupper():
        return want.capitalize()
    return want


def fix_indefinite_articles(title: str) -> str:
    """The title with each "a" or "an" agreeing with the next word's sound, when it reads as
    English and the case is clear; otherwise as it was."""
    words = _WORD.findall(title)
    if not _is_english(words):
        return title
    pieces = re.split(r"(\s+)", title)
    tokens = [index for index, piece in enumerate(pieces) if piece and not piece.isspace()]
    for position, index in enumerate(tokens[:-1]):
        article = pieces[index]
        if article.lower() not in ("a", "an"):
            continue
        before = pieces[tokens[position - 1]].lower().strip(".,:;") if position else ""
        after = pieces[tokens[position + 1]]
        if before in _LETTER_LABELS or after.lower().strip(".,:;") in _NOT_AFTER_AN_ARTICLE:
            continue
        an = _an_before(after)
        if an is not None:
            pieces[index] = _as(article, an)
    return "".join(pieces)


def fix_title_articles(parsed: SEOTopics, keyphrase: str) -> SEOTopics:
    """Each title's articles by the next word's sound, unless the change would take out the
    keyphrase the title carries (a user's own "a" stays as they wrote it)."""
    for topic in parsed.topics:
        fixed = fix_indefinite_articles(topic.title)
        if fixed != topic.title and (
            contains_keyphrase(fixed, keyphrase) or not contains_keyphrase(topic.title, keyphrase)
        ):
            topic.title = fixed
    return parsed

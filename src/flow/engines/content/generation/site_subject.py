"""Whether an article's subject is one the site itself is about (rext-control#816).

A workspace's profile says whom the site serves and what it knows. Both shaped every article
it wrote, on any keyword: an article on standing desks for a site that sells an AI writing
tool told its reader to "stand during a site-crawl review", and one on compound interest
called it "a decent analogy for an SEO pro". The site's customers are an article's readers
only where the keyword's subject is the site's own.

Whether it is, is a judgement, and the outline's and the writer's instructions ask for it.
This module holds the one case that needs no judgement: the keyword and the title share no
word with anything the profile says. Then the customers and the company's expertise are
withheld from the outline and the writer, so nothing depends on an instruction being followed.
Deterministic (words in common, no model call), as the persona's fit for a subject is.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from src.flow.engines.content.generation.persona_relevance import _tokens

# What the profile says of the site: what it does and offers, whom it serves, what it writes about.
_PROFILE_FIELDS = (
    "about",
    "selling_position",
    "customer_profile",
    "target_audience",
    "content_pillars",
)
# A word and its plain forms count as one: "desks" and "desk", "writing" and "writer".
_ENDINGS = ("ing", "ers", "er", "es", "s")
_SHORTEST_STEM = 3


def _stems(text: Any) -> set[str]:
    stems = set()
    for word in _tokens(text):
        for ending in _ENDINGS:
            if word.endswith(ending) and len(word) - len(ending) >= _SHORTEST_STEM:
                word = word[: -len(ending)]
                break
        stems.add(word)
    return stems


def _text(value: Any) -> str:
    if isinstance(value, (list, tuple, set)):
        return " ".join(str(item) for item in value if item)
    return str(value or "")


def site_words(profile: Optional[dict]) -> set[str]:
    """Every meaningful word of what the profile says, the company's own name taken out of
    the sentences first: a site is not about a subject because its name holds the word."""
    profile = profile or {}
    name = str(profile.get("brand_name") or "").strip()
    words: set[str] = set()
    for field in _PROFILE_FIELDS:
        text = _text(profile.get(field))
        if name:
            text = re.sub(re.escape(name), " ", text, flags=re.IGNORECASE)
        words |= _stems(text)
    return words


def subject_overlap(
    profile: Optional[dict], *, keyword: Optional[str], title: Optional[str]
) -> Optional[float]:
    """The share (0 to 100) of the article's own words that the site's profile uses: the
    better of the keyword's and the title's. None when there is nothing to compare (a
    profile that says nothing, or no keyword and no title)."""
    site = site_words(profile)
    article = [words for words in (_stems(keyword), _stems(title)) if words]
    if not site or not article:
        return None
    return round(max(100.0 * len(words & site) / len(words) for words in article), 2)


def outside_the_sites_subject(
    profile: Optional[dict], *, keyword: Optional[str], title: Optional[str]
) -> bool:
    """Whether the article's subject is plainly not the site's: its keyword and its title
    share no word with what the profile says. Anything in between is left to the judgement
    the outline and the writer are asked for."""
    return subject_overlap(profile, keyword=keyword, title=title) == 0


def without_customers_and_expertise(profile: Optional[dict]) -> Optional[dict]:
    """The profile as an article outside the site's subject reads it: the brand's voice and
    name, and nothing of whom the site serves or what the company knows."""
    if not profile:
        return profile
    return {
        **profile,
        "customer_profile": "",
        "target_audience": [],
        "about": "",
        "selling_position": "",
        "content_pillars": [],
    }

"""An outline's main sections and their budgets, held to what an article needs.

Since an outline may nest H3 subsections under its H2s (rext-control#603), nothing held it to
its main sections: the list needs four entries, of any level. Outlines came back with one or two
H2s and every other topic as an H3 under them, and with the short budget meant for an H2 that
only introduces its H3s (80 to 120 words) on every section, so a blog was planned at about
800 words where the same keyword had 1,500 to 1,900 a day earlier (rext-control#837).

The prompt now says both rules plainly. This module is what holds them when the model does not:
it changes levels and budgets only, never a heading, a description or a point.
"""

from __future__ import annotations

MIN_MAIN_SECTIONS = 4
MAX_MAIN_SECTIONS = 8
# A section with no subsections is written whole from its own budget: the schema's default for
# a section (BlogSection.suggested_word_count), which is what outlines planned before the short
# budget of an introducing H2 spread to every section.
MAIN_SECTION_MIN_WORDS = 200

_CONTAINERS = ("structure", "content_structure")


def _level(section: dict) -> str:
    return str(section.get("heading_level") or "H2").upper()


def _children(sections: list[dict], index: int) -> list[int]:
    """The H3s directly under the H2 at ``index`` (their own H4s are theirs, not counted)."""
    kids = []
    for position in range(index + 1, len(sections)):
        level = _level(sections[position])
        if level == "H2":
            break
        if level == "H3":
            kids.append(position)
    return kids


def raise_subsections(
    sections: list[dict], least: int = MIN_MAIN_SECTIONS, most: int = MAX_MAIN_SECTIONS
) -> tuple[list[dict], int]:
    """``sections`` with at least ``least`` H2s where its H3s allow it, and how many were raised.

    The H2 with the most H3s gives them up first, all of them together (they are siblings, and
    stay siblings), as far as ``most`` H2s leave room. An H4 under a raised H3 becomes its H3.
    A list with no H3s to raise is returned as it is: nothing is invented.
    """
    sections = [dict(section) for section in sections if isinstance(section, dict)]
    raised = 0
    while True:
        main = [index for index, section in enumerate(sections) if _level(section) == "H2"]
        room = most - len(main)
        if len(main) >= least or room <= 0:
            break
        families = [kids for kids in (_children(sections, index) for index in main) if kids]
        if not families:
            break
        for position in max(families, key=len)[:room]:
            sections[position]["heading_level"] = "H2"
            raised += 1
            follower = position + 1
            while follower < len(sections) and _level(sections[follower]) == "H4":
                sections[follower]["heading_level"] = "H3"
                follower += 1
    return sections, raised


def fill_main_budgets(
    sections: list[dict], least_words: int = MAIN_SECTION_MIN_WORDS
) -> tuple[list[dict], int]:
    """``sections`` with every H2 that has no H3s given at least ``least_words``, and how many
    budgets were lifted. An H2 with H3s keeps its short budget: its H3s carry the section."""
    sections = [dict(section) for section in sections]
    lifted = 0
    for index, section in enumerate(sections):
        if _level(section) != "H2" or _children(sections, index):
            continue
        budget = section.get("suggested_word_count")
        if isinstance(budget, int) and not isinstance(budget, bool) and budget < least_words:
            section["suggested_word_count"] = least_words
            lifted += 1
    return sections, lifted


def hold_main_sections(outline: dict) -> tuple[int, int]:
    """Hold a generated outline's section list to its main sections and their budgets, in place.

    Only an outline whose sections carry heading levels (blog, pillar content): the types whose
    schema fixes the structure have no such list. Returns (sections raised, budgets lifted).
    """
    for key in _CONTAINERS:
        container = outline.get(key)
        sections = container.get("sections") if isinstance(container, dict) else None
        if not isinstance(sections, list) or not sections:
            continue
        if not any(isinstance(s, dict) and s.get("heading_level") for s in sections):
            return 0, 0
        sections, raised = raise_subsections(sections)
        sections, lifted = fill_main_budgets(sections)
        container["sections"] = sections
        return raised, lifted
    return 0, 0

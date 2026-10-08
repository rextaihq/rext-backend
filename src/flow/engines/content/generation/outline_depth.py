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

# The most a type's plan adds up to, where the product shows a narrower range than the outline
# model allows. A blog is 800 to 2,000 words on the content-type step and beside the outline's
# Target words; its model inherits the base bound (5,000). The bound is held here and not on
# the model: structured output is not strict, and a model that wrote a larger target would fail
# the run on a tighter bound. With whole budgets a blog of eight sections planned 2,200 words
# (rext-control#837).
PLAN_MAX_WORDS = {"blog": 2000}
# Budgets are brought down to a multiple of this, as the model writes them.
_BUDGET_STEP = 10

_CONTAINERS = ("structure", "content_structure")


def _level(section: dict) -> str:
    return str(section.get("heading_level") or "H2").upper()


def _children(sections: list[dict], index: int, skip: frozenset[int] = frozenset()) -> list[int]:
    """The H3s directly under the H2 at ``index`` (their own H4s are theirs, not counted),
    less the positions in ``skip``."""
    kids = []
    for position in range(index + 1, len(sections)):
        level = _level(sections[position])
        if level == "H2":
            break
        if level == "H3" and position not in skip:
            kids.append(position)
    return kids


def raise_subsections(
    sections: list[dict], least: int = MIN_MAIN_SECTIONS, most: int = MAX_MAIN_SECTIONS
) -> tuple[list[dict], int]:
    """``sections`` with at least ``least`` H2s where its H3s allow it, and how many were raised.

    * A subsection with no section above it (the list opens on H3s, or holds nothing else) is
      a main section that was given the wrong level: it is raised first.
    * Then the H2 with the most H3s gives them up, all of them together (they are siblings, and
      stay siblings). When only some fit under ``most`` H2s, the last ones are raised, so the
      ones left stay under the H2 they were written under.
    * An H4 under a raised H3 becomes its H3, and stays a detail: it is never raised in turn.

    ``most`` limits what is raised, not what the model wrote: an outline that already has more
    H2s than that is its schema's to accept or refuse. A list with nothing to raise is returned
    as it is: nothing is invented.
    """
    sections = [dict(section) for section in sections if isinstance(section, dict)]
    raised = 0
    details: set[int] = set()

    def lift(position: int) -> None:
        nonlocal raised
        sections[position]["heading_level"] = "H2"
        raised += 1
        follower = position + 1
        while follower < len(sections) and _level(sections[follower]) == "H4":
            sections[follower]["heading_level"] = "H3"
            details.add(follower)
            follower += 1

    def main() -> list[int]:
        return [index for index, section in enumerate(sections) if _level(section) == "H2"]

    first = next(iter(main()), len(sections))
    for position in range(first):
        if len(main()) >= most:
            break
        if _level(sections[position]) == "H3" and position not in details:
            lift(position)

    while True:
        room = most - len(main())
        if len(main()) >= least or room <= 0:
            break
        families = [
            kids
            for kids in (_children(sections, index, frozenset(details)) for index in main())
            if kids
        ]
        if not families:
            break
        for position in max(families, key=len)[-room:]:
            lift(position)
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


def _budget(section: dict) -> int | None:
    words = section.get("suggested_word_count")
    return words if isinstance(words, int) and not isinstance(words, bool) and words > 0 else None


def fit_budgets(
    sections: list[dict], most: int, least_words: int = MAIN_SECTION_MIN_WORDS
) -> tuple[list[dict], int]:
    """``sections`` with their budgets brought down in proportion until the plan adds up to
    ``most`` words or fewer, and how many words came off.

    Every budget gives the same share, so the plan keeps its shape. An H2 without H3s is not
    taken under ``least_words`` (the whole budget `fill_main_budgets` guarantees), and no other
    budget under half of that, so a plan of many sections can still come out above ``most``:
    the caller holds the article's target to ``most`` itself. A section without a budget
    counts as ``least_words``, as the sum does, and is left as it is.
    """
    sections = [dict(section) for section in sections]
    total = sum(_budget(section) or least_words for section in sections)
    if total <= most:
        return sections, 0
    removed = 0
    for index, section in enumerate(sections):
        budget = _budget(section)
        if budget is None:
            continue
        plain = _level(section) == "H2" and not _children(sections, index)
        floor = min(budget, least_words if plain else least_words // 2)
        fitted = max(floor, budget * most // total // _BUDGET_STEP * _BUDGET_STEP)
        removed += budget - fitted
        section["suggested_word_count"] = fitted
    return sections, removed


def hold_plan_inside_its_range(outline: dict, content_type: str) -> int:
    """Bring a generated outline's budgets inside the range the product shows for its type, in
    place. Returns the words that came off; 0 for a type whose model's own bound is that range
    already, and for an outline whose sections carry no heading levels."""
    most = PLAN_MAX_WORDS.get(content_type)
    if not most:
        return 0
    for key in _CONTAINERS:
        container = outline.get(key)
        sections = container.get("sections") if isinstance(container, dict) else None
        if not isinstance(sections, list) or not sections:
            continue
        kept = [section for section in sections if isinstance(section, dict)]
        fitted, removed = fit_budgets(kept, most)
        if removed:
            container["sections"] = fitted
        return removed
    return 0


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

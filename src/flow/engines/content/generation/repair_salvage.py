"""Keeping what a repair got right when it also broke something (FB2.16, rext-control#818).

A repair whose result broke a check that was passing used to be thrown away whole. On seven
real runs, 7 of 14 attempts ended that way, 6 of them for the same side effect, and four of
them carried a fix that was lost with the rest: the next attempt, half a minute later, made
the same fix again or never did.

A repair's result is the article's prose plus the lists the model echoes back beside it
(facts, links). So before a result is given up, it is taken apart, and every piece is judged
by the same deterministic checks, with no model call:

1. the prose as repaired, beside the lists the article already had;
2. failing that, the article as it was, with the repair's changed blocks (paragraphs,
   headings, lists) put in one at a time, each kept only if nothing that passed now fails;
   then every kept block the fixes don't need is taken out again, so what stays is the fix
   and not the rewording around it.

A result is kept only when it fixes at least one of the failed checks: changes that merely
do no harm are not worth keeping. Which checks an article fails is the caller's to say
(`failing`), so this module knows nothing about the checks themselves.
"""

import re
from difflib import SequenceMatcher
from typing import Callable, Iterable, Optional

from src.flow.engines.content.generation.link_integrity import (
    LINK_LIST_FIELDS,
    reconcile_link_lists,
)

# The fields a repair rewrites as prose. Everything else it returns is a list or a label
# echoed beside them.
PROSE_FIELDS = ("introduction", "body_markdown")
# Lists that describe the prose. A repair is a small edit: it has no business re-sourcing
# a fact, and what it echoes back here is where most thrown-away attempts went wrong.
ECHOED_LISTS = ("facts", *LINK_LIST_FIELDS)

_BLANK_LINES = re.compile(r"\n[ \t]*\n+")

Failing = Callable[[dict], set[str]]


def _blocks(text: str) -> list[str]:
    return [block for block in _BLANK_LINES.split((text or "").strip()) if block.strip()]


def _with_lists_of(article: dict, prose_from: dict) -> dict:
    """`prose_from`'s prose and labels with `article`'s lists, the link lists matched to the
    prose as every repair's are."""
    mixed = {**prose_from, **{field: article.get(field) for field in ECHOED_LISTS}}
    return reconcile_link_lists(article, mixed)


def _changes(before: str, after: str) -> tuple[list[str], list[tuple[int, int, list[str]]]]:
    """`before` as blocks, and what turns it into `after`: (from, to, the blocks instead).

    Neighbouring blocks that were each reworded are separate changes, so that one of them can
    be kept without the other; a stretch that was split, merged, added or removed is one.
    """
    old, new = _blocks(before), _blocks(after)
    matcher = SequenceMatcher(None, old, new, autojunk=False)
    changes: list[tuple[int, int, list[str]]] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        if i2 - i1 == j2 - j1:
            changes.extend((i1 + k, i1 + k + 1, [new[j1 + k]]) for k in range(i2 - i1))
        else:
            changes.append((i1, i2, new[j1:j2]))
    return old, changes


def _apply(old: list[str], changes: list[tuple[int, int, list[str]]], keep: set[int]) -> str:
    out: list[str] = []
    at = 0
    for index, (i1, i2, instead) in enumerate(changes):
        out.extend(old[at:i1])
        out.extend(instead if index in keep else old[i1:i2])
        at = i2
    out.extend(old[at:])
    return "\n\n".join(out)


def salvage_repair(
    article: dict,
    repaired: dict,
    failing: Failing,
    failed_before: set[str],
    ignore: Iterable[str] = (),
) -> tuple[Optional[dict], dict[str, int | str]]:
    """What of `repaired` can stand: it breaks no check `article` passed, and fixes one.

    `failing(content)` names the checks a content fails; `failed_before` those `article`
    failed; `ignore` those that count neither as broken nor as fixed (another stage's).
    Returns the article to keep (None when no useful part of the repair could be kept) and
    how it was reached: `{"how": "lists"}`, or `{"how": "blocks", "kept": n, "dropped": m}`.
    """
    ours = failed_before - set(ignore)

    def judge(content: dict) -> tuple[set[str], set[str]]:
        """What the content breaks, and what it fixes."""
        now = failing(content)
        return now - failed_before - set(ignore), ours - now

    # 1. The prose as repaired, the lists as they were.
    prose_only = _with_lists_of(article, repaired)
    broken, fixed = judge(prose_only)
    if not broken and fixed:
        return prose_only, {"how": "lists"}

    # 2. The article as it was, taking the repair's changes one block at a time.
    plans = {
        field: _changes(article.get(field) or "", repaired.get(field) or "")
        for field in PROSE_FIELDS
    }
    kept: dict[str, set[int]] = {field: set() for field in PROSE_FIELDS}

    def assembled() -> dict:
        prose = {field: _apply(*plans[field], kept[field]) for field in PROSE_FIELDS}
        return _with_lists_of(article, {**article, **prose})

    dropped = 0
    for field in PROSE_FIELDS:
        for index in range(len(plans[field][1])):
            kept[field].add(index)
            if judge(assembled())[0]:
                kept[field].discard(index)
                dropped += 1

    _, fixed = judge(assembled())
    if not fixed or not any(kept.values()):
        # Nothing of the repair can stay, or what can stay fixes nothing.
        return None, {"how": "blocks", "kept": 0, "dropped": dropped}

    # Out again with every change the fixes don't need.
    for field in PROSE_FIELDS:
        for index in sorted(kept[field]):
            kept[field].discard(index)
            if judge(assembled()) != (set(), fixed):
                kept[field].add(index)

    total = sum(len(indexes) for indexes in kept.values())
    return assembled(), {"how": "blocks", "kept": total, "dropped": dropped}

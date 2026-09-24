"""Reserve a structural slot for an approved brand promotion in the outline.

`promote_brand` is decided at outline REVIEW time — *after* the outline's
structure has already been generated and frozen. Until now nothing reacted to
that: the approved outline was passed to generation unchanged, so the writer
model read a Structural Plan with no slot for the brand anywhere in it, while a
separate paragraph of the prompt told it to feature the brand prominently. The
model resolved that contradiction the way models do — it mentioned the brand
wherever felt natural, which is why an approved promotion kept landing mid-body
or in the closing paragraph.

This module closes that gap by writing the brand into the approved outline
itself, so the plan and the instruction agree. `resolve_outline_structure` then
surfaces the slot to generation AND to `expected_sections`, which means
validation can hold the article to it.

Two hard constraints, both learned the expensive way:

1. **Never add a new top-level key.** `resolve_outline_structure` appends any
   unknown top-level key whose value is a non-empty dict (or list of dicts) as a
   structural block, and `resolve_expected_headings` turns that into a REQUIRED
   heading. A top-level `brand_slot: {...}` would manufacture a phantom
   "## Brand Slot" section that no article ever contains, failing
   `check_required_sections` forever. Every write below is nested inside a field
   the content type's schema already declares.

2. **Guard every write and no-op on surprise.** The approved outline is a plain
   dict that is never re-validated through Pydantic after approval, so a bad
   write raises nothing — it silently corrupts the plan. `isinstance` checks are
   the only safety net there is.
"""

from __future__ import annotations

import copy
import logging
import re
from dataclasses import dataclass
from typing import Any, Callable, Optional

from src.flow.engines.content.generation.brand_placement_policy import (
    DEFAULT_BODY_ATTENTION_MAX_FRACTION,
    resolve_brand_placement_policy,
)
from src.flow.model.structure.outlines import normalize_content_type
from src.flow.model.structure.outlines.product_names import (
    find_placeholder_names,
    is_placeholder_product_name,
)

logger = logging.getLogger(__name__)

# Key under `brand_voice_promotion` recording which outline block(s) the slot was
# written into. Nested there rather than top-level for constraint 1 above:
# `brand_voice_promotion` is already in outline_structure._NON_STRUCTURAL_KEYS, so
# nothing under it can be mistaken for a section.
SLOT_BLOCK_KEYS = "slot_block_keys"


@dataclass(frozen=True)
class BrandSlotWrite:
    """Where a slot writer put the brand.

    `path` is the human-readable location for logs — unchanged from when these
    writers returned a bare string. `block_keys` names the same location as
    TOP-LEVEL outline field(s), which is the vocabulary
    `resolve_outline_structure` speaks, so a later stage can find the field that
    carries the brand without re-deriving the decision made here.

    Publishing it matters: this module is the single place that decides where an
    approved brand mention belongs structurally, and anything that needs to know
    should read that decision rather than reimplement the dispatch below.
    """

    path: str
    block_keys: tuple[str, ...]


_WORD_RE = re.compile(r"[a-zA-Z0-9']+")
_STOPWORDS = {
    "the",
    "a",
    "an",
    "and",
    "or",
    "but",
    "of",
    "to",
    "in",
    "on",
    "for",
    "with",
    "is",
    "are",
    "was",
    "were",
    "this",
    "that",
    "it",
    "as",
    "by",
    "at",
    "be",
    "from",
    "your",
    "you",
    "we",
    "our",
    "will",
    "can",
    "has",
    "have",
    "not",
}


def _tokens(text: str) -> set[str]:
    return {w for w in _WORD_RE.findall((text or "").lower()) if len(w) > 2 and w not in _STOPWORDS}


def _relevance(a: str, b: str) -> float:
    """Cheap bag-of-words overlap, 0..1.

    Deliberately its own copy rather than reaching into validation.py's private
    helper: that one grades a finished mention, this one picks a slot. They
    answer different questions and should be free to diverge.
    """
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / min(len(ta), len(tb))


def _mentions(text: Any, brand_name: str) -> bool:
    return isinstance(text, str) and brand_name.lower() in text.lower()


def _claim(promo: dict) -> str:
    """The strongest one-line claim available from the approved promotion."""
    selling = (promo.get("selling_position") or "").strip()
    about = (promo.get("about") or "").strip()
    return selling or about


# ── per-type slot writers ────────────────────────────────────────────────────
# Each returns a short description of where it wrote, or None if the outline
# didn't have the shape it expected (in which case nothing was touched).


def _find_named_index(items: list, brand_name: str, *name_paths: tuple[str, ...]) -> Optional[int]:
    """Index of the entry already representing the brand, if the outline
    generator happened to include it. Moving that entry beats inserting a
    duplicate."""
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        for path in name_paths:
            node: Any = item
            for key in path:
                node = node.get(key) if isinstance(node, dict) else None
            if _mentions(node, brand_name):
                return idx
    return None


def _renumber(entries: list, key: str = "rank") -> None:
    for position, entry in enumerate(entries, start=1):
        if isinstance(entry, dict):
            entry[key] = position


def _fill_marker(brand_name: str) -> str:
    """The stand-in written wherever a per-product VALUE is required but unknown.

    Never a fabricated figure: the writer fills it from the approved
    About/selling-position text. Shared by every block that carries per-product
    values (feature matrix, pricing, tool pricing insights) so they cannot drift
    into inventing different kinds of placeholder.
    """
    return f"[{brand_name} — fill from brand info]"


def _add_brand_to_matrix(
    outline: dict,
    brand_name: str,
    names_field: str,
    values_field: str,
    matrix_key: str = "comparison_matrix",
) -> bool:
    """Add the brand as the first column of the feature-comparison table.

    Ranking the brand first (see the writers below) does not put it in the
    feature matrix: that block carries its OWN list of products, generated
    before the promotion was approved, so a best-tools article would rank the
    brand #1 and then publish a comparison table it is absent from. On a
    commercial-intent page the table is the part readers actually compare on, so
    being missing there undoes the ranking.

    Column and value field names differ per schema (best-tools says
    `tools_compared`/`tool_values`, product-roundup says `products`/`values`), so
    the caller passes its own — the knowledge stays in the writer that already
    owns that schema rather than in a registry here.

    Row values are kept aligned with the column list. Inserting a name without
    inserting a corresponding value shifts every row by one, which would hand a
    competitor's pricing or feature value to the brand — a worse defect than the
    missing column, since it invents specifics about our own product.
    """
    matrix = outline.get(matrix_key)
    if not isinstance(matrix, dict):
        return False
    names = matrix.get(names_field)
    if not isinstance(names, list):
        return False

    if any(_mentions(name, brand_name) for name in names):
        return True

    names.insert(0, brand_name)

    rows = matrix.get("rows")
    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, dict):
                continue
            values = row.get(values_field)
            if isinstance(values, list):
                # A placeholder, not a fabricated value — the writer fills it
                # from the approved About/selling-position text. The detailed
                # instruction rides on the field directive, not on every row.
                values.insert(0, _fill_marker(brand_name))
    return True


def _remove_from_matrix(
    outline: dict,
    name: str,
    names_field: str,
    values_field: str,
    matrix_key: str,
) -> bool:
    """Drop a product's COLUMN from the feature matrix, values included.

    The mirror of `_add_brand_to_matrix`, and it exists for the same reason:
    column names and row values are two parallel lists held in alignment only by
    index. Removing a name without removing the value at the same index shifts
    every later value one column left, handing one product another's pricing —
    the precise corruption this module now exists to prevent, just in the
    opposite direction.

    Used when a PLACEHOLDER product ("Agency A") is evicted: its row values were
    invented for a company that does not exist, so they must leave with it
    rather than be inherited by whoever takes the column.
    """
    matrix = outline.get(matrix_key)
    if not isinstance(matrix, dict):
        return False
    names = matrix.get(names_field)
    if not isinstance(names, list):
        return False

    index = next(
        (i for i, existing in enumerate(names) if _mentions(existing, name)),
        None,
    )
    if index is None:
        return False

    names.pop(index)
    rows = matrix.get("rows")
    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, dict):
                continue
            values = row.get(values_field)
            if isinstance(values, list) and index < len(values):
                values.pop(index)
    return True


def _add_brand_to_best_tools_blocks(outline: dict, promo: dict, brand_name: str) -> list[str]:
    """Carry the brand into best-tools' other name-keyed blocks.

    Same reasoning as the feature matrix, which was singled out first: each of
    these blocks holds its OWN list of tool names, generated before the
    promotion was approved. Ranking the brand #1 and then publishing a decision
    guide, a pricing table and a use-case map that never mention it reads as an
    inconsistent page — the reader is told it is the top pick, then finds it
    absent from every block that supports the pick.

    Existing entries are never rewritten, only added to: reassigning an approved
    use case or category from a competitor to the brand would be a claim the
    reviewer did not approve. Returns the block keys written.
    """
    written: list[str] = []
    claim = _claim(promo)
    target_text = f"{promo.get('about', '')} {promo.get('selling_position', '')}"

    # The brand is rank 1, so it is this page's "best overall" — that field is a
    # single name, and leaving a competitor there contradicts the ranking above.
    decision_guide = outline.get("decision_guide")
    if isinstance(decision_guide, dict):
        if not any(_mentions(value, brand_name) for value in decision_guide.values()):
            decision_guide["best_overall"] = brand_name
        written.append("decision_guide")

    pricing_insights = outline.get("pricing_insights")
    if isinstance(pricing_insights, list):
        if not any(
            isinstance(item, dict) and _mentions(item.get("tool_name"), brand_name)
            for item in pricing_insights
        ):
            pricing_insights.insert(
                0,
                {
                    "tool_name": brand_name,
                    "pricing_summary": _fill_marker(brand_name),
                    "value_assessment": claim or f"Featured pick — {brand_name}.",
                },
            )
        written.append("pricing_insights")

    use_cases = outline.get("use_cases")
    if isinstance(use_cases, dict) and isinstance(use_cases.get("matches"), list):
        matches = use_cases["matches"]
        if not any(
            isinstance(match, dict) and _mentions(match.get("best_tool"), brand_name)
            for match in matches
        ):
            # Appended as its own match rather than taking one from a competitor:
            # the existing matches are approved judgements about other tools.
            matches.append(
                {
                    "use_case": claim or f"Teams choosing {brand_name}",
                    "best_tool": brand_name,
                    "reason": claim or f"Featured pick — {brand_name}.",
                }
            )
        written.append("use_cases")

    categories = outline.get("categories")
    if isinstance(categories, dict) and isinstance(categories.get("categories"), list):
        groups = [group for group in categories["categories"] if isinstance(group, dict)]
        already = any(
            isinstance(group.get("tools"), list)
            and any(_mentions(tool, brand_name) for tool in group["tools"])
            for group in groups
        )
        if groups and not already:
            # Into the category the brand genuinely belongs to, chosen by the
            # same relevance helper the body-section writer uses, so the brand
            # is not filed under an unrelated heading.
            group = max(
                groups,
                key=lambda g: _relevance(
                    target_text, f"{g.get('name', '')} {g.get('description', '')}"
                ),
            )
            tools = group.get("tools")
            if isinstance(tools, list):
                tools.insert(0, brand_name)
                written.append("categories")
        elif already:
            written.append("categories")

    return written


def _slot_best_tools(outline: dict, promo: dict, brand_name: str) -> Optional[BrandSlotWrite]:
    rankings = outline.get("rankings")
    if not isinstance(rankings, list) or not rankings or not isinstance(rankings[0], dict):
        return None
    ranked = rankings[0].get("ranked_tools")
    if not isinstance(ranked, list):
        return None

    in_matrix = _add_brand_to_matrix(outline, brand_name, "tools_compared", "tool_values")
    matrix_path = " + comparison_matrix.tools_compared[0]" if in_matrix else ""
    matrix_keys = ("comparison_matrix",) if in_matrix else ()

    existing = _find_named_index(ranked, brand_name, ("tool", "name"))
    if existing is not None:
        if existing == 0:
            path = "rankings[0].ranked_tools[0] (already first)"
        else:
            ranked.insert(0, ranked.pop(existing))
            path = "rankings[0].ranked_tools[0]"
    else:
        ranked.insert(
            0,
            {
                "rank": 1,
                "tool": {
                    "name": brand_name,
                    "description": _claim(promo),
                    "link": (promo.get("brand_url") or "").strip() or None,
                },
                "ranking_reason": f"Featured pick — {_claim(promo)}"
                if _claim(promo)
                else "Featured pick",
            },
        )
        path = "rankings[0].ranked_tools[0]"
    _renumber(ranked)

    extra_keys = _add_brand_to_best_tools_blocks(outline, promo, brand_name)
    extra_path = f" + {' + '.join(extra_keys)}" if extra_keys else ""
    return BrandSlotWrite(
        f"{path}{matrix_path}{extra_path}",
        ("rankings",) + matrix_keys + tuple(extra_keys),
    )


def _slot_product_roundup(outline: dict, promo: dict, brand_name: str) -> Optional[BrandSlotWrite]:
    best_picks = outline.get("best_picks")
    if not isinstance(best_picks, dict):
        return None
    groups = best_picks.get("groups")
    if not isinstance(groups, list) or not groups or not isinstance(groups[0], dict):
        return None
    products = groups[0].get("products")
    if not isinstance(products, list):
        return None

    in_matrix = _add_brand_to_matrix(outline, brand_name, "products", "values")
    matrix_path = " + comparison_matrix.products[0]" if in_matrix else ""
    matrix_keys = ("comparison_matrix",) if in_matrix else ()

    existing = _find_named_index(products, brand_name, ("product", "name"))
    if existing is not None:
        if existing == 0:
            return BrandSlotWrite(
                f"best_picks.groups[0].products[0] (already first){matrix_path}",
                ("best_picks",) + matrix_keys,
            )
        products.insert(0, products.pop(existing))
    else:
        products.insert(
            0,
            {
                "rank": 1,
                "product": {
                    "name": brand_name,
                    "description": _claim(promo),
                    "link": (promo.get("brand_url") or "").strip() or None,
                },
                "reason_for_rank": f"Featured pick — {_claim(promo)}"
                if _claim(promo)
                else "Featured pick",
            },
        )
    _renumber(products)
    return BrandSlotWrite(
        f"best_picks.groups[0].products[0]{matrix_path}", ("best_picks",) + matrix_keys
    )


def _same_product(value: Any, name: str) -> bool:
    """Exact (case/space-insensitive) product-name equality.

    Deliberately stricter than `_mentions`: this decides whether a REFERENCE in
    another block points at a given product, and substring matching there would
    treat "Ahrefs" and "Ahrefs Enterprise" as the same entity, quietly rewriting
    a reference to a product the user never touched.
    """
    if not isinstance(value, str) or not name:
        return False
    return " ".join(value.split()).casefold() == " ".join(name.split()).casefold()


def _normalize_compared_products(outline: dict) -> Optional[list]:
    """`outline["products"]` as a LIST, converting the legacy struct in place.

    Backward compatibility, and the only place that knows the old shape: outlines
    approved before the list migration are plain dicts sitting in LangGraph
    checkpoints as `{"product_a": {...}, "product_b": {...}}`, and they still
    have to flow through generation after this deploys. Converting on read keeps
    every caller below working on one shape instead of branching on two.
    """
    products = outline.get("products")
    if isinstance(products, list):
        return products
    if isinstance(products, dict):
        ordered = [
            products[key]
            for key in ("product_a", "product_b")
            if isinstance(products.get(key), dict)
        ]
        if not ordered:
            return None
        outline["products"] = ordered
        logger.info(
            "[BrandSlot] converted legacy product_a/product_b struct into a %d-item list.",
            len(ordered),
        )
        return ordered
    return None


def _drop_product_references(outline: dict, name: str) -> None:
    """Erase every trace of a product from the name-keyed comparison blocks.

    Called only when evicting a PLACEHOLDER ("Agency A"). Everything the outline
    says about such a product — its matrix column, its price, the use cases it
    "wins", the verdict naming it — was invented for a company that does not
    exist. Leaving any of it behind would let that fabricated data be inherited
    by whichever real product takes its place, which is strictly worse than the
    placeholder itself.

    References that cannot be neutralized without asserting something new are
    removed rather than repointed: a recommendation for a nonexistent product is
    deleted, while a "winner" pointing at one degrades to "tie" for the writer
    to resolve.
    """
    _remove_from_matrix(outline, name, "products_compared", "values", "feature_matrix")

    pricing = outline.get("pricing")
    if isinstance(pricing, dict) and isinstance(pricing.get("entries"), list):
        pricing["entries"] = [
            entry
            for entry in pricing["entries"]
            if not (isinstance(entry, dict) and _same_product(entry.get("product_name"), name))
        ]

    performance = outline.get("performance")
    if isinstance(performance, dict) and isinstance(performance.get("scores"), list):
        performance["scores"] = [
            score
            for score in performance["scores"]
            if not (isinstance(score, dict) and _same_product(score.get("product_name"), name))
        ]

    recommendations = outline.get("recommendations")
    if isinstance(recommendations, dict) and isinstance(
        recommendations.get("recommendations"), list
    ):
        recommendations["recommendations"] = [
            rec
            for rec in recommendations["recommendations"]
            if not (isinstance(rec, dict) and _same_product(rec.get("recommended_product"), name))
        ]

    use_cases = outline.get("use_cases")
    if isinstance(use_cases, dict) and isinstance(use_cases.get("comparisons"), list):
        for comparison in use_cases["comparisons"]:
            if isinstance(comparison, dict) and _same_product(comparison.get("best_choice"), name):
                comparison["best_choice"] = "tie"

    head_to_head = outline.get("head_to_head")
    if isinstance(head_to_head, dict):
        if _same_product(head_to_head.get("winner_overall"), name):
            head_to_head["winner_overall"] = "tie"
        for key, value in list(head_to_head.items()):
            if key != "winner_overall" and _same_product(value, name):
                head_to_head[key] = ""

    migration = outline.get("migration")
    if isinstance(migration, dict):
        for key in ("from_product", "to_product"):
            if _same_product(migration.get(key), name):
                migration[key] = ""


def _add_brand_to_comparison_blocks(outline: dict, promo: dict, brand_name: str) -> list[str]:
    """Carry the brand into the blocks a reader actually compares on.

    Being first in `products` is not the same as being IN the comparison: the
    table, the pricing list and the recommendations each carry their own
    name-keyed list, generated before the promotion was approved. A comparison
    that ranks the brand first and then publishes a feature table it is absent
    from has not featured it at all — which is the ranked-list lesson
    `_add_brand_to_matrix` already encodes, applied to the rest of the blocks.

    Returns the block keys written, for the caller's slot record.
    """
    written: list[str] = []
    claim = _claim(promo)

    if _add_brand_to_matrix(
        outline, brand_name, "products_compared", "values", matrix_key="feature_matrix"
    ):
        written.append("feature_matrix")

    pricing = outline.get("pricing")
    if isinstance(pricing, dict) and isinstance(pricing.get("entries"), list):
        entries = pricing["entries"]
        if not any(
            isinstance(e, dict) and _mentions(e.get("product_name"), brand_name) for e in entries
        ):
            entries.insert(0, {"product_name": brand_name, "price": _fill_marker(brand_name)})
        written.append("pricing")

    recommendations = outline.get("recommendations")
    if isinstance(recommendations, dict) and isinstance(
        recommendations.get("recommendations"), list
    ):
        items = recommendations["recommendations"]
        if not any(
            isinstance(r, dict) and _mentions(r.get("recommended_product"), brand_name)
            for r in items
        ):
            items.insert(
                0,
                {
                    "scenario": f"Readers who need what {brand_name} does best",
                    "recommended_product": brand_name,
                    "justification": claim or f"Featured pick — {brand_name}.",
                },
            )
        written.append("recommendations")

    return written


def _slot_comparison(outline: dict, promo: dict, brand_name: str) -> Optional[BrandSlotWrite]:
    """Put the approved brand INTO the comparison, without evicting anyone real.

    `products` is a list of 2-4 named products (see the comparison schema), so
    the brand is added by insertion at the front — the position this content
    type's policy asks for — and every other block references products by name,
    so that insertion re-points nothing.

    This replaces a two-slot implementation that could do neither. It had to
    choose between swapping the brand into a fixed slot — which silently left
    the feature matrix, pricing and verdict describing the previous occupant —
    and giving up entirely when both slots were full, which is what actually
    happened on the reported articles: two invented competitors ("Agency A",
    "Agency B") filled the slots, so the brand was appended to the hero
    subheadline and never appeared in the comparison at all.

    A placeholder-named product is not a competitor worth protecting, so it is
    evicted (together with everything the outline invented about it) to make
    room. A REAL product never is: if the list is already at capacity the brand
    still goes in at the front, and the list is allowed to exceed the schema's
    generation-time maximum rather than drop a product the user approved.
    """
    products = _normalize_compared_products(outline)
    if products is None:
        return None

    block_keys = ["products"]

    existing = _find_named_index(products, brand_name, ("name",))
    if existing is not None:
        if existing != 0:
            products.insert(0, products.pop(existing))
            path = "products[0] (promoted from a later position)"
        else:
            path = "products[0] (already the lead product)"
    else:
        brand_product = {
            "name": brand_name,
            "description": _claim(promo),
            "link": (promo.get("brand_url") or "").strip() or None,
        }

        # Take over ONE placeholder slot if there is one. Evicting a fake costs
        # nothing — everything the outline said about it was invented — and
        # because the brand is inserted in the same breath, the compared set
        # never shrinks. Any further placeholders are deliberately left in place:
        # removing them too could leave the brand with nothing to compare
        # against, and a page comparing one product is not a comparison. They are
        # logged here and flagged by validation; the real fix for them is the
        # outline prompt, which now receives real competitor names.
        placeholder_index = next(
            (
                index
                for index, product in enumerate(products)
                if isinstance(product, dict) and is_placeholder_product_name(product.get("name"))
            ),
            None,
        )

        if placeholder_index is not None:
            dropped = products.pop(placeholder_index)
            dropped_name = dropped.get("name") if isinstance(dropped, dict) else None
            if isinstance(dropped_name, str) and dropped_name.strip():
                _drop_product_references(outline, dropped_name)
            logger.info(
                "[BrandSlot] replaced placeholder compared product %r with '%s'.",
                dropped_name,
                brand_name,
            )
            path = "products[0] (replaced a placeholder product)"
        else:
            path = "products[0]"

        products.insert(0, brand_product)

        remaining = find_placeholder_names(
            product.get("name") for product in products if isinstance(product, dict)
        )
        if remaining:
            logger.warning(
                "[BrandSlot] comparison outline for '%s' still carries placeholder product "
                "name(s) %s — kept so the page still compares something, but this outline "
                "should have been generated with real competitor names.",
                brand_name,
                remaining,
            )

    block_keys.extend(_add_brand_to_comparison_blocks(outline, promo, brand_name))
    extra = [key for key in block_keys[1:]]
    if extra:
        path = f"{path} + {' + '.join(extra)}"
    return BrandSlotWrite(path, tuple(block_keys))


def _slot_alternatives(outline: dict, promo: dict, brand_name: str) -> Optional[BrandSlotWrite]:
    """Deliberately NOT `alternatives_list.competitors` — that field is typed as
    the competitor set, and filing our own product under it is semantically
    wrong. On an "alternatives to X" page the reader is already looking to
    switch, so the brand belongs in the differentiation/positioning block and the
    hero, as the featured answer."""
    written: list[str] = []
    block_keys: list[str] = []
    claim = _claim(promo)

    differentiation = outline.get("differentiation")
    if isinstance(differentiation, dict):
        positioning = differentiation.get("positioning_statement")
        if not _mentions(positioning, brand_name):
            differentiation["positioning_statement"] = (
                f"{brand_name} is the featured alternative: {claim}"
                if claim
                else f"{brand_name} is the featured alternative."
            )
        written.append("differentiation.positioning_statement")
        block_keys.append("differentiation")

    if _ensure_brand_in_hero(outline, promo, brand_name):
        written.append("hero")
        block_keys.append("hero")
    return BrandSlotWrite(" + ".join(written), tuple(block_keys)) if written else None


def _ensure_brand_in_hero(outline: dict, promo: dict, brand_name: str) -> bool:
    """Name the brand in the hero block if it isn't there already.

    Appends to the subheadline rather than rewriting the headline: the headline
    carries the page's search intent and mangling it costs more than it gains.
    """
    hero = outline.get("hero")
    if not isinstance(hero, dict):
        return False
    if _mentions(hero.get("headline"), brand_name) or _mentions(
        hero.get("subheadline"), brand_name
    ):
        return True

    claim = _claim(promo)
    addition = f"{brand_name} — {claim}" if claim else brand_name
    subheadline = hero.get("subheadline")
    hero["subheadline"] = (
        f"{subheadline.rstrip('. ')}. {addition}"
        if isinstance(subheadline, str) and subheadline.strip()
        else addition
    )
    return True


def _slot_body_section(
    outline: dict,
    promo: dict,
    brand_name: str,
    content_type: str,
) -> Optional[BrandSlotWrite]:
    """Body-led formats (blog, explainer, how-to, ...).

    Picks the most topically relevant section INSIDE the attention window, so the
    mention lands where readers still are rather than wherever the model drifts
    to. Writes a sentence into `key_points`, which is `List[str]` — not a new
    field on the section, which would be a schema the renderer doesn't know.
    """
    container = outline.get("structure")
    sections = container.get("sections") if isinstance(container, dict) else None
    if not isinstance(sections, list):
        # Some outlines carry a flat top-level `sections` list no schema declares;
        # resolve_outline_structure already treats it as a real block, so honour it.
        sections = outline.get("sections")
        if not isinstance(sections, list):
            return None
        container_label = "sections"
        block_key = "sections"
    else:
        container_label = "structure.sections"
        # The BLOCK is the container `structure`, not the nested section — that
        # is the top-level field resolve_outline_structure surfaces and the one a
        # generated model gets a field for.
        block_key = "structure"

    candidates = [(i, s) for i, s in enumerate(sections) if isinstance(s, dict)]
    if not candidates:
        return None

    policy = resolve_brand_placement_policy(content_type)
    max_fraction = policy.get("body_attention_max_fraction", DEFAULT_BODY_ATTENTION_MAX_FRACTION)
    # At least one candidate, even for a two-section outline.
    window_end = max(1, int(len(candidates) * max_fraction))
    in_window = candidates[:window_end]

    target_text = f"{promo.get('about', '')} {promo.get('selling_position', '')}"
    index, section = max(
        in_window,
        key=lambda pair: _relevance(
            target_text,
            f"{pair[1].get('heading', '')} {pair[1].get('purpose', '')} "
            f"{' '.join(p for p in pair[1].get('key_points', []) if isinstance(p, str))}",
        ),
    )

    key_points = section.get("key_points")
    if not isinstance(key_points, list):
        key_points = []
        section["key_points"] = key_points
    if any(_mentions(p, brand_name) for p in key_points):
        return BrandSlotWrite(
            f"{container_label}[{index}].key_points (already present)", (block_key,)
        )

    claim = _claim(promo)
    key_points.append(
        f"Work in the approved mention of {brand_name} here — {claim}"
        if claim
        else f"Work in the approved mention of {brand_name} here."
    )
    return BrandSlotWrite(f"{container_label}[{index}].key_points", (block_key,))


def _annotate_relevant_item(
    outline: dict,
    promo: dict,
    brand_name: str,
    block_key: str,
    items_field: str,
    text_field: str,
    match_fields: tuple[str, ...],
) -> Optional[str]:
    """Name the brand in the PROSE of the list item it most relates to.

    For formats whose policy puts the mention inside a section that is itself a
    list of typed items (a pros list, a requirements list), where inserting a
    fabricated item would assert something the reviewer never approved — a pro
    the product may not have, a buying criterion nobody chose. Appending to an
    existing item's explanatory prose keeps every approved item intact and its
    label untouched, which is what lets this satisfy policies that require the
    labels themselves to stay vendor-neutral.

    Appends rather than overwrites, the same way `_ensure_brand_in_hero` extends
    a subheadline instead of rewriting the headline: the approved copy is kept
    and the mention is added after it.

    Returns the path written, or None when the outline lacks the expected shape.
    """
    container = outline.get(block_key)
    if not isinstance(container, dict):
        return None
    items = container.get(items_field)
    if not isinstance(items, list):
        return None

    candidates = [(i, item) for i, item in enumerate(items) if isinstance(item, dict)]
    if not candidates:
        return None

    if any(_mentions(item.get(text_field), brand_name) for _i, item in candidates):
        return f"{block_key}.{items_field} (already present)"

    target_text = f"{promo.get('about', '')} {promo.get('selling_position', '')}"
    index, item = max(
        candidates,
        key=lambda pair: _relevance(
            target_text,
            " ".join(str(pair[1].get(f, "")) for f in match_fields),
        ),
    )

    claim = _claim(promo)
    addition = (
        f"Work in the approved mention of {brand_name} here — {claim}"
        if claim
        else f"Work in the approved mention of {brand_name} here."
    )
    existing = item.get(text_field)
    item[text_field] = (
        f"{existing.rstrip('. ')}. {addition}"
        if isinstance(existing, str) and existing.strip()
        else addition
    )
    return f"{block_key}.{items_field}[{index}].{text_field}"


def _slot_pros_cons(outline: dict, promo: dict, brand_name: str) -> Optional[BrandSlotWrite]:
    """Policy: "Naturally in the Pros section."

    Written into a pro's `explanation` rather than added as a new `point`: the
    points are the product's actual advantages, and manufacturing one to hold
    the brand would put a claim in the Pros list that the reviewer never
    approved — while the guardrail's whole premise is that this format only
    stays credible if both lists are genuine.
    """
    written = _annotate_relevant_item(
        outline,
        promo,
        brand_name,
        block_key="pros",
        items_field="pros",
        text_field="explanation",
        match_fields=("point", "explanation", "real_world_example"),
    )
    return BrandSlotWrite(written, ("pros",)) if written else None


def _slot_white_paper(outline: dict, promo: dict, brand_name: str) -> Optional[BrandSlotWrite]:
    """Policy: "One dedicated 'solution/framework' section ... immediately after
    the problem statement and methodology are established."

    Here a new entry IS the right write — unlike a pros list, a solution
    framework is explicitly a set of components proposed as the answer, so the
    brand belongs as one of them. Same insert-or-promote shape as the ranked
    -list writers above.
    """
    framework = outline.get("solution")
    if not isinstance(framework, dict):
        return None
    components = framework.get("components")
    if not isinstance(components, list):
        return None

    existing = _find_named_index(components, brand_name, ("name",))
    if existing is not None:
        return BrandSlotWrite(f"solution.components[{existing}] (already present)", ("solution",))

    claim = _claim(promo)
    components.append(
        {
            "name": brand_name,
            "description": claim or f"{brand_name} as an applied solution component.",
            "benefits": [claim] if claim else [],
        }
    )
    return BrandSlotWrite(f"solution.components[{len(components) - 1}]", ("solution",))


def _slot_buying_guide(outline: dict, promo: dict, brand_name: str) -> Optional[BrandSlotWrite]:
    """Policy: "One 'what to look for' criteria section ... The criteria section
    carries the mention." Guardrail: "Keep the criteria list itself
    vendor-neutral in wording."

    Those two pull in opposite directions unless the write is placed carefully:
    the mention goes into a requirement's `explanation` prose, while the
    requirement `name` — the criterion the reader scans — is left untouched and
    vendor-neutral. Naming the brand in the criterion itself would satisfy the
    placement rule by breaking the guardrail.

    The comparison table is handled too, for the same reason as the ranked-list
    types: its option list is generated before the promotion is approved, so the
    brand would otherwise be absent from the one block readers compare on.
    """
    written: list[str] = []
    block_keys: list[str] = []

    criteria = _annotate_relevant_item(
        outline,
        promo,
        brand_name,
        block_key="requirement_framework",
        items_field="requirements",
        text_field="explanation",
        match_fields=("name", "explanation"),
    )
    if criteria:
        written.append(criteria)
        block_keys.append("requirement_framework")

    if _add_brand_to_matrix(outline, brand_name, "options", "options_values"):
        written.append("comparison_matrix.options[0]")
        block_keys.append("comparison_matrix")

    return BrandSlotWrite(" + ".join(written), tuple(block_keys)) if written else None


_EXPLICIT_WRITERS: dict[str, Callable[[dict, dict, str], Optional[BrandSlotWrite]]] = {
    "best-tools": _slot_best_tools,
    "product-roundup": _slot_product_roundup,
    "comparison": _slot_comparison,
    "alternatives": _slot_alternatives,
    "pros-cons": _slot_pros_cons,
    "white-paper": _slot_white_paper,
    "buying-guide": _slot_buying_guide,
}


def apply_brand_slot_to_outline(outline: dict, content_type: str) -> dict:
    """Return a copy of `outline` with a structural slot reserved for the brand.

    Call this only when `promote_brand` is true. Soft-fails to an unchanged copy
    whenever the outline doesn't have the shape the content type implies — a
    missing slot degrades to the old behaviour, whereas a raise here would break
    outline approval entirely.
    """
    if not isinstance(outline, dict):
        return outline

    promo = outline.get("brand_voice_promotion") or {}
    brand_name = (promo.get("brand_name") or "").strip()
    if not brand_name:
        logger.info("[BrandSlot] promote_brand set but no brand_name; leaving outline unchanged.")
        return outline

    updated = copy.deepcopy(outline)
    normalized = normalize_content_type(content_type)

    try:
        writer = _EXPLICIT_WRITERS.get(normalized)
        if writer is not None:
            written = writer(updated, promo, brand_name)
        elif resolve_brand_placement_policy(normalized)["prefers_top"] and isinstance(
            updated.get("hero"), dict
        ):
            # Self-maintaining: any prefers_top page type with a hero block gets
            # the hero treatment without needing its own entry in a hardcoded list.
            written = (
                BrandSlotWrite("hero", ("hero",))
                if _ensure_brand_in_hero(updated, promo, brand_name)
                else None
            )
        else:
            written = _slot_body_section(updated, promo, brand_name, normalized)
    except Exception:
        logger.exception(
            "[BrandSlot] slot write failed for content_type=%s; leaving outline unchanged.",
            normalized,
        )
        return outline

    if not written:
        logger.warning(
            "[BrandSlot] no slot reserved for '%s' in content_type=%s — outline shape didn't match; "
            "generation falls back to prompt-only placement.",
            brand_name,
            normalized,
        )
        return outline

    # Publish the decision alongside the promotion it belongs to, so a later
    # stage can point at the field that carries the brand instead of
    # reimplementing the dispatch above. Guarded because the outline is a plain
    # dict that is never re-validated after approval.
    promotion = updated.get("brand_voice_promotion")
    if isinstance(promotion, dict):
        promotion[SLOT_BLOCK_KEYS] = list(written.block_keys)

    logger.info(
        "[BrandSlot] reserved %s for '%s' (content_type=%s)",
        written.path,
        brand_name,
        normalized,
    )
    return updated

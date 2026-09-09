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
                values.insert(0, f"[{brand_name} — fill from brand info]")
    return True


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
            return BrandSlotWrite(
                f"rankings[0].ranked_tools[0] (already first){matrix_path}",
                ("rankings",) + matrix_keys,
            )
        ranked.insert(0, ranked.pop(existing))
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
    _renumber(ranked)
    return BrandSlotWrite(f"rankings[0].ranked_tools[0]{matrix_path}", ("rankings",) + matrix_keys)


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


def _slot_comparison(outline: dict, promo: dict, brand_name: str) -> Optional[BrandSlotWrite]:
    """`products` is ComparedProducts{product_a, product_b} — a two-field struct,
    NOT a list. The previous prompt-level instruction told the model to add the
    brand as "the first entry in the compared Products list", an edit this schema
    cannot express, so the model fell back to mentioning it wherever it liked."""
    products = outline.get("products")
    if not isinstance(products, dict):
        return None
    product_a = products.get("product_a")
    product_b = products.get("product_b")

    if isinstance(product_a, dict) and _mentions(product_a.get("name"), brand_name):
        return BrandSlotWrite("products.product_a (already the lead product)", ("products",))
    if isinstance(product_b, dict) and _mentions(product_b.get("name"), brand_name):
        products["product_a"], products["product_b"] = product_b, product_a
        return BrandSlotWrite("products.product_a (promoted from product_b)", ("products",))

    brand_product = {
        "name": brand_name,
        "description": _claim(promo),
        "link": (promo.get("brand_url") or "").strip() or None,
    }

    # ComparedProducts holds exactly two. If both slots already hold real,
    # user-approved competitors, taking one for the brand would DELETE a product
    # the article's title and feature matrix still reference — a far worse defect
    # than a late mention. Fall back to the hero, which is where this content
    # type's policy wants the brand named anyway ("name ALL products being
    # compared, including the brand, right away"), and leave the comparison
    # itself intact.
    if isinstance(product_a, dict) and isinstance(product_b, dict):
        if _ensure_brand_in_hero(outline, promo, brand_name):
            return BrandSlotWrite("hero (both compared-product slots already occupied)", ("hero",))
        return None

    if isinstance(product_a, dict):
        products["product_b"] = product_a
    products["product_a"] = brand_product
    return BrandSlotWrite("products.product_a", ("products",))


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


_EXPLICIT_WRITERS: dict[str, Callable[[dict, dict, str], Optional[BrandSlotWrite]]] = {
    "best-tools": _slot_best_tools,
    "product-roundup": _slot_product_roundup,
    "comparison": _slot_comparison,
    "alternatives": _slot_alternatives,
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

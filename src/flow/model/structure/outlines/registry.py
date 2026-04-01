from __future__ import annotations

from typing import Dict, Literal, Type

from pydantic import BaseModel

from src.flow.model.structure.intent_suggestion import INTENT_TO_CONTENT_TYPES

from .article import ArticleOutlineBase, validate_article_outline
from .checklist import ChecklistOutlineBase, validate_checklist_outline
from .comparison import ComparisonOutlineBase, validate_comparison_outline
from .how_to import HowToOutlineBase, validate_how_to_outline
from .navigational import NavigationalOutlineBase, validate_navigational_outline
from .review import ReviewOutlineBase, validate_review_outline
from .transactional import TransactionalOutlineBase, validate_transactional_outline

# ---------------------------------------------------------------------------
# Per-content-type schema classes (one per slug)
# ---------------------------------------------------------------------------

def _make_subclass(base: Type[BaseModel], slug: str) -> Type[BaseModel]:
    # Avoid metaprogramming-heavy `pydantic.create_model`; keep schema names stable.
    return type(
        f"{slug.replace('-', '_').title().replace('_', '')}Outline",
        (base,),
        {
            "__annotations__": {"content_type": Literal[slug]},
            "content_type": slug,
            "__content_type_slug__": slug,
        },
    )


# Base mapping: slug -> base schema (then we create named subclasses per slug)
_SLUG_TO_BASE: Dict[str, Type[BaseModel]] = {}

# Informational
for slug in INTENT_TO_CONTENT_TYPES.get("informational", []):
    if slug in {"how-to-guide", "tutorial", "documentation", "login-guide"}:
        _SLUG_TO_BASE[slug] = HowToOutlineBase
    elif slug == "checklist":
        _SLUG_TO_BASE[slug] = ChecklistOutlineBase
    else:
        _SLUG_TO_BASE[slug] = ArticleOutlineBase

# Commercial
for slug in INTENT_TO_CONTENT_TYPES.get("commercial", []):
    if slug == "in-depth-review":
        _SLUG_TO_BASE[slug] = ReviewOutlineBase
    else:
        _SLUG_TO_BASE[slug] = ComparisonOutlineBase

# Navigational / transactional
for slug in INTENT_TO_CONTENT_TYPES.get("navigational", []):
    _SLUG_TO_BASE[slug] = NavigationalOutlineBase
for slug in INTENT_TO_CONTENT_TYPES.get("transactional", []):
    _SLUG_TO_BASE[slug] = TransactionalOutlineBase


CONTENT_TYPES: tuple[str, ...] = tuple(_SLUG_TO_BASE.keys())

# Concrete registry used by runtime selection
_SCHEMA_REGISTRY: Dict[str, Type[BaseModel]] = {
    slug: _make_subclass(base, slug) for slug, base in _SLUG_TO_BASE.items()
}


def get_outline_schema(content_type: str) -> Type[BaseModel]:
    """Return the Pydantic schema class for a given canonical content_type slug."""
    if not content_type:
        return _SCHEMA_REGISTRY["blog"]
    return _SCHEMA_REGISTRY.get(content_type, _SCHEMA_REGISTRY["blog"])


def validate_outline_quality(content_type: str, outline: BaseModel) -> None:
    """Extra quality gate beyond schema validation (raises ValueError on failure)."""
    if content_type in {"how-to-guide", "tutorial", "documentation", "login-guide"}:
        validate_how_to_outline(outline)  # type: ignore[arg-type]
        return
    if content_type == "checklist":
        validate_checklist_outline(outline)  # type: ignore[arg-type]
        return
    if content_type == "in-depth-review":
        validate_review_outline(outline)  # type: ignore[arg-type]
        return
    if content_type in {
        "comparison",
        "best-tools",
        "alternatives",
        "pros-cons",
        "product-roundup",
        "buying-guide",
    }:
        validate_comparison_outline(outline)  # type: ignore[arg-type]
        return
    if content_type in INTENT_TO_CONTENT_TYPES.get("navigational", []):
        validate_navigational_outline(outline)  # type: ignore[arg-type]
        return
    if content_type in INTENT_TO_CONTENT_TYPES.get("transactional", []):
        validate_transactional_outline(outline)  # type: ignore[arg-type]
        return

    # Default: article-like
    validate_article_outline(outline)  # type: ignore[arg-type]

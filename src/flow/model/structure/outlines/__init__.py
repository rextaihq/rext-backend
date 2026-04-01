"""Content-type-specific outline schemas (Pydantic).

This package contains strongly-typed, content-type-driven outline schemas and
quality checks used by the outline generation node.
"""

from .registry import get_outline_schema, validate_outline_quality

__all__ = ["get_outline_schema", "validate_outline_quality"]


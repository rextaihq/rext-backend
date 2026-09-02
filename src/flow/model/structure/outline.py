"""Legacy generic outline exports.

`Section` and `Fact` come from `outlines.base` — the canonical definitions —
NOT from the blog schema. They were previously re-exported from
`outlines.infomational.blog`, which meant any per-type schema that happened to
define its own `Section` silently replaced the shared one for every importer
(`structure/__init__.py`, `structure/content.py`, `contents/base.py`).
"""

from .outlines.base import Fact, Section
from .outlines.infomational.blog import BlogOutline as Outline

__all__ = ["Outline", "Section", "Fact"]

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel


def _canonical_text(s: str) -> str:
    s = (s or "").lower().strip()
    s = re.sub(r"[^a-z0-9\s]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _contains_keyphrase(title: str, focus_keyphrase: str) -> bool:
    title_c = _canonical_text(title)
    focus_c = _canonical_text(focus_keyphrase)
    if not title_c or not focus_c:
        return False

    if focus_c in title_c:
        return True

    # "Close variant": require all tokens to appear somewhere in the title.
    title_tokens = set(title_c.split())
    focus_tokens = [t for t in focus_c.split() if t]
    return bool(focus_tokens) and all(t in title_tokens for t in focus_tokens)


def post_process_outline(content_type: str, outline: BaseModel) -> BaseModel:
    """Light post-processing to reduce avoidable validation rejections.

    This only applies safe, mechanical fixes (no semantic rewriting).
    """
    update: dict[str, Any] = {}

    focus = getattr(outline, "focus_keyphrase", "") or ""
    title = getattr(outline, "title", "") or ""
    if focus and title and not _contains_keyphrase(title, focus):
        update["title"] = f"{focus}: {title}"

    # Ensure the model reports the canonical slug that was requested.
    if hasattr(outline, "content_type") and content_type:
        if getattr(outline, "content_type", None) != content_type:
            update["content_type"] = content_type

    return outline.model_copy(update=update) if update else outline


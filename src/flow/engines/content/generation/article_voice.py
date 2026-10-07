"""The article's voice: the author persona's tone first, then the brand's voice profile.

The workspace's Brand Voice Profile (`brand_voice` table: the voice traits and
the customer profile, drafted from the customer's site and editable on the
dashboard's Brand Voice page) used to reach only the brand mention and the
persona ranking; the writer never read it (rext-control #161). It now steers
the writing beside the persona, and the persona's own tone wins where the two
disagree (the founder's decision, option 1).

The persona middleware reads the profile once per article (fresh from the
database, so an edit counts on the very next run), puts the writer's block in
its system prompt, and records the voice on the run's counters. That record
travels in generation_meta to the humanize pass, which keeps the same voice
while rewriting instead of imposing its own.
"""

from __future__ import annotations

import logging
from typing import Any, Optional
from uuid import UUID

logger = logging.getLogger(__name__)

MAX_TRAITS = 8
MAX_TRAIT_CHARS = 60
MAX_TEXT_CHARS = 600


def _clip(text: Any, limit: int) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def article_voice(persona_tone: Any, profile: Optional[dict]) -> dict[str, Any]:
    """The voice to write in, as plain data (what the counters and generation_meta carry)."""
    profile = profile or {}
    traits = [
        _clip(t, MAX_TRAIT_CHARS)
        for t in (profile.get("traits") or [])
        if isinstance(t, str) and t.strip()
    ][:MAX_TRAITS]
    return {
        "persona_tone": _clip(persona_tone, MAX_TEXT_CHARS),
        "brand_traits": traits,
        "customer_profile": _clip(profile.get("customer_profile"), MAX_TEXT_CHARS),
    }


async def fetch_brand_voice_profile(workspace_id: Any) -> Optional[dict[str, Any]]:
    """The workspace's voice traits and customer profile, or None. Never raises."""
    if not workspace_id:
        return None
    try:
        from sqlalchemy import select

        from src.api.database.async_database import get_pooled_langgraph_db_context
        from src.api.models.knowledge_models.knowledge_model import BrandVoice
        from src.utils.loop_bridge import run_on_main_loop

        async def _fetch():
            async with get_pooled_langgraph_db_context() as db:
                result = await db.execute(
                    select(BrandVoice.brand_voice, BrandVoice.customer_profile).where(
                        BrandVoice.workspace_id == UUID(str(workspace_id))
                    )
                )
                return result.first()

        row = await run_on_main_loop(_fetch())
    except Exception:  # noqa: BLE001 - the voice is guidance; a failed read never stops a run
        logger.warning("[ArticleVoice] brand voice read failed (non-fatal)", exc_info=True)
        return None
    if row is None:
        return None
    traits, customer_profile = row
    return {
        "traits": traits if isinstance(traits, list) else [],
        "customer_profile": customer_profile or "",
    }


def format_voice_for_writer(voice: dict[str, Any]) -> str:
    """The writer's system-prompt block; empty when the profile holds nothing."""
    traits = voice.get("brand_traits") or []
    customer = voice.get("customer_profile") or ""
    if not traits and not customer:
        return ""
    lines = ["## THE BRAND'S VOICE (from the workspace's Brand Voice Profile)", ""]
    if traits:
        lines.append(
            f"- **Voice:** {', '.join(traits)}. Let it shape word choice, rhythm and register."
        )
    if customer:
        lines.append(f"- **Who the brand writes for:** {customer}")
    if voice.get("persona_tone"):
        lines.append(
            "- **Precedence:** your own Voice & Tone above comes first. Where it and this brand "
            "voice disagree, follow your own; let the brand voice shape everything yours leaves open."
        )
    else:
        lines.append("- There is no author tone for this article: this voice sets the tone.")
    return "\n".join(lines)


def format_voice_for_rewrite(voice: Optional[dict[str, Any]]) -> str:
    """The humanize pass's instruction to keep the article's voice; empty when there is none."""
    voice = voice or {}
    tone = voice.get("persona_tone") or ""
    traits = voice.get("brand_traits") or []
    customer = voice.get("customer_profile") or ""
    if not (tone or traits or customer):
        return ""
    parts = [
        "",
        "THE ARTICLE'S VOICE — keep the article in this voice while rewriting. It outranks every "
        "general style rule above (tone, register, contractions, casual phrasing):",
    ]
    if tone:
        parts.append(f"- The author's tone (comes first): {tone}")
    if traits:
        parts.append(f"- The brand's voice: {', '.join(traits)}")
    if customer:
        parts.append(f"- Written for: {customer}")
    if tone and traits:
        parts.append(
            "- Where the author's tone and the brand's voice disagree, follow the author's."
        )
    return "\n".join(parts) + "\n"

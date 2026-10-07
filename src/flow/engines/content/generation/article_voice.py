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
import re
from typing import Any, Optional
from uuid import UUID

logger = logging.getLogger(__name__)

MAX_TRAITS = 8
MAX_TRAIT_CHARS = 60
MAX_TEXT_CHARS = 600
MAX_LIST_ITEMS = 6
MAX_ITEM_CHARS = 80
# The profile accepts a name this long; it is kept whole, since it is what gets matched.
MAX_NAME_CHARS = 255


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
    name = _clip(profile.get("brand_name"), MAX_NAME_CHARS)
    return {
        "persona_tone": _clip(persona_tone, MAX_TEXT_CHARS),
        "brand_traits": traits,
        "customer_profile": _clip(profile.get("customer_profile"), MAX_TEXT_CHARS),
        # What the company knows and offers (FB2.21, rext-control#702): the writer's expertise.
        # Kept without the company's own name (taken out before the text is cut, so a long
        # name can't survive as a fragment); the name itself is kept whole beside it.
        "brand_name": name,
        "about": _clip(_without_name(profile.get("about"), name), MAX_TEXT_CHARS),
        "selling_position": _clip(
            _without_name(profile.get("selling_position"), name), MAX_TEXT_CHARS
        ),
        "target_audience": _short_list(profile.get("target_audience"), name),
        "content_pillars": _short_list(profile.get("content_pillars"), name),
    }


def _short_list(values: Any, name: str = "") -> list[str]:
    return [
        _clip(_without_name(value, name), MAX_ITEM_CHARS)
        for value in (values if isinstance(values, list) else [])
        if isinstance(value, str) and value.strip()
    ][:MAX_LIST_ITEMS]


async def fetch_brand_voice_profile(workspace_id: Any) -> Optional[dict[str, Any]]:
    """The workspace's Brand Voice Profile as the writer reads it (the voice traits, the
    customer profile, and what the company knows and offers), or None. Never raises."""
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
                    select(
                        BrandVoice.brand_voice,
                        BrandVoice.customer_profile,
                        BrandVoice.brand_name,
                        BrandVoice.about,
                        BrandVoice.selling_position,
                        BrandVoice.target_audience,
                        BrandVoice.content_pillar,
                    ).where(BrandVoice.workspace_id == UUID(str(workspace_id)))
                )
                return result.first()

        row = await run_on_main_loop(_fetch())
    except Exception:  # noqa: BLE001 - the voice is guidance; a failed read never stops a run
        logger.warning("[ArticleVoice] brand voice read failed (non-fatal)", exc_info=True)
        return None
    if row is None:
        return None
    traits, customer_profile, brand_name, about, selling_position, audience, pillars = row
    return {
        "traits": traits if isinstance(traits, list) else [],
        "customer_profile": customer_profile or "",
        "brand_name": brand_name or "",
        "about": about or "",
        "selling_position": selling_position or "",
        "target_audience": audience if isinstance(audience, list) else [],
        "content_pillars": pillars if isinstance(pillars, list) else [],
    }


def _without_name(text: Any, brand_name: str) -> str:
    """``text`` with the company's own name replaced by "the company".

    The profile's own sentences name the brand ("Acme Tools is a planner for …"). Read as
    written, they put the name in front of the writer on every article, whatever the user
    chose about mentioning it. What the company knows is the point here, not what it is called.
    """
    # Whitespace first: a profile drafted from a site can hold "Acme  CMS", which the name
    # ("Acme CMS") would not match, and the later clipping would close the gap again.
    text = " ".join(text.split()) if isinstance(text, str) else ""
    name = " ".join((brand_name or "").split())
    if not name or not text:
        return text
    pattern = r"(?<![0-9A-Za-z])" + re.escape(name) + r"(?![0-9A-Za-z])"
    replaced = re.sub(pattern, "the company", text, flags=re.IGNORECASE)
    return replaced[:1].upper() + replaced[1:]


def format_expertise_for_writer(voice: dict[str, Any]) -> str:
    """What the company knows and offers, as the writer's expertise; empty when the profile
    holds none of it. Never a reason to name the brand: the mention has its own rules."""
    about = voice.get("about") or ""
    offer = voice.get("selling_position") or ""
    pillars = voice.get("content_pillars") or []
    audiences = voice.get("target_audience") or []
    if not (about or offer or pillars or audiences):
        return ""
    lines = [
        "## WHAT THE COMPANY BEHIND THIS SITE KNOWS AND OFFERS (your expertise, not a pitch)",
        "",
    ]
    if about:
        lines.append(f"- **What it does:** {about}")
    if offer:
        lines.append(f"- **What it offers:** {offer}")
    if pillars:
        lines.append(f"- **What it writes about:** {'; '.join(pillars)}")
    if audiences:
        lines.append(f"- **Who it serves:** {'; '.join(audiences)}")
    lines.append(
        "- **How to use this:** write as a practitioner at this company would: choose the "
        "examples, the level of detail and the angle its customers need, and where the article "
        "touches what the company does, speak from that knowledge."
    )
    lines.append(
        "- **No facts from here:** this shapes how you write, it is not a source. Do not state "
        "the company's own numbers, clients, results or history from it. Every figure, name "
        "and result in the article follows the evidence rules of this prompt, as before."
    )
    lines.append(
        "- **What this is not:** permission to name the company or its product, or to pitch "
        "it. Whether the brand is mentioned, and where, is set only by the brand rules of this "
        "prompt (a PRODUCT-LED MENTION or a BRAND EXCLUSION block). With neither, name it only "
        "where the article's own title or focus keyphrase already does."
    )
    return "\n".join(lines)


def format_voice_for_writer(voice: dict[str, Any]) -> str:
    """The writer's system-prompt block: the brand's voice, then what the company knows and
    offers; empty when the profile holds nothing."""
    blocks = [_format_voice_block(voice), format_expertise_for_writer(voice)]
    return "\n\n".join(block for block in blocks if block)


def _format_voice_block(voice: dict[str, Any]) -> str:
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

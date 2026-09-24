"""Brand voice embedding service — stores and searches brand identity in the LangGraph vector store."""

import uuid
from typing import Optional

from src.flow.store.rext_store import generate_store
from src.utils.logger import logger

_RECOMMENDED_THRESHOLD = 0.35
_NAMESPACE_PREFIX = "brand_voice"


class BrandVoiceEmbeddingService:
    """Handles embedding and semantic search for workspace brand voice data."""

    async def upsert_brand_voice_embedding(
        self,
        workspace_id: uuid.UUID,
        brand_data: dict,
        workspace_name: Optional[str] = None,
    ) -> bool:
        """Build a text representation of the brand voice and store it in the vector store.

        Args:
            workspace_id: Workspace UUID.
            brand_data: Normalized brand voice fields (brand_name, about, selling_position, etc.).
            workspace_name: Internal workspace label — used only as a last-resort
                display fallback when brand_data has no explicit brand_name.

        Returns:
            True on success, False otherwise.
        """
        brand_name = (brand_data.get("brand_name") or "").strip() or workspace_name
        text_to_embed = _build_brand_text(brand_data, brand_name)
        if not text_to_embed:
            logger.warning(f"[BrandVoiceEmbed] No text to embed for workspace {workspace_id}")
            return False

        try:
            namespace = (_NAMESPACE_PREFIX, str(workspace_id))
            value = {
                "brand_name": brand_name or "",
                "about": brand_data.get("about") or "",
                "selling_position": brand_data.get("selling_position") or "",
                "text": text_to_embed,
            }
            async with generate_store() as store:
                await store.aput(
                    namespace=namespace,
                    key="brand_voice",
                    value=value,
                    index=["text"],
                )
            logger.info(f"[BrandVoiceEmbed] Upserted embedding for workspace {workspace_id}")
            return True
        except Exception as e:
            logger.error(
                f"[BrandVoiceEmbed] Failed to upsert for workspace {workspace_id}: {e}",
                exc_info=True,
            )
            return False

    async def search_brand_voice_relevance(
        self,
        workspace_id: uuid.UUID,
        query: str,
    ) -> Optional[dict]:
        """Semantic search against the workspace brand voice embedding.

        Returns a dict with brand_name, about, selling_position, score, recommended
        or None if no embedding exists.
        """
        if not query:
            return None
        try:
            namespace = (_NAMESPACE_PREFIX, str(workspace_id))
            async with generate_store() as store:
                results = await store.asearch(namespace, query=query, limit=1)

            if not results:
                return None

            item = results[0]
            score = round(float(item.score or 0.0), 4)
            val = item.value
            return {
                "brand_name": val.get("brand_name") or "",
                "about": val.get("about") or "",
                "selling_position": val.get("selling_position") or "",
                "score": score,
                "recommended": score >= _RECOMMENDED_THRESHOLD,
            }
        except Exception as e:
            logger.warning(f"[BrandVoiceEmbed] Search failed for workspace {workspace_id}: {e}")
            return None


def _build_brand_text(brand_data: dict, brand_name: Optional[str]) -> str:
    """Assemble embedding text from brand voice fields."""
    parts: list[str] = []

    if brand_name:
        parts.append(f"Brand: {brand_name}")

    for field, label in (
        ("about", "About"),
        ("selling_position", "Selling position"),
        ("customer_profile", "Customer profile"),
    ):
        val = brand_data.get(field)
        if val:
            parts.append(f"{label}: {val}")

    for field, label in (
        ("brand_voice", "Brand voice"),
        ("content_pillar", "Content pillars"),
        ("target_audience", "Target audience"),
    ):
        items = brand_data.get(field)
        if isinstance(items, list) and items:
            parts.append(f"{label}: {', '.join(str(i) for i in items)}")

    return "\n".join(parts).strip()

import uuid
from typing import Optional, List

from src.api.models.content_models.content import Content
from src.flow.store.rext_store import generate_store
from src.utils.logger import logger
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from langgraph.store.base import IndexConfig


class ContentEmbeddingService:
    """
    Handles generation and storage of embeddings for content using LangGraph's BaseStore.
    This replaces the custom pgvector implementation by relying on LangGraph's 
    built-in semantic search and PostgreSQL vector management.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def upsert_content_embedding(self, content_id: uuid.UUID, workspace_id: uuid.UUID) -> bool:
        """
        Generate and upsert an embedding for a piece of content.
        Stores the data in the LangGraph store, which automatically embeds 'text_to_embed'.
        
        Args:
            content_id: UUID of the content to embed.
            workspace_id: UUID of the workspace (for multitenant isolation).
            
        Returns:
            bool: True if successful, False otherwise.
        """
        from sqlalchemy import select
        result = await self.db.execute(
            select(Content).options(selectinload(Content.seo_data)).where(Content.id == content_id)
        )
        content = result.scalar_one_or_none()
        if not content:
            logger.error(f"Cannot embed missing content {content_id}")
            return False

        title = content.title or ""
        intro = content.introduction or ""
        seo = content.seo_data

        tags: list[str] = [str(t) for t in (content.tags or [])]  # type: ignore[union-attr]
        # Tags first — they are the strongest topic signal
        parts: list[str] = ([f"Tags: {', '.join(tags)}"] if tags else [])
        parts.append(str(title))

        if seo:
            focus = str(seo.focus_keyphrase) if seo.focus_keyphrase else ""
            meta_desc = str(seo.meta_description) if seo.meta_description else ""
            if focus:
                parts.append(f"Focus: {focus}")
            # Drop secondary keywords that are just "[focus] + extra words" — they add noise not signal
            raw_secondary: list = list(seo.secondary_keywords or [])  # type: ignore[arg-type]
            focus_lower = focus.lower()
            deduped = [
                str(k) for k in raw_secondary
                if not str(k).lower().startswith(focus_lower)
            ]
            if deduped:
                parts.append(f"Keywords: {', '.join(deduped)}")
            if meta_desc:
                parts.append(meta_desc)
        if intro:
            parts.append(str(intro))

        text_to_embed = "\n".join(parts).strip()

        if not text_to_embed:
            logger.warning(f"No text to embed for content {content_id}")
            return False

        try:
            # We store this in the ("content", str(workspace_id)) namespace
            namespace = ("content", str(workspace_id))
            key = str(content_id)
            
            value = {
                "title": title,
                "slug": content.slug,
                "status": content.status,
                "text": text_to_embed
            }

            async with generate_store() as store:
                await store.aput(
                    namespace=namespace,
                    key=key,
                    value=value,
                    index=["text"]
                )
                
            logger.info(f"Upserted embedding to LangGraph store for content {content_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to upsert embedding to LangGraph store for {content_id}: {str(e)}", exc_info=True)
            return False

    async def search_related_content(
        self, workspace_id: uuid.UUID, query: str, limit: int = 5
    ) -> List[dict]:
        """
        Perform a semantic cosine similarity search for related content.
        
        Args:
            workspace_id: UUID of the workspace to search within.
            query: The text to search for.
            limit: Max number of results.
            
        Returns:
            List of dicts with content metadata and similarity scores.
        """
        try:
            namespace = ("content", str(workspace_id))
            
            results = []
            async with generate_store() as store:
                # search performs semantic search automatically if store has an embedder
                search_results = await store.asearch(
                    namespace,
                    query=query,
                    limit=limit,
                )
                
                for item in search_results:
                    val = item.value
                    full_text = val.get("text") or ""
                    results.append({
                        "content_id": item.key,
                        "title": val.get("title"),
                        "slug": val.get("slug"),
                        "status": val.get("status"),
                        "excerpt": full_text[:300].strip() if full_text else "",
                        "similarity_score": round(float(item.score or 0.0), 4)
                    })
                    
            return results
        except Exception as e:
            logger.error(f"LangGraph store search failed for workspace {workspace_id}: {str(e)}", exc_info=True)
            return []


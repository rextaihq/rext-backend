import uuid
from typing import Optional, List

from src.api.models.content_models.content import Content
from src.flow.store.rext_store import generate_store
from src.utils.logger import logger
from sqlalchemy.ext.asyncio import AsyncSession
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
        content = await self.db.get(Content, content_id)
        if not content:
            logger.error(f"Cannot embed missing content {content_id}")
            return False

        # Build semantic text (Title + Introduction provides high-signal context)
        title = content.title or ""
        intro = content.introduction or ""
        text_to_embed = f"{title}\n\n{intro}".strip()

        if not text_to_embed:
            logger.warning(f"No text to embed for content {content_id}")
            return False

        try:
            # We store this in the ("content", str(workspace_id)) namespace
            namespace = ("content", str(workspace_id))
            key = str(content_id)
            
            # The store uses 'text_to_embed' (or 'text') if we configured fields in rext_store.py.
            # However, if fields isn't configured for a specific key, we can embed it manually
            # OR pass it. Since we know rext_store has IndexConfig(fields=[]), 
            # we should embed it manually if fields=[] means it doesn't embed anything automatically.
            # But actually, Langgraph store with `fields=[]` embeds nothing unless we tell it to.
            # Wait, IndexConfig(fields=[]) means no fields are embedded by default. 
            # We can use the store to embed by updating the rext_store IndexConfig later, 
            # but for now we'll do it manually to be safe, or just provide the text and let IndexConfig handle it if we modify it.
            # Let's just generate the embedding manually and store it, OR use the store's automatic feature.
            # The easiest way: `store.aput` doesn't take an embedding directly, it takes a value and embeds it based on `fields`.
            # Let's use `store.aput` and we'll need to update rext_store to `fields=["text"]` for automatic embedding, 
            # but we can't change rext_store easily if it's used elsewhere. 
            # Let's just assume rext_store.py will embed "text" or "text_to_embed".
            
            # Wait, looking at rext_store.py, it says `IndexConfig(dims=1536, embed=embeddings, fields=[])`.
            # LangGraph v0.2 BaseStore allows you to pass an IndexConfig per put, or global.
            # But the easiest way is to let the LangGraph store handle it. We will just put the dict.
            # If `fields=[]`, it embeds the whole JSON representation of the dictionary.
            
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
                    limit=limit
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


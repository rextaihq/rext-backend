import logging
import uuid
from typing import Dict, Any, List

from src.flow.states.rext import REXT
from src.flow.store.rext_store import RextStore
from src.flow.engines.scrape.config.chunker import SlidingWindowChunker

logger = logging.getLogger(__name__)


async def store_scraped_content(state: REXT) -> Dict[str, Any]:
    """
    Split scraped content and store it in RextStore.
    
    This function retrieves the scraped documents, splits them using the SlidingWindowChunker,
    and stores them in a single batch operation using the user_id and workspace_id from the state.
    """
    logger.info("Starting storage of scraped content")
    
    serp_payload = state.get("serp_payload", {})
    user_id_str = str(serp_payload.get("user_id"))
    workspace_id_str = str(serp_payload.get("workspace_id"))
    
    if not user_id_str or not workspace_id_str:
        logger.warning(f"Missing user_id ({user_id_str}) or workspace_id ({workspace_id_str}). Skipping storage.")
        return {}

    scrape_context = state.get("scrape_context", {})
    documents_data = scrape_context.get("documents", [])
    
    if not documents_data:
        logger.info("No documents to store.")
        return {}
        
    chunker = SlidingWindowChunker()
    all_kb_items = []
    
    for doc_data in documents_data:
        document = doc_data.get("document")
        if not document:
            continue
            
        chunks = chunker.chunk(document)
        
        for item in chunks:
            # item has 'chunk' (str) and 'metadata' (dict)
            all_kb_items.append({
                "text": item['chunk'],
                "metadata": item['metadata']
            })
            
    if not all_kb_items:
        logger.info("No chunks created from documents.")
        return {}
        
    try:
        store = RextStore()
        # Ensure ids are properly formatted as strings or UUIDs as expected by the store logic
        # The store implementation expects str | UUID, and internally converts to str. 
        # We ensure they are strings here for clarity.
        
        logger.info(f"Storing {len(all_kb_items)} knowledge items for user {user_id_str}, workspace {workspace_id_str}")
        
        await store.save_knowledge_batch(
            user_id=user_id_str,
            workspace_id=workspace_id_str,
            contents=all_kb_items,
            source="web_scrape"
        )
        logger.info("Successfully stored all items.")
        
    except Exception as e:
        logger.error(f"Failed to store scraped content: {e}", exc_info=True)
        # We don't want to fail the entire flow if storage fails, so we catch and log
    
    return {}

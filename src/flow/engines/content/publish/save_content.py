import logging
from src.flow.states.wrext import WREXT
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from src.api.models.content_models.content import Content
from uuid import UUID
import markdown

logger = logging.getLogger(__name__)

async def save_content(state: WREXT):
    """
    Save generated content to the database.
    
    Extracts final content from the workflow state and persists it to the Content table.
    This is the final node in the content generation workflow.
    """
    logger.info("Saving generated content to database")
    
    content_state = state.get("content", {})
    final_content = content_state.get("final_content", {})
    request_payload = state.get("request_payload", {})
    
    # Extract content ID from payload
    content_id_str = request_payload.get("content_id")
    if not content_id_str:
        logger.error("No content_id found in request_payload")
        return {
            "content": {
                **content_state,
                "status": "failed",
                "error": "No content_id provided"
            }
        }
    
    content_id = UUID(content_id_str)
    
    # Extract generated fields from final_content
    title = final_content.get("title")
    slug = final_content.get("slug")
    meta_title = final_content.get("meta_title")
    meta_description = final_content.get("meta_description")
    introduction = final_content.get("introduction")
    body_markdown = final_content.get("body_markdown")
    focus_keyphrase = final_content.get("focus_keyphrase")
    keyphrase_density = final_content.get("keyphrase_density")
    tags = final_content.get("tags", [])
    secondary_keywords = final_content.get("secondary_keywords", [])
    
    # Extract structured data
    images_data = final_content.get("images", [])
    internal_links = final_content.get("internal_links", [])
    outbound_links = final_content.get("outbound_links", [])
    schema_markup_obj = final_content.get("schema_markup", {})
    
    # Combine links into single structure
    links_data = {
        "internal": internal_links,
        "outbound": outbound_links
    }
    
    # Convert markdown to HTML
    body_html = None
    if body_markdown:
        try:
            body_html = markdown.markdown(
                body_markdown,
                extensions=['extra', 'nl2br', 'sane_lists', 'tables', 'toc']
            )
            logger.info(f"Converted markdown to HTML ({len(body_html)} chars)")
        except Exception as e:
            logger.warning(f"Failed to convert markdown to HTML: {e}")
    
    # Get database session from state (injected by workflow executor)
    db: AsyncSession = state.get("db_session")
    
    if not db:
        logger.error("No database session found in state")
        return {
            "content": {
                **content_state,
                "status": "failed",
                "error": "No database session available"
            }
        }
    
    try:
        # Fetch content record
        result = await db.execute(
            select(Content).where(Content.id == content_id)
        )
        content = result.scalar_one_or_none()
        
        if not content:
            logger.error(f"Content {content_id} not found")
            return {
                "content": {
                    **content_state,
                    "status": "failed",
                    "error": f"Content {content_id} not found"
                }
            }
        
        # Update content fields
        if title:
            content.title = title
        if slug:
            content.slug = slug
        if meta_title:
            content.meta_title = meta_title
        if meta_description:
            content.meta_description = meta_description
        if introduction:
            content.introduction = introduction
        if body_markdown:
            content.body_markdown = body_markdown
        if body_html:
            content.body_html = body_html
        if focus_keyphrase:
            content.focus_keyphrase = focus_keyphrase
        if keyphrase_density is not None:
            content.keyphrase_density = keyphrase_density
        if tags:
            content.tags = tags
        if secondary_keywords:
            content.secondary_keywords = secondary_keywords
        
        # Store structured data as JSONB
        if images_data:
            content.images_data = images_data
        if links_data:
            content.links_data = links_data
        if schema_markup_obj:
            content.schema_markup = schema_markup_obj
        
        # Set status to ready (content is complete and ready for review/publishing)
        content.status = "ready"
        
        # Flush changes to database
        await db.flush()
        
        logger.info(f"✅ Successfully saved content {content_id} to database")
        
        return {
            "content": {
                **content_state,
                "status": "saved",
                "content_id": str(content_id)
            }
        }
    
    except Exception as e:
        logger.error(f"Failed to save content to database: {str(e)}")
        return {
            "content": {
                **content_state,
                "status": "failed",
                "error": str(e)
            }
        }

import logging
from src.flow.states.wrext import WREXT
from src.services.wordpress_publisher import WordPressPublisher

logger = logging.getLogger(__name__)

def handle_publish(state: WREXT):
    """
    Handle the 'publish' action - publishes content to WordPress.
    """
    logger.info("Handling publish action - publishing content to WordPress")
    
    content_state = state.get("content", {})
    final_content = content_state.get("final_content", {})
    
    # Extract content details
    title = final_content.get("title", "Untitled Post")
    body_markdown = final_content.get("body_markdown", "")
    meta_description = final_content.get("meta_description", "")
    tags = final_content.get("tags", [])
    
    # Initialize WordPress publisher
    wp_publisher = WordPressPublisher()
    
    # Track WordPress publish result
    wordpress_result = None
    publish_error = None
    
    try:
        # Publish to WordPress
        wordpress_result = wp_publisher.publish_post(
            title=title,
            content=body_markdown,
            status="publish",  # Publish immediately
            excerpt=meta_description,
            tags=tags
        )
        
        logger.info(f"✅ Content published to WordPress successfully! Link: {wordpress_result.get('link')}")
        
    except Exception as e:
        publish_error = str(e)
        logger.error(f"❌ Failed to publish to WordPress: {publish_error}")
    
    # Update state with publish results
    return {
        "content": {
            **content_state,
            "final_content": {
                **final_content,
                "status": "approved",
                "wordpress_post_id": wordpress_result.get("post_id") if wordpress_result else None,
                "wordpress_link": wordpress_result.get("link") if wordpress_result else None,
                "publish_error": publish_error
            },
            "status": "completed" if not publish_error else "failed"
        }
    }

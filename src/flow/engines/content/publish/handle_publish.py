import logging
from src.flow.states.wrext import WREXT
from src.services.wordpress_publisher import WordPressPublisher
from src.api.models import WorkspaceIntegration
from src.api.database.async_database import get_async_db_context
from sqlalchemy import select

logger = logging.getLogger(__name__)

async def handle_publish(state: WREXT):
    """
    Handle the 'publish' action - publishes content to WordPress.
    """
    logger.info("Handling publish action - publishing content to WordPress")
    
    content_state = state.get("content", {})
    final_content = content_state.get("final_content", {})
    site_id = content_state.get("site_id")
    
    # Extract content details
    title = final_content.get("title", "Untitled Post")
    body_markdown = final_content.get("body_markdown", "")
    meta_description = final_content.get("meta_description", "")
    tags = final_content.get("tags", [])
    
    # Track WordPress publish result
    wordpress_result = None
    publish_error = None
    
    # Initialize WordPress publisher with site credentials from DB or environment variables
    wp_publisher = None
    wp_config = {} # Initialize an empty config dict

    if site_id:
        try:
            async with get_async_db_context() as db:
                query = select(WorkspaceIntegration).where(WorkspaceIntegration.id == site_id)
                result = await db.execute(query)
                site = result.scalar_one_or_none()
                
                if site and site.integration_type.lower() == "wordpress":
                    wp_config = {
                        "url": site.site_url,
                        "username": site.username,
                        "password": site.app_password
                    }
                    logger.info(f"Using DB-stored credentials for site {site_id}")
                else:
                    publish_error = f"Connected site not found or not WordPress: {site_id}"
                    logger.warning(f"Site {site_id} not found or not WordPress. Falling back to env vars if no error.")
        except Exception as e:
            publish_error = f"Error fetching site credentials: {str(e)}"
            logger.error(f"Error fetching site credentials for {site_id}: {e}")
    
    # Initialize publisher with either DB or Env credentials, only if no error occurred during DB fetch
    if not publish_error:
        wp_publisher = WordPressPublisher(
            site_url=wp_config.get("url") or os.getenv("WORDPRESS_SITE_URL"),
            username=wp_config.get("username") or os.getenv("WORDPRESS_USERNAME"),
            app_password=wp_config.get("password") or os.getenv("WORDPRESS_APP_PASSWORD")
        )
        
        # Check if publisher was successfully initialized with at least a site_url
        if not wp_publisher.site_url:
            publish_error = "WordPress site URL not configured (neither in DB nor environment variables)."
            logger.error(publish_error)

    if wp_publisher and not publish_error: # Only proceed if publisher is initialized and no prior error
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

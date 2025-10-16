from src.flow.states.content_state import ContentState
from src.api.models.content_models.content import Content
from src.api.database.async_database import get_sync_db as get_db
from src.flow.utils.progress_helper import update_node_progress
from langsmith import traceable, trace
from datetime import datetime, timezone
import markdown


@traceable(
    run_type="chain",
    name="Save Generated Content",
    metadata={
        "description": "Saves the generated blog content to the database.",
        "inputs": ["generated_blog", "content_id"],
        "outputs": ["content_saved"],
        "dependencies": ["SQLAlchemy", "Content"],
        "category": "database_write"
    },
    tags=["Database", "ContentSave", "SQLAlchemy"],
    project_name="WREXT"
)
def save_content(state: ContentState):
    """
    Save the generated blog content to the database.
    Updates the content record with generated body_markdown, title, and status.
    """
    print("\n💾 [SaveContent] Starting...")

    payload = state.get("request_payload", {})

    # Update progress (95%)
    content_id = payload.get("content_id")
    if content_id:
        update_node_progress(content_id, "saving_content")

    # Get generated blog from state
    generated_blog = state.get("generated_blog")

    if not generated_blog:
        error_msg = "No generated blog found in state"
        print(f"⚠️ {error_msg}")
        return {
            "error": [{"node": "save_content", "message": error_msg}]
        }

    if not content_id:
        error_msg = "Missing content_id in payload"
        print(f"⚠️ {error_msg}")
        return {
            "error": [{"node": "save_content", "message": error_msg}]
        }

    db = next(get_db())
    try:
        # Fetch content record
        content = db.query(Content).filter(Content.id == content_id).first()

        if not content:
            error_msg = f"Content {content_id} not found in database"
            print(f"⚠️ {error_msg}")
            return {
                "error": [{"node": "save_content", "message": error_msg}]
            }

        # Update content with generated data
        # Try to get full content from BlogArticle
        blog_content = None
        if hasattr(generated_blog, 'get_full_content'):
            blog_content = generated_blog.get_full_content()
        elif hasattr(generated_blog, 'content'):
            blog_content = generated_blog.content

        if blog_content:
            content.body_markdown = blog_content
            print(f"✅ Updated body_markdown ({len(blog_content)} chars)")

            # Convert markdown to HTML
            try:
                html_content = markdown.markdown(
                    blog_content,
                    extensions=['extra', 'nl2br', 'sane_lists', 'tables', 'toc']
                )
                content.body_html = html_content
                print(f"✅ Updated body_html ({len(html_content)} chars)")
            except Exception as e:
                print(f"⚠️ Failed to convert markdown to HTML: {e}")
        else:
            print("⚠️ Generated blog content is empty or not found")
            print(f"   Generated blog type: {type(generated_blog)}")
            print(f"   Generated blog attributes: {dir(generated_blog)}")

        if hasattr(generated_blog, 'title') and generated_blog.title:
            content.title = generated_blog.title
            print(f"✅ Updated title: {generated_blog.title}")

        # Update thread ID if provided
        thread_id = payload.get("thread_id")
        if thread_id:
            content.langgraph_thread_id = thread_id
            print(f"✅ Updated thread_id: {thread_id}")

        # Update status to "ready"
        content.status = "ready"
        content.updated_at = datetime.now(timezone.utc)

        # Commit changes
        db.commit()
        db.refresh(content)

        print(f"✅ Content {content_id} saved successfully")

        return {
            "content_saved": True
        }

    except Exception as e:
        db.rollback()
        error_msg = f"Unexpected error while saving content: {str(e)}"
        print(f"❌ {error_msg}")
        return {
            "error": [{"node": "save_content", "message": error_msg}]
        }

    finally:
        db.close()

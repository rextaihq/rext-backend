"""
Knowledge Base Processing Started Email Template

Sent when knowledge base processing begins.
"""

from emails.components import primary_button, simple_footer, simple_header
from emails.utils.renderer import compose_email


def render_kb_processing_started_email(
    user_name: str,
    kb_name: str,
    item_count: int,
    estimated_time: str,
    workspace_name: str,
    dashboard_url: str = "https://app.rext.ai/knowledge-base",
    frontend_url: str = "https://app.rext.ai",
) -> str:
    """
    Render knowledge base processing started email template.

    Sent when KB processing begins.

    Args:
        user_name: User's first name or display name
        kb_name: Name of the knowledge base
        item_count: Number of items being processed
        estimated_time: Estimated processing time (e.g., "5 minutes", "2 hours")
        workspace_name: Name of the workspace
        dashboard_url: URL to KB dashboard
        frontend_url: Base frontend URL

    Returns:
        Complete HTML email string
    """
    email_html = compose_email(
        [
            simple_header(),
            """
        <h1 style="color: #111827; font-size: 28px; font-weight: 700; margin: 0 0 16px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            📚 Knowledge Base Processing Started
        </h1>
        """,
            f"""
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Hi {user_name},
        </p>
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            We've started processing your knowledge base <strong>{kb_name}</strong> in the <strong>{workspace_name}</strong> workspace.
        </p>
        """,
            f"""
        <div style="margin: 32px 0; padding: 24px; background-color: #eff6ff; border: 2px solid #93c5fd; border-radius: 8px;">
            <h2 style="color: #1e40af; font-size: 18px; font-weight: 600; margin: 0 0 12px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                Processing Details
            </h2>
            <ul style="color: #374151; font-size: 15px; line-height: 22px; margin: 0; padding-left: 20px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                <li><strong>Items:</strong> {item_count:,} document{"s" if item_count != 1 else ""}</li>
                <li><strong>Estimated time:</strong> {estimated_time}</li>
                <li><strong>Status:</strong> In Progress</li>
            </ul>
        </div>
        """,
            """
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            We're analyzing, indexing, and preparing your knowledge base for intelligent content generation. You'll receive another email when processing is complete.
        </p>
        """,
            """
        <div style="margin: 24px 0; padding: 20px; background-color: #f9fafb; border-radius: 8px;">
            <h3 style="color: #111827; font-size: 16px; font-weight: 600; margin: 0 0 12px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                What's happening:
            </h3>
            <ul style="color: #6b7280; font-size: 14px; line-height: 22px; margin: 0; padding-left: 20px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                <li>Extracting text and metadata</li>
                <li>Creating semantic embeddings</li>
                <li>Building search index</li>
                <li>Optimizing for retrieval</li>
            </ul>
        </div>
        """,
            primary_button("View Dashboard", dashboard_url),
            """
        <p style="color: #6b7280; font-size: 14px; line-height: 20px; margin: 32px 0 0 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            In the meantime, you can continue working in your workspace. We'll notify you when everything is ready!
        </p>
        """,
            simple_footer(),
        ]
    )

    return email_html

"""
Knowledge Base Item Added Email Template

Sent when a new item is successfully added to the knowledge base.
"""

from emails.components import primary_button, simple_footer, simple_header
from emails.utils.renderer import compose_email


def render_kb_item_added_email(
    user_name: str,
    kb_name: str,
    item_name: str,
    item_type: str,
    workspace_name: str,
    total_items: int,
    dashboard_url: str = "https://app.rext.ai/knowledge-base",
    frontend_url: str = "https://app.rext.ai",
) -> str:
    """
    Render knowledge base item added email template.

    Sent when a new item is added to the KB.

    Args:
        user_name: User's first name or display name
        kb_name: Name of the knowledge base
        item_name: Name of the added item
        item_type: Type of item (e.g., "PDF", "URL", "Text Document")
        workspace_name: Name of the workspace
        total_items: Total number of items in KB after addition
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
            📄 New Item Added to Knowledge Base
        </h1>
        """,
            f"""
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Hi {user_name},
        </p>
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            A new item has been successfully added to your knowledge base <strong>{kb_name}</strong> in the <strong>{workspace_name}</strong> workspace.
        </p>
        """,
            f"""
        <div style="margin: 32px 0; padding: 24px; background-color: #ecfdf5; border: 2px solid #6ee7b7; border-radius: 8px;">
            <h2 style="color: #065f46; font-size: 18px; font-weight: 600; margin: 0 0 12px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                Item Details
            </h2>
            <ul style="color: #374151; font-size: 15px; line-height: 22px; margin: 0; padding-left: 20px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                <li><strong>Name:</strong> {item_name}</li>
                <li><strong>Type:</strong> {item_type}</li>
                <li><strong>Total items in KB:</strong> {total_items:,}</li>
            </ul>
        </div>
        """,
            """
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            The item has been indexed and is now available for content generation. You can start using it immediately in your AI-powered workflows.
        </p>
        """,
            """
        <div style="margin: 24px 0; padding: 20px; background-color: #eff6ff; border-radius: 8px;">
            <h3 style="color: #111827; font-size: 16px; font-weight: 600; margin: 0 0 12px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                💡 Pro Tip
            </h3>
            <p style="color: #6b7280; font-size: 14px; line-height: 22px; margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                The more quality content you add to your knowledge base, the better your AI-generated content will be. Consider organizing related items together for optimal results.
            </p>
        </div>
        """,
            primary_button("View Knowledge Base", dashboard_url),
            """
        <p style="color: #6b7280; font-size: 14px; line-height: 20px; margin: 32px 0 0 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Keep building your knowledge base to unlock even more powerful content generation capabilities!
        </p>
        """,
            simple_footer(),
        ]
    )

    return email_html

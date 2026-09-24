"""
Knowledge Base Processing Failed Email Template

Sent when knowledge base processing fails.
"""

from emails.components import primary_button, secondary_button, simple_footer, simple_header
from emails.utils.renderer import compose_email


def render_kb_processing_failed_email(
    user_name: str,
    kb_name: str,
    error_message: str,
    workspace_name: str,
    items_attempted: int,
    retry_url: str = "https://app.rext.ai/knowledge-base",
    support_url: str = "https://app.rext.ai/support",
    frontend_url: str = "https://app.rext.ai",
) -> str:
    """
    Render knowledge base processing failed email template.

    Sent when KB processing encounters an error.

    Args:
        user_name: User's first name or display name
        kb_name: Name of the knowledge base
        error_message: Description of the error
        workspace_name: Name of the workspace
        items_attempted: Number of items attempted to process
        retry_url: URL to retry processing
        support_url: URL to contact support
        frontend_url: Base frontend URL

    Returns:
        Complete HTML email string
    """
    email_html = compose_email(
        [
            simple_header(),
            """
        <h1 style="color: #111827; font-size: 28px; font-weight: 700; margin: 0 0 16px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            ⚠️ Knowledge Base Processing Failed
        </h1>
        """,
            f"""
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Hi {user_name},
        </p>
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            We encountered an issue while processing your knowledge base <strong>{kb_name}</strong> in the <strong>{workspace_name}</strong> workspace.
        </p>
        """,
            f"""
        <div style="margin: 32px 0; padding: 24px; background-color: #fef2f2; border: 2px solid #fca5a5; border-radius: 8px;">
            <h2 style="color: #991b1b; font-size: 18px; font-weight: 600; margin: 0 0 12px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                Error Details
            </h2>
            <p style="color: #374151; font-size: 14px; line-height: 22px; margin: 0 0 12px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                <strong>Items attempted:</strong> {items_attempted:,}
            </p>
            <p style="color: #6b7280; font-size: 14px; line-height: 20px; margin: 0; padding: 12px; background-color: #f9fafb; border-radius: 4px; font-family: 'Courier New', Courier, monospace;">
                {error_message}
            </p>
        </div>
        """,
            """
        <div style="margin: 24px 0; padding: 20px; background-color: #f9fafb; border-radius: 8px;">
            <h3 style="color: #111827; font-size: 16px; font-weight: 600; margin: 0 0 12px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                Common causes:
            </h3>
            <ul style="color: #6b7280; font-size: 14px; line-height: 22px; margin: 0; padding-left: 20px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                <li>Unsupported file formats</li>
                <li>Files too large (max 10MB per file)</li>
                <li>Corrupted or inaccessible files</li>
                <li>Temporary service disruption</li>
            </ul>
        </div>
        """,
            """
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Don't worry! You can try processing again, or contact our support team for assistance.
        </p>
        """,
            primary_button("Retry Processing", retry_url),
            """
        <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="margin: 16px 0;">
            <tr>
                <td align="center">
        """,
            secondary_button("Contact Support", support_url),
            """
                </td>
            </tr>
        </table>
        """,
            """
        <p style="color: #6b7280; font-size: 14px; line-height: 20px; margin: 32px 0 0 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Our support team is here to help resolve this issue quickly. Include this error message when contacting support for faster assistance.
        </p>
        """,
            simple_footer(),
        ]
    )

    return email_html

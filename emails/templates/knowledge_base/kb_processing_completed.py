"""
Knowledge Base Processing Completed Email Template

Sent when knowledge base processing completes successfully.
"""
from emails.components import simple_header, primary_button, secondary_button, simple_footer
from emails.utils.renderer import compose_email


def render_kb_processing_completed_email(
    user_name: str,
    kb_name: str,
    items_processed: int,
    processing_time: str,
    workspace_name: str,
    dashboard_url: str = "https://app.wrext.com/knowledge-base",
    create_content_url: str = "https://app.wrext.com/content/new",
    frontend_url: str = "https://app.wrext.com"
) -> str:
    """
    Render knowledge base processing completed email template.

    Sent when KB processing completes successfully.

    Args:
        user_name: User's first name or display name
        kb_name: Name of the knowledge base
        items_processed: Number of items successfully processed
        processing_time: Time taken to process (e.g., "5 minutes", "2 hours")
        workspace_name: Name of the workspace
        dashboard_url: URL to KB dashboard
        create_content_url: URL to start creating content
        frontend_url: Base frontend URL

    Returns:
        Complete HTML email string
    """
    email_html = compose_email([
        simple_header(),
        f"""
        <h1 style="color: #111827; font-size: 28px; font-weight: 700; margin: 0 0 16px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            ✅ Knowledge Base Ready!
        </h1>
        """,
        f"""
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Hi {user_name},
        </p>
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Great news! Your knowledge base <strong>{kb_name}</strong> in the <strong>{workspace_name}</strong> workspace has been successfully processed and is ready to use.
        </p>
        """,
        f"""
        <div style="margin: 32px 0; padding: 24px; background-color: #ecfdf5; border: 2px solid #6ee7b7; border-radius: 8px;">
            <h2 style="color: #065f46; font-size: 18px; font-weight: 600; margin: 0 0 12px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                Processing Complete
            </h2>
            <ul style="color: #374151; font-size: 15px; line-height: 22px; margin: 0; padding-left: 20px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                <li><strong>Items processed:</strong> {items_processed:,} document{"s" if items_processed != 1 else ""}</li>
                <li><strong>Processing time:</strong> {processing_time}</li>
                <li><strong>Status:</strong> ✅ Ready</li>
            </ul>
        </div>
        """,
        """
        <div style="margin: 24px 0; padding: 20px; background-color: #f9fafb; border-radius: 8px;">
            <h3 style="color: #111827; font-size: 16px; font-weight: 600; margin: 0 0 12px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                What you can do now:
            </h3>
            <ul style="color: #6b7280; font-size: 14px; line-height: 22px; margin: 0; padding-left: 20px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                <li>Generate AI-powered content using your knowledge base</li>
                <li>Search through your indexed documents</li>
                <li>Add more items to expand your knowledge base</li>
                <li>Configure content generation settings</li>
            </ul>
        </div>
        """,
        """
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Your knowledge base is now fully indexed and ready to power intelligent content generation!
        </p>
        """,
        primary_button("Create Content", create_content_url),
        """
        <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="margin: 16px 0;">
            <tr>
                <td align="center">
        """,
        secondary_button("View Knowledge Base", dashboard_url),
        """
                </td>
            </tr>
        </table>
        """,
        """
        <p style="color: #6b7280; font-size: 14px; line-height: 20px; margin: 32px 0 0 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Need help getting started? Check out our documentation or contact our support team.
        </p>
        """,
        simple_footer()
    ])

    return email_html

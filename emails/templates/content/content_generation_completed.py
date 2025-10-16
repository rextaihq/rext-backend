"""
Content Generation Completed Email Template

Sent when AI content generation completes successfully.
"""
from emails.components import simple_header, primary_button, simple_footer
from emails.utils.renderer import compose_email


def render_content_generation_completed_email(
    user_name: str,
    content_title: str,
    content_excerpt: str,
    content_url: str,
    generated_at: str,
    word_count: int,
    ai_model: str = "GPT-4",
    frontend_url: str = "https://app.wrext.com"
) -> str:
    """
    Render content generation completed email template.

    Sent when content generation completes successfully.

    Args:
        user_name: User's first name or display name
        content_title: Title of the generated content
        content_excerpt: First ~200 characters of content
        content_url: URL to view/edit the content
        generated_at: Timestamp of generation (e.g., "Oct 12, 2025 3:45 PM")
        word_count: Number of words in generated content
        ai_model: AI model used (e.g., "GPT-4", "Claude")
        frontend_url: Base frontend URL

    Returns:
        Complete HTML email string
    """
    email_html = compose_email([
        simple_header(),
        f"""
        <h1 style="color: #111827; font-size: 28px; font-weight: 700; margin: 0 0 16px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Your Content is Ready! ✨
        </h1>
        """,
        f"""
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Hi {user_name},
        </p>
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Great news! Your content "<strong>{content_title}</strong>" has been generated successfully.
        </p>
        """,
        f"""
        <div style="margin: 32px 0; padding: 24px; background-color: #f9fafb; border-left: 4px solid #667eea; border-radius: 4px;">
            <p style="color: #111827; font-size: 16px; font-weight: 600; margin: 0 0 12px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                Preview:
            </p>
            <p style="color: #4b5563; font-size: 14px; line-height: 22px; margin: 0; font-style: italic; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                "{content_excerpt}..."
            </p>
        </div>
        """,
        primary_button("View & Edit Content", content_url),
        f"""
        <div style="margin: 32px 0 0 0; padding: 20px; background-color: #f9fafb; border-radius: 8px;">
            <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%">
                <tr>
                    <td style="color: #6b7280; font-size: 13px; padding: 4px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        Generated
                    </td>
                    <td style="color: #111827; font-size: 13px; padding: 4px 0; text-align: right; font-weight: 500; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        {generated_at}
                    </td>
                </tr>
                <tr>
                    <td style="color: #6b7280; font-size: 13px; padding: 4px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        Word Count
                    </td>
                    <td style="color: #111827; font-size: 13px; padding: 4px 0; text-align: right; font-weight: 500; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        {word_count:,}
                    </td>
                </tr>
                <tr>
                    <td style="color: #6b7280; font-size: 13px; padding: 4px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        AI Model
                    </td>
                    <td style="color: #111827; font-size: 13px; padding: 4px 0; text-align: right; font-weight: 500; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        {ai_model}
                    </td>
                </tr>
            </table>
        </div>
        """,
        simple_footer()
    ])

    return email_html

"""
Refund Issued Email Template

Sent when a refund is processed for a subscription or order.
"""

from emails.components import primary_button, simple_footer, simple_header
from emails.utils.renderer import compose_email


def render_refund_issued_email(
    user_name: str,
    order_id: str,
    refund_amount: str,
    refund_date: str,
    refund_method: str = None,
    original_plan_name: str = None,
    frontend_url: str = "https://app.rext.ai",
) -> str:
    """
    Render refund issued email template.

    Sent when a refund is processed for an order or subscription.

    Args:
        user_name: User's first name or display name
        order_id: Order or transaction ID
        refund_amount: Amount refunded (e.g., "$99.99")
        refund_date: Date refund was processed (e.g., "January 18, 2025")
        refund_method: Optional payment method info (e.g., "Visa ending in 4242")
        original_plan_name: Optional plan name that was refunded
        frontend_url: Base frontend URL

    Returns:
        Complete HTML email string
    """
    email_html = compose_email(
        [
            simple_header(),
            """
        <h1 style="color: #2563eb; font-size: 28px; font-weight: 700; margin: 0 0 16px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Refund Processed
        </h1>
        """,
            f"""
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Hi {user_name},
        </p>
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Your refund has been successfully processed. We've issued <strong>{refund_amount}</strong> back to your original payment method.
        </p>
        """,
            """
        <div style="margin: 32px 0; padding: 24px; background-color: #eff6ff; border: 2px solid #93c5fd; border-radius: 8px;">
            <h2 style="color: #2563eb; font-size: 18px; font-weight: 600; margin: 0 0 12px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                When Will I See My Refund?
            </h2>
            <p style="color: #374151; font-size: 15px; line-height: 22px; margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                Refunds typically appear in your account within <strong>5-10 business days</strong>, depending on your bank or card issuer. The funds will be returned to the same payment method used for the original purchase.
            </p>
        </div>
        """,
            f"""
        <div style="margin: 24px 0; padding: 20px; background-color: #f9fafb; border-radius: 8px;">
            <h3 style="color: #111827; font-size: 16px; font-weight: 600; margin: 0 0 16px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                Refund Details
            </h3>
            <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%">
                {
                ""
                if not original_plan_name
                else f'''
                <tr>
                    <td style="color: #6b7280; font-size: 14px; padding: 8px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        Plan
                    </td>
                    <td style="color: #111827; font-size: 14px; padding: 8px 0; text-align: right; font-weight: 600; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        {original_plan_name}
                    </td>
                </tr>
                <tr>
                    <td colspan="2" style="height: 1px; background-color: #e5e7eb;"></td>
                </tr>
                '''
            }
                <tr>
                    <td style="color: #6b7280; font-size: 14px; padding: 8px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        Order ID
                    </td>
                    <td style="color: #111827; font-size: 14px; padding: 8px 0; text-align: right; font-weight: 600; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        {order_id}
                    </td>
                </tr>
                <tr>
                    <td colspan="2" style="height: 1px; background-color: #e5e7eb;"></td>
                </tr>
                <tr>
                    <td style="color: #6b7280; font-size: 14px; padding: 8px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        Refund Amount
                    </td>
                    <td style="color: #059669; font-size: 16px; padding: 8px 0; text-align: right; font-weight: 700; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        {refund_amount}
                    </td>
                </tr>
                <tr>
                    <td colspan="2" style="height: 1px; background-color: #e5e7eb;"></td>
                </tr>
                <tr>
                    <td style="color: #6b7280; font-size: 14px; padding: 8px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        Refund Date
                    </td>
                    <td style="color: #111827; font-size: 14px; padding: 8px 0; text-align: right; font-weight: 600; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        {refund_date}
                    </td>
                </tr>
                {
                ""
                if not refund_method
                else f'''
                <tr>
                    <td colspan="2" style="height: 1px; background-color: #e5e7eb;"></td>
                </tr>
                <tr>
                    <td style="color: #6b7280; font-size: 14px; padding: 8px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        Refund Method
                    </td>
                    <td style="color: #111827; font-size: 14px; padding: 8px 0; text-align: right; font-weight: 600; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        {refund_method}
                    </td>
                </tr>
                '''
            }
            </table>
        </div>
        """,
            primary_button("Return to Dashboard", frontend_url),
            """
        <p style="color: #6b7280; font-size: 14px; line-height: 20px; margin: 32px 0 0 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            <strong>Changed your mind?</strong> You're always welcome to return and subscribe again. We'd love to have you back!
        </p>
        <p style="color: #6b7280; font-size: 14px; line-height: 20px; margin: 16px 0 0 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            <strong>Questions about your refund?</strong> Contact our support team and we'll be happy to help.
        </p>
        <p style="color: #6b7280; font-size: 14px; line-height: 20px; margin: 16px 0 0 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            We appreciate the time you spent with Rext AI and hope to see you again in the future.
        </p>
        """,
            simple_footer(),
        ]
    )

    return email_html

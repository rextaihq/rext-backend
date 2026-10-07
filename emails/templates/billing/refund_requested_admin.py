"""
Refund Requested (Admin Alert) Email Template

Sent to super admins when a customer raises a refund request, so a request
does not sit unseen until someone happens to open the admin panel.

Unlike the other billing templates, the recipient is staff rather than the
customer, so it leads with the facts needed to decide and links straight to
the review queue.
"""

from html import escape

from emails.components import primary_button, simple_footer, simple_header
from emails.utils.renderer import compose_email


def render_refund_requested_admin_email(
    admin_name: str,
    customer_email: str,
    product_name: str,
    refund_amount: str,
    order_id: str,
    reason: str,
    requested_date: str,
    review_url: str,
    frontend_url: str = "https://app.rext.ai",
) -> str:
    """
    Render the admin alert for a new customer refund request.

    Args:
        admin_name: Name of the admin receiving the alert
        customer_email: Email of the customer who asked for the refund
        product_name: What they bought (e.g. "Pro - Monthly")
        refund_amount: Formatted amount (e.g. "$189.00")
        order_id: LemonSqueezy order id
        reason: The customer's stated reason, in their own words
        requested_date: When the request was raised
        review_url: Deep link to the admin review queue
        frontend_url: Base frontend URL

    Returns:
        Complete HTML email string
    """
    # compose_email() only joins component strings — it does NOT escape them.
    # (The escaping in the renderer belongs to template-variable substitution,
    # which this path does not use.) The reason is customer-supplied free text
    # going into an email read by staff, so escape every interpolated value
    # here rather than trusting the composer.
    admin_name = escape(str(admin_name))
    customer_email = escape(str(customer_email))
    product_name = escape(str(product_name))
    refund_amount = escape(str(refund_amount))
    order_id = escape(str(order_id))
    reason = escape(str(reason))
    requested_date = escape(str(requested_date))

    email_html = compose_email(
        [
            simple_header(),
            """
        <h1 style="color: #171717; font-size: 28px; font-weight: 700; margin: 0 0 16px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Refund Requested
        </h1>
        """,
            f"""
        <p style="color: #404040; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Hi {admin_name},
        </p>
        <p style="color: #404040; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            <strong>{customer_email}</strong> has requested a refund of
            <strong>{refund_amount}</strong>. No money has moved &mdash; the
            refund is only issued once you approve it.
        </p>
        """,
            f"""
        <div style="margin: 32px 0; padding: 24px; background-color: #fafafa; border: 1px solid #e5e5e5; border-radius: 8px;">
            <table style="width: 100%; border-collapse: collapse; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                <tr>
                    <td style="color: #737373; font-size: 14px; padding: 4px 0;">Product</td>
                    <td style="color: #171717; font-size: 14px; padding: 4px 0; text-align: right;"><strong>{product_name}</strong></td>
                </tr>
                <tr>
                    <td style="color: #737373; font-size: 14px; padding: 4px 0;">Amount</td>
                    <td style="color: #171717; font-size: 14px; padding: 4px 0; text-align: right;"><strong>{refund_amount}</strong></td>
                </tr>
                <tr>
                    <td style="color: #737373; font-size: 14px; padding: 4px 0;">Order</td>
                    <td style="color: #171717; font-size: 14px; padding: 4px 0; text-align: right;">{order_id}</td>
                </tr>
                <tr>
                    <td style="color: #737373; font-size: 14px; padding: 4px 0;">Requested</td>
                    <td style="color: #171717; font-size: 14px; padding: 4px 0; text-align: right;">{requested_date}</td>
                </tr>
            </table>
        </div>
        """,
            f"""
        <div style="margin: 24px 0; padding: 20px; background-color: #fafafa; border-left: 4px solid #d4d4d4; border-radius: 4px;">
            <p style="color: #737373; font-size: 13px; font-weight: 600; margin: 0 0 8px 0; text-transform: uppercase; letter-spacing: 0.5px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                Customer's reason
            </p>
            <p style="color: #404040; font-size: 15px; line-height: 22px; margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                {reason}
            </p>
        </div>
        """,
            primary_button("Review this request", review_url),
            simple_footer(),
        ]
    )

    return email_html

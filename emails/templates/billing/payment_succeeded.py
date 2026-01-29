"""
Payment Succeeded Email Template

Sent when a payment is successfully processed (receipt).
"""
from emails.components import simple_header, primary_button, simple_footer
from emails.utils.renderer import compose_email


def render_payment_succeeded_email(
    user_name: str,
    plan_name: str,
    amount: str,
    payment_date: str,
    next_billing_date: str,
    invoice_url: str = None,
    card_brand: str = None,
    card_last_four: str = None,
    dashboard_url: str = "https://app.rext.com/settings/billing",
    frontend_url: str = "https://app.rext.com"
) -> str:
    """
    Render payment succeeded email template.

    Sent as a receipt after successful payment.

    Args:
        user_name: User's first name or display name
        plan_name: Name of the plan
        amount: Payment amount (e.g., "$29.99")
        payment_date: Date of payment (e.g., "January 15, 2025")
        next_billing_date: Next billing date (e.g., "February 15, 2025")
        invoice_url: Optional URL to download invoice
        card_brand: Optional card brand (e.g., "Visa", "Mastercard")
        card_last_four: Optional last 4 digits of card (e.g., "4242")
        dashboard_url: URL to billing dashboard
        frontend_url: Base frontend URL

    Returns:
        Complete HTML email string
    """
    invoice_button = ""
    if invoice_url:
        invoice_button = f"""
        <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="margin: 24px 0;">
            <tr>
                <td>
                    <a href="{invoice_url}" style="display: inline-block; padding: 12px 24px; background-color: #ffffff; color: #667eea; text-decoration: none; border-radius: 6px; font-weight: 600; border: 2px solid #667eea; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        Download Invoice
                    </a>
                </td>
            </tr>
        </table>
        """

    email_html = compose_email([
        simple_header(),
        f"""
        <h1 style="color: #111827; font-size: 28px; font-weight: 700; margin: 0 0 16px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Payment Received ✓
        </h1>
        """,
        f"""
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Hi {user_name},
        </p>
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Thank you! Your payment has been successfully processed. Here's your receipt:
        </p>
        """,
        f"""
        <div style="margin: 32px 0; padding: 24px; background-color: #f9fafb; border: 2px solid #e5e7eb; border-radius: 8px;">
            <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%">
                <tr>
                    <td style="color: #6b7280; font-size: 14px; padding: 8px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        Payment Date
                    </td>
                    <td style="color: #111827; font-size: 14px; padding: 8px 0; text-align: right; font-weight: 600; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        {payment_date}
                    </td>
                </tr>
                <tr>
                    <td colspan="2" style="height: 1px; background-color: #e5e7eb;"></td>
                </tr>
                <tr>
                    <td style="color: #6b7280; font-size: 14px; padding: 8px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        Plan
                    </td>
                    <td style="color: #111827; font-size: 14px; padding: 8px 0; text-align: right; font-weight: 600; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        {plan_name}
                    </td>
                </tr>
                <tr>
                    <td colspan="2" style="height: 1px; background-color: #e5e7eb;"></td>
                </tr>
                <tr>
                    <td style="color: #6b7280; font-size: 14px; padding: 8px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        Amount Paid
                    </td>
                    <td style="color: #10b981; font-size: 18px; padding: 8px 0; text-align: right; font-weight: 700; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        {amount}
                    </td>
                </tr>
                {"" if not (card_brand and card_last_four) else f'''
                <tr>
                    <td colspan="2" style="height: 1px; background-color: #e5e7eb;"></td>
                </tr>
                <tr>
                    <td style="color: #6b7280; font-size: 14px; padding: 8px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        Payment Method
                    </td>
                    <td style="color: #111827; font-size: 14px; padding: 8px 0; text-align: right; font-weight: 600; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        {card_brand} •••• {card_last_four}
                    </td>
                </tr>
                '''}
                <tr>
                    <td colspan="2" style="height: 1px; background-color: #e5e7eb;"></td>
                </tr>
                <tr>
                    <td style="color: #6b7280; font-size: 14px; padding: 8px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        Next Billing Date
                    </td>
                    <td style="color: #111827; font-size: 14px; padding: 8px 0; text-align: right; font-weight: 600; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        {next_billing_date}
                    </td>
                </tr>
            </table>
        </div>
        """,
        invoice_button,
        primary_button("View Billing Dashboard", dashboard_url),
        """
        <p style="color: #6b7280; font-size: 14px; line-height: 20px; margin: 32px 0 0 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Questions about your bill? Contact our support team - we're here to help!
        </p>
        """,
        simple_footer()
    ])

    return email_html

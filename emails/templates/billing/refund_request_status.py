"""
Refund Request Status Email Templates

The three points in a refund request's life that the customer hears about:
we received it, an admin approved it, or an admin declined it. The money
actually arriving is a separate event with its own template
(`refund_issued.py`), because it happens later and says something different.

These three share one body: the same order summary, the same layout, and only
the heading, the opening line and the accent colour change. They live in one
module rather than three near-identical files so the wording can be compared
side by side and the shared parts cannot drift apart.
"""

from emails.components import primary_button, simple_footer, simple_header
from emails.utils.renderer import compose_email

FONT = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif"


def _status_email(
    *,
    heading: str,
    accent: str,
    intro: str,
    user_name: str,
    product_name: str,
    refund_amount: str,
    order_id: str,
    requested_date: str,
    note_title: str = None,
    note_body: str = None,
    button_text: str = "View your billing",
    frontend_url: str = "https://app.rext.ai",
) -> str:
    """Compose one refund-request status email.

    Args:
        heading: The h1, e.g. "Refund request approved".
        accent: Hex colour for the heading and the note box.
        intro: The opening paragraph, already phrased for this status.
        user_name: Who to greet.
        product_name: What was bought.
        refund_amount: Formatted, e.g. "$25.00".
        order_id: LemonSqueezy order id, so support can find it.
        requested_date: When the customer asked.
        note_title: Optional heading for the highlighted box.
        note_body: Optional body for that box — the admin's note, or what
            happens next.
        button_text: Call to action label.
        frontend_url: Base frontend URL.

    Returns:
        Complete HTML email string.
    """
    blocks = [
        simple_header(),
        f"""
        <h1 style="color: {accent}; font-size: 28px; font-weight: 700; margin: 0 0 16px 0; font-family: {FONT};">
            {heading}
        </h1>
        """,
        f"""
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: {FONT};">
            Hi {user_name},
        </p>
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: {FONT};">
            {intro}
        </p>
        """,
        f"""
        <table role="presentation" style="width: 100%; margin: 0 0 24px 0; border: 1px solid #e5e7eb; border-radius: 8px; border-collapse: separate; border-spacing: 0;">
            <tr>
                <td style="padding: 16px 20px; color: #6b7280; font-size: 14px; font-family: {FONT};">Product</td>
                <td style="padding: 16px 20px; color: #111827; font-size: 14px; font-weight: 600; text-align: right; font-family: {FONT};">{product_name}</td>
            </tr>
            <tr>
                <td style="padding: 16px 20px; border-top: 1px solid #e5e7eb; color: #6b7280; font-size: 14px; font-family: {FONT};">Amount requested</td>
                <td style="padding: 16px 20px; border-top: 1px solid #e5e7eb; color: #111827; font-size: 14px; font-weight: 600; text-align: right; font-family: {FONT};">{refund_amount}</td>
            </tr>
            <tr>
                <td style="padding: 16px 20px; border-top: 1px solid #e5e7eb; color: #6b7280; font-size: 14px; font-family: {FONT};">Order</td>
                <td style="padding: 16px 20px; border-top: 1px solid #e5e7eb; color: #111827; font-size: 14px; text-align: right; font-family: {FONT};">#{order_id}</td>
            </tr>
            <tr>
                <td style="padding: 16px 20px; border-top: 1px solid #e5e7eb; color: #6b7280; font-size: 14px; font-family: {FONT};">Requested on</td>
                <td style="padding: 16px 20px; border-top: 1px solid #e5e7eb; color: #111827; font-size: 14px; text-align: right; font-family: {FONT};">{requested_date}</td>
            </tr>
        </table>
        """,
    ]

    if note_title and note_body:
        blocks.append(
            f"""
        <div style="margin: 0 0 32px 0; padding: 20px; background-color: #f9fafb; border-left: 4px solid {accent}; border-radius: 4px;">
            <h2 style="color: {accent}; font-size: 16px; font-weight: 600; margin: 0 0 8px 0; font-family: {FONT};">
                {note_title}
            </h2>
            <p style="color: #374151; font-size: 15px; line-height: 22px; margin: 0; font-family: {FONT};">
                {note_body}
            </p>
        </div>
        """
        )

    blocks.append(primary_button(button_text, f"{frontend_url}/billing"))
    blocks.append(simple_footer())

    return compose_email(blocks)


def render_refund_request_received_email(
    user_name: str,
    product_name: str,
    refund_amount: str,
    order_id: str,
    requested_date: str,
    frontend_url: str = "https://app.rext.ai",
) -> str:
    """Confirm to the customer that their refund request is in the queue.

    Says explicitly that no money has moved, so an approval email arriving
    later is not read as a second refund.
    """
    return _status_email(
        heading="We've got your refund request",
        accent="#2563eb",
        intro=(
            f"Thanks — we've received your request to refund "
            f"<strong>{refund_amount}</strong> and our team will review it."
        ),
        user_name=user_name,
        product_name=product_name,
        refund_amount=refund_amount,
        order_id=order_id,
        requested_date=requested_date,
        note_title="What happens next",
        note_body=(
            "Nothing has been charged back yet. We'll email you as soon as a "
            "decision is made, and again once any refund has been sent to your "
            "payment method."
        ),
        frontend_url=frontend_url,
    )


def render_refund_approved_email(
    user_name: str,
    product_name: str,
    refund_amount: str,
    order_id: str,
    requested_date: str,
    admin_note: str = None,
    frontend_url: str = "https://app.rext.ai",
) -> str:
    """Tell the customer their request was approved.

    Approval and payout are separate steps, so this deliberately does not claim
    the money has been sent — `refund_issued` says that, once it has.
    """
    return _status_email(
        heading="Your refund has been approved",
        accent="#059669",
        intro=(f"Good news — we've approved your refund of <strong>{refund_amount}</strong>."),
        user_name=user_name,
        product_name=product_name,
        refund_amount=refund_amount,
        order_id=order_id,
        requested_date=requested_date,
        note_title="A note from our team" if admin_note else "What happens next",
        note_body=(
            admin_note
            or "We're processing the payment now. You'll get one more email "
            "once the money is on its way back to you."
        ),
        frontend_url=frontend_url,
    )


def render_refund_rejected_email(
    user_name: str,
    product_name: str,
    refund_amount: str,
    order_id: str,
    requested_date: str,
    admin_note: str = None,
    frontend_url: str = "https://app.rext.ai",
) -> str:
    """Tell the customer their request was declined, and why."""
    return _status_email(
        heading="About your refund request",
        accent="#b45309",
        intro=(
            f"We've reviewed your request to refund "
            f"<strong>{refund_amount}</strong>, and we're not able to approve "
            f"it on this occasion."
        ),
        user_name=user_name,
        product_name=product_name,
        refund_amount=refund_amount,
        order_id=order_id,
        requested_date=requested_date,
        note_title="Why" if admin_note else "If you think this is wrong",
        note_body=(admin_note or "Reply to this email and we'll take another look."),
        button_text="View your billing",
        frontend_url=frontend_url,
    )

"""
Example: Workspace Invitation Email

Demonstrates how to create a workspace invitation email using the template system.
This can be used as a reference for implementing actual templates.
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from emails.components import primary_button, simple_header, standard_footer
from emails.utils.renderer import compose_email


def create_invitation_email(
    workspace_name: str,
    inviter_name: str,
    inviter_email: str,
    invitation_url: str,
    workspace_logo_url: str = None,
) -> str:
    """
    Create a workspace invitation email.

    Args:
        workspace_name: Name of the workspace
        inviter_name: Name of the person sending invitation
        inviter_email: Email of the person sending invitation
        invitation_url: URL to accept the invitation
        workspace_logo_url: Optional logo URL for the workspace

    Returns:
        Complete HTML email string
    """
    # Build header (with or without logo)
    if workspace_logo_url:
        from emails.components.header import branded_header

        header_html = branded_header(workspace_logo_url, workspace_name)
    else:
        header_html = simple_header(workspace_name)

    # Build email content
    email_html = compose_email(
        [
            header_html,
            """
        <h1 style="color: #111827; font-size: 24px; font-weight: 600; margin: 0 0 16px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            You've been invited to join {workspace_name}
        </h1>
        """.format(workspace_name=workspace_name),
            """
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            <strong>{inviter_name}</strong> ({inviter_email}) has invited you to collaborate on <strong>{workspace_name}</strong>.
        </p>
        """.format(
                inviter_name=inviter_name,
                inviter_email=inviter_email,
                workspace_name=workspace_name,
            ),
            """
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Click the button below to accept this invitation and get started.
        </p>
        """,
            primary_button("Accept Invitation", invitation_url),
            """
        <div style="margin-top: 24px; padding: 16px; background-color: #f9fafb; border-radius: 6px; border-left: 4px solid #3b82f6;">
            <p style="color: #6b7280; font-size: 14px; line-height: 20px; margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                <strong>Note:</strong> This invitation will expire in 7 days. If you don't know {inviter_name}, you can safely ignore this email.
            </p>
        </div>
        """.format(inviter_name=inviter_name),
            standard_footer(company_name="Rext AI", company_address="Built for modern teams"),
        ],
        preview_text=f"You've been invited to join {workspace_name} on Rext AI",
    )

    return email_html


def main():
    """Generate example invitation email."""
    # Example data
    html = create_invitation_email(
        workspace_name="Acme Corporation",
        inviter_name="John Doe",
        inviter_email="john@acme.com",
        invitation_url="https://app.rext.com/invite/abc123xyz",
    )

    # Save to file
    output_path = Path(__file__).parent / "invitation_example_output.html"
    with open(output_path, "w") as f:
        f.write(html)

    print("✅ Invitation email generated successfully!")
    print(f"📄 Saved to: {output_path}")
    print("\n💡 Open the file in a browser to preview the email.")


if __name__ == "__main__":
    main()

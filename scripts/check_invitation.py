import asyncio
from sqlalchemy import select
from src.api.database.async_database import get_async_db_context
from src.api.models.user_models.invitations import UserInvitations


async def check_invitation():
    token = "5FFOkjRLMkU4ubzun9a9IgT2UXLn1bYnTNsrLcxOJVU"
    async with get_async_db_context() as db:
        result = await db.execute(
            select(UserInvitations).where(UserInvitations.invitation_token == token)
        )
        invitation = result.scalar_one_or_none()
        if invitation:
            print("Invitation found:")
            print(f" - Email: {invitation.email}")
            print(f" - Status: {invitation.status}")
            print(f" - Expires at: {invitation.expires_at}")
            print(f" - Workspace ID: {invitation.workspace_id}")
        else:
            print("Invitation not found by token.")

        # List all invitations to see if there's any pending one
        result = await db.execute(
            select(UserInvitations).order_by(UserInvitations.created_at.desc()).limit(5)
        )
        invitations = result.scalars().all()
        print("\nRecent invitations:")
        for inv in invitations:
            print(
                f" - {inv.email} | Status: {inv.status} | Token index: {inv.invitation_token[:10]}..."
            )


if __name__ == "__main__":
    asyncio.run(check_invitation())

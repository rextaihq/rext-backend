"""
Send Invitation Reminders

Sends the reminder of every pending workspace invitation that expires within two
days. The server's scheduler runs this once a day (src/tasks/scheduled_tasks.py,
job ``invitation_reminders``); this script runs the same job by hand:

    python -m src.scripts.send_invitation_reminders

The emails' logo is published to storage when the server starts. A run from here
has no such start, so it publishes the logo first; without it the emails show the
name as text.
"""

import asyncio

from emails.components.header import publish_logo
from src.api.tasks.invitation_reminder_task import run_invitation_reminders_task
from src.utils.logger import logger


async def main() -> int:
    """Main entry point for the script."""
    logger.info("Starting invitation reminder job...")
    if not await asyncio.to_thread(publish_logo):
        logger.warning("Email logo not published; the reminders show the name as text")
    reminded = await run_invitation_reminders_task()
    logger.info(f"Sent {reminded} invitation reminders")
    return reminded


if __name__ == "__main__":
    asyncio.run(main())

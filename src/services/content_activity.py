"""Recording what happens to content as events, not as state.

The dashboard's Recent Activities panel used to be a listing of the content
table: one row per article, ordered by when the article was created. That is a
picture of the present, and an activity feed is a record of the past, so three
things it was asked for could not work.

  - Changing an article's status rewrote `content.status` in place. The panel
    re-read the same row, so a draft becoming published looked like the entry
    had been overwritten rather than a new thing having happened.
  - Deleting an article left no trace. The delete is a soft one, so the row
    stayed and kept showing its pre-delete status; nothing said it was gone.
  - The author column came from a join on `created_by_user_id`, so it named
    whoever wrote the article rather than whoever performed the action.

Each of those is the same mistake, and none of them can be fixed by changing
the query. What is needed is a row per event, written when the event happens
and never revisited, holding the title and status *at that moment* so the entry
still reads correctly once the article itself is gone.

`audit_logs` is already that table - append-only, with an actor, an action,
old and new values, and a timestamp - so these events go there rather than into
a second log that would need its own retention, permissions and UI.

Failures here never fail the operation. `create_audit_log` swallows its own
errors and returns None; an article that saved but whose activity did not get
recorded is a gap in a feed, and refusing the save would be worse.
"""

from typing import Optional
from uuid import UUID

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.utils.audit_helper import create_audit_log

#: `resource_type` for every content event, and what the dashboard query
#: filters on. A constant because a typo in one of the writers would silently
#: drop those events out of the feed.
CONTENT_RESOURCE = "content"

ACTION_CREATED = "content.created"
ACTION_UPDATED = "content.updated"
ACTION_STATUS_CHANGED = "content.status_changed"
ACTION_PUBLISHED = "content.published"
ACTION_DELETED = "content.deleted"
#: Back from the workspace's trash (G45). Its entry shows the status it returns with.
ACTION_RESTORED = "content.restored"

#: The status a deletion reports. A deleted article's last real status was
#: whatever it happened to be - "draft", usually - and showing that would make
#: the entry indistinguishable from an ordinary edit in a panel that displays
#: the status and little else.
DELETED_STATUS = "deleted"


async def record_content_activity(
    db: AsyncSession,
    content,
    action: str,
    *,
    user_id: Optional[UUID],
    workspace_id: UUID,
    previous_status: Optional[str] = None,
    request: Optional[Request] = None,
) -> None:
    """Write one content event to the audit log.

    The title and status are copied into the row rather than referenced. That
    is the whole point: a week later the article may have been renamed, moved
    on to another status or deleted, and the entry still has to read as what
    happened at the time.
    """
    status = DELETED_STATUS if action == ACTION_DELETED else content.status

    await create_audit_log(
        db=db,
        user_id=user_id,
        action=action,
        resource_type=CONTENT_RESOURCE,
        resource_id=str(content.id),
        workspace_id=workspace_id,
        old_values={"status": previous_status} if previous_status is not None else None,
        new_values={"title": content.title, "status": status},
        request=request,
    )


def status_change_action(previous_status: Optional[str], new_status: Optional[str]) -> str:
    """Which action a status transition should be filed under.

    Publishing is called out separately because it is the transition anyone
    scanning the feed is actually looking for; everything else is a status
    change like any other.
    """
    if previous_status == new_status:
        return ACTION_UPDATED
    if new_status == "published":
        return ACTION_PUBLISHED
    return ACTION_STATUS_CHANGED


__all__ = [
    "ACTION_CREATED",
    "ACTION_DELETED",
    "ACTION_PUBLISHED",
    "ACTION_RESTORED",
    "ACTION_STATUS_CHANGED",
    "ACTION_UPDATED",
    "CONTENT_RESOURCE",
    "DELETED_STATUS",
    "record_content_activity",
    "status_change_action",
]

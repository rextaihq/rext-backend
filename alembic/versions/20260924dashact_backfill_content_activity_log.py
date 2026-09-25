"""Backfill content activity events so Recent Activities is not empty on deploy.

Revision ID: 20260924dashact
Revises: 20260922persona

The dashboard's Recent Activities panel used to read the content table
directly. It now reads the append-only audit log, which is what lets a status
change add an entry rather than overwrite one and a deletion show up at all.

Nothing has ever written content events to that log, so without this the panel
would be blank in every existing workspace until somebody happened to edit
something - a visible regression, and one that would read as the new query
being broken.

So one event is synthesised per existing article: a creation for those still
present, a deletion for those already soft-deleted, each dated to when it
actually happened and attributed to the article's creator. They carry
`audit_metadata->>'backfilled' = 'true'`, which is what the downgrade removes
and what tells anyone reading the log later that these were reconstructed
rather than observed - a backfilled creation is the only event that article
has, not the whole of its history.

gen_random_uuid() is in core Postgres from 13 on; this runs on 16.

Idempotent: re-running inserts nothing, because each statement skips articles
that already have an event of that kind.
"""

from alembic import op

revision = "20260924dashact"
down_revision = "20260922persona"
branch_labels = None
depends_on = None

_BACKFILL_CREATED = """
INSERT INTO audit_logs (
    id, user_id, full_name, user_email, action, resource_type, resource_id,
    workspace_id, new_values, audit_metadata, status, created_at
)
SELECT
    gen_random_uuid(),
    c.created_by_user_id,
    u.full_name,
    u.email,
    'content.created',
    'content',
    c.id::text,
    c.workspace_id,
    jsonb_build_object('title', c.title, 'status', c.status),
    jsonb_build_object('backfilled', true),
    'success',
    c.created_at
FROM content c
LEFT JOIN users u ON u.id = c.created_by_user_id
WHERE c.deleted_at IS NULL
  AND NOT EXISTS (
      SELECT 1 FROM audit_logs a
      WHERE a.resource_type = 'content'
        AND a.resource_id = c.id::text
        AND a.action = 'content.created'
  );
"""

# Deleted articles get the event that matters for them. Their creation is not
# backfilled: the panel is a feed of recent events, and an article that was
# created and then deleted should read as deleted, not as two entries.
_BACKFILL_DELETED = """
INSERT INTO audit_logs (
    id, user_id, full_name, user_email, action, resource_type, resource_id,
    workspace_id, old_values, new_values, audit_metadata, status, created_at
)
SELECT
    gen_random_uuid(),
    c.created_by_user_id,
    u.full_name,
    u.email,
    'content.deleted',
    'content',
    c.id::text,
    c.workspace_id,
    jsonb_build_object('status', c.status),
    jsonb_build_object('title', c.title, 'status', 'deleted'),
    jsonb_build_object('backfilled', true),
    'success',
    c.deleted_at
FROM content c
LEFT JOIN users u ON u.id = c.created_by_user_id
WHERE c.deleted_at IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM audit_logs a
      WHERE a.resource_type = 'content'
        AND a.resource_id = c.id::text
        AND a.action = 'content.deleted'
  );
"""

_REMOVE_BACKFILL = """
DELETE FROM audit_logs
WHERE resource_type = 'content'
  AND audit_metadata ->> 'backfilled' = 'true';
"""


def upgrade() -> None:
    op.execute(_BACKFILL_CREATED)
    op.execute(_BACKFILL_DELETED)


def downgrade() -> None:
    # Only the synthesised rows. Events recorded by the application since the
    # upgrade are real history and are left alone.
    op.execute(_REMOVE_BACKFILL)

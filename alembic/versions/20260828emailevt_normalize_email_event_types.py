"""normalize email_events.event_type (strip 'email.' prefix)

Revision ID: 20260828emailevt
Revises: 20260827perms
Create Date: 2026-08-28

Resend delivers webhook event types prefixed with ``email.`` (``email.opened``,
``email.delivered`` ...). The ingestion service used to store that raw value,
but ``EmailEvent.event_type`` is documented as canonical/un-prefixed and
``EmailAnalyticsService`` queries the un-prefixed form (``opened``, ``clicked``,
``complained``). As a result every open/click/complaint metric read 0.

The service is fixed to normalize on ingestion. This migration:

1. Rewrites existing rows to the canonical form.
2. Backfills ``email_logs.status = 'delivered'`` for logs that already received
   a delivered event but were left at ``sent`` (the old status-update code
   compared against the prefixed string and mostly still matched, but any rows
   that slipped through are repaired here).
"""
from alembic import op


revision = "20260828emailevt"
down_revision = "20260827perms"
branch_labels = None
depends_on = None


_CANONICAL_TYPES = (
    "sent",
    "delivered",
    "delivery_delayed",
    "bounced",
    "complained",
    "opened",
    "clicked",
)


def upgrade():
    # 1. Strip the "email." prefix from existing event rows.
    op.execute(
        r"""
        UPDATE email_events
        SET event_type = regexp_replace(event_type, '^email\.', '')
        WHERE event_type LIKE 'email.%'
        """
    )

    # 2. Repair delivered status for logs that have a delivered event but are
    #    still marked 'sent'.
    op.execute(
        """
        UPDATE email_logs el
        SET status = 'delivered',
            delivered_at = COALESCE(el.delivered_at, ev.created_at)
        FROM email_events ev
        WHERE ev.email_log_id = el.id
          AND ev.event_type = 'delivered'
          AND el.status = 'sent'
        """
    )


def downgrade():
    # Re-add the "email." prefix to canonical event types. The status backfill
    # in step 2 is not reversed (there is no way to know which rows it touched).
    types_list = ", ".join(f"'{t}'" for t in _CANONICAL_TYPES)
    op.execute(
        f"""
        UPDATE email_events
        SET event_type = 'email.' || event_type
        WHERE event_type IN ({types_list})
        """
    )

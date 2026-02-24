"""add_notification_composite_partial_indexes

Replace the four generic composite indexes on the ``notifications`` table with
six targeted partial indexes (``WHERE is_deleted = false AND is_archived = false``)
that match the exact query patterns used in ``get_notifications`` and
``get_unread_count``.

Changes
-------
* DROP   idx_user_created          (superseded by idx_notif_user_active_created)
* DROP   idx_user_type_created     (superseded by idx_notif_user_type_created w/ WHERE)
* DROP   idx_workspace_created     (superseded by idx_notif_user_workspace_created w/ WHERE)
* KEEP   idx_user_read_deleted     (used by mark-as-read path; column fixed: is_deleted)
* CREATE idx_notif_user_active_created   (user_id, created_at) WHERE is_deleted=false AND is_archived=false
* CREATE idx_notif_user_unread          (user_id) WHERE is_deleted=false AND is_archived=false AND is_read=false
* CREATE idx_notif_user_type_created    (user_id, type, created_at) WHERE ...
* CREATE idx_notif_user_category_created (user_id, category, created_at) WHERE ...
* CREATE idx_notif_user_workspace_created (user_id, workspace_id, created_at) WHERE ...

Revision ID: 20260224_add_notification_composite_partial_indexes
Revises: 20260224_migrate_preferences_to_jsonb
Create Date: 2026-02-24

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# ---------------------------------------------------------------------------
# Revision identifiers
# ---------------------------------------------------------------------------
revision: str = "20260224_add_notification_composite_partial_indexes"
down_revision: Union[str, Sequence[str], None] = "20260224_migrate_preferences_to_jsonb"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "notifications"
_ACTIVE_WHERE = "is_deleted = false AND is_archived = false"
_UNREAD_WHERE = "is_deleted = false AND is_archived = false AND is_read = false"


def upgrade() -> None:
    # ── Drop superseded generic indexes ──────────────────────────────────────
    op.drop_index("idx_user_created", table_name=_TABLE, if_exists=True)
    op.drop_index("idx_user_type_created", table_name=_TABLE, if_exists=True)
    op.drop_index("idx_workspace_created", table_name=_TABLE, if_exists=True)

    # The old idx_user_read_deleted referenced 'deleted_at' (a column from
    # SoftDeleteMixin) rather than the boolean 'is_deleted'. Drop and recreate
    # it correctly pointing at 'is_deleted'.
    op.drop_index("idx_user_read_deleted", table_name=_TABLE, if_exists=True)
    op.create_index(
        "idx_user_read_deleted",
        _TABLE,
        ["user_id", "is_read", "is_deleted"],
    )

    # ── Create new partial indexes ────────────────────────────────────────────
    # 1) Primary listing: ORDER BY created_at DESC for active notifications
    op.create_index(
        "idx_notif_user_active_created",
        _TABLE,
        ["user_id", "created_at"],
        postgresql_where=sa.text(_ACTIVE_WHERE),
    )

    # 2) Unread count / badge counter (most-frequent query)
    op.create_index(
        "idx_notif_user_unread",
        _TABLE,
        ["user_id"],
        postgresql_where=sa.text(_UNREAD_WHERE),
    )

    # 3) Type filter
    op.create_index(
        "idx_notif_user_type_created",
        _TABLE,
        ["user_id", "type", "created_at"],
        postgresql_where=sa.text(_ACTIVE_WHERE),
    )

    # 4) Category filter
    op.create_index(
        "idx_notif_user_category_created",
        _TABLE,
        ["user_id", "category", "created_at"],
        postgresql_where=sa.text(_ACTIVE_WHERE),
    )

    # 5) Workspace filter
    op.create_index(
        "idx_notif_user_workspace_created",
        _TABLE,
        ["user_id", "workspace_id", "created_at"],
        postgresql_where=sa.text(_ACTIVE_WHERE),
    )


def downgrade() -> None:
    # ── Drop the new partial indexes ──────────────────────────────────────────
    op.drop_index("idx_notif_user_workspace_created", table_name=_TABLE, if_exists=True)
    op.drop_index("idx_notif_user_category_created", table_name=_TABLE, if_exists=True)
    op.drop_index("idx_notif_user_type_created", table_name=_TABLE, if_exists=True)
    op.drop_index("idx_notif_user_unread", table_name=_TABLE, if_exists=True)
    op.drop_index("idx_notif_user_active_created", table_name=_TABLE, if_exists=True)

    # ── Restore idx_user_read_deleted to its original (incorrect) form ────────
    op.drop_index("idx_user_read_deleted", table_name=_TABLE, if_exists=True)
    op.create_index(
        "idx_user_read_deleted",
        _TABLE,
        ["user_id", "is_read", "deleted_at"],
    )

    # ── Restore the three superseded generic indexes ───────────────────────────
    op.create_index(
        "idx_user_created",
        _TABLE,
        ["user_id", "created_at"],
    )
    op.create_index(
        "idx_user_type_created",
        _TABLE,
        ["user_id", "type", "created_at"],
    )
    op.create_index(
        "idx_workspace_created",
        _TABLE,
        ["workspace_id", "created_at"],
    )

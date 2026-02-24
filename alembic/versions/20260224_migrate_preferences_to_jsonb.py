"""migrate_notification_preferences_to_jsonb

Replace 31 individual Boolean preference columns in ``notification_preferences``
with a single JSONB ``category_preferences`` column.  Existing row data is
migrated in-database using ``jsonb_build_object`` so no data is lost.

Revision ID: 20260224_migrate_preferences_to_jsonb
Revises: f9e8d7c6b5a4
Create Date: 2026-02-24

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# ---------------------------------------------------------------------------
# Revision identifiers
# ---------------------------------------------------------------------------
revision: str = "20260224_migrate_preferences_to_jsonb"
down_revision: Union[str, Sequence[str], None] = "f9e8d7c6b5a4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Columns being migrated out of the table
_BOOL_COLUMNS: list[tuple[str, bool]] = [
    # (column_name, default_value)
    # Workspace
    ("ws_invite_received", True),
    ("ws_invite_accepted", True),
    ("ws_role_changed", True),
    ("ws_member_removed", True),
    # Content Generation
    ("gen_started", True),
    ("gen_completed", True),
    ("gen_failed", True),
    ("gen_published", True),
    # Billing
    ("billing_payment_success", True),
    ("billing_payment_failed", True),
    ("billing_subscription_cancelled", True),
    ("billing_subscription_expiring", True),
    ("billing_trial_ending", True),
    ("billing_usage_limit_warning", True),
    ("billing_usage_limit_exceeded", True),
    # Knowledge Base
    ("kb_processing_completed", True),
    ("kb_processing_failed", True),
    # Extended email/in-app category toggles
    ("email_team_activity", True),
    ("in_app_team_activity", True),
    ("email_security_alerts", True),
    ("in_app_security_alerts", True),
    ("email_billing_updates", True),
    ("in_app_billing_updates", True),
    ("email_product_updates", False),
    ("in_app_product_updates", False),
    ("email_content_updates", True),
    ("in_app_content_updates", True),
    ("email_mentions", True),
    ("in_app_mentions", True),
    ("email_comments", True),
    ("in_app_comments", True),
]

_TABLE = "notification_preferences"


def upgrade() -> None:
    # ── Phase 1: Add nullable JSONB column ───────────────────────────────
    op.add_column(
        _TABLE,
        sa.Column("category_preferences", JSONB(), nullable=True),
    )

    # ── Phase 2: Migrate existing boolean column data into JSONB ─────────
    # Build the jsonb_build_object argument list from the column names.
    # Each column is cast to boolean explicitly to handle any stored-as-integer edge cases.
    jsonb_pairs = ", ".join(
        f"'{col}', {col}::boolean"
        for col, _ in _BOOL_COLUMNS
    )
    op.execute(
        f"UPDATE {_TABLE} SET category_preferences = jsonb_build_object({jsonb_pairs})"
    )

    # ── Phase 3: Enforce NOT NULL now that all rows have been populated ───
    op.alter_column(
        _TABLE,
        "category_preferences",
        nullable=False,
        server_default="{}",
    )

    # ── Phase 4: Drop the now-redundant boolean columns ───────────────────
    for col, _ in _BOOL_COLUMNS:
        op.drop_column(_TABLE, col)


def downgrade() -> None:
    # ── Phase 1: Re-add boolean columns with safe server defaults ─────────
    for col, default in _BOOL_COLUMNS:
        default_text = "true" if default else "false"
        op.add_column(
            _TABLE,
            sa.Column(
                col,
                sa.Boolean(),
                nullable=False,
                server_default=sa.text(default_text),
            ),
        )

    # ── Phase 2: Restore values from JSONB ───────────────────────────────
    for col, default in _BOOL_COLUMNS:
        default_text = "true" if default else "false"
        op.execute(
            f"""
            UPDATE {_TABLE}
            SET {col} = COALESCE((category_preferences->>'{col}')::boolean, {default_text})
            """
        )

    # ── Phase 3: Drop the JSONB column ────────────────────────────────────
    op.drop_column(_TABLE, "category_preferences")

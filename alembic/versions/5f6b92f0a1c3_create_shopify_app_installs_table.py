"""create shopify app installs table

Revision ID: 5f6b92f0a1c3
Revises: 9a9a7e36e5e0
Create Date: 2026-05-15 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "5f6b92f0a1c3"
down_revision: Union[str, Sequence[str], None] = "9a9a7e36e5e0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "shopify_app_installs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("shop_url", sa.String(length=255), nullable=False),
        sa.Column("access_token", sa.Text(), nullable=False),
        sa.Column("scopes", sa.String(), nullable=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("linked_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("linked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "installed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["linked_by"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspace.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("shop_url"),
    )
    op.create_index(
        op.f("ix_shopify_app_installs_shop_url"),
        "shopify_app_installs",
        ["shop_url"],
        unique=False,
    )
    op.create_index(
        op.f("ix_shopify_app_installs_workspace_id"),
        "shopify_app_installs",
        ["workspace_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f("ix_shopify_app_installs_workspace_id"),
        table_name="shopify_app_installs",
    )
    op.drop_index(
        op.f("ix_shopify_app_installs_shop_url"),
        table_name="shopify_app_installs",
    )
    op.drop_table("shopify_app_installs")

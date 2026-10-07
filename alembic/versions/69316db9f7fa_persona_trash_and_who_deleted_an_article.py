"""persona trash and who deleted an article

A workspace's trash (G45, rext-control #397): a deleted persona keeps its row with deleted_at
set, as a deleted article already does, and both record who deleted them. The partial indexes
serve the trash's listing and the purge, and stay small (only deleted rows).

Revision ID: 69316db9f7fa
Revises: 28a7cf7247ad
Create Date: 2026-10-07 10:44:25.196290

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "69316db9f7fa"
down_revision: Union[str, Sequence[str], None] = "28a7cf7247ad"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("content", sa.Column("deleted_by", sa.UUID(), nullable=True))
    op.create_index(
        "ix_content_trash",
        "content",
        ["workspace_id", "deleted_at"],
        unique=False,
        postgresql_where=sa.text("deleted_at IS NOT NULL"),
    )
    op.create_foreign_key(
        "content_deleted_by_fkey", "content", "users", ["deleted_by"], ["id"], ondelete="SET NULL"
    )
    op.add_column("persona", sa.Column("deleted_by", sa.UUID(), nullable=True))
    op.add_column("persona", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index(
        "ix_persona_trash",
        "persona",
        ["workspace_id", "deleted_at"],
        unique=False,
        postgresql_where=sa.text("deleted_at IS NOT NULL"),
    )
    op.create_foreign_key(
        "persona_deleted_by_fkey", "persona", "users", ["deleted_by"], ["id"], ondelete="SET NULL"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("persona_deleted_by_fkey", "persona", type_="foreignkey")
    op.drop_index(
        "ix_persona_trash", table_name="persona", postgresql_where=sa.text("deleted_at IS NOT NULL")
    )
    op.drop_column("persona", "deleted_at")
    op.drop_column("persona", "deleted_by")
    op.drop_constraint("content_deleted_by_fkey", "content", type_="foreignkey")
    op.drop_index(
        "ix_content_trash", table_name="content", postgresql_where=sa.text("deleted_at IS NOT NULL")
    )
    op.drop_column("content", "deleted_by")

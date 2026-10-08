"""add content_versions: an article's text as a save left it

Revision ID: 5526221cce30
Revises: f53595e1d014
Create Date: 2026-10-08 05:19:04.000000

FB2.25 (revnix/rext-control#706), part four: the editor's history. A new, empty table; no
existing row changes. One row is an article's title, introduction, body and images as a save
left them, with who made it and how (generation, edit, restore, publish). Rows go with their
article (ON DELETE CASCADE) and outlive their maker's account (ON DELETE SET NULL).

The downgrade drops the table and the versions in it.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5526221cce30"
down_revision: Union[str, Sequence[str], None] = "f53595e1d014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "content_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("content_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("introduction", sa.Text(), nullable=True),
        sa.Column("body_markdown", sa.Text(), nullable=True),
        sa.Column("body_html", sa.Text(), nullable=True),
        sa.Column("images_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("word_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["content_id"], ["content.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspace.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id"),
    )
    op.create_index(
        "ix_content_versions_content_created", "content_versions", ["content_id", "created_at"]
    )
    op.create_index("ix_content_versions_workspace_id", "content_versions", ["workspace_id"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_content_versions_workspace_id", table_name="content_versions")
    op.drop_index("ix_content_versions_content_created", table_name="content_versions")
    op.drop_table("content_versions")

"""Add content.persona_id — the author persona chosen in the outline step.

Revision ID: 20260922persona
Revises: 20260921bvdelete

The persona a reader sees credited on the published post is chosen in the
content outline step, long before publishing, and has to survive republishing
months later. Reading it back out of the LangGraph thread at publish time is
not an option — the thread is an implementation detail of one run — so it is
stored on the content row.

ON DELETE SET NULL: deleting a persona must not delete articles they authored;
the post simply loses its remembered author and falls back to the site default.

Idempotent.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260922persona"
down_revision = "20260921bvdelete"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    columns = [c["name"] for c in inspector.get_columns("content")]
    if "persona_id" not in columns:
        op.add_column(
            "content",
            sa.Column(
                "persona_id",
                postgresql.UUID(as_uuid=True),
                nullable=True,
                comment="Author persona selected during the content outline step",
            ),
        )

    fk_names = [fk["name"] for fk in inspector.get_foreign_keys("content")]
    if "fk_content_persona_id" not in fk_names:
        op.create_foreign_key(
            "fk_content_persona_id",
            "content",
            "persona",
            ["persona_id"],
            ["id"],
            ondelete="SET NULL",
        )

    index_names = [idx["name"] for idx in inspector.get_indexes("content")]
    if "ix_content_persona_id" not in index_names:
        op.create_index("ix_content_persona_id", "content", ["persona_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_content_persona_id", table_name="content")
    op.drop_constraint("fk_content_persona_id", "content", type_="foreignkey")
    op.drop_column("content", "persona_id")

"""content titles unique only among live hand-written articles

Revision ID: 28a7cf7247ad
Revises: 3d51938f0c7e
Create Date: 2026-10-07 02:22:22.521592

G55 (revnix/rext-control#498). uq_content_workspace_title made every title unique in a workspace,
the trash included, so a generated article whose title the workspace already had was refused and
lost: the title step offers the same titles for a keyword. A title stays unique only among the live
articles written by hand (no langgraph_thread_id); a generated one may repeat it, and its slug stays
unique (uq_content_workspace_slug). No rows change.

The downgrade puts the old constraint back, which fails once two articles share a title.
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "28a7cf7247ad"
down_revision: Union[str, Sequence[str], None] = "3d51938f0c7e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_constraint(op.f("uq_content_workspace_title"), "content", type_="unique")
    op.create_index(
        "uq_content_workspace_title_by_hand",
        "content",
        ["workspace_id", "title"],
        unique=True,
        postgresql_where=sa.text("langgraph_thread_id IS NULL AND deleted_at IS NULL"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        "uq_content_workspace_title_by_hand",
        table_name="content",
        postgresql_where=sa.text("langgraph_thread_id IS NULL AND deleted_at IS NULL"),
    )
    op.create_unique_constraint(
        op.f("uq_content_workspace_title"),
        "content",
        ["workspace_id", "title"],
        postgresql_nulls_not_distinct=False,
    )

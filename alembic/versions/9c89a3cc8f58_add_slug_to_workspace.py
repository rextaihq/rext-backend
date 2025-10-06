"""add_slug_to_workspace

Revision ID: 9c89a3cc8f58
Revises: h2i3j4k5l6m7
Create Date: 2025-10-04 18:53:20.549951

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9c89a3cc8f58'
down_revision: Union[str, Sequence[str], None] = 'h2i3j4k5l6m7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add slug column as nullable first
    op.add_column('workspace', sa.Column('slug', sa.String(), nullable=True))

    # Create index for slug
    op.create_index('ix_workspace_slug', 'workspace', ['slug'])

    # Populate existing workspaces with slugs
    connection = op.get_bind()
    result = connection.execute(sa.text("SELECT id, name FROM workspace"))

    from src.utils.slug_utils import generate_workspace_slug

    # Generate slugs for existing workspaces
    for row in result:
        workspace_id = row[0]
        name = row[1]
        base_slug = generate_workspace_slug(name)

        # Check for uniqueness and append number if needed
        slug = base_slug
        counter = 1
        while connection.execute(
            sa.text("SELECT 1 FROM workspace WHERE slug = :slug AND id != :id"),
            {"slug": slug, "id": workspace_id}
        ).fetchone():
            slug = f"{base_slug}-{counter}"
            counter += 1

        # Update workspace with slug
        connection.execute(
            sa.text("UPDATE workspace SET slug = :slug WHERE id = :id"),
            {"slug": slug, "id": workspace_id}
        )

    # Now make slug not nullable and unique
    op.alter_column('workspace', 'slug', nullable=False)
    op.create_unique_constraint('uq_workspace_slug', 'workspace', ['slug'])


def downgrade() -> None:
    """Downgrade schema."""
    # Drop unique constraint
    op.drop_constraint('uq_workspace_slug', 'workspace', type_='unique')

    # Drop index
    op.drop_index('ix_workspace_slug', 'workspace')

    # Drop column
    op.drop_column('workspace', 'slug')

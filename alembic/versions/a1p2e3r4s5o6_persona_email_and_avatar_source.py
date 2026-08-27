"""Add email and avatar_source to persona.

A persona carried one avatar_url and nothing to say where the picture came
from, so a photograph of the person and a generated placeholder were stored
identically and the interface could not tell a reader which they were looking
at. avatar_source records that.

email exists so a Gravatar can be derived for someone the crawl found no
picture of, and so a person who has one can keep it when their site publishes
no photograph at all.

Revision ID: a1p2e3r4s5o6
Revises: f0c503357612
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1p2e3r4s5o6"
down_revision: Union[str, Sequence[str], None] = "f0c503357612"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Both nullable: every existing persona predates them, and a picture whose
    # origin was never recorded should read as unknown rather than as a claim.
    op.add_column("persona", sa.Column("avatar_source", sa.String(20), nullable=True))
    op.add_column("persona", sa.Column("email", sa.String(320), nullable=True))


def downgrade() -> None:
    op.drop_column("persona", "email")
    op.drop_column("persona", "avatar_source")

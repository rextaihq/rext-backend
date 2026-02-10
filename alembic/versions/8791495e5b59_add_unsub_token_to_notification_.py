"""add_unsub_token_to_notification_preferences.py

Revision ID: 8791495e5b59
Revises: d26fdfa01a6d
Create Date: 2026-02-10 01:01:38.193405

"""
import secrets
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8791495e5b59'
down_revision: Union[str, Sequence[str], None] = 'd26fdfa01a6d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add column as nullable
    op.add_column(
        'notification_preferences',
        sa.Column('unsubscribe_token', sa.String(), nullable=True)
    )

    # 2. Backfill existing rows with secure tokens
    connection = op.get_bind()
    rows = connection.execute(
        sa.text("SELECT id FROM notification_preferences")
    ).fetchall()

    for row in rows:
        connection.execute(
            sa.text(
                """
                UPDATE notification_preferences
                SET unsubscribe_token = :token
                WHERE id = :id
                """
            ),
            {
                "token": secrets.token_urlsafe(32),
                "id": row.id,
            },
        )

    # 3. Enforce NOT NULL
    op.alter_column(
        'notification_preferences',
        'unsubscribe_token',
        nullable=False
    )

    # 4. Add UNIQUE constraint
    op.create_unique_constraint(
        'uq_notification_preferences_unsubscribe_token',
        'notification_preferences',
        ['unsubscribe_token']
    )
def downgrade() -> None:
    op.drop_constraint(
        'uq_notification_preferences_unsubscribe_token',
        'notification_preferences',
        type_='unique'
    )
    op.drop_column('notification_preferences', 'unsubscribe_token')

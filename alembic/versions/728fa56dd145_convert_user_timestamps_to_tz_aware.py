"""convert_user_timestamps_to_tz_aware

Revision ID: 728fa56dd145
Revises: 428689ad2535
Create Date: 2026-02-10 18:25:06.573398

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '728fa56dd145'
down_revision: Union[str, Sequence[str], None] = '428689ad2535'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Users table
    op.execute("ALTER TABLE users ALTER COLUMN password_changed_at TYPE TIMESTAMP WITH TIME ZONE USING password_changed_at AT TIME ZONE 'UTC'")
    op.execute("ALTER TABLE users ALTER COLUMN locked_until TYPE TIMESTAMP WITH TIME ZONE USING locked_until AT TIME ZONE 'UTC'")
    op.execute("ALTER TABLE users ALTER COLUMN email_verified_at TYPE TIMESTAMP WITH TIME ZONE USING email_verified_at AT TIME ZONE 'UTC'")
    op.execute("ALTER TABLE users ALTER COLUMN last_login_at TYPE TIMESTAMP WITH TIME ZONE USING last_login_at AT TIME ZONE 'UTC'")
    op.execute("ALTER TABLE users ALTER COLUMN created_at TYPE TIMESTAMP WITH TIME ZONE USING created_at AT TIME ZONE 'UTC'")
    op.execute("ALTER TABLE users ALTER COLUMN updated_at TYPE TIMESTAMP WITH TIME ZONE USING updated_at AT TIME ZONE 'UTC'")
    op.execute("ALTER TABLE users ALTER COLUMN deactivated_at TYPE TIMESTAMP WITH TIME ZONE USING deactivated_at AT TIME ZONE 'UTC'")
    op.execute("ALTER TABLE users ALTER COLUMN deleted_at TYPE TIMESTAMP WITH TIME ZONE USING deleted_at AT TIME ZONE 'UTC'")

    # User Sessions table
    op.execute("ALTER TABLE user_sessions ALTER COLUMN created_at TYPE TIMESTAMP WITH TIME ZONE USING created_at AT TIME ZONE 'UTC'")
    op.execute("ALTER TABLE user_sessions ALTER COLUMN last_activity_at TYPE TIMESTAMP WITH TIME ZONE USING last_activity_at AT TIME ZONE 'UTC'")
    op.execute("ALTER TABLE user_sessions ALTER COLUMN expires_at TYPE TIMESTAMP WITH TIME ZONE USING expires_at AT TIME ZONE 'UTC'")
    op.execute("ALTER TABLE user_sessions ALTER COLUMN revoked_at TYPE TIMESTAMP WITH TIME ZONE USING revoked_at AT TIME ZONE 'UTC'")


def downgrade() -> None:
    """Downgrade schema."""
    # Users table
    op.execute("ALTER TABLE users ALTER COLUMN password_changed_at TYPE TIMESTAMP WITHOUT TIME ZONE")
    op.execute("ALTER TABLE users ALTER COLUMN locked_until TYPE TIMESTAMP WITHOUT TIME ZONE")
    op.execute("ALTER TABLE users ALTER COLUMN email_verified_at TYPE TIMESTAMP WITHOUT TIME ZONE")
    op.execute("ALTER TABLE users ALTER COLUMN last_login_at TYPE TIMESTAMP WITHOUT TIME ZONE")
    op.execute("ALTER TABLE users ALTER COLUMN created_at TYPE TIMESTAMP WITHOUT TIME ZONE")
    op.execute("ALTER TABLE users ALTER COLUMN updated_at TYPE TIMESTAMP WITHOUT TIME ZONE")
    op.execute("ALTER TABLE users ALTER COLUMN deactivated_at TYPE TIMESTAMP WITHOUT TIME ZONE")
    op.execute("ALTER TABLE users ALTER COLUMN deleted_at TYPE TIMESTAMP WITHOUT TIME ZONE")

    # User Sessions table
    op.execute("ALTER TABLE user_sessions ALTER COLUMN created_at TYPE TIMESTAMP WITHOUT TIME ZONE")
    op.execute("ALTER TABLE user_sessions ALTER COLUMN last_activity_at TYPE TIMESTAMP WITHOUT TIME ZONE")
    op.execute("ALTER TABLE user_sessions ALTER COLUMN expires_at TYPE TIMESTAMP WITHOUT TIME ZONE")
    op.execute("ALTER TABLE user_sessions ALTER COLUMN revoked_at TYPE TIMESTAMP WITHOUT TIME ZONE")

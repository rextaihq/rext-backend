"""encrypt_integration_credentials

Revision ID: 77d8aee32a44
Revises: 41a6d104b66f
Create Date: 2026-02-11 15:36:50.731152

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '77d8aee32a44'
down_revision: Union[str, Sequence[str], None] = '41a6d104b66f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


import os
from cryptography.fernet import Fernet

def upgrade() -> None:
    """Encrypt existing plaintext credential values."""
    conn = op.get_bind()
    key = os.environ.get("FIELD_ENCRYPTION_KEY")
    if not key:
        raise RuntimeError("FIELD_ENCRYPTION_KEY must be set before running this migration")
    fernet = Fernet(key.encode())

    # Get data from integrations table
    results = conn.execute(
        sa.text("SELECT id, app_password, api_key FROM integrations WHERE app_password IS NOT NULL OR api_key IS NOT NULL")
    ).fetchall()

    for row in results:
        updates = {}
        # Only encrypt if not already encrypted (Fernet tokens start with gAAAA)
        if row.app_password and not row.app_password.startswith("gAAAA"):
            updates["app_password"] = fernet.encrypt(row.app_password.encode("utf-8")).decode("utf-8")
        if row.api_key and not row.api_key.startswith("gAAAA"):
            updates["api_key"] = fernet.encrypt(row.api_key.encode("utf-8")).decode("utf-8")

        if updates:
            set_clause = ", ".join(f"{k} = :{k}" for k in updates)
            query = sa.text(f"UPDATE integrations SET {set_clause} WHERE id = :id")
            conn.execute(query, {**updates, "id": row.id})

def downgrade() -> None:
    """Decrypt credential values back to plaintext."""
    conn = op.get_bind()
    key = os.environ.get("FIELD_ENCRYPTION_KEY")
    if not key:
        raise RuntimeError("FIELD_ENCRYPTION_KEY must be set before running this migration")
    fernet = Fernet(key.encode())

    results = conn.execute(
        sa.text("SELECT id, app_password, api_key FROM integrations WHERE app_password IS NOT NULL OR api_key IS NOT NULL")
    ).fetchall()

    for row in results:
        updates = {}
        # Only decrypt if it looks like a Fernet token
        if row.app_password and row.app_password.startswith("gAAAA"):
            try:
                updates["app_password"] = fernet.decrypt(row.app_password.encode("utf-8")).decode("utf-8")
            except Exception:
                pass
        if row.api_key and row.api_key.startswith("gAAAA"):
            try:
                updates["api_key"] = fernet.decrypt(row.api_key.encode("utf-8")).decode("utf-8")
            except Exception:
                pass

        if updates:
            set_clause = ", ".join(f"{k} = :{k}" for k in updates)
            query = sa.text(f"UPDATE integrations SET {set_clause} WHERE id = :id")
            conn.execute(query, {**updates, "id": row.id})

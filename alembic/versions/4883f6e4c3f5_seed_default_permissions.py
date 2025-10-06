"""seed_default_permissions

Revision ID: 4883f6e4c3f5
Revises: cc3bde5553b9
Create Date: 2025-10-01 21:20:42.777231

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy import orm
from sqlalchemy.ext.declarative import declarative_base
import uuid
from datetime import datetime

# revision identifiers, used by Alembic.
revision: str = '4883f6e4c3f5'
down_revision: Union[str, Sequence[str], None] = 'cc3bde5553b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

Base = declarative_base()


# Define Permission model for seeding (lightweight version)
class Permission(Base):
    __tablename__ = 'permissions'
    id = sa.Column(sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True)
    name = sa.Column(sa.String(150), unique=True, nullable=False)
    display_name = sa.Column(sa.String(200))
    description = sa.Column(sa.Text)
    resource = sa.Column(sa.String(50))
    action = sa.Column(sa.String(50))
    created_at = sa.Column(sa.TIMESTAMP, nullable=False)


def upgrade() -> None:
    """Add default permissions."""
    bind = op.get_bind()
    session = orm.Session(bind=bind)

    permissions_to_create = [
        {"name": "content.create", "display_name": "Create Content",
         "description": "Allows creating new content", "resource": "content", "action": "create"},
        {"name": "content.update", "display_name": "Update Content",
         "description": "Allows updating content", "resource": "content", "action": "update"},
        {"name": "content.delete", "display_name": "Delete Content",
         "description": "Allows deleting content", "resource": "content", "action": "delete"},
        {"name": "topic.create", "display_name": "Create Topic",
         "description": "Allows creating new topics", "resource": "topic", "action": "create"},
        {"name": "topic.update", "display_name": "Update Topic",
         "description": "Allows updating topics", "resource": "topic", "action": "update"},
        {"name": "topic.delete", "display_name": "Delete Topic",
         "description": "Allows deleting topics", "resource": "topic", "action": "delete"},
    ]

    for perm_data in permissions_to_create:
        # Check if permission already exists (idempotent)
        exists = session.query(Permission).filter_by(name=perm_data["name"]).first()
        if not exists:
            perm = Permission(
                id=uuid.uuid4(),
                name=perm_data["name"],
                display_name=perm_data["display_name"],
                description=perm_data["description"],
                resource=perm_data["resource"],
                action=perm_data["action"],
                created_at=datetime.utcnow()
            )
            session.add(perm)

    session.commit()


def downgrade() -> None:
    """Remove default permissions."""
    bind = op.get_bind()
    session = orm.Session(bind=bind)

    permission_names = [
        "content.create", "content.update", "content.delete",
        "topic.create", "topic.update", "topic.delete"
    ]

    for name in permission_names:
        session.query(Permission).filter_by(name=name).delete()

    session.commit()

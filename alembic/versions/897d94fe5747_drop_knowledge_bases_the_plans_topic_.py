"""drop knowledge bases, the plans' topic and knowledge limits and the kb notification settings

Revision ID: 897d94fe5747
Revises: cd6b868bf9d7
Create Date: 2026-10-06 16:34:29.604855

Knowledge bases and the Topic Builder are removed from the product
(rext-control#367; the founder, 2026-10-06: "remove these completely", and
"there are no customers at all, we have not launched yet"). This drops their
tables (website, knowledge_files and text_knowledge, then knowledge_base),
the plans' max_topics and max_knowledge_items, and email_preferences'
kb_processing_* columns. It also deletes what named them: knowledge-base
notifications, the kb_processing_* keys of notification_preferences, and any
topic.* or knowledge.* permission (role_permissions follows by cascade).

No data is kept, by the founder's decision. The downgrade puts the tables and
columns back empty; the deleted rows do not come back.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "897d94fe5747"
down_revision: Union[str, Sequence[str], None] = "cd6b868bf9d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # What named the removed features, while the columns it lives in still exist.
    op.execute(
        "DELETE FROM notifications"
        " WHERE type = 'kb'"
        " OR category IN ('kb_processing_completed', 'kb_processing_failed')"
    )
    op.execute(
        "UPDATE notification_preferences"
        " SET category_preferences = category_preferences"
        " - 'kb_processing_completed' - 'kb_processing_failed'"
        " WHERE category_preferences ?| array['kb_processing_completed', 'kb_processing_failed']"
    )
    op.execute(
        "DELETE FROM permissions"
        " WHERE resource IN ('topic', 'knowledge')"
        " OR name LIKE 'topic.%' OR name LIKE 'knowledge.%'"
    )

    # The tables that point at knowledge_base go first.
    op.drop_index(op.f("ix_website_knowledge_base_id"), table_name="website")
    op.drop_index(op.f("ix_website_workspace_id"), table_name="website")
    op.drop_index(op.f("ix_website_workspace_kb"), table_name="website")
    op.drop_index(op.f("ix_website_workspace_url"), table_name="website")
    op.drop_table("website")
    op.drop_index(op.f("ix_knowledge_files_file_hash"), table_name="knowledge_files")
    op.drop_index(op.f("ix_knowledge_files_knowledge_base_id"), table_name="knowledge_files")
    op.drop_index(op.f("ix_knowledge_files_workspace_hash"), table_name="knowledge_files")
    op.drop_index(op.f("ix_knowledge_files_workspace_id"), table_name="knowledge_files")
    op.drop_index(op.f("ix_knowledge_files_workspace_kb"), table_name="knowledge_files")
    op.drop_table("knowledge_files")
    op.drop_index(op.f("ix_text_knowledge_knowledge_base_id"), table_name="text_knowledge")
    op.drop_index(op.f("ix_text_knowledge_workspace_id"), table_name="text_knowledge")
    op.drop_index(op.f("ix_text_knowledge_workspace_kb"), table_name="text_knowledge")
    op.drop_table("text_knowledge")
    op.drop_index(op.f("ix_knowledge_base_created_by_user_id"), table_name="knowledge_base")
    op.drop_index(op.f("ix_knowledge_base_workspace_id"), table_name="knowledge_base")
    op.drop_index(op.f("ix_knowledge_base_workspace_name"), table_name="knowledge_base")
    op.drop_index(op.f("ix_knowledge_base_workspace_type"), table_name="knowledge_base")
    op.drop_table("knowledge_base")
    op.drop_column("email_preferences", "kb_processing_failed")
    op.drop_column("email_preferences", "kb_processing_completed")
    op.drop_column("subscription_plans", "max_topics")
    op.drop_column("subscription_plans", "max_knowledge_items")


def downgrade() -> None:
    """Downgrade schema: the tables and columns back, empty (the rows are not kept)."""
    op.add_column(
        "subscription_plans",
        sa.Column("max_knowledge_items", sa.INTEGER(), autoincrement=False, nullable=True),
    )
    op.add_column(
        "subscription_plans",
        sa.Column("max_topics", sa.INTEGER(), autoincrement=False, nullable=True),
    )
    op.add_column(
        "email_preferences",
        sa.Column(
            "kb_processing_completed",
            sa.BOOLEAN(),
            server_default=sa.text("true"),
            autoincrement=False,
            nullable=False,
        ),
    )
    op.add_column(
        "email_preferences",
        sa.Column(
            "kb_processing_failed",
            sa.BOOLEAN(),
            server_default=sa.text("true"),
            autoincrement=False,
            nullable=False,
        ),
    )
    op.create_table(
        "knowledge_base",
        sa.Column("id", sa.UUID(), autoincrement=False, nullable=False),
        sa.Column("workspace_id", sa.UUID(), autoincrement=False, nullable=False),
        sa.Column("name", sa.VARCHAR(length=255), autoincrement=False, nullable=False),
        sa.Column("description", sa.TEXT(), autoincrement=False, nullable=True),
        sa.Column("type", sa.VARCHAR(length=50), autoincrement=False, nullable=False),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            autoincrement=False,
            nullable=False,
        ),
        sa.Column(
            "updated_at", postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=True
        ),
        sa.Column("created_by_user_id", sa.UUID(), autoincrement=False, nullable=True),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name=op.f("knowledge_base_created_by_user_id_fkey"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspace.id"],
            name=op.f("knowledge_base_workspace_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("knowledge_base_pkey")),
        sa.UniqueConstraint(
            "id",
            name=op.f("knowledge_base_id_key"),
            postgresql_include=[],
            postgresql_nulls_not_distinct=False,
        ),
    )
    op.create_index(
        op.f("ix_knowledge_base_workspace_type"),
        "knowledge_base",
        ["workspace_id", "type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_knowledge_base_workspace_name"),
        "knowledge_base",
        ["workspace_id", "name"],
        unique=False,
    )
    op.create_index(
        op.f("ix_knowledge_base_workspace_id"), "knowledge_base", ["workspace_id"], unique=False
    )
    op.create_index(
        op.f("ix_knowledge_base_created_by_user_id"),
        "knowledge_base",
        ["created_by_user_id"],
        unique=False,
    )
    op.create_table(
        "knowledge_files",
        sa.Column("id", sa.UUID(), autoincrement=False, nullable=False),
        sa.Column("workspace_id", sa.UUID(), autoincrement=False, nullable=False),
        sa.Column("file_name", sa.VARCHAR(), autoincrement=False, nullable=False),
        sa.Column("file_type", sa.VARCHAR(), autoincrement=False, nullable=False),
        sa.Column("file_size", sa.INTEGER(), autoincrement=False, nullable=False),
        sa.Column("file_path", sa.VARCHAR(), autoincrement=False, nullable=False),
        sa.Column(
            "status",
            sa.VARCHAR(),
            server_default=sa.text("'completed'::character varying"),
            autoincrement=False,
            nullable=False,
        ),
        sa.Column("char_count", sa.INTEGER(), autoincrement=False, nullable=True),
        sa.Column("word_count", sa.INTEGER(), autoincrement=False, nullable=True),
        sa.Column(
            "created_at", postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=False
        ),
        sa.Column("file_hash", sa.VARCHAR(length=64), autoincrement=False, nullable=True),
        sa.Column("mime_type", sa.VARCHAR(length=100), autoincrement=False, nullable=True),
        sa.Column("chunk_count", sa.INTEGER(), autoincrement=False, nullable=True),
        sa.Column("knowledge_base_id", sa.UUID(), autoincrement=False, nullable=False),
        sa.Column(
            "updated_at", postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=True
        ),
        sa.ForeignKeyConstraint(
            ["knowledge_base_id"],
            ["knowledge_base.id"],
            name=op.f("fk_knowledge_files_knowledge_base"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspace.id"],
            name=op.f("knowledge_files_workspace_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("knowledge_files_pkey")),
        sa.UniqueConstraint(
            "id",
            name=op.f("knowledge_files_id_key"),
            postgresql_include=[],
            postgresql_nulls_not_distinct=False,
        ),
    )
    op.create_index(
        op.f("ix_knowledge_files_workspace_kb"),
        "knowledge_files",
        ["workspace_id", "knowledge_base_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_knowledge_files_workspace_id"), "knowledge_files", ["workspace_id"], unique=False
    )
    op.create_index(
        op.f("ix_knowledge_files_workspace_hash"),
        "knowledge_files",
        ["workspace_id", "file_hash"],
        unique=False,
    )
    op.create_index(
        op.f("ix_knowledge_files_knowledge_base_id"),
        "knowledge_files",
        ["knowledge_base_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_knowledge_files_file_hash"), "knowledge_files", ["file_hash"], unique=False
    )
    op.create_table(
        "text_knowledge",
        sa.Column("id", sa.UUID(), autoincrement=False, nullable=False),
        sa.Column("workspace_id", sa.UUID(), autoincrement=False, nullable=False),
        sa.Column(
            "title",
            sa.VARCHAR(),
            server_default=sa.text("'Untitled Note'::character varying"),
            autoincrement=False,
            nullable=False,
        ),
        sa.Column("content", sa.TEXT(), autoincrement=False, nullable=False),
        sa.Column(
            "tags", postgresql.JSONB(astext_type=sa.Text()), autoincrement=False, nullable=True
        ),
        sa.Column(
            "custom_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            autoincrement=False,
            nullable=True,
        ),
        sa.Column(
            "created_at", postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=False
        ),
        sa.Column(
            "updated_at", postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=True
        ),
        sa.Column("knowledge_base_id", sa.UUID(), autoincrement=False, nullable=False),
        sa.ForeignKeyConstraint(
            ["knowledge_base_id"],
            ["knowledge_base.id"],
            name=op.f("fk_text_knowledge_knowledge_base"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspace.id"],
            name=op.f("text_knowledge_workspace_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("text_knowledge_pkey")),
        sa.UniqueConstraint(
            "id",
            name=op.f("text_knowledge_id_key"),
            postgresql_include=[],
            postgresql_nulls_not_distinct=False,
        ),
    )
    op.create_index(
        op.f("ix_text_knowledge_workspace_kb"),
        "text_knowledge",
        ["workspace_id", "knowledge_base_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_text_knowledge_workspace_id"), "text_knowledge", ["workspace_id"], unique=False
    )
    op.create_index(
        op.f("ix_text_knowledge_knowledge_base_id"),
        "text_knowledge",
        ["knowledge_base_id"],
        unique=False,
    )
    op.create_table(
        "website",
        sa.Column("id", sa.UUID(), autoincrement=False, nullable=False),
        sa.Column("workspace_id", sa.UUID(), autoincrement=False, nullable=False),
        sa.Column("url", sa.VARCHAR(), autoincrement=False, nullable=False),
        sa.Column(
            "status",
            sa.VARCHAR(),
            server_default=sa.text("'process'::character varying"),
            autoincrement=False,
            nullable=False,
        ),
        sa.Column("char_count", sa.INTEGER(), autoincrement=False, nullable=True),
        sa.Column("word_count", sa.INTEGER(), autoincrement=False, nullable=True),
        sa.Column("knowledge_base_id", sa.UUID(), autoincrement=False, nullable=False),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            autoincrement=False,
            nullable=False,
        ),
        sa.Column(
            "updated_at", postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=True
        ),
        sa.Column("title", sa.VARCHAR(length=255), autoincrement=False, nullable=True),
        sa.ForeignKeyConstraint(
            ["knowledge_base_id"],
            ["knowledge_base.id"],
            name=op.f("fk_website_knowledge_base"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspace.id"],
            name=op.f("website_workspace_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("website_pkey")),
        sa.UniqueConstraint(
            "id",
            name=op.f("website_id_key"),
            postgresql_include=[],
            postgresql_nulls_not_distinct=False,
        ),
    )
    op.create_index(
        op.f("ix_website_workspace_url"), "website", ["workspace_id", "url"], unique=False
    )
    op.create_index(
        op.f("ix_website_workspace_kb"),
        "website",
        ["workspace_id", "knowledge_base_id"],
        unique=False,
    )
    op.create_index(op.f("ix_website_workspace_id"), "website", ["workspace_id"], unique=False)
    op.create_index(
        op.f("ix_website_knowledge_base_id"), "website", ["knowledge_base_id"], unique=False
    )

"""Remove Media Library tables and permissions."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260915media"
down_revision = "20260914integration"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS content_media")
    op.execute("DROP TABLE IF EXISTS media")
    op.execute("DELETE FROM role_permissions WHERE permission_id IN (SELECT id FROM permissions WHERE name LIKE 'media.%')")
    op.execute("DELETE FROM permissions WHERE name LIKE 'media.%'")


def downgrade() -> None:
    op.create_table("media", sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False), sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False), sa.Column("filename", sa.String(255), nullable=False), sa.Column("original_filename", sa.String(255), nullable=False), sa.Column("file_type", sa.String(100), nullable=False), sa.Column("file_size", sa.BigInteger(), nullable=False), sa.Column("file_extension", sa.String(10)), sa.Column("storage_backend", sa.String(20), server_default="r2"), sa.Column("storage_path", sa.String(500), nullable=False), sa.Column("storage_bucket", sa.String(100)), sa.Column("public_url", sa.String(500)), sa.Column("title", sa.String(255)), sa.Column("description", sa.Text()), sa.Column("alt_text", sa.String(500)), sa.Column("file_metadata", postgresql.JSONB(), server_default="{}"), sa.Column("folder", sa.String(255)), sa.Column("tags", postgresql.ARRAY(sa.String()), server_default="{}"), sa.Column("is_public", sa.Boolean(), server_default=sa.text("false")), sa.Column("access_level", sa.String(20), server_default="private"), sa.Column("thumbnail_path", sa.String(500)), sa.Column("thumbnail_url", sa.String(500)), sa.Column("width", sa.Integer()), sa.Column("height", sa.Integer()), sa.Column("processing_status", sa.String(20), server_default="pending"), sa.Column("processing_error", sa.Text()), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")), sa.Column("updated_at", sa.DateTime(timezone=True)), sa.Column("deleted_at", sa.DateTime(timezone=True)))
    for column in ("workspace_id", "user_id", "file_type", "folder", "processing_status"):
        op.create_index(f"ix_media_{column}", "media", [column])
    op.create_table("content_media", sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")), sa.Column("content_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("content.id", ondelete="CASCADE"), nullable=False), sa.Column("media_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("media.id", ondelete="CASCADE"), nullable=False), sa.Column("usage_type", sa.String(50)), sa.Column("position", sa.Integer()), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")), sa.UniqueConstraint("content_id", "media_id", name="uq_content_media"))
    op.create_index("ix_content_media_media_id", "content_media", ["media_id"])
    op.create_index("ix_content_media_content_id", "content_media", ["content_id"])

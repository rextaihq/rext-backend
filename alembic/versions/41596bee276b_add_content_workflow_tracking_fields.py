"""add_content_workflow_tracking_fields

Add fields to track content approval workflow:
- published_at: When content was published
- submitted_for_review_at: When content was submitted for review
- reviewed_at: When content was reviewed (approved/rejected)
- reviewed_by_user_id: Who reviewed the content
- review_notes: Feedback from reviewer

Also updates existing content status values:
- 'ready' → 'approved'
- 'generating' → 'draft'

Valid status values: draft, pending_review, approved, rejected, published, archived

Revision ID: 41596bee276b
Revises: a973deb06456
Create Date: 2025-10-20 11:13:15.314747

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '41596bee276b'
down_revision: Union[str, Sequence[str], None] = 'a973deb06456'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add workflow tracking fields to content table."""
    print("\n" + "="*80)
    print("ADDING CONTENT WORKFLOW TRACKING FIELDS")
    print("="*80)

    # Add new columns
    print("\n→ Adding workflow tracking columns...")

    op.add_column('content', sa.Column('published_at', sa.DateTime(timezone=True), nullable=True))
    print("  ✓ Added published_at")

    op.add_column('content', sa.Column('submitted_for_review_at', sa.DateTime(timezone=True), nullable=True))
    print("  ✓ Added submitted_for_review_at")

    op.add_column('content', sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True))
    print("  ✓ Added reviewed_at")

    op.add_column('content', sa.Column('reviewed_by_user_id', postgresql.UUID(as_uuid=True), nullable=True))
    print("  ✓ Added reviewed_by_user_id")

    op.add_column('content', sa.Column('review_notes', sa.Text, nullable=True))
    print("  ✓ Added review_notes")

    # Add foreign key for reviewed_by_user_id
    print("\n→ Adding foreign key constraint...")
    op.create_foreign_key(
        'fk_content_reviewed_by_user',
        'content', 'users',
        ['reviewed_by_user_id'], ['id'],
        ondelete='SET NULL'
    )
    print("  ✓ Added foreign key: fk_content_reviewed_by_user")

    # Update existing content status values
    print("\n→ Updating existing content status values...")

    # Update 'ready' to 'approved'
    op.execute("""
        UPDATE content
        SET status = 'approved'
        WHERE status = 'ready'
    """)
    print("  ✓ Updated status: 'ready' → 'approved'")

    # Update 'generating' to 'draft'
    op.execute("""
        UPDATE content
        SET status = 'draft'
        WHERE status = 'generating'
    """)
    print("  ✓ Updated status: 'generating' → 'draft'")

    print("\n" + "="*80)
    print("✓ WORKFLOW TRACKING FIELDS ADDED!")
    print("\n  Valid status values:")
    print("    - draft: Content being worked on")
    print("    - pending_review: Submitted for review")
    print("    - approved: Reviewed and approved")
    print("    - rejected: Needs changes")
    print("    - published: Live/published")
    print("    - archived: Archived content")
    print("="*80 + "\n")


def downgrade() -> None:
    """Remove workflow tracking fields from content table."""
    print("\n" + "="*80)
    print("REMOVING CONTENT WORKFLOW TRACKING FIELDS")
    print("="*80)

    # Drop foreign key first
    print("\n→ Removing foreign key constraint...")
    op.drop_constraint('fk_content_reviewed_by_user', 'content', type_='foreignkey')
    print("  ✓ Dropped foreign key: fk_content_reviewed_by_user")

    # Drop columns
    print("\n→ Removing workflow tracking columns...")

    op.drop_column('content', 'review_notes')
    print("  ✓ Removed review_notes")

    op.drop_column('content', 'reviewed_by_user_id')
    print("  ✓ Removed reviewed_by_user_id")

    op.drop_column('content', 'reviewed_at')
    print("  ✓ Removed reviewed_at")

    op.drop_column('content', 'submitted_for_review_at')
    print("  ✓ Removed submitted_for_review_at")

    op.drop_column('content', 'published_at')
    print("  ✓ Removed published_at")

    # Revert status values
    print("\n→ Reverting content status values...")

    op.execute("""
        UPDATE content
        SET status = 'ready'
        WHERE status = 'approved'
    """)
    print("  ✓ Reverted status: 'approved' → 'ready'")

    print("\n" + "="*80)
    print("✓ DOWNGRADE COMPLETE!")
    print("="*80 + "\n")

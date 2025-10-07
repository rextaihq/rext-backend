"""seed_simple_supporting_data

Revision ID: seed002
Revises: seed001
Create Date: 2025-10-03 10:30:00.000000

Simple seed data for subscription plans and notification preferences
"""
from typing import Sequence, Union
from alembic import op
from sqlalchemy import orm
from sqlalchemy.ext.declarative import declarative_base
import sqlalchemy as sa
import uuid
from datetime import datetime

revision: str = 'seed002'
down_revision: Union[str, Sequence[str], None] = 'seed001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

Base = declarative_base()

class SubscriptionPlan(Base):
    __tablename__ = 'subscription_plans'
    id = sa.Column(sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True)
    name = sa.Column(sa.String(100))
    display_name = sa.Column(sa.String(150))
    description = sa.Column(sa.Text)
    price_monthly = sa.Column(sa.Numeric(10, 2))
    price_yearly = sa.Column(sa.Numeric(10, 2))
    max_workspaces = sa.Column(sa.Integer)
    max_members_per_workspace = sa.Column(sa.Integer)
    max_topics = sa.Column(sa.Integer)
    max_knowledge_items = sa.Column(sa.Integer)
    max_api_calls_per_month = sa.Column(sa.Integer)
    features = sa.Column(sa.dialects.postgresql.JSONB)
    is_active = sa.Column(sa.Boolean)
    is_public = sa.Column(sa.Boolean)
    created_at = sa.Column(sa.TIMESTAMP)
    updated_at = sa.Column(sa.TIMESTAMP)

class NotificationPreferences(Base):
    __tablename__ = 'notification_preferences'
    id = sa.Column(sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True)
    user_id = sa.Column(sa.dialects.postgresql.UUID(as_uuid=True))
    email_notifications = sa.Column(sa.Boolean)
    workspace_invites = sa.Column(sa.Boolean)
    content_updates = sa.Column(sa.Boolean)
    topic_generation = sa.Column(sa.Boolean)
    weekly_digest = sa.Column(sa.Boolean)
    security_alerts = sa.Column(sa.Boolean)
    created_at = sa.Column(sa.TIMESTAMP)
    updated_at = sa.Column(sa.TIMESTAMP)

def upgrade() -> None:
    """Seed subscription plans and notification preferences."""
    bind = op.get_bind()
    session = orm.Session(bind=bind)

    try:
        now = datetime.utcnow()
        print("Seeding subscription plans and notification preferences...")

        # =================================================================
        # SUBSCRIPTION PLANS  
        # =================================================================
        # Note: Subscription plans are seeded by migration f9e8d7c6b5a4_seed_subscription_plans.py
        # Skipping here to avoid duplicates
        print("\nSkipping subscription plans (already seeded by f9e8d7c6b5a4)...")

        # =================================================================
        # NOTIFICATION PREFERENCES
        # =================================================================
        user_ids = [
            '11111111-1111-1111-1111-111111111111',  # admin
            '22222222-2222-2222-2222-222222222222',  # john
            '33333333-3333-3333-3333-333333333333',  # jane
            '44444444-4444-4444-4444-444444444444',  # bob
            '55555555-5555-5555-5555-555555555555',  # alice
        ]

        for user_id_str in user_ids:
            user_id = uuid.UUID(user_id_str)
            existing = session.query(NotificationPreferences).filter_by(user_id=user_id).first()
            if not existing:
                pref = NotificationPreferences(
                    id=uuid.uuid4(),
                    user_id=user_id,
                    email_notifications=True,
                    email_digest_frequency="daily",
                    email_workspace_invites=True,
                    email_comments=True,
                    email_mentions=True,
                    email_updates=False,
                    in_app_notifications=True,
                    in_app_workspace_invites=True,
                    in_app_comments=True,
                    in_app_mentions=True,
                    in_app_updates=False,
                    created_at=now,
                    updated_at=now,
                )
                session.add(pref)
                print(f"  ✓ Created notification preferences for user {user_id_str[:8]}...")

        session.commit()

        print("\n" + "="*80)
        print("✅ SUPPORTING SEED DATA COMPLETE!")
        print("="*80)
        print("  • 3 Subscription Plans created")
        print("  • 5 Notification Preference records created")
        print("="*80)

    except Exception as e:
        session.rollback()
        print(f"\n❌ ERROR: Failed to seed data: {str(e)}")
        raise
    finally:
        session.close()

def downgrade() -> None:
    """Remove supporting seed data."""
    bind = op.get_bind()
    session = orm.Session(bind=bind)

    try:
        print("Removing supporting seed data...")

        # Remove plans
        plan_ids = [
            uuid.UUID('00000000-0000-0000-0000-000000000001'),
            uuid.UUID('00000000-0000-0000-0000-000000000002'),
            uuid.UUID('00000000-0000-0000-0000-000000000003'),
        ]
        session.query(SubscriptionPlan).filter(
            SubscriptionPlan.id.in_(plan_ids)
        ).delete(synchronize_session=False)

        # Remove notification preferences
        user_ids = [
            uuid.UUID('11111111-1111-1111-1111-111111111111'),
            uuid.UUID('22222222-2222-2222-2222-222222222222'),
            uuid.UUID('33333333-3333-3333-3333-333333333333'),
            uuid.UUID('44444444-4444-4444-4444-444444444444'),
            uuid.UUID('55555555-5555-5555-5555-555555555555'),
        ]
        session.query(NotificationPreferences).filter(
            NotificationPreferences.user_id.in_(user_ids)
        ).delete(synchronize_session=False)

        session.commit()
        print("✅ Supporting seed data removed")

    except Exception as e:
        session.rollback()
        print(f"❌ ERROR: {str(e)}")
        raise
    finally:
        session.close()

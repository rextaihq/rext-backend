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
        plans_data = [
            {
                "id": "00000000-0000-0000-0000-000000000001",
                "name": "free",
                "display_name": "Free Plan",
                "price_monthly": 0,
                "price_yearly": 0,
                "max_workspaces": 1,
                "max_members_per_workspace": 1,
                "max_topics": 10,
                "max_knowledge_items": 50,
                "max_api_calls_per_month": 1000,
            },
            {
                "id": "00000000-0000-0000-0000-000000000002",
                "name": "starter",
                "display_name": "Starter Plan",
                "price_monthly": 29,
                "price_yearly": 290,
                "max_workspaces": 3,
                "max_members_per_workspace": 5,
                "max_topics": 50,
                "max_knowledge_items": 500,
                "max_api_calls_per_month": 10000,
            },
            {
                "id": "00000000-0000-0000-0000-000000000003",
                "name": "professional",
                "display_name": "Professional Plan",
                "price_monthly": 99,
                "price_yearly": 990,
                "max_workspaces": 10,
                "max_members_per_workspace": 20,
                "max_topics": 200,
                "max_knowledge_items": 2000,
                "max_api_calls_per_month": 50000,
            },
        ]

        for plan_data in plans_data:
            plan_id = uuid.UUID(plan_data["id"])
            existing = session.query(SubscriptionPlan).filter_by(id=plan_id).first()
            if not existing:
                plan = SubscriptionPlan(
                    id=plan_id,
                    name=plan_data["name"],
                    display_name=plan_data["display_name"],
                    description=f"{plan_data['display_name']} - Perfect for testing and development",
                    price_monthly=plan_data["price_monthly"],
                    price_yearly=plan_data["price_yearly"],
                    max_workspaces=plan_data["max_workspaces"],
                    max_members_per_workspace=plan_data["max_members_per_workspace"],
                    max_topics=plan_data["max_topics"],
                    max_knowledge_items=plan_data["max_knowledge_items"],
                    max_api_calls_per_month=plan_data["max_api_calls_per_month"],
                    features={},
                    is_active=True,
                    is_public=True,
                    created_at=now,
                    updated_at=now,
                )
                session.add(plan)
                print(f"  ✓ Created plan: {plan_data['display_name']}")

        session.flush()

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
                    workspace_invites=True,
                    content_updates=True,
                    topic_generation=True,
                    weekly_digest=True,
                    security_alerts=True,
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

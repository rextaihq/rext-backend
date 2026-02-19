"""seed_super_admin_from_env

Seeds super admin user and trial subscription plan from environment variables.

Revision ID: 6a35a3742a53
Revises: bcf75908be78
Create Date: 2025-10-14 17:29:59.666517

Required Environment Variables:
- SUPER_ADMIN_EMAIL: Email for super admin account
- SUPER_ADMIN_PASSWORD: Password for super admin account
- SUPER_ADMIN_FIRST_NAME: First name (optional, defaults to "Super")
- SUPER_ADMIN_LAST_NAME: Last name (optional, defaults to "Admin")

This migration:
1. Creates super admin user from environment variables
2. Assigns super_admin role with all permissions
3. Creates trial subscription plan (14 days, limited features)
4. Is idempotent - safe to run multiple times
"""
from typing import Sequence, Union
from alembic import op
from sqlalchemy import orm
from sqlalchemy.ext.declarative import declarative_base
import sqlalchemy as sa
import uuid
from datetime import datetime, timezone
from decimal import Decimal
import bcrypt
import os

# revision identifiers, used by Alembic.
revision: str = '6a35a3742a53'
down_revision: Union[str, Sequence[str], None] = 'bcf75908be78'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

Base = declarative_base()


# Lightweight models for seeding
class Users(Base):
    __tablename__ = 'users'
    id = sa.Column(sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True)
    email = sa.Column(sa.String(255), unique=True, nullable=False)
    username = sa.Column(sa.String(100), unique=True, nullable=False)
    password_hash = sa.Column(sa.String(255), nullable=False)
    first_name = sa.Column(sa.String(100))
    last_name = sa.Column(sa.String(100))
    display_name = sa.Column(sa.String(200))
    status = sa.Column(sa.String(20), default="active")
    email_verified = sa.Column(sa.Boolean, default=True)
    email_verified_at = sa.Column(sa.DateTime(timezone=True))
    language = sa.Column(sa.String(10), default="en")
    timezone = sa.Column(sa.String(50), default="UTC")
    created_at = sa.Column(sa.DateTime(timezone=True), nullable=False)
    updated_at = sa.Column(sa.DateTime(timezone=True))


class Role(Base):
    __tablename__ = 'roles'
    id = sa.Column(sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True)
    name = sa.Column(sa.String(100), unique=True, nullable=False)


class UserRole(Base):
    __tablename__ = 'user_roles'
    id = sa.Column(sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True)
    user_id = sa.Column(sa.dialects.postgresql.UUID(as_uuid=True), nullable=False)
    role_id = sa.Column(sa.dialects.postgresql.UUID(as_uuid=True), nullable=False)
    workspace_id = sa.Column(sa.dialects.postgresql.UUID(as_uuid=True))
    assigned_by_user_id = sa.Column(sa.dialects.postgresql.UUID(as_uuid=True))
    is_primary = sa.Column(sa.Boolean, default=True)
    assigned_at = sa.Column(sa.DateTime(timezone=True), nullable=False)


class SubscriptionPlan(Base):
    __tablename__ = 'subscription_plans'
    id = sa.Column(sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True)
    name = sa.Column(sa.String(100), unique=True, nullable=False)
    display_name = sa.Column(sa.String(150), nullable=False)
    description = sa.Column(sa.Text)
    price_monthly = sa.Column(sa.Numeric(10, 2))
    price_yearly = sa.Column(sa.Numeric(10, 2))
    features = sa.Column(sa.dialects.postgresql.JSONB)
    max_workspaces = sa.Column(sa.Integer)
    max_members_per_workspace = sa.Column(sa.Integer)
    max_topics = sa.Column(sa.Integer)
    max_knowledge_items = sa.Column(sa.Integer)
    max_api_calls_per_month = sa.Column(sa.Integer)
    is_active = sa.Column(sa.Boolean, default=True)
    is_public = sa.Column(sa.Boolean, default=True)
    provider_price_id_monthly = sa.Column(sa.String(255))
    provider_price_id_yearly = sa.Column(sa.String(255))
    created_at = sa.Column(sa.DateTime(timezone=True), nullable=False)
    updated_at = sa.Column(sa.DateTime(timezone=True))


def upgrade() -> None:
    """Seed super admin user and trial plan from environment variables."""
    bind = op.get_bind()
    session = orm.Session(bind=bind)

    try:
        now = datetime.now(timezone.utc)

        print("\n" + "="*80)
        print("SEEDING SUPER ADMIN & TRIAL PLAN")
        print("="*80)

        # =================================================================
        # GET ENVIRONMENT VARIABLES
        # =================================================================
        admin_email = os.getenv('SUPER_ADMIN_EMAIL')
        admin_password = os.getenv('SUPER_ADMIN_PASSWORD')
        admin_first_name = os.getenv('SUPER_ADMIN_FIRST_NAME', 'Super')
        admin_last_name = os.getenv('SUPER_ADMIN_LAST_NAME', 'Admin')

        if not admin_email or not admin_password:
            print("\n⚠️  WARNING: SUPER_ADMIN_EMAIL and SUPER_ADMIN_PASSWORD not set")
            print("    Super admin user will NOT be created.")
            print("    Set these environment variables and re-run migration to create super admin.")
            print("\n    Required:")
            print("      - SUPER_ADMIN_EMAIL")
            print("      - SUPER_ADMIN_PASSWORD")
            print("    Optional:")
            print("      - SUPER_ADMIN_FIRST_NAME (default: 'Super')")
            print("      - SUPER_ADMIN_LAST_NAME (default: 'Admin')")
        else:
            # =================================================================
            # CREATE SUPER ADMIN USER
            # =================================================================
            print("\n1. Creating super admin user...")

            # Check if user already exists
            existing_user = session.query(Users).filter_by(email=admin_email).first()

            if existing_user:
                print(f"   ⚠️  Super admin user already exists: {admin_email}")
                super_admin_id = existing_user.id
            else:
                # Hash password
                password_hash = bcrypt.hashpw(
                    admin_password.encode('utf-8'),
                    bcrypt.gensalt()
                ).decode('utf-8')

                # Generate username from email
                username = admin_email.split('@')[0].lower()

                # Check if username exists, make unique if needed
                base_username = username
                counter = 1
                while session.query(Users).filter_by(username=username).first():
                    username = f"{base_username}{counter}"
                    counter += 1

                super_admin_id = uuid.uuid4()
                display_name = f"{admin_first_name} {admin_last_name}"

                super_admin = Users(
                    id=super_admin_id,
                    email=admin_email,
                    username=username,
                    password_hash=password_hash,
                    first_name=admin_first_name,
                    last_name=admin_last_name,
                    display_name=display_name,
                    status="active",
                    email_verified=True,
                    email_verified_at=now,
                    language="en",
                    timezone="UTC",
                    created_at=now,
                    updated_at=now,
                )
                session.add(super_admin)
                session.flush()
                print(f"   ✅ Created super admin user: {admin_email}")
                print(f"      Username: {username}")
                print(f"      Display name: {display_name}")

            # =================================================================
            # ASSIGN SUPER_ADMIN ROLE
            # =================================================================
            print("\n2. Assigning super_admin role...")

            super_admin_role = session.query(Role).filter_by(name='super_admin').first()

            if not super_admin_role:
                print("   ⚠️  WARNING: 'super_admin' role not found in database")
                print("      Please ensure role seeding migrations have been run")
            else:
                # Check if role already assigned
                existing_role = session.query(UserRole).filter_by(
                    user_id=super_admin_id,
                    role_id=super_admin_role.id,
                    workspace_id=None
                ).first()

                if existing_role:
                    print(f"   ⚠️  Super admin role already assigned")
                else:
                    user_role = UserRole(
                        id=uuid.uuid4(),
                        user_id=super_admin_id,
                        role_id=super_admin_role.id,
                        workspace_id=None,  # Global role
                        assigned_by_user_id=super_admin_id,  # Self-assigned
                        is_primary=True,
                        assigned_at=now,
                    )
                    session.add(user_role)
                    print(f"   ✅ Assigned super_admin role (global scope)")

        # =================================================================
        # CREATE TRIAL SUBSCRIPTION PLAN
        # =================================================================
        print("\n3. Creating trial subscription plan...")

        existing_trial = session.query(SubscriptionPlan).filter_by(name='trial').first()

        if existing_trial:
            print(f"   ⚠️  Trial plan already exists, skipping...")
        else:
            trial_plan = SubscriptionPlan(
                id=uuid.uuid4(),
                name="trial",
                display_name="Trial Plan",
                description="14-day free trial with limited features. Perfect for testing and evaluation.",
                price_monthly=Decimal("0.00"),
                price_yearly=Decimal("0.00"),
                features={
                    "trial_duration_days": 14,
                    "collaboration": "Basic",
                    "support": "Community",
                    "api_access": "Limited",
                    "custom_branding": False,
                    "advanced_analytics": False,
                    "priority_support": False
                },
                max_workspaces=1,
                max_members_per_workspace=3,
                max_topics=10,
                max_knowledge_items=20,
                max_api_calls_per_month=100,
                is_active=True,
                is_public=False,  # Trial is not publicly selectable, auto-assigned on signup
                provider_price_id_monthly=None,
                provider_price_id_yearly=None,
                created_at=now,
                updated_at=now
            )
            session.add(trial_plan)
            print(f"   ✅ Created trial subscription plan")
            print(f"      Duration: 14 days")
            print(f"      Limits: 1 workspace, 3 members, 10 topics, 20 knowledge items")

        session.commit()

        # =================================================================
        # FINAL SUMMARY
        # =================================================================
        print("\n" + "="*80)
        print("✅ SEEDING COMPLETE!")
        print("="*80)

        if admin_email and admin_password:
            print(f"\nSuper Admin Account:")
            print(f"  Email: {admin_email}")
            print(f"  Password: [as configured in SUPER_ADMIN_PASSWORD]")
            print(f"\nYou can now log in with these credentials.")
        else:
            print(f"\n⚠️  No super admin created (environment variables not set)")

        print(f"\nTrial Plan:")
        print(f"  Created successfully - will be auto-assigned on user signup")
        print("="*80 + "\n")

    except Exception as e:
        session.rollback()
        print(f"\n❌ ERROR: Failed to seed data: {str(e)}")
        import traceback
        traceback.print_exc()
        raise
    finally:
        session.close()


def downgrade() -> None:
    """Remove super admin user and trial plan."""
    bind = op.get_bind()
    session = orm.Session(bind=bind)

    try:
        print("\n" + "="*80)
        print("REMOVING SUPER ADMIN & TRIAL PLAN")
        print("="*80)

        # Get environment variables
        admin_email = os.getenv('SUPER_ADMIN_EMAIL')

        if admin_email:
            # Remove super admin user (cascade will remove user_roles)
            user = session.query(Users).filter_by(email=admin_email).first()
            if user:
                # Remove user roles first
                session.query(UserRole).filter_by(user_id=user.id).delete()
                # Remove user
                session.delete(user)
                print(f"   ✅ Removed super admin user: {admin_email}")
            else:
                print(f"   ⚠️  Super admin user not found: {admin_email}")

        # Remove trial plan
        trial_plan = session.query(SubscriptionPlan).filter_by(name='trial').first()
        if trial_plan:
            session.delete(trial_plan)
            print(f"   ✅ Removed trial subscription plan")
        else:
            print(f"   ⚠️  Trial plan not found")

        session.commit()
        print("\n✅ Downgrade complete")
        print("="*80 + "\n")

    except Exception as e:
        session.rollback()
        print(f"\n❌ ERROR: Failed to downgrade: {str(e)}")
        raise
    finally:
        session.close()

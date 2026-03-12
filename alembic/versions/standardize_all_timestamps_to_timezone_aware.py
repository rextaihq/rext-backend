"""Standardize all timestamp columns to DateTime(timezone=True).

Converts all TIMESTAMP columns to DateTime(timezone=True) across all tables for timezone-aware datetime handling.

Revision ID: standardize_timestamps
Revises: seed009_comprehensive_rbac_permissions
Create Date: 2026-02-09 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'standardize_timestamps'
down_revision = 'f23456789abc'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Upgrade: Convert TIMESTAMP to DateTime(timezone=True)."""
    
    # User-related tables
    op.alter_column(
        'users',
        'password_changed_at',
        existing_type=sa.TIMESTAMP(),
        type_=sa.DateTime(timezone=True),
        postgresql_using=f"password_changed_at AT TIME ZONE 'UTC'",
        nullable=True
    )
    
    op.alter_column(
        'users',
        'locked_until',
        existing_type=sa.TIMESTAMP(),
        type_=sa.DateTime(timezone=True),
        postgresql_using=f"locked_until AT TIME ZONE 'UTC'",
        nullable=True
    )
    
    op.alter_column(
        'users',
        'email_verified_at',
        existing_type=sa.TIMESTAMP(),
        type_=sa.DateTime(timezone=True),
        postgresql_using=f"email_verified_at AT TIME ZONE 'UTC'",
        nullable=True
    )
    
    op.alter_column(
        'users',
        'last_login_at',
        existing_type=sa.TIMESTAMP(),
        type_=sa.DateTime(timezone=True),
        postgresql_using=f"last_login_at AT TIME ZONE 'UTC'",
        nullable=True
    )
    
    op.alter_column(
        'users',
        'created_at',
        existing_type=sa.TIMESTAMP(),
        type_=sa.DateTime(timezone=True),
        postgresql_using=f"created_at AT TIME ZONE 'UTC'"
    )
    
    op.alter_column(
        'users',
        'updated_at',
        existing_type=sa.TIMESTAMP(),
        type_=sa.DateTime(timezone=True),
        postgresql_using=f"updated_at AT TIME ZONE 'UTC'",
        nullable=True
    )
    
    op.alter_column(
        'users',
        'deactivated_at',
        existing_type=sa.TIMESTAMP(),
        type_=sa.DateTime(timezone=True),
        postgresql_using=f"deactivated_at AT TIME ZONE 'UTC'",
        nullable=True
    )
    
    op.alter_column(
        'users',
        'deleted_at',
        existing_type=sa.TIMESTAMP(),
        type_=sa.DateTime(timezone=True),
        postgresql_using=f"deleted_at AT TIME ZONE 'UTC'",
        nullable=True
    )
    
    # Invitations table
    op.alter_column(
        'user_invitations',
        'created_at',
        existing_type=sa.TIMESTAMP(),
        type_=sa.DateTime(timezone=True),
        postgresql_using=f"created_at AT TIME ZONE 'UTC'"
    )
    
    op.alter_column(
        'user_invitations',
        'expires_at',
        existing_type=sa.TIMESTAMP(),
        type_=sa.DateTime(timezone=True),
        postgresql_using=f"expires_at AT TIME ZONE 'UTC'"
    )
    
    # OAuth Accounts table
    op.alter_column(
        'oauth_accounts',
        'token_expires_at',
        existing_type=sa.TIMESTAMP(),
        type_=sa.DateTime(timezone=True),
        postgresql_using=f"token_expires_at AT TIME ZONE 'UTC'",
        nullable=True
    )
    
    op.alter_column(
        'oauth_accounts',
        'created_at',
        existing_type=sa.TIMESTAMP(),
        type_=sa.DateTime(timezone=True),
        postgresql_using=f"created_at AT TIME ZONE 'UTC'"
    )
    
    op.alter_column(
        'oauth_accounts',
        'updated_at',
        existing_type=sa.TIMESTAMP(),
        type_=sa.DateTime(timezone=True),
        postgresql_using=f"updated_at AT TIME ZONE 'UTC'",
        nullable=True
    )
    
    op.alter_column(
        'oauth_accounts',
        'last_used_at',
        existing_type=sa.TIMESTAMP(),
        type_=sa.DateTime(timezone=True),
        postgresql_using=f"last_used_at AT TIME ZONE 'UTC'",
        nullable=True
    )
    
    # Roles table
    op.alter_column(
        'roles',
        'created_at',
        existing_type=sa.TIMESTAMP(),
        type_=sa.DateTime(timezone=True),
        postgresql_using=f"created_at AT TIME ZONE 'UTC'"
    )
    
    op.alter_column(
        'roles',
        'updated_at',
        existing_type=sa.TIMESTAMP(),
        type_=sa.DateTime(timezone=True),
        postgresql_using=f"updated_at AT TIME ZONE 'UTC'",
        nullable=True
    )
    
    # Permissions table
    op.alter_column(
        'permissions',
        'created_at',
        existing_type=sa.TIMESTAMP(),
        type_=sa.DateTime(timezone=True),
        postgresql_using=f"created_at AT TIME ZONE 'UTC'",
        nullable=True
    )
    
    # Role Permissions table
    op.alter_column(
        'role_permissions',
        'created_at',
        existing_type=sa.TIMESTAMP(),
        type_=sa.DateTime(timezone=True),
        postgresql_using=f"created_at AT TIME ZONE 'UTC'"
    )
    
    # User Roles table
    op.alter_column(
        'user_roles',
        'assigned_at',
        existing_type=sa.TIMESTAMP(),
        type_=sa.DateTime(timezone=True),
        postgresql_using=f"assigned_at AT TIME ZONE 'UTC'"
    )
    
    # User Sessions table
    op.alter_column(
        'user_sessions',
        'created_at',
        existing_type=sa.TIMESTAMP(),
        type_=sa.DateTime(timezone=True),
        postgresql_using=f"created_at AT TIME ZONE 'UTC'"
    )
    
    op.alter_column(
        'user_sessions',
        'last_activity_at',
        existing_type=sa.TIMESTAMP(),
        type_=sa.DateTime(timezone=True),
        postgresql_using=f"last_activity_at AT TIME ZONE 'UTC'"
    )
    
    op.alter_column(
        'user_sessions',
        'expires_at',
        existing_type=sa.TIMESTAMP(),
        type_=sa.DateTime(timezone=True),
        postgresql_using=f"expires_at AT TIME ZONE 'UTC'"
    )
    
    op.alter_column(
        'user_sessions',
        'revoked_at',
        existing_type=sa.TIMESTAMP(),
        type_=sa.DateTime(timezone=True),
        postgresql_using=f"revoked_at AT TIME ZONE 'UTC'",
        nullable=True
    )
    
    # Token Blacklist table
    op.alter_column(
        'token_blacklist',
        'revoked_at',
        existing_type=sa.TIMESTAMP(),
        type_=sa.DateTime(timezone=True),
        postgresql_using=f"revoked_at AT TIME ZONE 'UTC'"
    )
    
    op.alter_column(
        'token_blacklist',
        'expires_at',
        existing_type=sa.TIMESTAMP(),
        type_=sa.DateTime(timezone=True),
        postgresql_using=f"expires_at AT TIME ZONE 'UTC'"
    )
    
    # Notification Preferences table
    op.alter_column(
        'notification_preferences',
        'created_at',
        existing_type=sa.TIMESTAMP(),
        type_=sa.DateTime(timezone=True),
        postgresql_using=f"created_at AT TIME ZONE 'UTC'"
    )
    
    op.alter_column(
        'notification_preferences',
        'updated_at',
        existing_type=sa.TIMESTAMP(),
        type_=sa.DateTime(timezone=True),
        postgresql_using=f"updated_at AT TIME ZONE 'UTC'"
    )
    
    # Workspace Members table
    op.alter_column(
        'workspace_members',
        'joined_at',
        existing_type=sa.TIMESTAMP(),
        type_=sa.DateTime(timezone=True),
        postgresql_using=f"joined_at AT TIME ZONE 'UTC'"
    )
    
    op.alter_column(
        'workspace_members',
        'last_activity_at',
        existing_type=sa.TIMESTAMP(),
        type_=sa.DateTime(timezone=True),
        postgresql_using=f"last_activity_at AT TIME ZONE 'UTC'",
        nullable=True
    )
    
    # Email Templates table
    op.alter_column(
        'email_templates',
        'created_at',
        existing_type=sa.TIMESTAMP(),
        type_=sa.DateTime(timezone=True),
        postgresql_using=f"created_at AT TIME ZONE 'UTC'"
    )
    
    op.alter_column(
        'email_templates',
        'updated_at',
        existing_type=sa.TIMESTAMP(),
        type_=sa.DateTime(timezone=True),
        postgresql_using=f"updated_at AT TIME ZONE 'UTC'",
        nullable=True
    )
    
    # Media table
    op.alter_column(
        'media',
        'created_at',
        existing_type=sa.TIMESTAMP(),
        type_=sa.DateTime(timezone=True),
        postgresql_using=f"created_at AT TIME ZONE 'UTC'"
    )
    
    op.alter_column(
        'media',
        'updated_at',
        existing_type=sa.TIMESTAMP(),
        type_=sa.DateTime(timezone=True),
        postgresql_using=f"updated_at AT TIME ZONE 'UTC'",
        nullable=True
    )
    
    op.alter_column(
        'media',
        'deleted_at',
        existing_type=sa.TIMESTAMP(),
        type_=sa.DateTime(timezone=True),
        postgresql_using=f"deleted_at AT TIME ZONE 'UTC'",
        nullable=True
    )
    
    # Subscription Plans table
    op.alter_column(
        'subscription_plans',
        'created_at',
        existing_type=sa.TIMESTAMP(),
        type_=sa.DateTime(timezone=True),
        postgresql_using=f"created_at AT TIME ZONE 'UTC'"
    )
    
    op.alter_column(
        'subscription_plans',
        'updated_at',
        existing_type=sa.TIMESTAMP(),
        type_=sa.DateTime(timezone=True),
        postgresql_using=f"updated_at AT TIME ZONE 'UTC'",
        nullable=True
    )
    
    # Subscriptions table
    op.alter_column(
        'user_subscriptions',
        'start_date',
        existing_type=sa.TIMESTAMP(),
        type_=sa.DateTime(timezone=True),
        postgresql_using=f"start_date AT TIME ZONE 'UTC'"
    )
    
    op.alter_column(
        'user_subscriptions',
        'end_date',
        existing_type=sa.TIMESTAMP(),
        type_=sa.DateTime(timezone=True),
        postgresql_using=f"end_date AT TIME ZONE 'UTC'",
        nullable=True
    )
    
    op.alter_column(
        'user_subscriptions',
        'trial_end_date',
        existing_type=sa.TIMESTAMP(),
        type_=sa.DateTime(timezone=True),
        postgresql_using=f"trial_end_date AT TIME ZONE 'UTC'",
        nullable=True
    )
    
    op.alter_column(
        'user_subscriptions',
        'cancelled_at',
        existing_type=sa.TIMESTAMP(),
        type_=sa.DateTime(timezone=True),
        postgresql_using=f"cancelled_at AT TIME ZONE 'UTC'",
        nullable=True
    )
    
    op.alter_column(
        'user_subscriptions',
        'renews_at',
        existing_type=sa.TIMESTAMP(),
        type_=sa.DateTime(timezone=True),
        postgresql_using=f"renews_at AT TIME ZONE 'UTC'",
        nullable=True
    )
    
    op.alter_column(
        'user_subscriptions',
        'ends_at',
        existing_type=sa.TIMESTAMP(),
        type_=sa.DateTime(timezone=True),
        postgresql_using=f"ends_at AT TIME ZONE 'UTC'",
        nullable=True
    )
    
    op.alter_column(
        'user_subscriptions',
        'grace_period_end',
        existing_type=sa.TIMESTAMP(),
        type_=sa.DateTime(timezone=True),
        postgresql_using=f"grace_period_end AT TIME ZONE 'UTC'",
        nullable=True
    )
    
    op.alter_column(
        'user_subscriptions',
        'payment_failed_at',
        existing_type=sa.TIMESTAMP(),
        type_=sa.DateTime(timezone=True),
        postgresql_using=f"payment_failed_at AT TIME ZONE 'UTC'",
        nullable=True
    )
    
    op.alter_column(
        'user_subscriptions',
        'usage_reset_date',
        existing_type=sa.TIMESTAMP(),
        type_=sa.DateTime(timezone=True),
        postgresql_using=f"usage_reset_date AT TIME ZONE 'UTC'",
        nullable=True
    )
    
    op.alter_column(
        'user_subscriptions',
        'created_at',
        existing_type=sa.TIMESTAMP(),
        type_=sa.DateTime(timezone=True),
        postgresql_using=f"created_at AT TIME ZONE 'UTC'"
    )
    
    op.alter_column(
        'user_subscriptions',
        'updated_at',
        existing_type=sa.TIMESTAMP(),
        type_=sa.DateTime(timezone=True),
        postgresql_using=f"updated_at AT TIME ZONE 'UTC'",
        nullable=True
    )
    
    # Webhook Events table
    op.alter_column(
        'webhook_events',
        'processed_at',
        existing_type=sa.TIMESTAMP(),
        type_=sa.DateTime(timezone=True),
        postgresql_using=f"processed_at AT TIME ZONE 'UTC'",
        nullable=True
    )
    
    op.alter_column(
        'webhook_events',
        'created_at',
        existing_type=sa.TIMESTAMP(),
        type_=sa.DateTime(timezone=True),
        postgresql_using=f"created_at AT TIME ZONE 'UTC'"
    )
    
    op.alter_column(
        'webhook_events',
        'updated_at',
        existing_type=sa.TIMESTAMP(),
        type_=sa.DateTime(timezone=True),
        postgresql_using=f"updated_at AT TIME ZONE 'UTC'"
    )
    
    # Refunds table
    op.alter_column(
        'refunds',
        'processed_at',
        existing_type=sa.TIMESTAMP(),
        type_=sa.DateTime(timezone=True),
        postgresql_using=f"processed_at AT TIME ZONE 'UTC'",
        nullable=True
    )
    
    op.alter_column(
        'refunds',
        'created_at',
        existing_type=sa.TIMESTAMP(),
        type_=sa.DateTime(timezone=True),
        postgresql_using=f"created_at AT TIME ZONE 'UTC'"
    )
    
    op.alter_column(
        'refunds',
        'updated_at',
        existing_type=sa.TIMESTAMP(),
        type_=sa.DateTime(timezone=True),
        postgresql_using=f"updated_at AT TIME ZONE 'UTC'"
    )
    
    # Payment Methods table
    op.alter_column(
        'payment_methods',
        'created_at',
        existing_type=sa.TIMESTAMP(),
        type_=sa.DateTime(timezone=True),
        postgresql_using=f"created_at AT TIME ZONE 'UTC'"
    )
    
    op.alter_column(
        'payment_methods',
        'updated_at',
        existing_type=sa.TIMESTAMP(),
        type_=sa.DateTime(timezone=True),
        postgresql_using=f"updated_at AT TIME ZONE 'UTC'",
        nullable=True
    )
    
    # Licenses table
    op.alter_column(
        'licenses',
        'activated_at',
        existing_type=sa.TIMESTAMP(),
        type_=sa.DateTime(timezone=True),
        postgresql_using=f"activated_at AT TIME ZONE 'UTC'",
        nullable=True
    )
    
    op.alter_column(
        'licenses',
        'expires_at',
        existing_type=sa.TIMESTAMP(),
        type_=sa.DateTime(timezone=True),
        postgresql_using=f"expires_at AT TIME ZONE 'UTC'",
        nullable=True
    )
    
    op.alter_column(
        'licenses',
        'created_at',
        existing_type=sa.TIMESTAMP(),
        type_=sa.DateTime(timezone=True),
        postgresql_using=f"created_at AT TIME ZONE 'UTC'"
    )
    
    op.alter_column(
        'licenses',
        'updated_at',
        existing_type=sa.TIMESTAMP(),
        type_=sa.DateTime(timezone=True),
        postgresql_using=f"updated_at AT TIME ZONE 'UTC'"
    )
    
    # License Activations table
    op.alter_column(
        'license_activations',
        'activated_at',
        existing_type=sa.TIMESTAMP(timezone=True),
        type_=sa.DateTime(timezone=True),
        postgresql_using=f"activated_at AT TIME ZONE 'UTC'"
    )
    
    op.alter_column(
        'license_activations',
        'deactivated_at',
        existing_type=sa.TIMESTAMP(timezone=True),
        type_=sa.DateTime(timezone=True),
        postgresql_using=f"deactivated_at AT TIME ZONE 'UTC'",
        nullable=True
    )
    
    op.alter_column(
        'license_activations',
        'last_checked_at',
        existing_type=sa.TIMESTAMP(timezone=True),
        type_=sa.DateTime(timezone=True),
        postgresql_using=f"last_checked_at AT TIME ZONE 'UTC'",
        nullable=True
    )
    
    # Discount Usage table
    op.alter_column(
        'discount_usage',
        'applied_at',
        existing_type=sa.TIMESTAMP(timezone=True),
        type_=sa.DateTime(timezone=True),
        postgresql_using=f"applied_at AT TIME ZONE 'UTC'"
    )
    
    # Trial Conversions table (already using DateTime, but ensure consistency)
    # These may already be correct, but including for completeness
    
    # Content Media table
    op.alter_column(
        'content_media',
        'created_at',
        existing_type=sa.TIMESTAMP(timezone=True),
        type_=sa.DateTime(timezone=True),
        postgresql_using=f"created_at AT TIME ZONE 'UTC'"
    )
    
    # Audit Logs table
    op.alter_column(
        'audit_logs',
        'created_at',
        existing_type=sa.TIMESTAMP(),
        type_=sa.DateTime(timezone=True),
        postgresql_using=f"created_at AT TIME ZONE 'UTC'"
    )
    
    # Notifications table
    op.alter_column(
        'notifications',
        'read_at',
        existing_type=sa.TIMESTAMP(),
        type_=sa.DateTime(timezone=True),
        postgresql_using=f"read_at AT TIME ZONE 'UTC'",
        nullable=True
    )
    
    op.alter_column(
        'notifications',
        'archived_at',
        existing_type=sa.TIMESTAMP(),
        type_=sa.DateTime(timezone=True),
        postgresql_using=f"archived_at AT TIME ZONE 'UTC'",
        nullable=True
    )
    
    op.alter_column(
        'notifications',
        'deleted_at',
        existing_type=sa.TIMESTAMP(),
        type_=sa.DateTime(timezone=True),
        postgresql_using=f"deleted_at AT TIME ZONE 'UTC'",
        nullable=True
    )
    
    op.alter_column(
        'notifications',
        'email_sent_at',
        existing_type=sa.TIMESTAMP(),
        type_=sa.DateTime(timezone=True),
        postgresql_using=f"email_sent_at AT TIME ZONE 'UTC'",
        nullable=True
    )
    
    op.alter_column(
        'notifications',
        'sse_sent_at',
        existing_type=sa.TIMESTAMP(),
        type_=sa.DateTime(timezone=True),
        postgresql_using=f"sse_sent_at AT TIME ZONE 'UTC'",
        nullable=True
    )
    
    op.alter_column(
        'notifications',
        'expires_at',
        existing_type=sa.TIMESTAMP(),
        type_=sa.DateTime(timezone=True),
        postgresql_using=f"expires_at AT TIME ZONE 'UTC'",
        nullable=True
    )
    
    op.alter_column(
        'notifications',
        'created_at',
        existing_type=sa.TIMESTAMP(),
        type_=sa.DateTime(timezone=True),
        postgresql_using=f"created_at AT TIME ZONE 'UTC'"
    )
    
    op.alter_column(
        'notifications',
        'updated_at',
        existing_type=sa.TIMESTAMP(),
        type_=sa.DateTime(timezone=True),
        postgresql_using=f"updated_at AT TIME ZONE 'UTC'"
    )
    
    # Email Preferences table
    op.alter_column(
        'email_preferences',
        'created_at',
        existing_type=sa.TIMESTAMP(),
        type_=sa.DateTime(timezone=True),
        postgresql_using=f"created_at AT TIME ZONE 'UTC'",
        nullable=True
    )
    
    op.alter_column(
        'email_preferences',
        'updated_at',
        existing_type=sa.TIMESTAMP(),
        type_=sa.DateTime(timezone=True),
        postgresql_using=f"updated_at AT TIME ZONE 'UTC'",
        nullable=True
    )
    
    # User Preferences table
    op.alter_column(
        'user_preferences',
        'created_at',
        existing_type=sa.TIMESTAMP(),
        type_=sa.DateTime(timezone=True),
        postgresql_using=f"created_at AT TIME ZONE 'UTC'"
    )
    
    op.alter_column(
        'user_preferences',
        'updated_at',
        existing_type=sa.TIMESTAMP(),
        type_=sa.DateTime(timezone=True),
        postgresql_using=f"updated_at AT TIME ZONE 'UTC'"
    )
    
    # User Onboarding table
    op.alter_column(
        'user_onboarding',
        'started_at',
        existing_type=sa.TIMESTAMP(timezone=True),
        type_=sa.DateTime(timezone=True),
        postgresql_using=f"started_at AT TIME ZONE 'UTC'"
    )
    
    op.alter_column(
        'user_onboarding',
        'completed_at',
        existing_type=sa.TIMESTAMP(timezone=True),
        type_=sa.DateTime(timezone=True),
        postgresql_using=f"completed_at AT TIME ZONE 'UTC'",
        nullable=True
    )
    
    op.alter_column(
        'user_onboarding',
        'created_at',
        existing_type=sa.TIMESTAMP(timezone=True),
        type_=sa.DateTime(timezone=True),
        postgresql_using=f"created_at AT TIME ZONE 'UTC'"
    )
    
    op.alter_column(
        'user_onboarding',
        'updated_at',
        existing_type=sa.TIMESTAMP(timezone=True),
        type_=sa.DateTime(timezone=True),
        postgresql_using=f"updated_at AT TIME ZONE 'UTC'"
    )
    
    # Error Logs table
    op.alter_column(
        'error_logs',
        'timestamp',
        existing_type=sa.DateTime(),
        type_=sa.DateTime(timezone=True),
        postgresql_using=f"timestamp AT TIME ZONE 'UTC'"
    )
    
    op.alter_column(
        'error_logs',
        'resolved_at',
        existing_type=sa.DateTime(),
        type_=sa.DateTime(timezone=True),
        postgresql_using=f"resolved_at AT TIME ZONE 'UTC'",
        nullable=True
    )
    
    # Content table
    op.alter_column(
        'content',
        'created_at',
        existing_type=sa.TIMESTAMP(timezone=True),
        type_=sa.DateTime(timezone=True),
        postgresql_using=f"created_at AT TIME ZONE 'UTC'"
    )
    
    op.alter_column(
        'content',
        'updated_at',
        existing_type=sa.TIMESTAMP(timezone=True),
        type_=sa.DateTime(timezone=True),
        postgresql_using=f"updated_at AT TIME ZONE 'UTC'",
        nullable=True
    )
    
    op.alter_column(
        'content',
        'wordpress_published_at',
        existing_type=sa.TIMESTAMP(timezone=True),
        type_=sa.DateTime(timezone=True),
        postgresql_using=f"wordpress_published_at AT TIME ZONE 'UTC'",
        nullable=True
    )
    
    # Workspace table
    op.alter_column(
        'workspace',
        'created_at',
        existing_type=sa.TIMESTAMP(timezone=True),
        type_=sa.DateTime(timezone=True),
        postgresql_using=f"created_at AT TIME ZONE 'UTC'"
    )
    
    op.alter_column(
        'workspace',
        'updated_at',
        existing_type=sa.TIMESTAMP(timezone=True),
        type_=sa.DateTime(timezone=True),
        postgresql_using=f"updated_at AT TIME ZONE 'UTC'",
        nullable=True
    )
    
    # Platform Admin Invitations table
    op.alter_column(
        'platform_admin_invitations',
        'created_at',
        existing_type=sa.TIMESTAMP(),
        type_=sa.DateTime(timezone=True),
        postgresql_using=f"created_at AT TIME ZONE 'UTC'"
    )
    
    op.alter_column(
        'platform_admin_invitations',
        'expires_at',
        existing_type=sa.TIMESTAMP(),
        type_=sa.DateTime(timezone=True),
        postgresql_using=f"expires_at AT TIME ZONE 'UTC'"
    )
    
    op.alter_column(
        'platform_admin_invitations',
        'accepted_at',
        existing_type=sa.TIMESTAMP(),
        type_=sa.DateTime(timezone=True),
        postgresql_using=f"accepted_at AT TIME ZONE 'UTC'",
        nullable=True
    )
    
    op.alter_column(
        'platform_admin_invitations',
        'declined_at',
        existing_type=sa.TIMESTAMP(),
        type_=sa.DateTime(timezone=True),
        postgresql_using=f"declined_at AT TIME ZONE 'UTC'",
        nullable=True
    )
    
    op.alter_column(
        'platform_admin_invitations',
        'revoked_at',
        existing_type=sa.TIMESTAMP(),
        type_=sa.DateTime(timezone=True),
        postgresql_using=f"revoked_at AT TIME ZONE 'UTC'",
        nullable=True
    )


def downgrade() -> None:
    """Downgrade: Revert DateTime(timezone=True) back to TIMESTAMP."""
    
    # User-related tables - reverting
    op.alter_column(
        'users',
        'password_changed_at',
        existing_type=sa.DateTime(timezone=True),
        type_=sa.TIMESTAMP(),
        nullable=True
    )
    
    op.alter_column(
        'users',
        'locked_until',
        existing_type=sa.DateTime(timezone=True),
        type_=sa.TIMESTAMP(),
        nullable=True
    )
    
    op.alter_column(
        'users',
        'email_verified_at',
        existing_type=sa.DateTime(timezone=True),
        type_=sa.TIMESTAMP(),
        nullable=True
    )
    
    op.alter_column(
        'users',
        'last_login_at',
        existing_type=sa.DateTime(timezone=True),
        type_=sa.TIMESTAMP(),
        nullable=True
    )
    
    op.alter_column(
        'users',
        'created_at',
        existing_type=sa.DateTime(timezone=True),
        type_=sa.TIMESTAMP()
    )
    
    op.alter_column(
        'users',
        'updated_at',
        existing_type=sa.DateTime(timezone=True),
        type_=sa.TIMESTAMP(),
        nullable=True
    )
    
    op.alter_column(
        'users',
        'deactivated_at',
        existing_type=sa.DateTime(timezone=True),
        type_=sa.TIMESTAMP(),
        nullable=True
    )
    
    op.alter_column(
        'users',
        'deleted_at',
        existing_type=sa.DateTime(timezone=True),
        type_=sa.TIMESTAMP(),
        nullable=True
    )
    
    # Invitations table
    op.alter_column(
        'user_invitations',
        'created_at',
        existing_type=sa.DateTime(timezone=True),
        type_=sa.TIMESTAMP()
    )
    
    op.alter_column(
        'user_invitations',
        'expires_at',
        existing_type=sa.DateTime(timezone=True),
        type_=sa.TIMESTAMP()
    )
    
    # OAuth Accounts table
    op.alter_column(
        'oauth_accounts',
        'token_expires_at',
        existing_type=sa.DateTime(timezone=True),
        type_=sa.TIMESTAMP(),
        nullable=True
    )
    
    op.alter_column(
        'oauth_accounts',
        'created_at',
        existing_type=sa.DateTime(timezone=True),
        type_=sa.TIMESTAMP()
    )
    
    op.alter_column(
        'oauth_accounts',
        'updated_at',
        existing_type=sa.DateTime(timezone=True),
        type_=sa.TIMESTAMP(),
        nullable=True
    )
    
    op.alter_column(
        'oauth_accounts',
        'last_used_at',
        existing_type=sa.DateTime(timezone=True),
        type_=sa.TIMESTAMP(),
        nullable=True
    )
    
    # Roles table
    op.alter_column(
        'roles',
        'created_at',
        existing_type=sa.DateTime(timezone=True),
        type_=sa.TIMESTAMP()
    )
    
    op.alter_column(
        'roles',
        'updated_at',
        existing_type=sa.DateTime(timezone=True),
        type_=sa.TIMESTAMP(),
        nullable=True
    )
    
    # Permissions table
    op.alter_column(
        'permissions',
        'created_at',
        existing_type=sa.DateTime(timezone=True),
        type_=sa.TIMESTAMP(),
        nullable=True
    )
    
    # Role Permissions table
    op.alter_column(
        'role_permissions',
        'created_at',
        existing_type=sa.DateTime(timezone=True),
        type_=sa.TIMESTAMP()
    )
    
    # User Roles table
    op.alter_column(
        'user_roles',
        'assigned_at',
        existing_type=sa.DateTime(timezone=True),
        type_=sa.TIMESTAMP()
    )
    
    # User Sessions table
    op.alter_column(
        'user_sessions',
        'created_at',
        existing_type=sa.DateTime(timezone=True),
        type_=sa.TIMESTAMP()
    )
    
    op.alter_column(
        'user_sessions',
        'last_activity_at',
        existing_type=sa.DateTime(timezone=True),
        type_=sa.TIMESTAMP()
    )
    
    op.alter_column(
        'user_sessions',
        'expires_at',
        existing_type=sa.DateTime(timezone=True),
        type_=sa.TIMESTAMP()
    )
    
    op.alter_column(
        'user_sessions',
        'revoked_at',
        existing_type=sa.DateTime(timezone=True),
        type_=sa.TIMESTAMP(),
        nullable=True
    )
    
    # Token Blacklist table
    op.alter_column(
        'token_blacklist',
        'revoked_at',
        existing_type=sa.DateTime(timezone=True),
        type_=sa.TIMESTAMP()
    )
    
    op.alter_column(
        'token_blacklist',
        'expires_at',
        existing_type=sa.DateTime(timezone=True),
        type_=sa.TIMESTAMP()
    )
    
    # Notification Preferences table
    op.alter_column(
        'notification_preferences',
        'created_at',
        existing_type=sa.DateTime(timezone=True),
        type_=sa.TIMESTAMP()
    )
    
    op.alter_column(
        'notification_preferences',
        'updated_at',
        existing_type=sa.DateTime(timezone=True),
        type_=sa.TIMESTAMP()
    )
    
    # Workspace Members table
    op.alter_column(
        'workspace_members',
        'joined_at',
        existing_type=sa.DateTime(timezone=True),
        type_=sa.TIMESTAMP()
    )
    
    op.alter_column(
        'workspace_members',
        'last_activity_at',
        existing_type=sa.DateTime(timezone=True),
        type_=sa.TIMESTAMP(),
        nullable=True
    )
    
    # Email Templates table
    op.alter_column(
        'email_templates',
        'created_at',
        existing_type=sa.DateTime(timezone=True),
        type_=sa.TIMESTAMP()
    )
    
    op.alter_column(
        'email_templates',
        'updated_at',
        existing_type=sa.DateTime(timezone=True),
        type_=sa.TIMESTAMP(),
        nullable=True
    )
    
    # Media table
    op.alter_column(
        'media',
        'created_at',
        existing_type=sa.DateTime(timezone=True),
        type_=sa.TIMESTAMP()
    )
    
    op.alter_column(
        'media',
        'updated_at',
        existing_type=sa.DateTime(timezone=True),
        type_=sa.TIMESTAMP(),
        nullable=True
    )
    
    op.alter_column(
        'media',
        'deleted_at',
        existing_type=sa.DateTime(timezone=True),
        type_=sa.TIMESTAMP(),
        nullable=True
    )
    
    # Subscription Plans table
    op.alter_column(
        'subscription_plans',
        'created_at',
        existing_type=sa.DateTime(timezone=True),
        type_=sa.TIMESTAMP()
    )
    
    op.alter_column(
        'subscription_plans',
        'updated_at',
        existing_type=sa.DateTime(timezone=True),
        type_=sa.TIMESTAMP(),
        nullable=True
    )
    
    # Subscriptions table
    op.alter_column(
        'user_subscriptions',
        'start_date',
        existing_type=sa.DateTime(timezone=True),
        type_=sa.TIMESTAMP()
    )
    
    op.alter_column(
        'user_subscriptions',
        'end_date',
        existing_type=sa.DateTime(timezone=True),
        type_=sa.TIMESTAMP(),
        nullable=True
    )
    
    op.alter_column(
        'user_subscriptions',
        'trial_end_date',
        existing_type=sa.DateTime(timezone=True),
        type_=sa.TIMESTAMP(),
        nullable=True
    )
    
    op.alter_column(
        'user_subscriptions',
        'cancelled_at',
        existing_type=sa.DateTime(timezone=True),
        type_=sa.TIMESTAMP(),
        nullable=True
    )
    
    op.alter_column(
        'user_subscriptions',
        'renews_at',
        existing_type=sa.DateTime(timezone=True),
        type_=sa.TIMESTAMP(),
        nullable=True
    )
    
    op.alter_column(
        'user_subscriptions',
        'ends_at',
        existing_type=sa.DateTime(timezone=True),
        type_=sa.TIMESTAMP(),
        nullable=True
    )
    
    op.alter_column(
        'user_subscriptions',
        'grace_period_end',
        existing_type=sa.DateTime(timezone=True),
        type_=sa.TIMESTAMP(),
        nullable=True
    )
    
    op.alter_column(
        'user_subscriptions',
        'payment_failed_at',
        existing_type=sa.DateTime(timezone=True),
        type_=sa.TIMESTAMP(),
        nullable=True
    )
    
    op.alter_column(
        'user_subscriptions',
        'usage_reset_date',
        existing_type=sa.DateTime(timezone=True),
        type_=sa.TIMESTAMP(),
        nullable=True
    )
    
    op.alter_column(
        'user_subscriptions',
        'created_at',
        existing_type=sa.DateTime(timezone=True),
        type_=sa.TIMESTAMP()
    )
    
    op.alter_column(
        'user_subscriptions',
        'updated_at',
        existing_type=sa.DateTime(timezone=True),
        type_=sa.TIMESTAMP(),
        nullable=True
    )
    
    # Webhook Events table
    op.alter_column(
        'webhook_events',
        'processed_at',
        existing_type=sa.DateTime(timezone=True),
        type_=sa.TIMESTAMP(),
        nullable=True
    )
    
    op.alter_column(
        'webhook_events',
        'created_at',
        existing_type=sa.DateTime(timezone=True),
        type_=sa.TIMESTAMP()
    )
    
    op.alter_column(
        'webhook_events',
        'updated_at',
        existing_type=sa.DateTime(timezone=True),
        type_=sa.TIMESTAMP()
    )
    
    # Refunds table
    op.alter_column(
        'refunds',
        'processed_at',
        existing_type=sa.DateTime(timezone=True),
        type_=sa.TIMESTAMP(),
        nullable=True
    )
    
    op.alter_column(
        'refunds',
        'created_at',
        existing_type=sa.DateTime(timezone=True),
        type_=sa.TIMESTAMP()
    )
    
    op.alter_column(
        'refunds',
        'updated_at',
        existing_type=sa.DateTime(timezone=True),
        type_=sa.TIMESTAMP()
    )
    
    # Payment Methods table
    op.alter_column(
        'payment_methods',
        'created_at',
        existing_type=sa.DateTime(timezone=True),
        type_=sa.TIMESTAMP()
    )
    
    op.alter_column(
        'payment_methods',
        'updated_at',
        existing_type=sa.DateTime(timezone=True),
        type_=sa.TIMESTAMP(),
        nullable=True
    )
    
    # Licenses table
    op.alter_column(
        'licenses',
        'activated_at',
        existing_type=sa.DateTime(timezone=True),
        type_=sa.TIMESTAMP(),
        nullable=True
    )
    
    op.alter_column(
        'licenses',
        'expires_at',
        existing_type=sa.DateTime(timezone=True),
        type_=sa.TIMESTAMP(),
        nullable=True
    )
    
    op.alter_column(
        'licenses',
        'created_at',
        existing_type=sa.DateTime(timezone=True),
        type_=sa.TIMESTAMP()
    )
    
    op.alter_column(
        'licenses',
        'updated_at',
        existing_type=sa.DateTime(timezone=True),
        type_=sa.TIMESTAMP()
    )
    
    # License Activations table
    op.alter_column(
        'license_activations',
        'activated_at',
        existing_type=sa.DateTime(timezone=True),
        type_=sa.TIMESTAMP(timezone=True)
    )
    
    op.alter_column(
        'license_activations',
        'deactivated_at',
        existing_type=sa.DateTime(timezone=True),
        type_=sa.TIMESTAMP(timezone=True),
        nullable=True
    )
    
    op.alter_column(
        'license_activations',
        'last_checked_at',
        existing_type=sa.DateTime(timezone=True),
        type_=sa.TIMESTAMP(timezone=True),
        nullable=True
    )
    
    # Discount Usage table
    op.alter_column(
        'discount_usage',
        'applied_at',
        existing_type=sa.DateTime(timezone=True),
        type_=sa.TIMESTAMP(timezone=True)
    )
    
    # Content Media table
    op.alter_column(
        'content_media',
        'created_at',
        existing_type=sa.DateTime(timezone=True),
        type_=sa.TIMESTAMP(timezone=True)
    )
    
    # Audit Logs table
    op.alter_column(
        'audit_logs',
        'created_at',
        existing_type=sa.DateTime(timezone=True),
        type_=sa.TIMESTAMP()
    )
    
    # Notifications table
    op.alter_column(
        'notifications',
        'read_at',
        existing_type=sa.DateTime(timezone=True),
        type_=sa.TIMESTAMP(),
        nullable=True
    )
    
    op.alter_column(
        'notifications',
        'archived_at',
        existing_type=sa.DateTime(timezone=True),
        type_=sa.TIMESTAMP(),
        nullable=True
    )
    
    op.alter_column(
        'notifications',
        'deleted_at',
        existing_type=sa.DateTime(timezone=True),
        type_=sa.TIMESTAMP(),
        nullable=True
    )
    
    op.alter_column(
        'notifications',
        'email_sent_at',
        existing_type=sa.DateTime(timezone=True),
        type_=sa.TIMESTAMP(),
        nullable=True
    )
    
    op.alter_column(
        'notifications',
        'sse_sent_at',
        existing_type=sa.DateTime(timezone=True),
        type_=sa.TIMESTAMP(),
        nullable=True
    )
    
    op.alter_column(
        'notifications',
        'expires_at',
        existing_type=sa.DateTime(timezone=True),
        type_=sa.TIMESTAMP(),
        nullable=True
    )
    
    op.alter_column(
        'notifications',
        'created_at',
        existing_type=sa.DateTime(timezone=True),
        type_=sa.TIMESTAMP()
    )
    
    op.alter_column(
        'notifications',
        'updated_at',
        existing_type=sa.DateTime(timezone=True),
        type_=sa.TIMESTAMP()
    )
    
    # Email Preferences table
    op.alter_column(
        'email_preferences',
        'created_at',
        existing_type=sa.DateTime(timezone=True),
        type_=sa.TIMESTAMP(),
        nullable=True
    )
    
    op.alter_column(
        'email_preferences',
        'updated_at',
        existing_type=sa.DateTime(timezone=True),
        type_=sa.TIMESTAMP(),
        nullable=True
    )
    
    # User Preferences table
    op.alter_column(
        'user_preferences',
        'created_at',
        existing_type=sa.DateTime(timezone=True),
        type_=sa.TIMESTAMP()
    )
    
    op.alter_column(
        'user_preferences',
        'updated_at',
        existing_type=sa.DateTime(timezone=True),
        type_=sa.TIMESTAMP()
    )
    
    # User Onboarding table
    op.alter_column(
        'user_onboarding',
        'started_at',
        existing_type=sa.DateTime(timezone=True),
        type_=sa.TIMESTAMP(timezone=True)
    )
    
    op.alter_column(
        'user_onboarding',
        'completed_at',
        existing_type=sa.DateTime(timezone=True),
        type_=sa.TIMESTAMP(timezone=True),
        nullable=True
    )
    
    op.alter_column(
        'user_onboarding',
        'created_at',
        existing_type=sa.DateTime(timezone=True),
        type_=sa.TIMESTAMP(timezone=True)
    )
    
    op.alter_column(
        'user_onboarding',
        'updated_at',
        existing_type=sa.DateTime(timezone=True),
        type_=sa.TIMESTAMP(timezone=True)
    )
    
    # Error Logs table
    op.alter_column(
        'error_logs',
        'timestamp',
        existing_type=sa.DateTime(timezone=True),
        type_=sa.DateTime()
    )
    
    op.alter_column(
        'error_logs',
        'resolved_at',
        existing_type=sa.DateTime(timezone=True),
        type_=sa.DateTime(),
        nullable=True
    )
    
    # Content table
    op.alter_column(
        'content',
        'created_at',
        existing_type=sa.DateTime(timezone=True),
        type_=sa.TIMESTAMP(timezone=True)
    )
    
    op.alter_column(
        'content',
        'updated_at',
        existing_type=sa.DateTime(timezone=True),
        type_=sa.TIMESTAMP(timezone=True),
        nullable=True
    )
    
    op.alter_column(
        'content',
        'wordpress_published_at',
        existing_type=sa.DateTime(timezone=True),
        type_=sa.TIMESTAMP(timezone=True),
        nullable=True
    )
    
    # Workspace table
    op.alter_column(
        'workspace',
        'created_at',
        existing_type=sa.DateTime(timezone=True),
        type_=sa.TIMESTAMP(timezone=True)
    )
    
    op.alter_column(
        'workspace',
        'updated_at',
        existing_type=sa.DateTime(timezone=True),
        type_=sa.TIMESTAMP(timezone=True),
        nullable=True
    )
    
    # Platform Admin Invitations table
    op.alter_column(
        'platform_admin_invitations',
        'created_at',
        existing_type=sa.DateTime(timezone=True),
        type_=sa.TIMESTAMP()
    )
    
    op.alter_column(
        'platform_admin_invitations',
        'expires_at',
        existing_type=sa.DateTime(timezone=True),
        type_=sa.TIMESTAMP()
    )
    
    op.alter_column(
        'platform_admin_invitations',
        'accepted_at',
        existing_type=sa.DateTime(timezone=True),
        type_=sa.TIMESTAMP(),
        nullable=True
    )
    
    op.alter_column(
        'platform_admin_invitations',
        'declined_at',
        existing_type=sa.DateTime(timezone=True),
        type_=sa.TIMESTAMP(),
        nullable=True
    )
    
    op.alter_column(
        'platform_admin_invitations',
        'revoked_at',
        existing_type=sa.DateTime(timezone=True),
        type_=sa.TIMESTAMP(),
        nullable=True
    )

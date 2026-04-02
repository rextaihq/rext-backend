"""update_lemonsqueezy_plan_ids_2026

Revision ID: update_ls_ids_2026
Revises: 9bf42d4f9b39
Create Date: 2026-04-02 00:00:00.000000

Updates Basic and Pro plan LemonSqueezy product/variant IDs to new values.
"""
from typing import Sequence, Union
from alembic import op
from sqlalchemy import orm
from sqlalchemy.ext.declarative import declarative_base
import sqlalchemy as sa
from datetime import datetime, timezone

revision: str = 'update_ls_ids_2026'
down_revision: Union[str, Sequence[str], None] = '9bf42d4f9b39'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

Base = declarative_base()


class SubscriptionPlan(Base):
    __tablename__ = 'subscription_plans'
    id = sa.Column(sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True)
    name = sa.Column(sa.String(100), unique=True, nullable=False)
    lemonsqueezy_product_id = sa.Column(sa.String(255))
    lemonsqueezy_variant_id_monthly = sa.Column(sa.String(255))
    lemonsqueezy_variant_id_yearly = sa.Column(sa.String(255))
    lemonsqueezy_store_id = sa.Column(sa.String(255))
    provider_price_id_monthly = sa.Column(sa.String(255))
    provider_price_id_yearly = sa.Column(sa.String(255))
    updated_at = sa.Column(sa.TIMESTAMP)


def upgrade() -> None:
    bind = op.get_bind()
    session = orm.Session(bind=bind)

    now = datetime.now(timezone.utc).replace(tzinfo=None)

    # ── Basic Plan ────────────────────────────────────────────────────────────
    basic = session.query(SubscriptionPlan).filter_by(name='basic').first()
    if basic:
        basic.lemonsqueezy_product_id = "941169"
        basic.lemonsqueezy_variant_id_monthly = "1479192"
        basic.lemonsqueezy_variant_id_yearly = "1479213"
        basic.provider_price_id_monthly = "1479192"
        basic.provider_price_id_yearly = "1479213"
        basic.updated_at = now
        print("✅ Updated Basic plan LemonSqueezy IDs")
    else:
        print("⚠️  Basic plan not found — skipping")

    # ── Pro Plan ──────────────────────────────────────────────────────────────
    pro = session.query(SubscriptionPlan).filter_by(name='pro').first()
    if pro:
        pro.lemonsqueezy_product_id = "941200"
        pro.lemonsqueezy_variant_id_monthly = "1479235"
        pro.lemonsqueezy_variant_id_yearly = "1479253"
        pro.provider_price_id_monthly = "1479235"
        pro.provider_price_id_yearly = "1479253"
        pro.updated_at = now
        print("✅ Updated Pro plan LemonSqueezy IDs")
    else:
        print("⚠️  Pro plan not found — skipping")

    session.commit()
    print("\n✅ Migration complete — LemonSqueezy plan IDs updated")


def downgrade() -> None:
    bind = op.get_bind()
    session = orm.Session(bind=bind)

    now = datetime.now(timezone.utc).replace(tzinfo=None)

    # Restore previous Basic plan IDs
    basic = session.query(SubscriptionPlan).filter_by(name='basic').first()
    if basic:
        basic.lemonsqueezy_product_id = "665157"
        basic.lemonsqueezy_variant_id_monthly = "1045158"
        basic.lemonsqueezy_variant_id_yearly = "1049347"
        basic.provider_price_id_monthly = "1045158"
        basic.provider_price_id_yearly = "1049347"
        basic.updated_at = now

    # Restore previous Pro plan IDs
    pro = session.query(SubscriptionPlan).filter_by(name='pro').first()
    if pro:
        pro.lemonsqueezy_product_id = "667795"
        pro.lemonsqueezy_variant_id_monthly = "1049346"
        pro.lemonsqueezy_variant_id_yearly = "1049351"
        pro.provider_price_id_monthly = "1049346"
        pro.provider_price_id_yearly = "1049351"
        pro.updated_at = now

    session.commit()
    print("✅ Downgrade complete — LemonSqueezy IDs restored to previous values")

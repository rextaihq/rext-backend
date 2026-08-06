"""update_lemonsqueezy_plan_ids_2026

Revision ID: update_ls_ids_2026
Revises: 9bf42d4f9b39
Create Date: 2026-04-02 00:00:00.000000

Updates Basic and Pro plan LemonSqueezy product/variant IDs to new values.
"""
from typing import Sequence, Union
import os
from alembic import op
from sqlalchemy import orm
from sqlalchemy.ext.declarative import declarative_base
import sqlalchemy as sa
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

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


def _normalize_env(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _plan_env_token(plan_name: str) -> str:
    return "".join(char if char.isalnum() else "_" for char in plan_name.upper()).strip("_")


def _get_required_plan_ids(plan_name: str) -> dict[str, str | None]:
    token = _plan_env_token(plan_name)
    names = {
        "product_id": f"LEMONSQUEEZY_{token}_PRODUCT_ID",
        "variant_id_monthly": f"LEMONSQUEEZY_{token}_VARIANT_ID_MONTHLY",
        "variant_id_yearly": f"LEMONSQUEEZY_{token}_VARIANT_ID_YEARLY",
        "store_id": f"LEMONSQUEEZY_{token}_STORE_ID",
        "global_store_id": "LEMONSQUEEZY_STORE_ID",
    }
    values = {
        "product_id": _normalize_env(os.getenv(names["product_id"])),
        "variant_id_monthly": _normalize_env(os.getenv(names["variant_id_monthly"])),
        "variant_id_yearly": _normalize_env(os.getenv(names["variant_id_yearly"])),
        "store_id": _normalize_env(os.getenv(names["store_id"])) or _normalize_env(os.getenv(names["global_store_id"])),
    }
    missing = [
        names[field]
        for field in ("product_id", "variant_id_monthly", "variant_id_yearly")
        if not values[field]
    ]
    if missing:
        raise RuntimeError(
            f"Missing LemonSqueezy env vars for plan '{plan_name}': {', '.join(missing)}"
        )
    return values


def upgrade() -> None:
    bind = op.get_bind()
    session = orm.Session(bind=bind)

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    basic_ids = _get_required_plan_ids("basic")
    pro_ids = _get_required_plan_ids("pro")

    # ── Basic Plan ────────────────────────────────────────────────────────────
    basic = session.query(SubscriptionPlan).filter_by(name='basic').first()
    if basic:
        basic.lemonsqueezy_product_id = basic_ids["product_id"]
        basic.lemonsqueezy_variant_id_monthly = basic_ids["variant_id_monthly"]
        basic.lemonsqueezy_variant_id_yearly = basic_ids["variant_id_yearly"]
        basic.lemonsqueezy_store_id = basic_ids["store_id"]
        basic.provider_price_id_monthly = basic_ids["variant_id_monthly"]
        basic.provider_price_id_yearly = basic_ids["variant_id_yearly"]
        basic.updated_at = now
        print("✅ Updated Basic plan LemonSqueezy IDs")
    else:
        print("⚠️  Basic plan not found — skipping")

    # ── Pro Plan ──────────────────────────────────────────────────────────────
    pro = session.query(SubscriptionPlan).filter_by(name='pro').first()
    if pro:
        pro.lemonsqueezy_product_id = pro_ids["product_id"]
        pro.lemonsqueezy_variant_id_monthly = pro_ids["variant_id_monthly"]
        pro.lemonsqueezy_variant_id_yearly = pro_ids["variant_id_yearly"]
        pro.lemonsqueezy_store_id = pro_ids["store_id"]
        pro.provider_price_id_monthly = pro_ids["variant_id_monthly"]
        pro.provider_price_id_yearly = pro_ids["variant_id_yearly"]
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

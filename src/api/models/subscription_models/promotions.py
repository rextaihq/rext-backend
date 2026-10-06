"""
Promotions: time-boxed offers on new subscriptions, kept as data.

A promotion gives bonus credits (``kind = 'bonus_credits'``) to a paid
subscription started inside its window: either a multiple of the plan's monthly
credits for the first month (``credit_multiplier = 2`` doubles it) or a fixed
number (``bonus_credits``). It can be limited to some plans and billing periods
and to a number of redemptions. The Lemon Squeezy webhook reads the promotion
that applies when a subscription is created and records the bonus as a credit
grant pointing at it. Price discounts are not promotions: they stay Lemon
Squeezy discount codes.
"""

import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Integer,
    String,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.sql import func

from src.api.database.base import Base
from src.api.models.base import SerializableMixin


class Promotion(Base, SerializableMixin):
    __tablename__ = "promotions"
    __table_args__ = (
        CheckConstraint("kind IN ('bonus_credits')", name="ck_promotions_kind"),
        CheckConstraint("starts_at < ends_at", name="ck_promotions_window"),
        CheckConstraint(
            "(credit_multiplier IS NOT NULL AND credit_multiplier > 1 AND bonus_credits IS NULL)"
            " OR (bonus_credits IS NOT NULL AND bonus_credits > 0 AND credit_multiplier IS NULL)",
            name="ck_promotions_bonus",
        ),
        CheckConstraint(
            "max_redemptions IS NULL OR max_redemptions > 0", name="ck_promotions_max_redemptions"
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, nullable=False)
    # Stable id shared with the marketing site's campaign ("launch-2026-10").
    code = Column(String(64), nullable=False, unique=True)
    # How the bonus is named where the customer sees it ("Launch bonus").
    label = Column(String(100), nullable=False)
    kind = Column(String(32), nullable=False, server_default="bonus_credits")
    credit_multiplier = Column(Integer, nullable=True)
    bonus_credits = Column(Integer, nullable=True)
    starts_at = Column(DateTime(timezone=True), nullable=False)
    ends_at = Column(DateTime(timezone=True), nullable=False)
    # NULL: every paid plan / both billing periods.
    plan_names = Column(ARRAY(String(50)), nullable=True)
    billing_periods = Column(ARRAY(String(20)), nullable=True)
    max_redemptions = Column(Integer, nullable=True)
    is_active = Column(Boolean, nullable=False, server_default="true")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

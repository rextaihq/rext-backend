"""Business logic for subscription analytics endpoints."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.models.subscription_models.plans import SubscriptionPlan
from src.api.models.subscription_models.subscriptions import (
    BillingPeriod,
    SubscriptionStatus,
    UserSubscription,
)


class SubscriptionAnalyticsService:
    """Provide administrative analytics for subscription metrics."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_subscription_stats(self) -> Dict[str, Any]:
        """Return high-level subscription statistics."""
        counts = await self._count_by_status(
            [
                SubscriptionStatus.ACTIVE,
                SubscriptionStatus.TRIAL,
                SubscriptionStatus.CANCELLED,
                SubscriptionStatus.EXPIRED,
                SubscriptionStatus.SUSPENDED,
            ]
        )
        total_subscriptions = await self._count_all_subscriptions()

        mrr = await self._calculate_mrr(include_trial=True)
        arr = mrr * 12

        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        cancellations_last_month = await self._count_cancellations(thirty_days_ago)
        churn_rate = self._safe_percentage(cancellations_last_month, counts[SubscriptionStatus.ACTIVE])

        total_trials_ever = await self._count_trials_ever()
        converted_trials = await self._count_converted_trials()
        trial_conversion_rate = self._safe_percentage(converted_trials, total_trials_ever)

        average_ltv = round(mrr * 12 if counts[SubscriptionStatus.ACTIVE] > 0 else 0, 2)

        return {
            "data": {
                "total_subscriptions": total_subscriptions,
                "active_subscriptions": counts[SubscriptionStatus.ACTIVE],
                "trial_subscriptions": counts[SubscriptionStatus.TRIAL],
                "cancelled_subscriptions": counts[SubscriptionStatus.CANCELLED],
                "expired_subscriptions": counts[SubscriptionStatus.EXPIRED],
                "suspended_subscriptions": counts[SubscriptionStatus.SUSPENDED],
                "mrr": round(mrr, 2),
                "arr": round(arr, 2),
                "churn_rate_monthly": round(churn_rate, 2),
                "trial_conversion_rate": round(trial_conversion_rate, 2),
                "average_ltv": average_ltv,
            },
            "message": "Subscription statistics retrieved successfully",
        }

    async def get_revenue_metrics(self) -> Dict[str, Any]:
        """Return revenue metrics including plan breakdown."""
        current_mrr = await self._calculate_mrr(include_trial=True)
        new_revenue = await self._calculate_new_revenue(days=30)
        by_plan = await self._calculate_plan_revenue()

        growth_rate = self._safe_percentage(new_revenue, current_mrr)

        return {
            "data": {
                "current_month": {
                    "mrr": round(current_mrr, 2),
                    "new_revenue": round(new_revenue, 2),
                    "expansion_revenue": 0.0,
                    "contraction_revenue": 0.0,
                    "churned_revenue": 0.0,
                },
                "by_plan": by_plan,
                "growth_rate": round(growth_rate, 2),
            },
            "message": "Revenue metrics retrieved successfully",
        }

    async def get_churn_analysis(self, period_days: int) -> Dict[str, Any]:
        """Return churn analysis over a period."""
        period_start = datetime.utcnow() - timedelta(days=period_days)
        period_end = datetime.utcnow()

        total_active_start = await self._count_active_at_start(period_start)
        new_subscriptions = await self._count_new_subscriptions(period_start, period_end)
        cancellations = await self._count_cancellations(period_start, period_end)
        total_active_end = await self._count_active_now()

        churn_rate = self._safe_percentage(cancellations, total_active_start)
        retention_rate = round(100 - churn_rate, 2)

        return {
            "data": {
                "period": f"last_{period_days}_days",
                "total_active_start": total_active_start,
                "new_subscriptions": new_subscriptions,
                "cancellations": cancellations,
                "total_active_end": total_active_end,
                "churn_rate": round(churn_rate, 2),
                "retention_rate": retention_rate,
            },
            "message": "Churn analysis retrieved successfully",
        }

    async def get_trial_conversion_metrics(self, period_days: int) -> Dict[str, Any]:
        """Return trial conversion metrics over a period."""
        period_start = datetime.utcnow() - timedelta(days=period_days)

        total_trials_started = await self._count_trials_started(period_start)
        trials_converted = await self._count_trials_converted(period_start)
        trials_expired = await self._count_trials_expired(period_start)
        trials_active = await self._count_trials_active(period_start)
        conversion_rate = self._safe_percentage(trials_converted, total_trials_started)
        average_length = await self._average_trial_length(period_start)

        return {
            "data": {
                "total_trials_started": total_trials_started,
                "trials_converted": trials_converted,
                "trials_expired": trials_expired,
                "trials_active": trials_active,
                "conversion_rate": round(conversion_rate, 2),
                "average_trial_length_days": average_length,
            },
            "message": "Trial conversion metrics retrieved successfully",
        }

    async def _count_all_subscriptions(self) -> int:
        result = await self.db.execute(select(func.count(UserSubscription.id)))
        return result.scalar() or 0

    async def _count_by_status(self, statuses: List[SubscriptionStatus]) -> Dict[SubscriptionStatus, int]:
        counts: Dict[SubscriptionStatus, int] = {status: 0 for status in statuses}
        for status in statuses:
            result = await self.db.execute(
                select(func.count(UserSubscription.id)).where(UserSubscription.status == status)
            )
            counts[status] = result.scalar() or 0
        return counts

    async def _count_cancellations(self, start: datetime, end: datetime | None = None) -> int:
        filters = [UserSubscription.cancelled_at >= start]
        if end is not None:
            filters.append(UserSubscription.cancelled_at <= end)
        result = await self.db.execute(select(func.count(UserSubscription.id)).where(*filters))
        return result.scalar() or 0

    async def _count_trials_ever(self) -> int:
        result = await self.db.execute(
            select(func.count(UserSubscription.id)).where(
                or_(
                    UserSubscription.status == SubscriptionStatus.TRIAL,
                    and_(
                        UserSubscription.status == SubscriptionStatus.ACTIVE,
                        UserSubscription.trial_end_date.isnot(None),
                    ),
                )
            )
        )
        return result.scalar() or 0

    async def _count_converted_trials(self) -> int:
        result = await self.db.execute(
            select(func.count(UserSubscription.id)).where(
                UserSubscription.status == SubscriptionStatus.ACTIVE,
                UserSubscription.trial_end_date.isnot(None),
            )
        )
        return result.scalar() or 0

    async def _calculate_mrr(self, include_trial: bool = False) -> float:
        statuses = [SubscriptionStatus.ACTIVE]
        if include_trial:
            statuses.append(SubscriptionStatus.TRIAL)

        query = (
            select(
                func.sum(
                    case(
                        (UserSubscription.billing_period == BillingPeriod.MONTHLY, SubscriptionPlan.price_monthly),
                        (
                            UserSubscription.billing_period == BillingPeriod.YEARLY,
                            SubscriptionPlan.price_yearly / 12,
                        ),
                        else_=0,
                    )
                )
            )
            .join(SubscriptionPlan, UserSubscription.plan_id == SubscriptionPlan.id)
            .where(UserSubscription.status.in_(statuses))
        )
        result = await self.db.execute(query)
        value = result.scalar()
        return float(value) if value else 0.0

    async def _calculate_new_revenue(self, days: int) -> float:
        start_date = datetime.utcnow() - timedelta(days=days)
        query = (
            select(
                func.sum(
                    case(
                        (UserSubscription.billing_period == BillingPeriod.MONTHLY, SubscriptionPlan.price_monthly),
                        (
                            UserSubscription.billing_period == BillingPeriod.YEARLY,
                            SubscriptionPlan.price_yearly / 12,
                        ),
                        else_=0,
                    )
                )
            )
            .join(SubscriptionPlan, UserSubscription.plan_id == SubscriptionPlan.id)
            .where(UserSubscription.start_date >= start_date)
        )
        result = await self.db.execute(query)
        value = result.scalar()
        return float(value) if value else 0.0

    async def _calculate_plan_revenue(self) -> List[Dict[str, Any]]:
        query = (
            select(
                SubscriptionPlan.id,
                SubscriptionPlan.name,
                SubscriptionPlan.display_name,
                func.count(UserSubscription.id).label("subscription_count"),
                func.sum(
                    case(
                        (UserSubscription.billing_period == BillingPeriod.MONTHLY, SubscriptionPlan.price_monthly),
                        (
                            UserSubscription.billing_period == BillingPeriod.YEARLY,
                            SubscriptionPlan.price_yearly / 12,
                        ),
                        else_=0,
                    )
                ).label("revenue_monthly"),
            )
            .join(UserSubscription, SubscriptionPlan.id == UserSubscription.plan_id)
            .where(UserSubscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL]))
            .group_by(SubscriptionPlan.id, SubscriptionPlan.name, SubscriptionPlan.display_name)
        )

        result = await self.db.execute(query)
        records = result.all()

        data: List[Dict[str, Any]] = []
        for plan_id, plan_name, display_name, count, revenue_monthly in records:
            monthly_rev = float(revenue_monthly or 0)
            data.append(
                {
                    "plan_id": str(plan_id),
                    "plan_name": plan_name,
                    "plan_display_name": display_name,
                    "subscription_count": count,
                    "revenue_monthly": round(monthly_rev, 2),
                    "revenue_yearly": round(monthly_rev * 12, 2),
                }
            )
        return data

    async def _count_active_at_start(self, period_start: datetime) -> int:
        result = await self.db.execute(
            select(func.count(UserSubscription.id)).where(
                UserSubscription.start_date < period_start,
                or_(
                    UserSubscription.end_date.is_(None),
                    UserSubscription.end_date > period_start,
                ),
            )
        )
        return result.scalar() or 0

    async def _count_active_now(self) -> int:
        result = await self.db.execute(
            select(func.count(UserSubscription.id)).where(
                UserSubscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL])
            )
        )
        return result.scalar() or 0

    async def _count_new_subscriptions(self, start: datetime, end: datetime) -> int:
        result = await self.db.execute(
            select(func.count(UserSubscription.id)).where(
                UserSubscription.start_date >= start,
                UserSubscription.start_date <= end,
            )
        )
        return result.scalar() or 0

    async def _count_trials_started(self, period_start: datetime) -> int:
        result = await self.db.execute(
            select(func.count(UserSubscription.id)).where(
                UserSubscription.start_date >= period_start,
                UserSubscription.trial_end_date.isnot(None),
            )
        )
        return result.scalar() or 0

    async def _count_trials_converted(self, period_start: datetime) -> int:
        result = await self.db.execute(
            select(func.count(UserSubscription.id)).where(
                UserSubscription.start_date >= period_start,
                UserSubscription.status == SubscriptionStatus.ACTIVE,
                UserSubscription.trial_end_date.isnot(None),
            )
        )
        return result.scalar() or 0

    async def _count_trials_expired(self, period_start: datetime) -> int:
        result = await self.db.execute(
            select(func.count(UserSubscription.id)).where(
                UserSubscription.start_date >= period_start,
                UserSubscription.status == SubscriptionStatus.EXPIRED,
                UserSubscription.trial_end_date.isnot(None),
            )
        )
        return result.scalar() or 0

    async def _count_trials_active(self, period_start: datetime) -> int:
        result = await self.db.execute(
            select(func.count(UserSubscription.id)).where(
                UserSubscription.start_date >= period_start,
                UserSubscription.status == SubscriptionStatus.TRIAL,
            )
        )
        return result.scalar() or 0

    async def _average_trial_length(self, period_start: datetime) -> float:
        query = select(
            func.extract("epoch", UserSubscription.trial_end_date - UserSubscription.start_date) / 86400
        ).where(
            UserSubscription.start_date >= period_start,
            UserSubscription.trial_end_date.isnot(None),
        )
        result = await self.db.execute(query)
        lengths = [row[0] for row in result.all() if row[0]]
        if not lengths:
            return 0.0
        return round(sum(lengths) / len(lengths), 1)

    @staticmethod
    def _safe_percentage(numerator: float, denominator: float) -> float:
        if not denominator:
            return 0.0
        return (numerator / denominator) * 100

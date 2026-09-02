"""Business logic for subscription analytics endpoints."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.models.subscription_models.plans import SubscriptionPlan
from src.api.models.subscription_models.subscriptions import (
    BillingPeriod,
    SubscriptionStatus,
    UserSubscription,
)
from src.api.models.user_models.users import Users
from src.services.webhook_monitoring_service import _mask_email


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

        thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
        cancellations_last_month = await self._count_cancellations(thirty_days_ago)
        churn_rate = self._safe_percentage(
            cancellations_last_month, counts[SubscriptionStatus.ACTIVE]
        )

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
        period_start = datetime.now(timezone.utc) - timedelta(days=period_days)
        period_end = datetime.now(timezone.utc)

        total_active_start = await self._count_active_at_start(period_start)
        new_subscriptions = await self._count_new_subscriptions(period_start, period_end)
        cancellations = await self._count_cancellations(period_start, period_end)
        reason_breakdown = await self._get_cancellation_reason_breakdown(period_start, period_end)
        total_active_end = await self._count_active_now()

        # Churn is cancellations / subscriptions exposed to churn during the period.
        # Normally that is the count active at the start of the window. When there is
        # no history that far back (e.g. a freshly seeded/restored environment) fall
        # back to the subscriptions that existed at any point in the window so the
        # rate stays meaningful instead of collapsing to 0% / 100% retention.
        churn_base = total_active_start or (total_active_start + new_subscriptions)
        note = None
        if not total_active_start and churn_base:
            note = (
                "No subscriptions predate the selected period; churn is calculated "
                "against subscriptions active during the period."
            )

        churn_rate = self._safe_percentage(cancellations, churn_base)
        retention_rate = round(max(0.0, 100 - churn_rate), 2)

        return {
            "data": {
                "period": f"last_{period_days}_days",
                "total_active_start": total_active_start,
                "new_subscriptions": new_subscriptions,
                "cancellations": cancellations,
                "total_active_end": total_active_end,
                "churn_rate": round(churn_rate, 2),
                "retention_rate": retention_rate,
                "cancellation_reasons": reason_breakdown,
                "note": note,
            },
            "message": "Churn analysis retrieved successfully",
        }

    async def get_trial_conversion_metrics(self, period_days: int) -> Dict[str, Any]:
        """Return trial conversion metrics over a period."""
        period_start = datetime.now(timezone.utc) - timedelta(days=period_days)

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

    async def _count_by_status(
        self, statuses: List[SubscriptionStatus]
    ) -> Dict[SubscriptionStatus, int]:
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
                        (
                            UserSubscription.billing_period == BillingPeriod.MONTHLY,
                            SubscriptionPlan.price_monthly,
                        ),
                        (
                            UserSubscription.billing_period == BillingPeriod.YEARLY,
                            SubscriptionPlan.price_yearly / 12,
                        ),
                        else_=0,
                    )
                )
            )
            .select_from(UserSubscription)
            .join(SubscriptionPlan, UserSubscription.plan_id == SubscriptionPlan.id)
            .where(UserSubscription.status.in_(statuses))
        )
        result = await self.db.execute(query)
        value = result.scalar()
        return float(value) if value else 0.0

    async def _calculate_new_revenue(self, days: int) -> float:
        start_date = datetime.now(timezone.utc) - timedelta(days=days)
        query = (
            select(
                func.sum(
                    case(
                        (
                            UserSubscription.billing_period == BillingPeriod.MONTHLY,
                            SubscriptionPlan.price_monthly,
                        ),
                        (
                            UserSubscription.billing_period == BillingPeriod.YEARLY,
                            SubscriptionPlan.price_yearly / 12,
                        ),
                        else_=0,
                    )
                )
            )
            .select_from(UserSubscription)
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
                        (
                            UserSubscription.billing_period == BillingPeriod.MONTHLY,
                            SubscriptionPlan.price_monthly,
                        ),
                        (
                            UserSubscription.billing_period == BillingPeriod.YEARLY,
                            SubscriptionPlan.price_yearly / 12,
                        ),
                        else_=0,
                    )
                ).label("revenue_monthly"),
            )
            .join(UserSubscription, SubscriptionPlan.id == UserSubscription.plan_id)
            .where(
                UserSubscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL])
            )
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
            func.extract("epoch", UserSubscription.trial_end_date - UserSubscription.start_date)
            / 86400
        ).where(
            UserSubscription.start_date >= period_start,
            UserSubscription.trial_end_date.isnot(None),
        )
        result = await self.db.execute(query)
        lengths = [row[0] for row in result.all() if row[0]]
        if not lengths:
            return 0.0
        return round(float(sum(lengths) / len(lengths)), 1)

    async def get_analytics_overview(self) -> Dict[str, Any]:
        """Return comprehensive analytics overview combining all key metrics."""
        # Get basic stats
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

        # Calculate revenue metrics
        mrr = await self._calculate_mrr(include_trial=True)
        arr = mrr * 12

        # Calculate churn rate
        thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
        cancellations_last_month = await self._count_cancellations(thirty_days_ago)
        churn_rate = self._safe_percentage(
            cancellations_last_month, counts[SubscriptionStatus.ACTIVE]
        )

        # Calculate trial conversion
        total_trials_ever = await self._count_trials_ever()
        converted_trials = await self._count_converted_trials()
        trial_conversion_rate = self._safe_percentage(converted_trials, total_trials_ever)

        # Get revenue by plan
        revenue_by_plan = await self._calculate_plan_revenue()

        # Get recent subscriptions
        recent_subscriptions = await self._get_recent_subscriptions(limit=10)

        # Calculate growth metricss
        new_revenue_30d = await self._calculate_new_revenue(days=30)
        growth_rate = self._safe_percentage(new_revenue_30d, mrr)

        return {
            "data": {
                "stats": {
                    "total_subscriptions": total_subscriptions,
                    "active_subscriptions": counts[SubscriptionStatus.ACTIVE],
                    "trial_subscriptions": counts[SubscriptionStatus.TRIAL],
                    "mrr": round(mrr, 2),
                    "arr": round(arr, 2),
                    "churn_rate_monthly": round(churn_rate, 2),
                    "trial_conversion_rate": round(trial_conversion_rate, 2),
                },
                "revenue_by_plan": revenue_by_plan,
                "growth_metrics": {
                    "new_revenue_30d": round(new_revenue_30d, 2),
                    "growth_rate": round(growth_rate, 2),
                },
                "recent_subscriptions": recent_subscriptions,
            },
            "message": "Analytics overview retrieved successfully",
        }

    async def get_revenue_history(self, period: str = "12_months") -> Dict[str, Any]:
        """Return historical revenue data for charts."""
        period_map = {
            "3_months": 3,
            "6_months": 6,
            "12_months": 12,
        }
        months = period_map.get(period, 12)

        history_data = []
        current_date = datetime.now(timezone.utc)

        for i in range(months, -1, -1):
            month_date = current_date - timedelta(days=30 * i)
            month_start = month_date.replace(day=1)

            # Calculate next month for range
            if month_date.month == 12:
                next_month = month_date.replace(year=month_date.year + 1, month=1, day=1)
            else:
                next_month = month_date.replace(month=month_date.month + 1, day=1)

            # Get MRR for this month
            mrr = await self._calculate_mrr_for_period(month_start, next_month)

            # Get new revenue
            new_revenue = await self._calculate_new_revenue_for_period(month_start, next_month)

            # Get churned revenue
            churned_revenue = await self._calculate_churned_revenue_for_period(
                month_start, next_month
            )

            history_data.append(
                {
                    "month": month_start.strftime("%Y-%m"),
                    "mrr": round(mrr, 2),
                    "new_revenue": round(new_revenue, 2),
                    "churned_revenue": round(churned_revenue, 2),
                    "net_revenue": round(new_revenue - churned_revenue, 2),
                }
            )

        return {
            "data": history_data,
            "message": "Revenue history retrieved successfully",
        }

    async def get_plan_distribution(self) -> Dict[str, Any]:
        """Return subscription distribution by plan with percentages."""
        total_active = await self._count_active_now()
        plan_data = await self._calculate_plan_revenue()

        # Add percentage to each plan
        for plan in plan_data:
            plan["percentage"] = self._safe_percentage(plan["subscription_count"], total_active)

        return {
            "data": plan_data,
            "total_subscriptions": total_active,
            "message": "Plan distribution retrieved successfully",
        }

    async def get_cohort_retention(self, cohort_months: int = 6) -> Dict[str, Any]:
        """Return cohort retention analysis."""
        cohorts = []
        current_date = datetime.now(timezone.utc)

        for i in range(cohort_months, -1, -1):
            cohort_date = current_date - timedelta(days=30 * i)
            cohort_month = cohort_date.replace(day=1)

            # Calculate next month
            if cohort_month.month == 12:
                next_month = cohort_month.replace(year=cohort_month.year + 1, month=1, day=1)
            else:
                next_month = cohort_month.replace(month=cohort_month.month + 1, day=1)

            # Get cohort size (subscriptions started in this month)
            cohort_size = await self._count_subscriptions_started_in_period(
                cohort_month, next_month
            )

            if cohort_size == 0:
                continue

            cohort_data = {
                "cohort": cohort_month.strftime("%Y-%m"),
                "size": cohort_size,
                "month_0": 100,  # Always 100% at start
            }

            # Calculate retention for subsequent months
            for month_offset in range(1, min(6, cohort_months + 1 - i)):
                retention_date = cohort_month + timedelta(days=30 * month_offset)
                retained = await self._count_retained_from_cohort(
                    cohort_month, next_month, retention_date
                )
                retention_percentage = self._safe_percentage(retained, cohort_size)
                cohort_data[f"month_{month_offset}"] = round(retention_percentage, 1)

            cohorts.append(cohort_data)

        return {
            "data": {"cohorts": cohorts},
            "message": "Cohort retention analysis retrieved successfully",
        }

    # Helper methods for new endpoints
    async def _get_recent_subscriptions(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent subscriptions with user and plan details."""
        query = (
            select(
                UserSubscription,
                Users.email,
                Users.display_name,
                SubscriptionPlan.display_name.label("plan_name"),
            )
            .join(Users, UserSubscription.user_id == Users.id)
            .join(SubscriptionPlan, UserSubscription.plan_id == SubscriptionPlan.id)
            .order_by(UserSubscription.start_date.desc())
            .limit(limit)
        )

        result = await self.db.execute(query)
        records = result.all()

        subscriptions = []
        for sub, user_email, user_name, plan_name in records:
            subscriptions.append(
                {
                    "subscription_id": str(sub.id),
                    "user_email_masked": _mask_email(user_email),
                    "user_name": user_name or "***",
                    "plan_name": plan_name,
                    "status": sub.status.value,
                    "start_date": sub.start_date.isoformat() if sub.start_date else None,
                }
            )

        return subscriptions

    async def _calculate_mrr_for_period(self, start: datetime, end: datetime) -> float:
        """Calculate MRR for a specific time period."""
        query = (
            select(
                func.sum(
                    case(
                        (
                            UserSubscription.billing_period == BillingPeriod.MONTHLY,
                            SubscriptionPlan.price_monthly,
                        ),
                        (
                            UserSubscription.billing_period == BillingPeriod.YEARLY,
                            SubscriptionPlan.price_yearly / 12,
                        ),
                        else_=0,
                    )
                )
            )
            .select_from(UserSubscription)
            .join(SubscriptionPlan, UserSubscription.plan_id == SubscriptionPlan.id)
            .where(
                UserSubscription.start_date < end,
                or_(
                    UserSubscription.end_date.is_(None),
                    UserSubscription.end_date >= start,
                ),
                UserSubscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL]),
            )
        )
        result = await self.db.execute(query)
        value = result.scalar()
        return float(value) if value else 0.0

    async def _calculate_new_revenue_for_period(self, start: datetime, end: datetime) -> float:
        """Calculate new revenue for a specific time period."""
        query = (
            select(
                func.sum(
                    case(
                        (
                            UserSubscription.billing_period == BillingPeriod.MONTHLY,
                            SubscriptionPlan.price_monthly,
                        ),
                        (
                            UserSubscription.billing_period == BillingPeriod.YEARLY,
                            SubscriptionPlan.price_yearly / 12,
                        ),
                        else_=0,
                    )
                )
            )
            .select_from(UserSubscription)
            .join(SubscriptionPlan, UserSubscription.plan_id == SubscriptionPlan.id)
            .where(
                UserSubscription.start_date >= start,
                UserSubscription.start_date < end,
            )
        )
        result = await self.db.execute(query)
        value = result.scalar()
        return float(value) if value else 0.0

    async def _calculate_churned_revenue_for_period(self, start: datetime, end: datetime) -> float:
        """Calculate churned revenue for a specific time period."""
        query = (
            select(
                func.sum(
                    case(
                        (
                            UserSubscription.billing_period == BillingPeriod.MONTHLY,
                            SubscriptionPlan.price_monthly,
                        ),
                        (
                            UserSubscription.billing_period == BillingPeriod.YEARLY,
                            SubscriptionPlan.price_yearly / 12,
                        ),
                        else_=0,
                    )
                )
            )
            .select_from(UserSubscription)
            .join(SubscriptionPlan, UserSubscription.plan_id == SubscriptionPlan.id)
            .where(
                UserSubscription.cancelled_at >= start,
                UserSubscription.cancelled_at < end,
            )
        )
        result = await self.db.execute(query)
        value = result.scalar()
        return float(value) if value else 0.0

    async def _count_subscriptions_started_in_period(self, start: datetime, end: datetime) -> int:
        """Count subscriptions started in a specific period."""
        result = await self.db.execute(
            select(func.count(UserSubscription.id)).where(
                UserSubscription.start_date >= start,
                UserSubscription.start_date < end,
            )
        )
        return result.scalar() or 0

    async def _count_retained_from_cohort(
        self, cohort_start: datetime, cohort_end: datetime, retention_date: datetime
    ) -> int:
        """Count how many from a cohort are still active at a retention date."""
        result = await self.db.execute(
            select(func.count(UserSubscription.id)).where(
                UserSubscription.start_date >= cohort_start,
                UserSubscription.start_date < cohort_end,
                or_(
                    UserSubscription.end_date.is_(None),
                    UserSubscription.end_date > retention_date,
                ),
                UserSubscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL]),
            )
        )
        return result.scalar() or 0

    async def _get_cancellation_reason_breakdown(
        self,
        start: datetime,
        end: datetime,
    ) -> Dict[str, int]:
        """Return breakdown of cancellation reasons for a period."""
        query = select(UserSubscription.cancellation_reason).where(
            UserSubscription.cancelled_at >= start,
            UserSubscription.cancelled_at <= end,
            UserSubscription.cancellation_reason.isnot(None),
        )

        result = await self.db.execute(query)
        rows = result.scalars().all()

        breakdown: Dict[str, int] = {}

        for reason_text in rows:
            if not reason_text:
                continue

            parts = [p.strip() for p in reason_text.split(";")]

            for part in parts:
                if part.startswith("Additional feedback"):
                    continue

                breakdown[part] = breakdown.get(part, 0) + 1

        return breakdown

    @staticmethod
    def _safe_percentage(numerator: float, denominator: float) -> float:
        if not denominator:
            return 0.0
        return (numerator / denominator) * 100

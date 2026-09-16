"""Business logic for subscription analytics endpoints."""

from __future__ import annotations

import re
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
from src.api.models.subscription_models.trial_conversions import TrialConversion
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
        churn_by_plan = await self._calculate_churn_by_plan(period_start, period_end)
        total_active_end = await self._count_active_now()

        # Churn rate definition:
        # Numerator: paid subscriptions cancelled during the period (excluding trial drop-offs).
        # Denominator (churn_base): Total customer subscriptions exposed to churn during the period.
        # If subscriptions are acquired during the period and cancel within the same period,
        # using only total_active_start produces misleading rates >100%.
        # The true exposed base is total_active_start + new_subscriptions.
        churn_base = total_active_start + new_subscriptions
        note = None
        if not total_active_start and new_subscriptions:
            note = (
                "No subscriptions predate the selected period; churn is calculated "
                "against subscriptions active during the period."
            )
        elif not churn_base:
            churn_base = total_active_end
            if churn_base:
                note = "Calculated against currently active subscriptions due to lack of historical events."

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
                "churn_by_plan": churn_by_plan,
                "note": note,
            },
            "message": "Churn analysis retrieved successfully",
        }

    async def get_trial_conversion_metrics(self, period_days: int) -> Dict[str, Any]:
        """Return trial conversion metrics over a period."""
        period_end = datetime.now(timezone.utc)
        period_start = period_end - timedelta(days=period_days)

        total_trials_started = await self._count_trials_started(period_start, period_end)
        trials_converted = await self._count_trials_converted(period_start, period_end)
        trials_expired = await self._count_trials_expired(period_start, period_end)
        trials_active = await self._count_trials_active(period_start, period_end)
        trials_cancelled = await self._count_trials_cancelled(period_start, period_end)

        # Reconcile funnel numbers so they logically account for the entire started cohort:
        total_accounted = trials_active + trials_converted + trials_expired + trials_cancelled
        if total_trials_started < total_accounted:
            total_trials_started = total_accounted

        conversion_rate = self._safe_percentage(trials_converted, total_trials_started)
        average_length = await self._average_trial_length(period_start, period_end)
        conversion_by_plan = await self._calculate_trial_conversion_by_plan(
            period_start, period_end
        )

        funnel = [
            {"stage": "Started", "count": total_trials_started},
            {"stage": "Active", "count": trials_active},
            {"stage": "Converted", "count": trials_converted},
            {"stage": "Expired", "count": trials_expired},
            {"stage": "Cancelled", "count": trials_cancelled},
        ]

        return {
            "data": {
                "total_trials_started": total_trials_started,
                "trials_converted": trials_converted,
                "trials_expired": trials_expired,
                "trials_active": trials_active,
                "trials_cancelled": trials_cancelled,
                "conversion_rate": round(conversion_rate, 2),
                "average_trial_length_days": average_length,
                "conversion_by_plan": conversion_by_plan,
                "funnel": funnel,
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

    @staticmethod
    def _trial_subscription_condition():
        """Condition identifying subscriptions that are or were trials."""
        return or_(
            UserSubscription.status == SubscriptionStatus.TRIAL,
            UserSubscription.trial_end_date.isnot(None),
            UserSubscription.id.in_(select(TrialConversion.subscription_id)),
            UserSubscription.plan_id.in_(
                select(SubscriptionPlan.id).where(func.lower(SubscriptionPlan.name) == "trial")
            ),
        )

    async def _count_cancellations(self, start: datetime, end: datetime | None = None) -> int:
        """Count cancellations of paid subscriptions within the period."""
        filters = [
            UserSubscription.status == SubscriptionStatus.CANCELLED,
            func.coalesce(
                UserSubscription.cancelled_at,
                UserSubscription.end_date,
                UserSubscription.updated_at,
            )
            >= start,
            # Exclude cancellations that happened during the trial period (they are trial drop-offs)
            or_(
                UserSubscription.trial_end_date.is_(None),
                and_(
                    UserSubscription.cancelled_at.isnot(None),
                    UserSubscription.cancelled_at > UserSubscription.trial_end_date,
                ),
            ),
        ]
        if end is not None:
            filters.append(
                func.coalesce(
                    UserSubscription.cancelled_at,
                    UserSubscription.end_date,
                    UserSubscription.updated_at,
                )
                <= end
            )
        result = await self.db.execute(
            select(func.count(func.distinct(UserSubscription.id))).where(*filters)
        )
        return result.scalar() or 0

    async def _count_trials_ever(self) -> int:
        result = await self.db.execute(
            select(func.count(func.distinct(UserSubscription.id))).where(
                self._trial_subscription_condition()
            )
        )
        return result.scalar() or 0

    async def _count_converted_trials(self) -> int:
        result = await self.db.execute(
            select(func.count(func.distinct(UserSubscription.id))).where(
                self._trial_subscription_condition(),
                UserSubscription.status != SubscriptionStatus.TRIAL,
                or_(
                    UserSubscription.id.in_(select(TrialConversion.subscription_id)),
                    UserSubscription.status == SubscriptionStatus.ACTIVE,
                    UserSubscription.user_id.in_(
                        select(UserSubscription.user_id).where(
                            UserSubscription.status == SubscriptionStatus.ACTIVE
                        )
                    ),
                ),
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
        """Count paid subscriptions that were active at the start of the period."""
        query = (
            select(func.count(func.distinct(UserSubscription.id)))
            .outerjoin(SubscriptionPlan, UserSubscription.plan_id == SubscriptionPlan.id)
            .where(
                UserSubscription.start_date < period_start,
                or_(
                    UserSubscription.end_date.is_(None),
                    UserSubscription.end_date > period_start,
                ),
                or_(
                    UserSubscription.cancelled_at.is_(None),
                    UserSubscription.cancelled_at > period_start,
                ),
                # Exclude active trials from paid customer churn base
                UserSubscription.status != SubscriptionStatus.TRIAL,
                or_(
                    SubscriptionPlan.name.is_(None),
                    func.lower(SubscriptionPlan.name) != "trial",
                ),
            )
        )
        result = await self.db.execute(query)
        return result.scalar() or 0

    async def _count_active_now(self) -> int:
        result = await self.db.execute(
            select(func.count(UserSubscription.id)).where(
                UserSubscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL])
            )
        )
        return result.scalar() or 0

    async def _count_new_subscriptions(self, start: datetime, end: datetime) -> int:
        """Count new paid subscriptions started within the period."""
        query = (
            select(func.count(func.distinct(UserSubscription.id)))
            .outerjoin(SubscriptionPlan, UserSubscription.plan_id == SubscriptionPlan.id)
            .where(
                UserSubscription.start_date >= start,
                UserSubscription.start_date <= end,
                UserSubscription.status != SubscriptionStatus.TRIAL,
                or_(
                    SubscriptionPlan.name.is_(None),
                    func.lower(SubscriptionPlan.name) != "trial",
                ),
            )
        )
        result = await self.db.execute(query)
        return result.scalar() or 0

    async def _count_trials_started(
        self, period_start: datetime, period_end: datetime | None = None
    ) -> int:
        """Count all trial subscriptions that started in the period."""
        filters = [
            UserSubscription.start_date >= period_start,
            self._trial_subscription_condition(),
        ]
        if period_end is not None:
            filters.append(UserSubscription.start_date <= period_end)
        result = await self.db.execute(
            select(func.count(func.distinct(UserSubscription.id))).where(*filters)
        )
        return result.scalar() or 0

    async def _count_trials_converted(
        self, period_start: datetime, period_end: datetime | None = None
    ) -> int:
        """Count trial subscriptions that started in the period and converted to paid."""
        paid_plans = select(SubscriptionPlan.id).where(func.lower(SubscriptionPlan.name) != "trial")
        filters = [
            UserSubscription.start_date >= period_start,
            self._trial_subscription_condition(),
            or_(
                UserSubscription.id.in_(select(TrialConversion.subscription_id)),
                and_(
                    UserSubscription.status == SubscriptionStatus.ACTIVE,
                    UserSubscription.plan_id.in_(paid_plans),
                ),
                UserSubscription.user_id.in_(
                    select(UserSubscription.user_id).where(
                        UserSubscription.status == SubscriptionStatus.ACTIVE,
                        UserSubscription.plan_id.in_(paid_plans),
                    )
                ),
            ),
        ]
        if period_end is not None:
            filters.append(UserSubscription.start_date <= period_end)
        result = await self.db.execute(
            select(func.count(func.distinct(UserSubscription.id))).where(*filters)
        )
        return result.scalar() or 0

    async def _count_trials_expired(
        self, period_start: datetime, period_end: datetime | None = None
    ) -> int:
        """Count trial subscriptions that started in the period and expired without converting."""
        now = datetime.now(timezone.utc)
        paid_plans = select(SubscriptionPlan.id).where(func.lower(SubscriptionPlan.name) != "trial")
        converted_sub_query = select(UserSubscription.id).where(
            or_(
                UserSubscription.id.in_(select(TrialConversion.subscription_id)),
                and_(
                    UserSubscription.status == SubscriptionStatus.ACTIVE,
                    UserSubscription.plan_id.in_(paid_plans),
                ),
                UserSubscription.user_id.in_(
                    select(UserSubscription.user_id).where(
                        UserSubscription.status == SubscriptionStatus.ACTIVE,
                        UserSubscription.plan_id.in_(paid_plans),
                    )
                ),
            )
        )
        filters = [
            UserSubscription.start_date >= period_start,
            self._trial_subscription_condition(),
            UserSubscription.status != SubscriptionStatus.CANCELLED,
            or_(
                UserSubscription.status == SubscriptionStatus.EXPIRED,
                and_(
                    UserSubscription.status == SubscriptionStatus.TRIAL,
                    UserSubscription.trial_end_date.isnot(None),
                    UserSubscription.trial_end_date < now,
                ),
            ),
            UserSubscription.id.not_in(converted_sub_query),
        ]
        if period_end is not None:
            filters.append(UserSubscription.start_date <= period_end)
        result = await self.db.execute(
            select(func.count(func.distinct(UserSubscription.id))).where(*filters)
        )
        return result.scalar() or 0

    async def _count_trials_active(
        self, period_start: datetime, period_end: datetime | None = None
    ) -> int:
        """Count trial subscriptions started in the period that are still actively in trial."""
        now = datetime.now(timezone.utc)
        paid_plans = select(SubscriptionPlan.id).where(func.lower(SubscriptionPlan.name) != "trial")
        converted_sub_query = select(UserSubscription.id).where(
            or_(
                UserSubscription.id.in_(select(TrialConversion.subscription_id)),
                and_(
                    UserSubscription.status == SubscriptionStatus.ACTIVE,
                    UserSubscription.plan_id.in_(paid_plans),
                ),
                UserSubscription.user_id.in_(
                    select(UserSubscription.user_id).where(
                        UserSubscription.status == SubscriptionStatus.ACTIVE,
                        UserSubscription.plan_id.in_(paid_plans),
                    )
                ),
            )
        )
        filters = [
            UserSubscription.start_date >= period_start,
            UserSubscription.status == SubscriptionStatus.TRIAL,
            or_(
                UserSubscription.trial_end_date.is_(None),
                UserSubscription.trial_end_date >= now,
            ),
            UserSubscription.id.not_in(converted_sub_query),
        ]
        if period_end is not None:
            filters.append(UserSubscription.start_date <= period_end)
        result = await self.db.execute(
            select(func.count(func.distinct(UserSubscription.id))).where(*filters)
        )
        return result.scalar() or 0

    async def _count_trials_cancelled(
        self, period_start: datetime, period_end: datetime | None = None
    ) -> int:
        """Count trial subscriptions started in the period that were cancelled without converting."""
        paid_plans = select(SubscriptionPlan.id).where(func.lower(SubscriptionPlan.name) != "trial")
        converted_sub_query = select(UserSubscription.id).where(
            or_(
                UserSubscription.id.in_(select(TrialConversion.subscription_id)),
                and_(
                    UserSubscription.status == SubscriptionStatus.ACTIVE,
                    UserSubscription.plan_id.in_(paid_plans),
                ),
                UserSubscription.user_id.in_(
                    select(UserSubscription.user_id).where(
                        UserSubscription.status == SubscriptionStatus.ACTIVE,
                        UserSubscription.plan_id.in_(paid_plans),
                    )
                ),
            )
        )
        filters = [
            UserSubscription.start_date >= period_start,
            UserSubscription.status == SubscriptionStatus.CANCELLED,
            self._trial_subscription_condition(),
            UserSubscription.id.not_in(converted_sub_query),
        ]
        if period_end is not None:
            filters.append(UserSubscription.start_date <= period_end)
        result = await self.db.execute(
            select(func.count(func.distinct(UserSubscription.id))).where(*filters)
        )
        return result.scalar() or 0

    async def _average_trial_length(
        self, period_start: datetime, period_end: datetime | None = None
    ) -> float:
        """Calculate average trial duration in days for trials started in the period."""
        filters = [
            UserSubscription.start_date >= period_start,
            UserSubscription.trial_end_date.isnot(None),
        ]
        if period_end is not None:
            filters.append(UserSubscription.start_date <= period_end)

        query = select(
            func.extract("epoch", UserSubscription.trial_end_date - UserSubscription.start_date)
            / 86400
        ).where(*filters)
        result = await self.db.execute(query)
        lengths = [row[0] for row in result.all() if row[0] is not None]
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

    async def _calculate_trial_conversion_by_plan(
        self, period_start: datetime, period_end: datetime | None = None
    ) -> List[Dict[str, Any]]:
        """Calculate trial conversion metrics broken down by subscription plan."""
        filters = [
            UserSubscription.start_date >= period_start,
            self._trial_subscription_condition(),
        ]
        if period_end is not None:
            filters.append(UserSubscription.start_date <= period_end)

        paid_plans = select(SubscriptionPlan.id).where(func.lower(SubscriptionPlan.name) != "trial")
        converted_cond = or_(
            UserSubscription.id.in_(select(TrialConversion.subscription_id)),
            and_(
                UserSubscription.status == SubscriptionStatus.ACTIVE,
                UserSubscription.plan_id.in_(paid_plans),
            ),
            UserSubscription.user_id.in_(
                select(UserSubscription.user_id).where(
                    UserSubscription.status == SubscriptionStatus.ACTIVE,
                    UserSubscription.plan_id.in_(paid_plans),
                )
            ),
        )

        query = (
            select(
                SubscriptionPlan.name,
                SubscriptionPlan.display_name,
                func.count(func.distinct(UserSubscription.id)).label("trials"),
                func.count(
                    func.distinct(case((converted_cond, UserSubscription.id), else_=None))
                ).label("conversions"),
            )
            .select_from(UserSubscription)
            .outerjoin(SubscriptionPlan, UserSubscription.plan_id == SubscriptionPlan.id)
            .where(*filters)
            .group_by(SubscriptionPlan.name, SubscriptionPlan.display_name)
        )

        result = await self.db.execute(query)
        records = result.all()

        data: List[Dict[str, Any]] = []
        for plan_name, display_name, trials, conversions in records:
            name = display_name or plan_name or "Standard Trial"
            trials_count = trials or 0
            conversions_count = conversions or 0
            rate = self._safe_percentage(conversions_count, trials_count)
            data.append(
                {
                    "plan_name": name,
                    "trials": trials_count,
                    "conversions": conversions_count,
                    "conversion_rate": round(rate, 2),
                }
            )
        return data

    async def _calculate_churn_by_plan(
        self, period_start: datetime, period_end: datetime | None = None
    ) -> List[Dict[str, Any]]:
        """Calculate churn metrics broken down by subscription plan."""
        end = period_end or datetime.now(timezone.utc)

        plans_result = await self.db.execute(select(SubscriptionPlan))
        plans = plans_result.scalars().all()

        # Group plan IDs by display name
        plans_by_name: Dict[str, List[Any]] = {}
        for plan in plans:
            if plan.name and plan.name.lower() == "trial":
                continue
            name = plan.display_name or plan.name or "Standard"
            plans_by_name.setdefault(name, []).append(plan.id)

        data: List[Dict[str, Any]] = []
        for name, plan_ids in plans_by_name.items():
            # Count cancellations for these plan IDs during period (excluding trial drop-offs)
            cancel_query = select(func.count(func.distinct(UserSubscription.id))).where(
                UserSubscription.plan_id.in_(plan_ids),
                UserSubscription.status == SubscriptionStatus.CANCELLED,
                func.coalesce(
                    UserSubscription.cancelled_at,
                    UserSubscription.end_date,
                    UserSubscription.updated_at,
                )
                >= period_start,
                func.coalesce(
                    UserSubscription.cancelled_at,
                    UserSubscription.end_date,
                    UserSubscription.updated_at,
                )
                <= end,
                or_(
                    UserSubscription.trial_end_date.is_(None),
                    UserSubscription.cancelled_at > UserSubscription.trial_end_date,
                ),
            )
            cancel_res = await self.db.execute(cancel_query)
            churned = cancel_res.scalar() or 0

            # Count active at start for these plan IDs
            active_start_query = select(func.count(func.distinct(UserSubscription.id))).where(
                UserSubscription.plan_id.in_(plan_ids),
                UserSubscription.start_date < period_start,
                or_(
                    UserSubscription.end_date.is_(None),
                    UserSubscription.end_date > period_start,
                ),
                or_(
                    UserSubscription.cancelled_at.is_(None),
                    UserSubscription.cancelled_at > period_start,
                ),
                UserSubscription.status != SubscriptionStatus.TRIAL,
            )
            active_res = await self.db.execute(active_start_query)
            active_start = active_res.scalar() or 0

            # Count new subscriptions during period for these plan IDs
            new_subs_query = select(func.count(func.distinct(UserSubscription.id))).where(
                UserSubscription.plan_id.in_(plan_ids),
                UserSubscription.start_date >= period_start,
                UserSubscription.start_date <= end,
                UserSubscription.status != SubscriptionStatus.TRIAL,
            )
            new_subs_res = await self.db.execute(new_subs_query)
            new_subs = new_subs_res.scalar() or 0

            total_base = active_start + new_subs
            if total_base == 0:
                active_now_query = select(func.count(func.distinct(UserSubscription.id))).where(
                    UserSubscription.plan_id.in_(plan_ids),
                    UserSubscription.status == SubscriptionStatus.ACTIVE,
                )
                active_now_res = await self.db.execute(active_now_query)
                total_base = active_now_res.scalar() or 0

            if total_base > 0 or churned > 0:
                churn_rate = self._safe_percentage(churned, total_base) if total_base > 0 else 0.0
                data.append(
                    {
                        "plan_name": name,
                        "churned": churned,
                        "total": total_base,
                        "churn_rate": round(churn_rate, 2),
                    }
                )
        return data

    @staticmethod
    def _parse_cancellation_reasons(reason_text: str) -> List[str]:
        """Parse cancellation reason string supporting multiple formats."""
        if not reason_text or not reason_text.strip():
            return []
        cleaned = reason_text.strip()

        # Format 1: Pipe-separated (Frontend format: "Reasons: A, B | Feedback: text")
        if " | " in cleaned or cleaned.startswith("Reasons:"):
            parts = cleaned.split(" | ")
            reasons: List[str] = []
            for part in parts:
                part = part.strip()
                if part.lower().startswith("feedback:"):
                    continue
                if part.lower().startswith("reasons:"):
                    part = part[8:].strip()
                for sub in re.split(r"[,;]", part):
                    sub = sub.strip()
                    if sub and not sub.lower().startswith("feedback:"):
                        reasons.append(sub)
            return reasons if reasons else [cleaned]

        # Format 2: Semicolon-separated (Legacy format: "Missing features; Additional feedback: text")
        if ";" in cleaned:
            reasons = []
            for part in cleaned.split(";"):
                part = part.strip()
                if part.lower().startswith("additional feedback:") or part.lower().startswith(
                    "feedback:"
                ):
                    continue
                if part.lower().startswith("reasons:"):
                    part = part[8:].strip()
                if part:
                    reasons.append(part)
            return reasons if reasons else [cleaned]

        # Format 3: Single plain reason
        return [cleaned]

    async def _get_cancellation_reason_breakdown(
        self,
        start: datetime,
        end: datetime,
    ) -> Dict[str, int]:
        """Return breakdown of cancellation reasons for a period."""
        query = select(UserSubscription.cancellation_reason).where(
            func.coalesce(
                UserSubscription.cancelled_at,
                UserSubscription.end_date,
                UserSubscription.updated_at,
            )
            >= start,
            func.coalesce(
                UserSubscription.cancelled_at,
                UserSubscription.end_date,
                UserSubscription.updated_at,
            )
            <= end,
            UserSubscription.cancellation_reason.isnot(None),
        )

        result = await self.db.execute(query)
        rows = result.scalars().all()

        breakdown: Dict[str, int] = {}

        for reason_text in rows:
            for reason in self._parse_cancellation_reasons(reason_text):
                if reason:
                    breakdown[reason] = breakdown.get(reason, 0) + 1

        return breakdown

    @staticmethod
    def _safe_percentage(numerator: float, denominator: float) -> float:
        if not denominator:
            return 0.0
        return (numerator / denominator) * 100

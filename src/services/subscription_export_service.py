"""
Subscription Export Service

Provides CSV export functionality for:
- Subscriptions data
- Invoices/payments data
- Usage data
"""
import csv
import io
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from sqlalchemy import and_, or_, desc, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from src.api.models.subscription_models.subscriptions import UserSubscription
from src.api.models.subscription_models.plans import SubscriptionPlan
# Note: Invoice model does not exist - invoice export functionality is not implemented
# from src.api.models.subscription_models.invoices import Invoice
from src.api.models.user_models.users import Users
from src.utils.logger import logger


class SubscriptionExportService:
    """Service for exporting subscription data to CSV."""

    def __init__(self, db: AsyncSession):
        """Initialize service with database session."""
        self.db = db

    async def export_subscriptions_csv(
        self,
        status: Optional[str] = None,
        plan_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> str:
        """
        Export subscriptions to CSV format.

        Args:
            status: Filter by subscription status (optional)
            plan_id: Filter by plan ID (optional)
            start_date: Filter by start date (optional)
            end_date: Filter by end date (optional)

        Returns:
            CSV string content
        """
        try:
            logger.info("Exporting subscriptions to CSV")

            # Build query conditions
            conditions = []

            if status:
                conditions.append(UserSubscription.status == status)

            if plan_id:
                conditions.append(UserSubscription.plan_id == plan_id)

            if start_date:
                conditions.append(UserSubscription.created_at >= start_date)

            if end_date:
                conditions.append(UserSubscription.created_at <= end_date)

            # Query subscriptions with related data
            stmt = select(
                UserSubscription,
                Users.email,
                Users.display_name,
                SubscriptionPlan.name.label('plan_name'),
                SubscriptionPlan.price_monthly,
                SubscriptionPlan.price_yearly
            ).join(
                Users,
                UserSubscription.user_id == Users.id
            ).join(
                SubscriptionPlan,
                UserSubscription.plan_id == SubscriptionPlan.id
            ).order_by(desc(UserSubscription.created_at))

            if conditions:
                stmt = stmt.where(and_(*conditions))

            result = await self.db.execute(stmt)
            rows = result.all()

            # Create CSV in memory
            output = io.StringIO()
            writer = csv.writer(output)

            # Write header
            writer.writerow([
                'Subscription ID',
                'User Email',
                'User Name',
                'Plan Name',
                'Status',
                'Billing Period',
                'Monthly Price',
                'Annual Price',
                'Trial End Date',
                'Current Period Start',
                'Current Period End',
                'Cancelled At',
                'Created At',
                'Updated At',
                'LemonSqueezy Subscription ID',
                'LemonSqueezy Customer ID'
            ])

            # Write data rows
            for row in rows:
                subscription = row[0]
                user_email = row[1]
                user_name = row[2]
                plan_name = row[3]
                monthly_price = row[4]
                annual_price = row[5]

                writer.writerow([
                    str(subscription.id),
                    user_email,
                    user_name or '',
                    plan_name,
                    subscription.status.value if subscription.status else '',
                    subscription.billing_period.value if subscription.billing_period else '',
                    f"${monthly_price:.2f}" if monthly_price else '',
                    f"${annual_price:.2f}" if annual_price else '',
                    subscription.trial_end_date.isoformat() if subscription.trial_end_date else '',
                    subscription.current_period_start.isoformat() if subscription.current_period_start else '',
                    subscription.current_period_end.isoformat() if subscription.current_period_end else '',
                    subscription.cancelled_at.isoformat() if subscription.cancelled_at else '',
                    subscription.created_at.isoformat() if subscription.created_at else '',
                    subscription.updated_at.isoformat() if subscription.updated_at else '',
                    subscription.lemonsqueezy_subscription_id or '',
                    subscription.lemonsqueezy_customer_id or ''
                ])

            csv_content = output.getvalue()
            output.close()

            logger.info(f"Exported {len(rows)} subscriptions to CSV")

            return csv_content

        except Exception as e:
            logger.error(
                f"Failed to export subscriptions to CSV: {str(e)}",
                extra={"error": str(e)}
            )
            raise

    async def export_invoices_csv(
        self,
        status: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        min_amount: Optional[float] = None
    ) -> str:
        """
        Export invoices to CSV format.

        Args:
            status: Filter by invoice status (optional)
            start_date: Filter by invoice date (optional)
            end_date: Filter by invoice date (optional)
            min_amount: Filter by minimum amount (optional)

        Returns:
            CSV string content

        Raises:
            NotImplementedError: Invoice model does not exist yet
        """
        # TODO: Implement invoice export when Invoice model is created
        # The Invoice database model does not exist in the codebase.
        # This functionality requires creating the Invoice model and migration first.
        raise NotImplementedError(
            "Invoice export is not available. The Invoice database model has not been implemented yet."
        )

    async def export_usage_data_csv(
        self,
        user_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> str:
        """
        Export usage data to CSV format.

        This aggregates subscription usage over time periods.

        Args:
            user_id: Filter by user ID (optional)
            start_date: Filter by date (optional)
            end_date: Filter by date (optional)

        Returns:
            CSV string content
        """
        try:
            logger.info("Exporting usage data to CSV")

            # Build query conditions
            conditions = []

            if user_id:
                conditions.append(UserSubscription.user_id == user_id)

            if start_date:
                conditions.append(UserSubscription.created_at >= start_date)

            if end_date:
                conditions.append(UserSubscription.created_at <= end_date)

            # Query subscriptions with plan limits
            stmt = select(
                UserSubscription,
                Users.email,
                Users.display_name,
                SubscriptionPlan.name.label('plan_name'),
                SubscriptionPlan.max_members_per_workspace,
                SubscriptionPlan.max_workspaces,
                SubscriptionPlan.max_knowledge_items
            ).join(
                Users,
                UserSubscription.user_id == Users.id
            ).join(
                SubscriptionPlan,
                UserSubscription.plan_id == SubscriptionPlan.id
            ).order_by(Users.email, desc(UserSubscription.created_at))

            if conditions:
                stmt = stmt.where(and_(*conditions))

            result = await self.db.execute(stmt)
            rows = result.all()

            # Create CSV in memory
            output = io.StringIO()
            writer = csv.writer(output)

            # Write header
            writer.writerow([
                'User Email',
                'User Name',
                'Subscription ID',
                'Plan Name',
                'Plan Max Members/Workspace',
                'Plan Max Workspaces',
                'Plan Max Knowledge Items',
                'Subscription Status',
                'Subscription Start',
                'Subscription End',
                'Current Period Start',
                'Current Period End',
                'Days Active'
            ])

            # Write data rows
            for row in rows:
                subscription = row[0]
                user_email = row[1]
                user_name = row[2]
                plan_name = row[3]
                max_members = row[4]
                max_workspaces = row[5]
                max_knowledge_items = row[6]

                # Calculate days active
                days_active = 0
                if subscription.created_at:
                    from datetime import timezone
                    end_date_calc = subscription.cancelled_at or datetime.now(timezone.utc)
                    if subscription.created_at.tzinfo is None:
                        # Handle naive datetime if necessary
                        days_active = (end_date_calc.replace(tzinfo=None) - subscription.created_at).days
                    else:
                        days_active = (end_date_calc - subscription.created_at).days

                writer.writerow([
                    user_email,
                    user_name or '',
                    str(subscription.id),
                    plan_name,
                    max_members if max_members else 'Unlimited',
                    max_workspaces if max_workspaces else 'Unlimited',
                    max_knowledge_items if max_knowledge_items else 'Unlimited',
                    subscription.status.value if subscription.status else '',
                    subscription.created_at.isoformat() if subscription.created_at else '',
                    subscription.cancelled_at.isoformat() if subscription.cancelled_at else '',
                    subscription.current_period_start.isoformat() if hasattr(subscription, 'current_period_start') and subscription.current_period_start else '',
                    subscription.current_period_end.isoformat() if hasattr(subscription, 'current_period_end') and subscription.current_period_end else '',
                    days_active
                ])

            csv_content = output.getvalue()
            output.close()

            logger.info(f"Exported {len(rows)} usage records to CSV")

            return csv_content

        except Exception as e:
            logger.error(
                f"Failed to export usage data to CSV: {str(e)}",
                extra={"error": str(e)}
            )
            raise

    async def export_revenue_summary_csv(
        self,
        months: int = 12
    ) -> str:
        """
        Export revenue summary by month to CSV.

        Args:
            months: Number of months to include (default 12)

        Returns:
            CSV string content
        """
        try:
            logger.info(f"Exporting {months}-month revenue summary to CSV")

            # Create CSV in memory
            output = io.StringIO()
            writer = csv.writer(output)

            # Write header
            writer.writerow([
                'Month',
                'New Subscriptions',
                'Cancelled Subscriptions',
                'Total Active (End of Month)',
                'New Revenue (MRR)',
                'Churned Revenue (MRR)',
                'Net Revenue Change'
            ])

            # Calculate for each month
            current_date = datetime.utcnow()

            for i in range(months - 1, -1, -1):
                month_date = current_date - timedelta(days=30 * i)
                month_start = month_date.replace(day=1)

                # Calculate next month
                if month_date.month == 12:
                    next_month = month_date.replace(year=month_date.year + 1, month=1, day=1)
                else:
                    next_month = month_date.replace(month=month_date.month + 1, day=1)

                # New subscriptions
                stmt_new = select(func.count(UserSubscription.id)).where(
                    UserSubscription.created_at >= month_start,
                    UserSubscription.created_at < next_month
                )
                result_new = await self.db.execute(stmt_new)
                new_subs = result_new.scalar() or 0

                # Cancelled subscriptions
                stmt_cancelled = select(func.count(UserSubscription.id)).where(
                    UserSubscription.cancelled_at >= month_start,
                    UserSubscription.cancelled_at < next_month
                )
                result_cancelled = await self.db.execute(stmt_cancelled)
                cancelled_subs = result_cancelled.scalar() or 0

                # Active subscriptions at end of month
                stmt_active = select(func.count(UserSubscription.id)).where(
                    UserSubscription.created_at < next_month,
                    or_(
                        UserSubscription.cancelled_at.is_(None),
                        UserSubscription.cancelled_at >= next_month
                    )
                )
                result_active = await self.db.execute(stmt_active)
                active_subs = result_active.scalar() or 0

                # Calculate actual average revenue from plan prices
                stmt_avg = select(func.avg(SubscriptionPlan.price_monthly)).join(
                    UserSubscription,
                    UserSubscription.plan_id == SubscriptionPlan.id
                ).where(
                    UserSubscription.created_at < next_month,
                    or_(
                        UserSubscription.cancelled_at.is_(None),
                        UserSubscription.cancelled_at >= next_month
                    )
                )
                result_avg = await self.db.execute(stmt_avg)
                avg_price = float(result_avg.scalar() or 0)

                # Calculate revenue using actual average
                new_revenue = new_subs * avg_price
                churned_revenue = cancelled_subs * avg_price
                net_change = new_revenue - churned_revenue

                writer.writerow([
                    month_start.strftime("%Y-%m"),
                    new_subs,
                    cancelled_subs,
                    active_subs,
                    f"${new_revenue:.2f}",
                    f"${churned_revenue:.2f}",
                    f"${net_change:.2f}"
                ])

            csv_content = output.getvalue()
            output.close()

            logger.info(f"Exported {months}-month revenue summary to CSV")

            return csv_content

        except Exception as e:
            logger.error(
                f"Failed to export revenue summary to CSV: {str(e)}",
                extra={"error": str(e)}
            )
            raise

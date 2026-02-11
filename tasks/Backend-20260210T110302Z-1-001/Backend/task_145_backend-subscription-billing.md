# Task 145: Revenue Summary Export Uses Hardcoded $29 Average Instead of Actual Plan Prices

## Metadata
- **Task ID:** TASK-145
- **Source:** B5 - Subscription & Billing (Finding #24 under P2 Medium)
- **Audit Report:** `audit-reports/backend-subscription-billing.md`
- **Priority:** P2 Medium
- **Category:** performance
- **Effort Estimate:** medium (1-4 hours)

---

## Description

The `export_revenue_summary_csv()` method in `src/services/subscription_export_service.py` uses a hardcoded `$29.00` placeholder average revenue per user to calculate monthly new revenue and churned revenue, instead of computing the actual figures from the `SubscriptionPlan` table's `price_monthly` and `price_yearly` columns.

At lines 382 and 385, the code computes:
```python
new_revenue = new_subs * 29.0  # Placeholder average
churned_revenue = cancelled_subs * 29.0  # Placeholder average
```

The `SubscriptionPlan` model (`src/api/models/subscription_models/plans.py`) has `price_monthly` (Numeric(10,2)) and `price_yearly` (Numeric(10,2)) columns with actual plan pricing data. The `UserSubscription` model has a `billing_period` column and a `plan_id` foreign key that links to the plan. All the data needed to compute real revenue already exists in the database.

This hardcoded value produces fabricated financial data in the CSV export. As plans are added, removed, or repriced, the $29 average becomes increasingly inaccurate. Admin users relying on this report for financial decisions will base them on fictitious numbers.

Notably, a separate endpoint at `src/api/routes/subscriptions/admin/export_routes.py` (the `export_revenue_summary_csv` route, lines 192-325) already computes revenue correctly using SQL `JOIN` + `CASE` expressions against actual plan prices. This demonstrates the correct approach already exists in the codebase — the service method simply was never updated to use it.

---

## Current Code

```python
# File: rext-backend/src/services/subscription_export_service.py
# Lines: 310-405
async def export_revenue_summary_csv(
    self,
    months: int = 12
) -> str:
    """
    Export revenue summary by month to CSV.
    """
    try:
        logger.info(f"Exporting {months}-month revenue summary to CSV")

        output = io.StringIO()
        writer = csv.writer(output)

        writer.writerow([
            'Month',
            'New Subscriptions',
            'Cancelled Subscriptions',
            'Total Active (End of Month)',
            'New Revenue (MRR)',
            'Churned Revenue (MRR)',
            'Net Revenue Change'
        ])

        current_date = datetime.utcnow()

        for i in range(months - 1, -1, -1):
            month_date = current_date - timedelta(days=30 * i)
            month_start = month_date.replace(day=1)

            if month_date.month == 12:
                next_month = month_date.replace(year=month_date.year + 1, month=1, day=1)
            else:
                next_month = month_date.replace(month=month_date.month + 1, day=1)

            # ... subscription counting queries ...

            # Calculate new revenue (simplified - would need plan price joins)
            new_revenue = new_subs * 29.0  # Placeholder average    <-- HARDCODED
            churned_revenue = cancelled_subs * 29.0  # Placeholder average  <-- HARDCODED

            net_change = new_revenue - churned_revenue

            writer.writerow([
                month_start.strftime("%Y-%m"),
                new_subs, cancelled_subs, active_subs,
                f"${new_revenue:.2f}",
                f"${churned_revenue:.2f}",
                f"${net_change:.2f}"
            ])

        csv_content = output.getvalue()
        output.close()
        return csv_content
    except Exception as e:
        logger.error(f"Failed to export revenue summary to CSV: {str(e)}")
        raise
```

---

## Why This Matters (Context & Reasoning)

This method generates the monthly revenue summary CSV that admin users download for financial reporting. The report is designed to show month-over-month revenue trends, including new MRR from new subscriptions and churned MRR from cancellations. If these figures are based on a hardcoded $29 average instead of actual plan prices, the report is meaningless for financial analysis, forecasting, or investor reporting.

The `SubscriptionPlan` model already stores actual pricing: `price_monthly` (Numeric(10,2)) and `price_yearly` (Numeric(10,2)). The `UserSubscription` model has `plan_id` (FK to plans) and `billing_period` (enum: MONTHLY/YEARLY). A simple `JOIN` with a `CASE` expression on `billing_period` would yield accurate per-subscription revenue, which can then be aggregated per month.

---

## Impact

- **Severity:** Financial reports show fabricated data. Admin decisions based on revenue trends are unreliable. If used for investor reporting, this could constitute reporting inaccurate metrics.
- **Affected Users/Flows:** Admin users who export revenue summaries via the admin dashboard. Any automated report consumption downstream.
- **Blast Radius:** Isolated to the `export_revenue_summary_csv` method in the export service. The route-level export at `export_routes.py` already computes revenue correctly.

---

## Recommended Solution

Replace the hardcoded `$29.0` multiplier with actual per-subscription revenue computed by joining `UserSubscription` with `SubscriptionPlan` and using a `CASE` expression on `billing_period`.

### Step 1: Add imports at the top of subscription_export_service.py

```python
# File: rext-backend/src/services/subscription_export_service.py
# Add to existing imports (near line 11):
from sqlalchemy import func, case, and_, or_
from src.api.models.subscription_models.plans import SubscriptionPlan
from src.api.models.subscription_models.subscriptions import BillingPeriod
```

### Step 2: Replace the hardcoded revenue calculations (lines 381-385)

Replace:
```python
            # Calculate new revenue (simplified - would need plan price joins)
            new_revenue = new_subs * 29.0  # Placeholder average

            # Calculate churned revenue (simplified)
            churned_revenue = cancelled_subs * 29.0  # Placeholder average
```

With:
```python
            # Calculate new revenue from actual plan prices
            stmt_new_revenue = (
                select(
                    func.coalesce(
                        func.sum(
                            case(
                                (UserSubscription.billing_period == BillingPeriod.MONTHLY, SubscriptionPlan.price_monthly),
                                (UserSubscription.billing_period == BillingPeriod.YEARLY, SubscriptionPlan.price_yearly / 12),
                                else_=0,
                            )
                        ),
                        0,
                    )
                )
                .join(SubscriptionPlan, UserSubscription.plan_id == SubscriptionPlan.id)
                .where(
                    UserSubscription.created_at >= month_start,
                    UserSubscription.created_at < next_month,
                )
            )
            result_new_rev = await self.db.execute(stmt_new_revenue)
            new_revenue = float(result_new_rev.scalar() or 0)

            # Calculate churned revenue from actual plan prices
            stmt_churned_revenue = (
                select(
                    func.coalesce(
                        func.sum(
                            case(
                                (UserSubscription.billing_period == BillingPeriod.MONTHLY, SubscriptionPlan.price_monthly),
                                (UserSubscription.billing_period == BillingPeriod.YEARLY, SubscriptionPlan.price_yearly / 12),
                                else_=0,
                            )
                        ),
                        0,
                    )
                )
                .join(SubscriptionPlan, UserSubscription.plan_id == SubscriptionPlan.id)
                .where(
                    UserSubscription.cancelled_at >= month_start,
                    UserSubscription.cancelled_at < next_month,
                )
            )
            result_churned_rev = await self.db.execute(stmt_churned_revenue)
            churned_revenue = float(result_churned_rev.scalar() or 0)
```

### Step 3: Also fix `datetime.utcnow()` on line 342 (while editing this method)

Replace:
```python
current_date = datetime.utcnow()
```
With:
```python
current_date = datetime.now(timezone.utc)
```

And add `timezone` to the datetime import at the top of the file:
```python
from datetime import datetime, timedelta, timezone
```

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `rext-backend/src/api/routes/subscriptions/admin/export_routes.py` | 192-325 | Already has correct revenue computation using SQL JOINs — use as reference pattern |
| `rext-backend/src/services/subscription_analytics_service.py` | 49 | `average_ltv` is calculated as `mrr * 12` which is correct (based on `_calculate_mrr`) |
| `rext-backend/src/api/routes/admin/reports_routes.py` | 98-215 | Revenue export route that also calls analytics service — verify its data is accurate |
| `rext-backend/src/services/subscription_export_service.py` | 277 | Another `datetime.utcnow()` in the same file (related to TASK-146) |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Log in as a super admin user
2. Navigate to the admin dashboard and trigger a revenue summary CSV export
3. Open the CSV and observe that "New Revenue (MRR)" equals `new_subs * $29.00` and "Churned Revenue (MRR)" equals `cancelled_subs * $29.00` regardless of actual plan prices
4. Compare with the route-level export (`GET /export/revenue-summary`) which shows correct plan-based pricing

### After Fix (Verify the Solution):
1. Ensure at least 2 subscription plans exist with different prices (e.g., $19/mo and $49/mo)
2. Ensure some subscriptions exist on each plan
3. Export the revenue summary CSV via the service method
4. Verify that "New Revenue (MRR)" reflects actual plan prices, not a flat $29 per subscription
5. Verify that monthly revenue for months with only $19/mo plan subs shows ~$19/sub, not $29/sub
6. Verify yearly subscriptions contribute `price_yearly / 12` to MRR

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/ -k "export" -v
```

---

## Acceptance Criteria

- [ ] No hardcoded dollar amounts used for revenue calculations in `subscription_export_service.py`
- [ ] New revenue calculated by joining `UserSubscription` with `SubscriptionPlan` and using actual `price_monthly`/`price_yearly`
- [ ] Churned revenue calculated the same way based on cancelled subscriptions' plan prices
- [ ] Yearly subscriptions contribute `price_yearly / 12` to monthly revenue (MRR normalization)
- [ ] CSV export values match the route-level export values for the same data
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [SQLAlchemy 2.0 `case()` expression](https://docs.sqlalchemy.org/en/20/core/sqlelement.html#sqlalchemy.sql.expression.case)
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** [SQLAlchemy aggregate functions with joins](https://docs.sqlalchemy.org/en/20/orm/queryguide/select.html#joining-to-subqueries)
- **Related Issues/PRs:** None

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-146 (datetime.utcnow deprecation — same file has occurrences), TASK-122 (export service references non-existent columns — same file)

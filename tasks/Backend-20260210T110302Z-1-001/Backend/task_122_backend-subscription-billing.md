# Task 122: Fix Export Service Referencing Non-Existent Database Columns — All Exports Crash

## Metadata
- **Task ID:** TASK-122
- **Source:** Backend Subscription & Billing Audit (Finding #3 under P0 Critical)
- **Audit Report:** `audit-reports/backend-subscription-billing.md`
- **Priority:** P0 Critical
- **Category:** bug
- **Effort Estimate:** medium (1-4 hours)

---

## Description

The `SubscriptionExportService` at `src/services/subscription_export_service.py` references multiple database column names that do not exist on the actual SQLAlchemy models, causing `AttributeError` crashes at runtime whenever any export endpoint is called. There are three distinct issues in this service:

**Issue 1: Wrong foreign key column name (line 60).** The service filters by `UserSubscription.subscription_plan_id` (line 60), but the actual `UserSubscription` model at `src/api/models/subscription_models/subscriptions.py:36` defines the column as `plan_id`, not `subscription_plan_id`. This causes an `AttributeError` when the `plan_id` query parameter is provided.

**Issue 2: Wrong price column names (lines 75-76).** The service references `SubscriptionPlan.monthly_price` and `SubscriptionPlan.annual_price` (lines 75-76), but the actual `SubscriptionPlan` model at `src/api/models/subscription_models/plans.py:21-22` defines these as `price_monthly` and `price_yearly`. This causes an `AttributeError` on every subscription export query (even without filters) because these columns are in the SELECT clause.

**Issue 3: Non-existent plan limit columns (lines 226-228).** The usage export query references `SubscriptionPlan.max_users` and `SubscriptionPlan.max_content_items` (lines 226, 228), but these columns do not exist on the `SubscriptionPlan` model. The actual model has `max_members_per_workspace` (line 28), `max_topics` (line 29), `max_knowledge_items` (line 30), and `max_api_calls_per_month` (line 31) — but no `max_users` or `max_content_items`. This causes the usage export to crash.

**Issue 4: Revenue summary uses hardcoded $29.00 average (lines 382-385).** The `export_revenue_summary_csv()` method uses `new_subs * 29.0` and `cancelled_subs * 29.0` as placeholder revenue calculations instead of computing actual revenue from plan prices. This produces fabricated financial data.

**Issue 5: Invoice export raises NotImplementedError (lines 178-184).** The `export_invoices_csv()` method is unimplemented and raises `NotImplementedError`. The route endpoint exists and is accessible, but the function always crashes.

Note: There is a SECOND `export_routes.py` at `src/api/routes/subscriptions/admin/export_routes.py` that does its own inline SQL queries with CORRECT column names (`UserSubscription.plan_id`, `SubscriptionPlan.price_monthly`, `SubscriptionPlan.price_yearly`). The service-based exports at `src/api/routes/admin/export_routes.py` use the broken `SubscriptionExportService`. These two export route files overlap — the admin one works, the service-based one crashes.

---

## Current Code

```python
# File: src/services/subscription_export_service.py
# Lines: 58-83 — Wrong column names in subscription export
        if plan_id:
            conditions.append(UserSubscription.subscription_plan_id == plan_id)  # WRONG: should be plan_id
        # ...
        stmt = select(
            UserSubscription,
            Users.email,
            Users.display_name,
            SubscriptionPlan.name.label('plan_name'),
            SubscriptionPlan.monthly_price,    # WRONG: should be price_monthly
            SubscriptionPlan.annual_price       # WRONG: should be price_yearly
        ).join(
            Users,
            UserSubscription.user_id == Users.id
        ).join(
            SubscriptionPlan,
            UserSubscription.subscription_plan_id == SubscriptionPlan.id  # WRONG: should be plan_id
        ).order_by(desc(UserSubscription.created_at))
```

```python
# File: src/services/subscription_export_service.py
# Lines: 221-234 — Non-existent columns in usage export
        stmt = select(
            UserSubscription,
            Users.email,
            Users.display_name,
            SubscriptionPlan.name.label('plan_name'),
            SubscriptionPlan.max_users,           # WRONG: column does not exist
            SubscriptionPlan.max_workspaces,      # OK: exists
            SubscriptionPlan.max_content_items    # WRONG: column does not exist
        ).join(
            Users,
            UserSubscription.user_id == Users.id
        ).join(
            SubscriptionPlan,
            UserSubscription.subscription_plan_id == SubscriptionPlan.id  # WRONG: should be plan_id
        )
```

```python
# File: src/services/subscription_export_service.py
# Lines: 382-385 — Hardcoded revenue calculation
            new_revenue = new_subs * 29.0  # Placeholder average
            churned_revenue = cancelled_subs * 29.0  # Placeholder average
```

---

## Why This Matters (Context & Reasoning)

The export service is the backend for admin data export functionality — allowing super admins to download subscription data, usage reports, and revenue summaries as CSV files. These exports are used for financial reporting, churn analysis, and business intelligence. When the service crashes, admins cannot extract any subscription data from the system, making financial reporting impossible through the admin UI.

The hardcoded $29.00 revenue figure is particularly dangerous because it produces plausible-looking but entirely fabricated financial data. An admin who doesn't know the value is hardcoded would make business decisions based on inaccurate revenue numbers. The fix should compute actual revenue from `SubscriptionPlan.price_monthly` weighted by subscriber counts.

The existence of two parallel export route files (`/admin/export_routes.py` using the broken service, and `/subscriptions/admin/export_routes.py` with inline working queries) suggests the service was written as a refactoring attempt that was never tested against the actual models.

---

## Impact

- **Severity:** All export endpoints using `SubscriptionExportService` crash with `AttributeError` at runtime. Revenue summary produces fabricated financial data. Invoice export is completely unimplemented.
- **Affected Users/Flows:** Admin users attempting to export subscription data, usage reports, or revenue summaries. Financial reporting workflows.
- **Blast Radius:** All 4 service-based export endpoints are broken. The parallel admin export routes at `src/api/routes/subscriptions/admin/export_routes.py` work correctly (they use inline queries with correct column names).

---

## Recommended Solution

### Step 1: Fix the subscription export column references

```python
# File: src/services/subscription_export_service.py
# Replace lines 55-83 with:

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
```

### Step 2: Fix the usage export column references

```python
# File: src/services/subscription_export_service.py
# Replace lines 221-235 with:

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
```

Also update the CSV header and data rows (lines 248-293) to match the new column names:

```python
# File: src/services/subscription_export_service.py
# Replace lines 248-293 with:

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
```

### Step 3: Replace hardcoded $29.00 with computed revenue

```python
# File: src/services/subscription_export_service.py
# Replace lines 354-398 with the following (inside the for loop in export_revenue_summary_csv):

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
```

### Step 4: Add proper error handling for unimplemented invoice export

```python
# File: src/services/subscription_export_service.py
# The export_invoices_csv method (lines 157-184) correctly raises NotImplementedError.
# No change needed here — but the route endpoint should catch this and return HTTP 501:

# File: src/api/routes/admin/export_routes.py
# Replace lines 110-116 in export_invoices with:
    try:
        csv_content = await service.export_invoices_csv(
            status=status,
            start_date=start_date,
            end_date=end_date,
            min_amount=min_amount
        )
    except NotImplementedError as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=501, detail=str(e))
```

### Step 5: Add missing import for SubscriptionPlan in revenue summary

```python
# File: src/services/subscription_export_service.py
# Ensure SubscriptionPlan is imported at the top (already present at line 18, verify it's used in the revenue method)
```

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `src/api/routes/admin/export_routes.py` | 32-214 | Route file that delegates to `SubscriptionExportService` — uses the broken service methods. Routes will work once the service is fixed. |
| `src/api/routes/subscriptions/admin/export_routes.py` | 38-446 | Parallel export routes with CORRECT inline queries — these work. Consider removing the duplicate service-based routes to avoid confusion. |
| `src/api/models/subscription_models/subscriptions.py` | 36 | Correct column: `plan_id = Column(UUID(as_uuid=True), ForeignKey("subscription_plans.id"), nullable=False)` |
| `src/api/models/subscription_models/plans.py` | 21-22 | Correct columns: `price_monthly`, `price_yearly` (not `monthly_price`, `annual_price`) |
| `src/api/models/subscription_models/plans.py` | 27-31 | Available plan limit columns: `max_workspaces`, `max_members_per_workspace`, `max_topics`, `max_knowledge_items`, `max_api_calls_per_month` |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Authenticate as a super admin user.
2. Call `GET /api/v1/admin/export/subscriptions` — observe HTTP 500 with `AttributeError: type object 'SubscriptionPlan' has no attribute 'monthly_price'`.
3. Call `GET /api/v1/admin/export/usage` — observe HTTP 500 with `AttributeError: type object 'SubscriptionPlan' has no attribute 'max_users'`.
4. Call `GET /api/v1/admin/export/revenue-summary` — observe the response contains hardcoded $29.00-based calculations.

### After Fix (Verify the Solution):
1. Call `GET /api/v1/admin/export/subscriptions` — expect a CSV download with correct subscription data.
2. Call `GET /api/v1/admin/export/usage` — expect a CSV download with correct usage data including `Max Members/Workspace`, `Max Workspaces`, `Max Knowledge Items`.
3. Call `GET /api/v1/admin/export/revenue-summary` — expect revenue figures based on actual plan prices from the database.
4. Call `GET /api/v1/admin/export/invoices` — expect HTTP 501 Not Implemented (not 500).

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/ -v -k "export" --no-header
```

---

## Acceptance Criteria

- [ ] `export_subscriptions_csv()` uses `UserSubscription.plan_id` (not `subscription_plan_id`)
- [ ] `export_subscriptions_csv()` uses `SubscriptionPlan.price_monthly` and `SubscriptionPlan.price_yearly` (not `monthly_price`/`annual_price`)
- [ ] `export_usage_data_csv()` uses `SubscriptionPlan.max_members_per_workspace` and `SubscriptionPlan.max_knowledge_items` (not `max_users`/`max_content_items`)
- [ ] `export_revenue_summary_csv()` computes revenue from actual plan prices instead of hardcoded $29.00
- [ ] All join conditions use `UserSubscription.plan_id == SubscriptionPlan.id`
- [ ] Invoice export route returns HTTP 501 (not 500) with a clear message
- [ ] All export endpoints produce valid CSV output for non-empty datasets
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [SQLAlchemy 2.0 - Using SELECT Statements](https://docs.sqlalchemy.org/en/20/tutorial/data_select.html) — Correct usage of `select()`, `.join()`, and column references in SQLAlchemy ORM queries
- **Security Advisory:** N/A (this is a bug, not a security vulnerability directly)
- **Migration Guide:** N/A
- **Best Practice Reference:** [SQLAlchemy Column Elements and Expressions](https://docs.sqlalchemy.org/en/20/core/sqlelement.html) — How to reference model columns correctly in SELECT statements
- **Related Issues/PRs:** N/A

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-120 (Missing admin auth on export endpoints — same export routes), TASK-042 (B2: Inconsistent timestamp column types — related model column naming), TASK-029 (B2: WorkspaceIntegration.to_dict() leaks credentials — similar pattern of incorrect column references)

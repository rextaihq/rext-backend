# Task 150: `discount_amount` Uses Float Type Annotation Instead of Decimal

## Metadata
- **Task ID:** TASK-150
- **Source:** B5 - Subscription & Billing (Finding #32 under P3 Low)
- **Audit Report:** `audit-reports/backend-subscription-billing.md`
- **Priority:** P3 Low
- **Category:** data-integrity
- **Effort Estimate:** small (< 1 hour)

---

## Description

The `DiscountUsage` model in `src/api/models/subscription_models/discount_usage.py` defines the `discount_amount` column with the correct database type (`Numeric(10, 2)`) but uses an incorrect Python type annotation (`Mapped[Optional[float]]`) at line 60. While the underlying PostgreSQL column stores values as `NUMERIC(10,2)` with exact decimal precision, SQLAlchemy's type mapping system sees the `float` annotation and converts the `Decimal` values returned by the database driver (psycopg2/asyncpg) into Python `float` objects. This introduces IEEE 754 binary floating-point representation errors into what should be exact decimal values.

The practical consequence is that financial calculations performed in Python on discount amounts may produce rounding errors. For example, a discount of `$10.00` stored precisely in PostgreSQL as `10.00` gets loaded into Python as `float(10.0)`, which appears correct in isolation but can produce errors in arithmetic: `float(0.1) + float(0.1) + float(0.1)` yields `0.30000000000000004` rather than `0.3`. These errors compound across multiple discount calculations and can cause accounting discrepancies.

Additionally, the `to_dict()` method at line 125 explicitly converts the value with `float(self.discount_amount)`, further cementing the float representation in API responses. According to SQLAlchemy 2.x documentation, `Mapped[Decimal]` should be used with `Numeric` column types to ensure Python `Decimal` objects are returned, preserving exact decimal precision throughout the application stack.

The correct approach per SQLAlchemy 2.x and Python financial data best practices is to use `Mapped[Optional[Decimal]]` with `from decimal import Decimal`, ensuring the entire pipeline — database storage, Python object, and API serialization — maintains exact decimal precision.

---

## Current Code

```python
# File: src/api/models/subscription_models/discount_usage.py
# Lines: 60-64
    discount_amount: Mapped[Optional[float]] = mapped_column(
        Numeric(10, 2),
        nullable=True,
        comment="Amount saved (in currency or percentage)"
    )
```

```python
# File: src/api/models/subscription_models/discount_usage.py
# Lines: 124-125
            "discount_amount": float(self.discount_amount) if self.discount_amount else None,
```

---

## Why This Matters (Context & Reasoning)

The `DiscountUsage` model tracks discount code usage during checkout, recording the monetary amount saved by each user. This data feeds into analytics, fraud prevention, and financial reporting. Even small floating-point rounding errors in discount amounts can compound when aggregated across many transactions, leading to discrepancies between reported discount totals and actual amounts. For a billing system, financial precision is a baseline requirement — not a nice-to-have.

The risk of NOT fixing this is that discount analytics and financial summaries may show values that don't match what was actually applied, eroding trust in the billing system's accuracy. While the database itself stores the values correctly (as `NUMERIC(10,2)`), the Python layer loses precision every time a value is loaded and used.

---

## Impact

- **Severity:** Discount calculations may produce rounding errors (e.g., `$9.999999999` instead of `$10.00`). These compound across aggregations and can cause accounting discrepancies in admin reports.
- **Affected Users/Flows:** Admin analytics dashboards, discount usage reports, financial exports, any code that aggregates discount amounts in Python.
- **Blast Radius:** Isolated to the `DiscountUsage` model and any services that perform arithmetic on `discount_amount` values in Python. The database layer is unaffected since it already uses `NUMERIC(10,2)`.

---

## Recommended Solution

### Step 1: Update the type annotation and import

```python
# File: src/api/models/subscription_models/discount_usage.py
# Replace line 9 and add Decimal import:
from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID
```

### Step 2: Change the `discount_amount` field annotation

```python
# File: src/api/models/subscription_models/discount_usage.py
# Replace lines 60-64:
    discount_amount: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(10, 2),
        nullable=True,
        comment="Amount saved (in currency or percentage)"
    )
```

### Step 3: Update the `to_dict()` serialization

```python
# File: src/api/models/subscription_models/discount_usage.py
# Replace line 125:
            "discount_amount": str(self.discount_amount) if self.discount_amount is not None else None,
```

Note: Using `str()` for Decimal serialization ensures exact representation in JSON (e.g., `"10.00"` instead of `10.0`). If the API consumers expect a numeric type rather than a string, use `float(self.discount_amount)` but be aware this reintroduces the precision issue at the serialization boundary. The preferred approach for financial APIs is to serialize as a string.

### Step 4: No database migration needed

Since the database column is already `Numeric(10, 2)`, no Alembic migration is required. This is a Python-layer-only change.

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `src/api/models/content_models/content_seo_data.py` | `20, 23, 25, 26` | Uses `Float` column type for `keyphrase_density`, `trust_score`, `seo_score`, `readability_score`. These are not financial values so Float is acceptable, but noted for awareness. |
| `src/services/webhook_handlers/order_handlers.py` | Various | May read `discount_amount` from webhook data and create `DiscountUsage` records — verify it passes `Decimal` values. |
| `src/services/subscription_analytics_service.py` | Various | May aggregate discount amounts — will benefit from Decimal precision. |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Start a Python shell with the project's dependencies loaded.
2. Query a `DiscountUsage` record: `result = await db.execute(select(DiscountUsage).limit(1))`
3. Check the type: `type(result.scalar_one().discount_amount)` — it will be `<class 'float'>`.
4. Perform arithmetic: `amount + Decimal("0.1")` will raise a `TypeError` because you can't add `float` and `Decimal` directly.

### After Fix (Verify the Solution):
1. Repeat the query above.
2. Check the type: `type(result.scalar_one().discount_amount)` — it should be `<class 'decimal.Decimal'>`.
3. Verify arithmetic works: `amount + Decimal("0.1")` should return a `Decimal` with exact precision.
4. Call the `to_dict()` method and verify `discount_amount` is a string like `"10.00"` (not `10.0`).

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/ -k "discount" -v
```

---

## Acceptance Criteria

- [ ] `discount_amount` field uses `Mapped[Optional[Decimal]]` type annotation
- [ ] `from decimal import Decimal` is imported in the model file
- [ ] `to_dict()` serializes `discount_amount` as a string for exact representation
- [ ] No database migration is needed (column type unchanged)
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [SQLAlchemy 2.0 — SQL Datatype Objects: Numeric](https://docs.sqlalchemy.org/en/20/core/type_basics.html#sqlalchemy.types.Numeric)
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** [Python `decimal` module documentation](https://docs.python.org/3/library/decimal.html)
- **Related Issues/PRs:** [SQLAlchemy Issue #131 — Data type for Numeric column should be Decimal, not float](https://github.com/dropbox/sqlalchemy-stubs/issues/131)

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-027, TASK-028 (also involve model-level issues in discount_usage.py — `__table_args__` at module level)

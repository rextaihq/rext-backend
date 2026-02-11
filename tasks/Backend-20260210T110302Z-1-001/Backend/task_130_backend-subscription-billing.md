# Task 130: Refund Model Uses String Status Column Instead of Database Enum

## Metadata
- **Task ID:** TASK-130
- **Source:** Backend Subscription & Billing Audit (Finding #17 under P1 High)
- **Audit Report:** `audit-reports/backend-subscription-billing.md`
- **Priority:** P1 High
- **Category:** data-integrity
- **Effort Estimate:** medium (1-4 hours)

---

## Description

The `Refund` model in `src/api/models/subscription_models/refunds.py` defines its `status` column as `String(20)` with a default of `RefundStatus.PENDING`, rather than using SQLAlchemy's `Enum` type (`SQLEnum`) as other models in the codebase do. Specifically, at line 85-90:

```python
status = Column(
    String(20),
    nullable=False,
    default=RefundStatus.PENDING,
    index=True
)
```

This stands in contrast to the `UserSubscription` model in the same module family (`src/api/models/subscription_models/subscriptions.py:39`) which correctly uses `SQLEnum(SubscriptionStatus)`:

```python
status = Column(SQLEnum(SubscriptionStatus), default=SubscriptionStatus.ACTIVE, nullable=False)
```

When a column is `String`, PostgreSQL performs no validation on the values stored. Any arbitrary string — including typos like `"comepleted"`, `"pendingg"`, or malicious values — can be written to the column without error. The `RefundStatus` Python enum (`PENDING`, `COMPLETED`, `FAILED`) provides application-level validation only when the enum is explicitly used in code, but direct SQL queries, manual database edits, or any code path that sets `refund.status = "some_string"` bypasses this entirely.

Additionally, the `default=RefundStatus.PENDING` on a `String` column stores the string representation of the enum member. Since `RefundStatus` inherits from `str`, this works coincidentally — `RefundStatus.PENDING` evaluates to `"pending"` — but it's fragile. If the enum's string representation changes or if someone passes the enum member object directly via SQLAlchemy, the behavior becomes unpredictable.

The `RefundService` (`src/services/refund_service.py`) assigns enum values correctly (lines 77, 117, 154), but the database itself has no constraint preventing invalid data. The service's `list_refunds` method (line 222) also compares `Refund.status == status` where `status` is a raw string parameter, further highlighting the mismatch between the typed enum and the untyped column.

---

## Current Code

```python
# File: src/api/models/subscription_models/refunds.py
# Lines: 24-30 (enum definition)
class RefundStatus(str, Enum):
    """Refund status enumeration."""

    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
```

```python
# File: src/api/models/subscription_models/refunds.py
# Lines: 85-90 (problematic column definition)
    status = Column(
        String(20),
        nullable=False,
        default=RefundStatus.PENDING,
        index=True
    )
```

```python
# File: src/api/models/subscription_models/subscriptions.py
# Line: 39 (correct pattern for comparison)
    status = Column(SQLEnum(SubscriptionStatus), default=SubscriptionStatus.ACTIVE, nullable=False)
```

---

## Why This Matters (Context & Reasoning)

The `Refund` model tracks financial refund operations for the entire billing system. Refund records are created when LemonSqueezy processes a refund (via webhook) or when an admin manually initiates a refund. The `status` field drives the refund lifecycle: `PENDING` → `COMPLETED` or `PENDING` → `FAILED`.

If invalid status values enter the database, several downstream effects occur:
1. Admin dashboard queries that filter by status (e.g., "show all pending refunds") will miss records with typos or unexpected values
2. The summary statistics in `RefundService.list_refunds()` that use `func.cast(Refund.status == RefundStatus.COMPLETED, ...)` will produce incorrect counts
3. Financial reporting becomes unreliable — the admin might see fewer completed refunds than actually exist
4. Debugging becomes harder since invalid statuses won't match any known enum value

This is a data integrity issue in a financial subsystem, making it a P1 priority.

---

## Impact

- **Severity:** Invalid refund statuses can silently enter the database, causing incorrect financial reporting, broken admin dashboard filters, and unreliable refund analytics. No runtime error occurs — the corruption is silent.
- **Affected Users/Flows:** Admin refund dashboard, refund webhook processing, refund analytics/exports, any financial reconciliation workflows.
- **Blast Radius:** Isolated to the `refunds` table, but impacts the reliability of all refund-related reporting and querying across the admin interface.

---

## Recommended Solution

### Step 1: Update the Refund model to use SQLAlchemy Enum

```python
# File: src/api/models/subscription_models/refunds.py
# Replace the imports section (lines 7-16) with:

import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    Integer,
    String,
    Text,
    TIMESTAMP,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import relationship

from src.api.database.base import Base
from src.api.models.base import SerializableMixin
```

```python
# File: src/api/models/subscription_models/refunds.py
# Replace the status column definition (lines 85-90) with:

    # Status
    status = Column(
        SQLEnum(RefundStatus, name="refundstatus", create_constraint=True),
        nullable=False,
        default=RefundStatus.PENDING,
        index=True
    )
```

### Step 2: Update the `to_dict()` method to handle enum serialization

```python
# File: src/api/models/subscription_models/refunds.py
# Replace the status line in to_dict() (line 122) with:

            "status": self.status.value if isinstance(self.status, RefundStatus) else self.status,
```

### Step 3: Update `RefundService.list_refunds` to accept enum instead of string

```python
# File: src/services/refund_service.py
# Line 222: Update the status filter to accept RefundStatus enum

        if status:
            if isinstance(status, str):
                try:
                    status = RefundStatus(status)
                except ValueError:
                    pass  # Let it fail at query time if invalid
            filters.append(Refund.status == status)
```

### Step 4: Create Alembic migration

```bash
cd rext-backend
```

Create a new migration file manually (since autogenerate may not handle String→Enum correctly):

```python
# File: alembic/versions/<new_revision>_refund_status_string_to_enum.py

"""Convert refund status from String to Enum type

Revision ID: <auto-generated>
Revises: <previous-head>
Create Date: <auto-generated>
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = '<auto-generated>'
down_revision = '<previous-head>'
branch_labels = None
depends_on = None

# Define the enum type
refundstatus_enum = postgresql.ENUM('pending', 'completed', 'failed', name='refundstatus', create_type=False)


def upgrade() -> None:
    # Step 1: Create the PostgreSQL ENUM type
    refundstatus_enum.create(op.get_bind(), checkfirst=True)

    # Step 2: Alter the column from VARCHAR to ENUM
    # PostgreSQL requires an explicit USING clause to cast existing values
    op.execute(
        "ALTER TABLE refunds "
        "ALTER COLUMN status TYPE refundstatus "
        "USING status::refundstatus"
    )

    # Step 3: Set the default
    op.alter_column(
        'refunds',
        'status',
        server_default='pending',
        existing_nullable=False,
    )


def downgrade() -> None:
    # Convert back to VARCHAR
    op.alter_column(
        'refunds',
        'status',
        type_=sa.String(20),
        existing_nullable=False,
        postgresql_using='status::text',
    )

    # Drop the enum type
    refundstatus_enum.drop(op.get_bind(), checkfirst=True)
```

### Step 5: Validate existing data before migration

Before running the migration, verify all existing refund status values are valid:

```sql
-- Run this query to check for invalid status values
SELECT DISTINCT status, COUNT(*)
FROM refunds
GROUP BY status;

-- All values should be: 'pending', 'completed', or 'failed'
-- If any other values exist, update them before migration:
-- UPDATE refunds SET status = 'failed' WHERE status NOT IN ('pending', 'completed', 'failed');
```

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `src/services/refund_service.py` | 77, 117, 154 | Sets `refund.status` to `RefundStatus` enum values — works correctly but relies on application-level enforcement only |
| `src/services/refund_service.py` | 222 | `list_refunds()` accepts `status` as `Optional[str]` — should accept `Optional[RefundStatus]` |
| `src/services/refund_service.py` | 260-269 | Summary statistics cast `Refund.status == RefundStatus.X` — may need adjustment for enum comparison |
| `src/api/routes/admin/refund_routes.py` | varies | Admin routes pass status as string from query params — needs validation |
| `src/api/schema/subscription/refund_schemas.py` | varies | Pydantic schemas should use `RefundStatus` enum for validation |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Connect to the database directly (e.g., via `psql`)
2. Run: `INSERT INTO refunds (id, user_id, lemonsqueezy_order_id, refund_amount, original_amount, status) VALUES (gen_random_uuid(), '<valid_user_id>', 'test_order', 1000, 2000, 'invalid_status');`
3. The insert succeeds — no error, no constraint violation
4. Run: `SELECT * FROM refunds WHERE status = 'invalid_status';` — the invalid row exists

### After Fix (Verify the Solution):
1. Run the Alembic migration: `alembic upgrade head`
2. Verify the column type: `SELECT column_name, data_type, udt_name FROM information_schema.columns WHERE table_name = 'refunds' AND column_name = 'status';` — should show `udt_name = 'refundstatus'`
3. Try inserting an invalid status: `INSERT INTO refunds (..., status) VALUES (..., 'invalid_status');` — should fail with a type error
4. Verify existing data: `SELECT DISTINCT status FROM refunds;` — should only show `pending`, `completed`, `failed`

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/ -k "refund" -v
```

---

## Acceptance Criteria

- [ ] `Refund.status` column uses `SQLEnum(RefundStatus)` instead of `String(20)`
- [ ] Alembic migration successfully converts existing `String` column to PostgreSQL `ENUM` type
- [ ] All existing refund records retain their correct status values after migration
- [ ] Invalid status values are rejected at the database level (INSERT/UPDATE with invalid value fails)
- [ ] `to_dict()` still returns the status as a string value (not the enum repr)
- [ ] `RefundService.list_refunds()` correctly filters by enum status
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** https://docs.sqlalchemy.org/en/20/core/type_basics.html#sqlalchemy.types.Enum — SQLAlchemy Enum type documentation
- **Security Advisory:** N/A
- **Migration Guide:** https://alembic.sqlalchemy.org/en/latest/ops.html#alembic.operations.Operations.alter_column — Alembic alter_column documentation
- **Best Practice Reference:** https://docs.sqlalchemy.org/en/20/dialects/postgresql.html#sqlalchemy.dialects.postgresql.ENUM — PostgreSQL-specific ENUM type documentation
- **Related Issues/PRs:** See `UserSubscription.status` (line 39 in `subscriptions.py`) for the correct pattern already used in this codebase

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-129 (SubscriptionStatus Enum Mismatch — similar enum consistency issue across layers)

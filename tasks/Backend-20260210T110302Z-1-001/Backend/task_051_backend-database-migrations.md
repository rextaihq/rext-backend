# Task 051: Standardize Mixed SQLAlchemy Column vs Mapped/mapped_column Styles

## Metadata
- **Task ID:** TASK-051
- **Source:** Backend Database & Migrations Audit (Finding #18 under P2 Medium)
- **Audit Report:** `audit-reports/backend-database-migrations.md`
- **Priority:** P2 Medium
- **Category:** code-quality
- **Effort Estimate:** medium (1-4 hours)

---

## Description

The codebase uses two distinct SQLAlchemy column declaration styles: the classic `Column()` style and the SQLAlchemy 2.0 `Mapped[T]`/`mapped_column()` annotated style. Three models in `src/api/models/subscription_models/` use the modern `Mapped`/`mapped_column` style, while all other ~30 models use the classic `Column()` style. This inconsistency means developers must understand and maintain two different patterns, and type checking tools may behave differently for each style.

The three outlier models using `mapped_column` are:

1. **`LicenseActivation`** (`src/api/models/subscription_models/license_activations.py`) — Uses `Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ...)` for all columns (lines 32-94). Imports `Mapped, mapped_column` from `sqlalchemy.orm` (line 14).

2. **`DiscountUsage`** (`src/api/models/subscription_models/discount_usage.py`) — Uses `Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ...)` for all columns (lines 32-97). Imports `Mapped, mapped_column` from `sqlalchemy.orm` (line 14).

3. **`TrialConversion`** (`src/api/models/subscription_models/trial_conversions.py`) — Uses `Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ...)` for all columns (lines 22-100). Imports `Mapped, mapped_column` from `sqlalchemy.orm` (line 8).

All three models are in the `subscription_models/` subdirectory, suggesting they were created in the same sprint or by the same developer. All other models — including `UserSubscription` and `SubscriptionPlan` in the same directory — use classic `Column()` style.

The SQLAlchemy 2.0 documentation states that `mapped_column()` is "an ORM-specific construct intended as a drop-in replacement for `Column` within Declarative mappings" and that "the `Column` form will always work in Declarative in the same way it always has." Both styles can coexist within a single mapping, and the `Column` style is not deprecated. However, the documentation also positions `mapped_column` as the modern approach for new code, especially when combined with `DeclarativeBase`.

Given that 30+ models use `Column()` and only 3 use `mapped_column`, the pragmatic short-term fix is to convert the 3 outliers back to `Column()` for consistency. A full migration to `mapped_column` across all 33+ models would be a much larger effort that should be planned as a dedicated initiative alongside the `DeclarativeBase` migration (TASK-041).

---

## Current Code

```python
# File: rext-backend/src/api/models/subscription_models/license_activations.py
# Lines 32-46 (mapped_column style)
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        unique=True,
        nullable=False
    )
    license_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("licenses.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    instance_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
        comment="Device ID, domain, or unique instance identifier"
    )
```

```python
# File: rext-backend/src/api/models/subscription_models/discount_usage.py
# Lines 32-57 (mapped_column style)
    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid()
    )
    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
```

```python
# File: rext-backend/src/api/models/subscription_models/trial_conversions.py
# Lines 22-100 (mapped_column style)
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        unique=True,
        nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
```

Compare with the standard pattern used by 30+ other models:

```python
# File: rext-backend/src/api/models/subscription_models/subscriptions.py
# Line 34-36 (Column style — standard pattern)
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    plan_id = Column(UUID(as_uuid=True), ForeignKey("subscription_plans.id"), nullable=False)
```

---

## Why This Matters (Context & Reasoning)

Code consistency is a force multiplier for development velocity. When a developer looks at model code, they should see one pattern for column declarations — not two. The current situation is especially confusing because the three `mapped_column` models sit alongside `Column`-style models in the same `subscription_models/` directory.

The `mapped_column` style provides benefits like type-safe annotations and IDE completion, but these benefits are only realized when used consistently across the entire codebase AND when the project uses `DeclarativeBase` (TASK-041). Currently, the project uses the legacy `declarative_base()` from `sqlalchemy.ext.declarative` (the subject of TASK-041), which means the type annotation benefits of `Mapped` are not fully leveraged.

Converting to `Column()` now ensures consistency, and the door remains open for a future full-codebase migration to `mapped_column` + `DeclarativeBase` as a planned initiative.

---

## Impact

- **Severity:** No runtime error. Developer confusion when switching between files in the same directory. IDEs may show different type information for functionally identical columns.
- **Affected Users/Flows:** Development experience only. No user-facing impact.
- **Blast Radius:** Low. Only 3 files need changes. No schema changes — `mapped_column` and `Column` produce identical database columns.

---

## Recommended Solution

Convert the 3 outlier models from `Mapped`/`mapped_column` to classic `Column()` style, matching the ~30 other models.

### Step 1: Convert LicenseActivation

```python
# File: rext-backend/src/api/models/subscription_models/license_activations.py
# Replace the entire file content with:

"""
License Activation model for tracking individual device/instance activations.

This model records each activation of a license key to a specific device or instance,
enabling activation limit enforcement and management.
"""

import uuid
from datetime import datetime

from sqlalchemy import Column, String, Boolean, ForeignKey, Index, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from src.api.database.base import Base
from src.api.models.base import SerializableMixin


class LicenseActivation(Base, SerializableMixin):
    """
    Track individual license activations to devices/instances.

    Each record represents one activation of a license key to a specific
    device, domain, or instance identifier.
    """

    __tablename__ = "license_activations"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False)

    # Foreign keys
    license_id = Column(UUID(as_uuid=True), ForeignKey("licenses.id", ondelete="CASCADE"), nullable=False, index=True)

    # Activation details
    instance_id = Column(String(255), nullable=False, index=True, comment="Device ID, domain, or unique instance identifier")
    instance_name = Column(String(255), nullable=True, comment="Human-readable name for the instance")

    # Status
    is_active = Column(Boolean, default=True, nullable=False, index=True)

    # Timestamps
    activated_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.current_timestamp())
    deactivated_at = Column(TIMESTAMP(timezone=True), nullable=True)
    last_checked_at = Column(TIMESTAMP(timezone=True), nullable=True, comment="Last time this activation was validated/checked")

    # Metadata
    activation_metadata = Column(JSONB, default=dict, nullable=False, comment="Additional info: IP, user agent, OS, etc.")

    # Indexes — INSIDE the class body (fixes TASK-027)
    __table_args__ = (
        Index('idx_license_activations_license_instance', 'license_id', 'instance_id'),
        Index('idx_license_activations_active', 'license_id', 'is_active'),
    )

    # Relationships
    license = relationship("License", back_populates="activations", lazy="joined")

    def __repr__(self) -> str:
        return (
            f"<LicenseActivation(id={self.id}, license_id={self.license_id}, "
            f"instance={self.instance_id}, active={self.is_active})>"
        )

    def deactivate(self):
        """Mark this activation as inactive."""
        from datetime import timezone
        self.is_active = False
        self.deactivated_at = datetime.now(timezone.utc)
```

### Step 2: Convert DiscountUsage

```python
# File: rext-backend/src/api/models/subscription_models/discount_usage.py
# Replace the entire file content with:

"""
Discount Usage model for tracking discount code usage.

This model records when users apply discount codes during checkout,
enabling analytics and fraud prevention.
"""

import uuid
from datetime import datetime

from sqlalchemy import Column, String, Numeric, ForeignKey, Index, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from src.api.database.base import Base
from src.api.models.base import SerializableMixin


class DiscountUsage(Base, SerializableMixin):
    """
    Track discount code usage for analytics and fraud prevention.

    Each record represents one instance of a user applying a discount code.
    This data is typically created by webhook handlers when an order is processed.
    """

    __tablename__ = "discount_usage"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())

    # Foreign keys
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    subscription_id = Column(UUID(as_uuid=True), ForeignKey("user_subscriptions.id", ondelete="SET NULL"), nullable=True, index=True)

    # Discount information
    discount_code = Column(String(100), nullable=False, index=True)
    discount_amount = Column(Numeric(10, 2), nullable=True, comment="Amount saved (in currency or percentage)")
    discount_amount_type = Column(String(20), nullable=True, comment="Type: 'percent' or 'fixed'")

    # LemonSqueezy references
    order_id = Column(String(255), nullable=True, comment="LemonSqueezy order ID")
    lemonsqueezy_discount_id = Column(String(255), nullable=True, comment="LemonSqueezy discount ID")

    # Metadata
    applied_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.current_timestamp(), index=True)
    usage_metadata = Column(JSONB, nullable=True, comment="Additional discount information from LemonSqueezy")

    # Indexes — INSIDE the class body (fixes TASK-028)
    __table_args__ = (
        Index('idx_discount_usage_user_id', 'user_id'),
        Index('idx_discount_usage_code', 'discount_code'),
        Index('idx_discount_usage_applied_at', 'applied_at'),
        Index('idx_discount_usage_subscription_id', 'subscription_id'),
    )

    # Relationships
    user = relationship("Users", back_populates="discount_usages", lazy="joined")
    subscription = relationship("UserSubscription", back_populates="discount_usages", lazy="select")

    def __repr__(self) -> str:
        return (
            f"<DiscountUsage(id={self.id}, user_id={self.user_id}, "
            f"code={self.discount_code}, amount={self.discount_amount})>"
        )
```

### Step 3: Convert TrialConversion

```python
# File: rext-backend/src/api/models/subscription_models/trial_conversions.py
# Replace the entire file content with:

"""Trial conversion tracking model."""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Column, String, Integer, Numeric, ForeignKey, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

from src.api.database.base import Base
from src.api.models.base import SerializableMixin


class TrialConversion(Base, SerializableMixin):
    """
    Track when trials convert to paid subscriptions.

    This table provides analytics on trial conversion rates,
    conversion timing, and revenue impact.
    """
    __tablename__ = "trial_conversions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False)

    # User and subscription references
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    subscription_id = Column(UUID(as_uuid=True), ForeignKey("user_subscriptions.id", ondelete="CASCADE"), nullable=False, index=True)

    # Trial timeline
    trial_started_at = Column(TIMESTAMP(timezone=True), nullable=False, comment="When the trial started")
    trial_ended_at = Column(TIMESTAMP(timezone=True), nullable=False, comment="When the trial ended")
    converted_at = Column(TIMESTAMP(timezone=True), default=datetime.utcnow, nullable=False, index=True, comment="When trial converted to paid")
    trial_duration_days = Column(Integer, nullable=False, comment="Total trial duration in days")

    # Conversion details
    conversion_plan_id = Column(UUID(as_uuid=True), ForeignKey("subscription_plans.id", ondelete="SET NULL"), nullable=False, index=True, comment="Plan user converted to")
    conversion_billing_period = Column(String(20), nullable=False, comment="Monthly or yearly")
    conversion_amount = Column(Numeric(10, 2), nullable=True, comment="First payment amount")

    # Metadata for extensibility
    conversion_metadata = Column(JSONB, default=dict, nullable=False, comment="Additional conversion data (discount code, source, etc.)")

    # Timestamps
    created_at = Column(TIMESTAMP(timezone=True), default=datetime.utcnow, nullable=False)

    # Relationships (using back_populates per TASK-050)
    user = relationship("Users", back_populates="trial_conversions")
    subscription = relationship("UserSubscription", back_populates="trial_conversions")
    plan = relationship("SubscriptionPlan", back_populates="trial_conversions")

    def __repr__(self):
        return f"<TrialConversion(id={self.id}, user_id={self.user_id}, converted_at={self.converted_at})>"

    @property
    def conversion_rate_days(self) -> int:
        """Calculate how many days into trial the conversion happened."""
        if self.converted_at and self.trial_started_at:
            delta = self.converted_at - self.trial_started_at
            return delta.days
        return 0
```

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `rext-backend/src/api/models/subscription_models/subscriptions.py` | 77-80 | Same directory, uses `Column()` style — no changes needed, already consistent |
| `rext-backend/src/api/models/subscription_models/plans.py` | All | Same directory, uses `Column()` style — no changes needed |
| `rext-backend/src/api/models/subscription_models/licenses.py` | All | Same directory, uses `Column()` style — no changes needed |
| `rext-backend/src/api/models/subscription_models/refunds.py` | All | Same directory — verify if it uses `mapped_column` (it uses `Mapped`/`mapped_column` based on the audit; if so, include in this task) |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Open `license_activations.py`, `discount_usage.py`, and `trial_conversions.py` — observe `Mapped[T] = mapped_column(...)` pattern
2. Open any other model (e.g., `subscriptions.py`) — observe `Column(...)` pattern
3. Confirm the inconsistency within the same directory

### After Fix (Verify the Solution):
1. Open all three files — verify they now use `Column()` style
2. Run `grep -r "mapped_column" rext-backend/src/api/models/` — should return 0 results
3. Run `grep -r "Mapped\[" rext-backend/src/api/models/` — should return 0 results
4. Start the FastAPI application — verify no import errors or model configuration warnings
5. Verify that all columns, relationships, indexes, and defaults are preserved identically
6. For `LicenseActivation`: verify `__table_args__` is now INSIDE the class body (combines with TASK-027 fix)
7. For `DiscountUsage`: verify `__table_args__` is now INSIDE the class body (combines with TASK-028 fix)

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/ -v -k "license or discount or trial" --no-header
cd rext-backend && python -m pytest tests/ -v --no-header
```

---

## Acceptance Criteria

- [ ] Zero `mapped_column` or `Mapped[` usages remain in model files
- [ ] All three files (`license_activations.py`, `discount_usage.py`, `trial_conversions.py`) use `Column()` style
- [ ] All column definitions, indexes, constraints, defaults, and comments are preserved exactly
- [ ] `LicenseActivation.__table_args__` is inside the class body (not at module level)
- [ ] `DiscountUsage.__table_args__` is inside the class body (not at module level)
- [ ] Relationship declarations are preserved (and use `back_populates` per TASK-050)
- [ ] Application starts without errors
- [ ] No schema changes — `alembic check` or `alembic revision --autogenerate` produces an empty migration
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [SQLAlchemy 2.0 Declarative Tables — mapped_column()](https://docs.sqlalchemy.org/en/20/orm/declarative_tables.html#using-mapped-column) — Official documentation stating `mapped_column` is the modern approach but `Column` remains fully supported
- **Security Advisory:** N/A
- **Migration Guide:** [SQLAlchemy 2.0 Major Migration Guide](https://docs.sqlalchemy.org/en/20/changelog/migration_20.html) — Migration path from legacy Column to mapped_column, and from declarative_base to DeclarativeBase
- **Best Practice Reference:** [SQLAlchemy Column vs MappedColumn Guide](https://openillumi.com/en/en-sqlalchemy-column-mapped-column-guide/) — Comparison of both styles with recommendations for when to use each
- **Related Issues/PRs:** [SQLAlchemy Discussion #9320: Too many ways to define ORM mapping](https://github.com/sqlalchemy/sqlalchemy/discussions/9320) — Community discussion about the proliferation of declaration styles

---

## Dependencies & Related Tasks

- **Depends on:** TASK-027 (LicenseActivation `__table_args__` fix) and TASK-028 (DiscountUsage `__table_args__` fix) should be completed first or coordinated with this task, as both modify the same files. The solution in this task incorporates those fixes (moving `__table_args__` inside the class body).
- **Blocks:** None
- **Related:** TASK-041 (Deprecated `declarative_base()` — future migration to `DeclarativeBase` would be the right time to consider a full codebase migration to `mapped_column`), TASK-050 (Mixed backref vs back_populates — `trial_conversions.py` relationships are updated in both tasks)

# Task 027: Fix Module-level __table_args__ in LicenseActivation - Composite Indexes Silently Ignored

## Metadata
- **Task ID:** TASK-027
- **Source:** Database & Migrations Audit (Finding #1 under P0 Critical)
- **Audit Report:** `audit-reports/backend-database-migrations.md`
- **Priority:** P0 Critical
- **Category:** bug
- **Effort Estimate:** small (< 1 hour)

---

## Description

The `LicenseActivation` model in `src/api/models/subscription_models/license_activations.py` has a critical bug where the `__table_args__` tuple is defined at **module level** (line 126) instead of inside the class body (which ends at line 117). SQLAlchemy's declarative system only recognizes `__table_args__` when it is defined as a class-level attribute within the model class body. When placed at module level, SQLAlchemy completely ignores it during table creation.

According to the [SQLAlchemy 2.0 documentation](https://docs.sqlalchemy.org/en/20/orm/declarative_tables.html), the `__table_args__` attribute must be specified as a declarative class attribute alongside `__tablename__` and column definitions. The current placement means two composite indexes are silently never created:

1. `idx_license_activations_license_instance` - composite index on `(license_id, instance_id)`
2. `idx_license_activations_active` - composite index on `(license_id, is_active)`

These indexes are critical for license validation queries that filter by `license_id + instance_id` (checking if a specific device already has an activation) or `license_id + is_active` (counting active activations for a license). Without these composite indexes, PostgreSQL will perform full table scans, which will degrade proportionally as the license_activations table grows.

---

## Current Code

```python
# File: rext-backend/src/api/models/subscription_models/license_activations.py
# Lines: 103-131

    def __repr__(self) -> str:
        return (
            f"<LicenseActivation(id={self.id}, license_id={self.license_id}, "
            f"instance={self.instance_id}, active={self.is_active})>"
        )

    def to_dict(self, **kwargs):
        """Custom serialization."""
        data = super().to_dict(**kwargs)
        # Convert UUIDs to strings
        if 'id' in data and isinstance(data['id'], uuid.UUID):
            data['id'] = str(data['id'])
        if 'license_id' in data and isinstance(data['license_id'], uuid.UUID):
            data['license_id'] = str(data['license_id'])
        return data

    def deactivate(self):
        """Mark this activation as inactive."""
        self.is_active = False
        self.deactivated_at = datetime.utcnow()


# Table indexes  <-- THIS IS OUTSIDE THE CLASS (MODULE LEVEL)
__table_args__ = (
    # Composite index for finding activations by license and instance
    Index('idx_license_activations_license_instance', 'license_id', 'instance_id'),
    # Index for finding active activations
    Index('idx_license_activations_active', 'license_id', 'is_active'),
)
```

---

## Why This Matters (Context & Reasoning)

The `LicenseActivation` model tracks individual device/instance activations for software licenses in the Rext AI subscription system. This is essential for:

1. **Activation Limit Enforcement**: When a user activates their license on a new device, the system must quickly count existing active activations to enforce limits
2. **Device Verification**: When validating a license, the system checks if the specific `(license_id, instance_id)` combination already exists
3. **License Management**: Admin dashboards need to list and manage activations per license

Without the composite indexes:
- `SELECT ... WHERE license_id = ? AND instance_id = ?` requires scanning the entire table
- `SELECT COUNT(*) FROM license_activations WHERE license_id = ? AND is_active = true` becomes progressively slower
- License validation latency increases as the customer base grows

---

## Impact

- **Severity:** License validation queries will perform full table scans, causing progressively degrading performance. At scale (10,000+ activations), this could add seconds of latency to license validation requests.
- **Affected Users/Flows:** All license activation and validation flows - every time a user's software checks its license, every time a new device is activated, every admin view of license details.
- **Blast Radius:** Isolated to license-related queries, but affects all customers using the license/activation feature.

---

## Recommended Solution

### Step 1: Move __table_args__ Inside the Class Body

Edit `rext-backend/src/api/models/subscription_models/license_activations.py`:

```python
# File: rext-backend/src/api/models/subscription_models/license_activations.py
# Replace lines 103-131 with the following (move __table_args__ before __repr__):

class LicenseActivation(Base, SerializableMixin):
    """
    Track individual license activations to devices/instances.

    Each record represents one activation of a license key to a specific
    device, domain, or instance identifier.
    """

    __tablename__ = "license_activations"

    # ... (keep all existing column definitions unchanged) ...

    # Relationships
    license: Mapped["License"] = relationship(
        "License",
        back_populates="activations",
        lazy="joined"
    )

    # Table arguments - MUST be inside the class body
    __table_args__ = (
        # Composite index for finding activations by license and instance
        Index('idx_license_activations_license_instance', 'license_id', 'instance_id'),
        # Index for finding active activations
        Index('idx_license_activations_active', 'license_id', 'is_active'),
    )

    def __repr__(self) -> str:
        return (
            f"<LicenseActivation(id={self.id}, license_id={self.license_id}, "
            f"instance={self.instance_id}, active={self.is_active})>"
        )

    def to_dict(self, **kwargs):
        """Custom serialization."""
        data = super().to_dict(**kwargs)
        if 'id' in data and isinstance(data['id'], uuid.UUID):
            data['id'] = str(data['id'])
        if 'license_id' in data and isinstance(data['license_id'], uuid.UUID):
            data['license_id'] = str(data['license_id'])
        return data

    def deactivate(self):
        """Mark this activation as inactive."""
        self.is_active = False
        self.deactivated_at = datetime.utcnow()

# Remove the module-level __table_args__ that was here (lines 125-131)
```

### Step 2: Generate Alembic Migration

```bash
cd rext-backend
alembic revision --autogenerate -m "add_license_activation_composite_indexes"
```

### Step 3: Verify the Generated Migration

The generated migration should contain:

```python
def upgrade() -> None:
    op.create_index('idx_license_activations_license_instance', 'license_activations', ['license_id', 'instance_id'], unique=False)
    op.create_index('idx_license_activations_active', 'license_activations', ['license_id', 'is_active'], unique=False)

def downgrade() -> None:
    op.drop_index('idx_license_activations_active', table_name='license_activations')
    op.drop_index('idx_license_activations_license_instance', table_name='license_activations')
```

### Step 4: Run the Migration

```bash
alembic upgrade head
```

### Step 5: Verify Indexes Exist in Database

```sql
SELECT indexname, indexdef
FROM pg_indexes
WHERE tablename = 'license_activations'
AND indexname LIKE 'idx_license_activations%';
```

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `src/api/models/subscription_models/discount_usage.py` | `135-140` | Same bug - `__table_args__` at module level (see TASK-028) |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Connect to the PostgreSQL database
2. Run: `SELECT indexname FROM pg_indexes WHERE tablename = 'license_activations';`
3. Verify that `idx_license_activations_license_instance` and `idx_license_activations_active` do NOT appear in the results

### After Fix (Verify the Solution):
1. Apply the code change (move `__table_args__` inside class)
2. Run: `alembic revision --autogenerate -m "add_license_activation_indexes"`
3. Verify the generated migration creates the two composite indexes
4. Run: `alembic upgrade head`
5. Connect to PostgreSQL and verify: `SELECT indexname FROM pg_indexes WHERE tablename = 'license_activations';`
6. Both `idx_license_activations_license_instance` and `idx_license_activations_active` should now appear

### Run Existing Tests:
```bash
cd rext-backend
pytest tests/ -v -k "license"
```

---

## Acceptance Criteria

- [ ] `__table_args__` is moved inside the `LicenseActivation` class body (before `__repr__`)
- [ ] Module-level `__table_args__` (lines 125-131) is deleted
- [ ] Alembic autogenerate detects and creates migration for the two composite indexes
- [ ] Migration runs successfully without errors
- [ ] Database inspection confirms both indexes exist on `license_activations` table
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass

---

## References & Resources

- **Official Docs:** [SQLAlchemy 2.0 - Table Configuration with Declarative](https://docs.sqlalchemy.org/en/20/orm/declarative_tables.html) - Documents that `__table_args__` must be a class-level attribute
- **Security Advisory:** N/A (this is a performance/correctness bug, not a security issue)
- **Migration Guide:** N/A
- **Best Practice Reference:** [SQLAlchemy - Composite Indexes](https://docs.sqlalchemy.org/en/20/core/constraints.html#indexes) - Best practices for defining indexes

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-028 (same bug in DiscountUsage model), TASK-004 (datetime.utcnow deprecation - note the `deactivate()` method uses this)

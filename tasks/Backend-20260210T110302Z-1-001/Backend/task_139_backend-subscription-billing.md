# Task 139: License Status Enum Mismatch — Frontend Has REVOKED But Backend Uses DISABLED for Revocation

## Metadata
- **Task ID:** TASK-139
- **Source:** Backend Subscription & Billing Audit (Finding #21 under P2 Medium)
- **Audit Report:** `audit-reports/backend-subscription-billing.md`
- **Priority:** P2 Medium
- **Category:** data-integrity
- **Effort Estimate:** medium (1-4 hours)

---

## Description

The `LicenseStatus` enum is defined in two places with inconsistent values:

**Backend** (`src/api/models/subscription_models/licenses.py`, line 12-17):
```python
class LicenseStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    EXPIRED = "expired"
    DISABLED = "disabled"
```
— 4 values.

**Frontend** (`rext-admin/types/license.ts`, line 11-17):
```typescript
export enum LicenseStatus {
    ACTIVE = "active",
    INACTIVE = "inactive",
    EXPIRED = "expired",
    DISABLED = "disabled",
    REVOKED = "revoked",
}
```
— 5 values. The frontend adds `REVOKED = "revoked"` which does not exist in the backend.

The backend's `LicenseService.revoke_license()` method (`src/services/license_service.py`, line 372) sets the license status to `LicenseStatus.DISABLED` when revoking a license — not a hypothetical `REVOKED` status. This means:

1. When an admin revokes a license via the API, the backend sets `status = "disabled"`
2. The frontend receives `"disabled"` in the API response
3. The frontend's `getStatusBadgeVariant()` function (`rext-admin/app/licenses/page.tsx`, line 134-135) groups `DISABLED` and `REVOKED` together with the same badge variant (`"secondary"`), but the `REVOKED` case is dead code — the backend never returns `"revoked"`
4. Any frontend code that checks `license.status === LicenseStatus.REVOKED` will **never match**, because the backend never sends this value

The practical effect is that revoked licenses display as "disabled" in the UI rather than "revoked", which is semantically incorrect. An admin who revokes a license expects to see a "Revoked" badge, not a "Disabled" badge. Revocation and disabling are conceptually different operations — revocation implies a permanent administrative action (often due to policy violations), while disabling is a temporary state change.

---

## Current Code

```python
# File: src/api/models/subscription_models/licenses.py
# Lines: 12-17
class LicenseStatus(str, enum.Enum):
    """License status enum."""
    ACTIVE = "active"
    INACTIVE = "inactive"
    EXPIRED = "expired"
    DISABLED = "disabled"
```

```typescript
// File: rext-admin/types/license.ts
// Lines: 11-17
export enum LicenseStatus {
  ACTIVE = "active",
  INACTIVE = "inactive",
  EXPIRED = "expired",
  DISABLED = "disabled",
  REVOKED = "revoked",
}
```

```python
# File: src/services/license_service.py
# Lines: 370-373 (revocation sets DISABLED, not REVOKED)
        # Update license status
        license_obj.status = LicenseStatus.DISABLED
        license_obj.activation_count = 0
```

```typescript
// File: rext-admin/app/licenses/page.tsx
// Lines: 128-139 (REVOKED case is dead code — never received from backend)
  const getStatusBadgeVariant = (status: LicenseStatus) => {
    switch (status) {
      case LicenseStatus.ACTIVE:
        return "default";
      case LicenseStatus.EXPIRED:
        return "destructive";
      case LicenseStatus.DISABLED:
      case LicenseStatus.REVOKED:
        return "secondary";
      default:
        return "outline";
    }
  };
```

---

## Why This Matters (Context & Reasoning)

Enum mismatches between frontend and backend are a common source of subtle bugs in full-stack applications. They cause:
- **Dead code paths** in the frontend (checking for values that never arrive)
- **Incorrect UI display** (showing "disabled" when the operation was "revocation")
- **Developer confusion** (which enum is the source of truth?)
- **Potential runtime errors** if strict enum parsing is added later

The license management system supports admin operations like revoking licenses for policy violations. The admin dashboard should clearly distinguish between a license that was manually disabled (temporary, can be re-enabled) and one that was revoked (permanent administrative action). Using the same status for both operations loses this semantic distinction.

The correct fix is to add `REVOKED` to the backend enum so both layers agree, and update the revocation service to use the new status value. This requires an Alembic migration to add the new value to the PostgreSQL enum type.

---

## Impact

- **Severity:** Revoked licenses display as "Disabled" in the admin UI. Frontend code checking for `REVOKED` status is dead code that never matches. Semantic distinction between disable and revoke is lost.
- **Affected Users/Flows:** Admin users managing licenses, license revocation workflow, license listing/filtering.
- **Blast Radius:** License management UI and API responses. No impact on end users (license enforcement still works correctly — `DISABLED` licenses are blocked regardless of the semantic label).

---

## Recommended Solution

Add `REVOKED` to the backend `LicenseStatus` enum, create an Alembic migration to update the PostgreSQL enum type, and update the revocation service to use `LicenseStatus.REVOKED`.

### Step 1: Add REVOKED to the backend enum

```python
# File: src/api/models/subscription_models/licenses.py
# Replace lines 12-17 with:

class LicenseStatus(str, enum.Enum):
    """License status enum."""
    ACTIVE = "active"
    INACTIVE = "inactive"
    EXPIRED = "expired"
    DISABLED = "disabled"
    REVOKED = "revoked"
```

### Step 2: Create an Alembic migration to add the enum value

```bash
cd rext-backend && alembic revision --autogenerate -m "add_revoked_to_license_status_enum"
```

Then edit the generated migration file:

```python
# File: alembic/versions/<generated>_add_revoked_to_license_status_enum.py

"""add revoked to license status enum

Revision ID: <auto-generated>
Revises: <auto-generated>
Create Date: <auto-generated>
"""
from alembic import op

# revision identifiers
revision = '<auto-generated>'
down_revision = '<auto-generated>'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # PostgreSQL requires ALTER TYPE to add enum values.
    # ADD VALUE IF NOT EXISTS is safe to run multiple times (PostgreSQL 10+).
    op.execute("ALTER TYPE licensestatus ADD VALUE IF NOT EXISTS 'revoked'")


def downgrade() -> None:
    # PostgreSQL does not support removing enum values directly.
    # To downgrade, you would need to:
    # 1. Update any rows using 'revoked' to 'disabled'
    # 2. Create a new enum type without 'revoked'
    # 3. Alter the column to use the new type
    # 4. Drop the old type
    # For simplicity, we just update any revoked licenses back to disabled.
    op.execute("UPDATE licenses SET status = 'disabled' WHERE status = 'revoked'")
```

### Step 3: Update the revocation service to use REVOKED

```python
# File: src/services/license_service.py
# Replace lines 371-372 with:

        # Update license status to REVOKED (not DISABLED — revocation is a distinct admin action)
        license_obj.status = LicenseStatus.REVOKED
        license_obj.activation_count = 0
```

### Step 4: Update the validation check in license service to also block REVOKED licenses

```python
# File: src/services/license_service.py
# Replace lines 72-77 with:

        # Check if license is disabled or revoked
        if license_obj.status == LicenseStatus.DISABLED:
            raise RextValidationException(
                message="This license has been disabled",
                field_errors={"license_key": ["License is disabled"]}
            )

        if license_obj.status == LicenseStatus.REVOKED:
            raise RextValidationException(
                message="This license has been revoked",
                field_errors={"license_key": ["License has been revoked by an administrator"]}
            )
```

### Step 5: Update the `is_valid` property to account for REVOKED status

```python
# File: src/api/models/subscription_models/licenses.py
# Replace lines 67-76 with:

    @property
    def is_valid(self) -> bool:
        """Check if license is currently valid."""
        if self.status not in (LicenseStatus.ACTIVE,):
            return False
        if self.expires_at and self.expires_at < datetime.utcnow():
            return False
        if self.activation_limit and self.activation_count >= self.activation_limit:
            return False
        return True
```

### Step 6: Update `to_dict()` to handle the new enum value

No changes needed — the existing `to_dict()` method at line 59-65 already handles any `LicenseStatus` enum value via `self.status.value`, so `REVOKED` will serialize to `"revoked"` automatically.

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `src/services/license_service.py` | `72-77` | Validation check needs to also block `REVOKED` licenses |
| `src/services/license_service.py` | `371-372` | Revocation sets `DISABLED` — should set `REVOKED` |
| `src/api/models/subscription_models/licenses.py` | `68-76` | `is_valid` property checks `status != ACTIVE` (already handles new value correctly) |
| `rext-admin/app/licenses/page.tsx` | `128-139` | Already handles `REVOKED` — dead code becomes live code after fix |
| `src/api/routes/admin/license_routes.py` | Various | Admin license endpoints — may need filtering by new status |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. As an admin, revoke a license via the API: `POST /api/v1/admin/licenses/{license_id}/revoke`
2. Fetch the license: `GET /api/v1/admin/licenses/{license_id}`
3. Observe the response has `"status": "disabled"` (not `"revoked"`)
4. In the admin UI, observe the license shows a "disabled" badge

### After Fix (Verify the Solution):
1. Run the Alembic migration: `alembic upgrade head`
2. Revoke a license via the API
3. Fetch the license and verify `"status": "revoked"` in the response
4. In the admin UI, verify the license shows a "revoked" badge (secondary variant)
5. Attempt to activate the revoked license — should receive "License has been revoked by an administrator" error
6. Verify that manually disabled licenses still show as "disabled" (not "revoked")
7. Verify that existing disabled licenses from previous revocations still work correctly (they remain "disabled" — only new revocations get "revoked")

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/ -k "license" -v
cd rext-admin && npx jest --testPathPattern="license" --verbose
```

---

## Acceptance Criteria

- [ ] Backend `LicenseStatus` enum includes `REVOKED = "revoked"`
- [ ] Alembic migration adds `revoked` to the PostgreSQL `licensestatus` enum type
- [ ] `LicenseService.revoke_license()` sets status to `REVOKED` (not `DISABLED`)
- [ ] License validation rejects `REVOKED` licenses with a specific error message
- [ ] Frontend and backend `LicenseStatus` enums have identical values
- [ ] Previously disabled licenses (non-revocation) remain with `DISABLED` status
- [ ] Admin UI correctly displays "revoked" badge for revoked licenses
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [PostgreSQL ALTER TYPE — ADD VALUE](https://www.postgresql.org/docs/current/sql-altertype.html)
- **Security Advisory:** N/A
- **Migration Guide:** [Alembic — Migration with PostgreSQL Enum Types](https://alembic.sqlalchemy.org/en/latest/ops.html)
- **Best Practice Reference:** [Migrating PostgreSQL Enum with SQLAlchemy and Alembic](https://code.keplergrp.com/blog/migrating-postgresql-enum-sqlalchemy-alembic)
- **Related Issues/PRs:** None

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-129 (SubscriptionStatus Enum Mismatch Across Three Layers — same class of problem with a different enum)

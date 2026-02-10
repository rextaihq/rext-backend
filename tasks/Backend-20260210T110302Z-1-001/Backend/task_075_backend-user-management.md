# Task 075: Add Missing `super().__init__()` Call in MemberService

## Metadata
- **Task ID:** TASK-075
- **Source:** B3 - User Management (Finding #21 under P2 Medium)
- **Audit Report:** `audit-reports/backend-user-management.md`
- **Priority:** P2 Medium
- **Category:** bug
- **Effort Estimate:** small (< 1 hour)

---

## Description

`MemberService` at `src/services/member_service.py` line 37 inherits from `InvitationService`, but its `__init__` method (lines 40-47) directly assigns `self.db = db` without calling `super().__init__(db)`. This means the parent class `InvitationService.__init__()` is never executed. Currently, `InvitationService.__init__()` (at `src/services/invitation_service.py` lines 47-54) only sets `self.db = db`, so the system works by coincidence — both child and parent happen to set the same attribute in the same way.

However, this is a fragile pattern. If `InvitationService.__init__()` is ever updated to perform additional initialization (e.g., setting up a cache, initializing a token generator, or registering event handlers), `MemberService` would silently skip that initialization, leading to difficult-to-debug runtime errors. This violates Python's inheritance best practices where subclasses should always call `super().__init__()` to ensure proper initialization of the entire class hierarchy. The Python documentation explicitly recommends calling `super().__init__()` to ensure cooperative multiple inheritance works correctly.

The `MemberService` class uses several methods from `InvitationService` (via inheritance), such as `get_invitation_by_id()`. If the parent's initialization is skipped and a future change adds state to the parent, these inherited methods could fail with `AttributeError`.

---

## Current Code

```python
# File: src/services/member_service.py
# Lines: 37-47
class MemberService(InvitationService):
    """Service for workspace member business logic"""

    def __init__(self, db: AsyncSession):
        """
        Initialize MemberService.

        Args:
            db: Async database session
        """
        self.db = db
```

```python
# File: src/services/invitation_service.py
# Lines: 44-54
class InvitationService:
    """Service for invitation business logic"""

    def __init__(self, db: AsyncSession):
        """
        Initialize InvitationService.

        Args:
            db: Async database session
        """
        self.db = db
```

---

## Why This Matters (Context & Reasoning)

`MemberService` is a critical service that handles workspace member CRUD operations, role updates, and member queries. It inherits from `InvitationService` to reuse invitation-related methods for flows like accepting invitations and adding members. The inheritance relationship is intentional and actively used. Skipping the parent's `__init__()` creates a hidden dependency: the system only works because the parent currently has a trivially simple `__init__()`. This is a maintenance hazard that will cause bugs the moment the parent class evolves.

---

## Impact

- **Severity:** Currently no visible bug, but any future change to `InvitationService.__init__()` will silently fail for `MemberService` instances, potentially causing `AttributeError` or incorrect behavior in production.
- **Affected Users/Flows:** All workspace member operations (add/remove members, role updates, invitation handling) that use `MemberService`.
- **Blast Radius:** Isolated to `MemberService` class, but it's a high-traffic service used across multiple route files.

---

## Recommended Solution

### Step 1: Replace direct `self.db = db` with `super().__init__(db)` in MemberService

```python
# File: src/services/member_service.py
# Replace lines 40-47 with:
    def __init__(self, db: AsyncSession):
        """
        Initialize MemberService.

        Args:
            db: Async database session
        """
        super().__init__(db)
```

This single change ensures that `InvitationService.__init__()` is properly called, which currently sets `self.db = db`. If the parent adds more initialization in the future, `MemberService` will automatically pick it up.

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `src/services/invitation_service.py` | 44-54 | Parent class whose `__init__` is being skipped |
| `src/api/routes/users/invitations.py` | 263 | Creates `InvitationService(db)` — uses parent directly |
| `src/api/routes/users/workspaces.py` | Various | Creates `MemberService(db)` — affected class |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Verify current behavior works (since parent only sets `self.db`):
   ```python
   service = MemberService(db)
   assert hasattr(service, 'db')  # True — set by MemberService.__init__
   ```
2. Temporarily add an attribute to `InvitationService.__init__()`:
   ```python
   self._invitation_cache = {}
   ```
3. Observe that `MemberService` instances do NOT have `_invitation_cache`

### After Fix (Verify the Solution):
1. Verify `MemberService` still works correctly for all member operations
2. Add a temporary attribute to `InvitationService.__init__()` and verify `MemberService` instances have it
3. Run all workspace member and invitation endpoint tests

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/ -k "member or invitation" -v
```

---

## Acceptance Criteria

- [ ] `MemberService.__init__()` calls `super().__init__(db)` instead of `self.db = db`
- [ ] All `MemberService` methods continue to work correctly
- [ ] Inherited `InvitationService` methods work correctly on `MemberService` instances
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [Python super() documentation](https://docs.python.org/3/library/functions.html#super)
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** [Python documentation — Cooperative Multiple Inheritance](https://docs.python.org/3/tutorial/classes.html#inheritance)
- **Related Issues/PRs:** N/A

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-074 (same file `member_service.py` — service layer commit removal)

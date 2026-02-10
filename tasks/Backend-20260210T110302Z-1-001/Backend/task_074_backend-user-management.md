# Task 074: Remove Unauthorized `db.commit()` Calls from Service Layer

## Metadata
- **Task ID:** TASK-074
- **Source:** B3 - User Management (Finding #15 under P2 Medium)
- **Audit Report:** `audit-reports/backend-user-management.md`
- **Priority:** P2 Medium
- **Category:** bug
- **Effort Estimate:** small (< 1 hour)

---

## Description

Two service classes — `UserPreferencesService` and `MemberService` — contain `await self.db.commit()` calls inside their methods, directly violating the project's stated architectural rule documented in each service's docstring: "Does NOT commit transactions (that's decorators/routes)." Specifically, `UserPreferencesService.update_preferences()` calls `await self.db.commit()` at line 122 of `src/services/user_preferences_service.py`, and `MemberService.remove_user_roles_in_workspace()` calls `await self.db.commit()` at line 626 of `src/services/member_service.py`.

This is problematic because it breaks transaction atomicity. When a route handler orchestrates multiple service calls within a single transaction (managed by `@db_transaction_handler` or explicit route-level commit), a service that commits mid-operation makes it impossible to roll back the entire operation if a subsequent step fails. For example, if a route removes a user from a workspace (calling `remove_user_roles_in_workspace()`) and then tries to delete the workspace membership, and the second operation fails, the role deletion has already been committed and cannot be rolled back.

According to SQLAlchemy best practices, `session.commit()` should only appear in "lifecycle" logic managed by the framework — a FastAPI dependency, middleware, decorator, or context manager — not inside business logic services. The correct approach is to use `await self.db.flush()` when intermediate results are needed (e.g., to get auto-generated IDs), which sends SQL to the database within the current transaction without committing it.

---

## Current Code

```python
# File: src/services/user_preferences_service.py
# Lines: 120-122
        if updates:
            preferences.updated_at = datetime.utcnow()
            await self.db.commit()
```

```python
# File: src/services/member_service.py
# Lines: 621-626
        # Delete each user role
        for user_role in user_roles:
            await self.db.delete(user_role)

        # ✅ Commit the changes
        await self.db.commit()
```

---

## Why This Matters (Context & Reasoning)

The project follows a layered architecture (Routes → Services → Models) where transaction boundaries are managed at the route/decorator level. Services handle business logic only. This design enables routes to compose multiple service calls into a single atomic transaction. When services commit independently, this contract is broken, making transaction management unpredictable across the application. The `remove_user_roles_in_workspace` method is called during workspace member removal — a critical operation that should be atomic with membership deletion.

---

## Impact

- **Severity:** If a multi-step operation fails after one of these services has already committed, the database will be left in an inconsistent state with no way to roll back the committed portion.
- **Affected Users/Flows:** User preferences updates and workspace member role removal operations. Any route that calls these methods as part of a larger transaction.
- **Blast Radius:** Moderate — affects two distinct service methods, but the pattern could be copy-pasted into future services if not corrected.

---

## Recommended Solution

### Step 1: Remove `await self.db.commit()` from `UserPreferencesService.update_preferences()`

```python
# File: src/services/user_preferences_service.py
# Replace lines 120-123 with:
        if updates:
            preferences.updated_at = datetime.utcnow()
            await self.db.flush()
            logger.info(f"Updated preferences for user {user_id}: {', '.join(updates)}")
```

### Step 2: Remove `await self.db.commit()` from `MemberService.remove_user_roles_in_workspace()`

```python
# File: src/services/member_service.py
# Replace lines 621-626 with:
        # Delete each user role
        for user_role in user_roles:
            await self.db.delete(user_role)

        # Flush to execute deletes within current transaction
        await self.db.flush()
```

### Step 3: Verify all callers handle commits at the route level

Check that all routes calling these methods either use `@db_transaction_handler(auto_commit=True)` or have explicit `await db.commit()` at the end of the route handler.

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `src/api/routes/users/preferences.py` | Caller | Route that calls `update_preferences()` — verify it commits |
| `src/api/routes/users/workspaces.py` | Caller | Route that may call `remove_user_roles_in_workspace()` — verify it commits |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Set a breakpoint after `update_preferences()` is called but before the route returns
2. Observe that the preferences change is already committed to the database even if the route hasn't finished
3. If the route subsequently fails, the preferences change cannot be rolled back

### After Fix (Verify the Solution):
1. Call the update preferences endpoint
2. Verify preferences are updated successfully (commit happens at route level)
3. Simulate a failure after `update_preferences()` in the route — verify the change is rolled back
4. Call remove member endpoint and verify role removal + membership deletion happen atomically

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/ -k "preferences or member" -v
```

---

## Acceptance Criteria

- [ ] `await self.db.commit()` removed from `user_preferences_service.py:122`
- [ ] `await self.db.commit()` removed from `member_service.py:626`
- [ ] Both replaced with `await self.db.flush()` for intermediate SQL execution
- [ ] All calling routes verified to handle commits properly
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [SQLAlchemy Session Basics — flush vs commit](https://docs.sqlalchemy.org/en/20/orm/session_basics.html)
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** [SQLAlchemy: Stop calling session.commit() — François Voron](https://www.francoisvoron.com/blog/sqlalchemy-stop-calling-session-commit)
- **Related Issues/PRs:** N/A

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-037 (Sync `create_audit_log()` commits within function — same architectural violation in B2)

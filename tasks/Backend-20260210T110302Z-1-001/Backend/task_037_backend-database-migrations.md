# Task 037: Fix Sync create_audit_log() Transaction Boundary Violation

## Metadata
- **Task ID:** TASK-037
- **Source:** Backend Database & Migrations Audit (Finding #11 under P1 High)
- **Audit Report:** `audit-reports/backend-database-migrations.md`
- **Priority:** P1 High
- **Category:** bug
- **Effort Estimate:** small (< 1 hour)

---

## Description

The synchronous `create_audit_log()` function in `src/utils/audit_helper.py` at line 85 calls `db.commit()` directly within the function body, which prematurely commits the database transaction. This violates the principle of transaction boundary management where inner functions should use `flush()` to participate in outer transactions rather than committing independently.

When this function is called from code wrapped by the `@db_transaction_handler` or `@transactional` decorators (which manage commit/rollback at the request boundary), the inner `db.commit()` causes the audit log record to be permanently committed even if subsequent operations in the same request fail. This breaks transactional atomicity - if a later database operation fails and the decorator performs a rollback, the audit log entry remains in the database as an orphan record documenting an action that was never actually completed.

The async version of the same function (`create_audit_log_async` at line 171) correctly uses `await db.flush()` instead of commit, demonstrating that the correct pattern is already understood and implemented elsewhere in the codebase. The sync version simply needs to be aligned with this established pattern.

According to SQLAlchemy best practices documented in the [official transaction management guide](https://docs.sqlalchemy.org/en/20/orm/session_transaction.html), `flush()` sends pending operations to the database without committing, allowing the outer transaction manager to decide when to commit or rollback the entire unit of work.

---

## Current Code

```python
# File: rext-backend/src/utils/audit_helper.py
# Lines: 84-94
        db.add(audit_log)
        db.commit()
        db.refresh(audit_log)

        logger.info(f"Audit log created: {action} on {resource_type}:{resource_id} by user:{user_id}")
        return audit_log

    except Exception as e:
        logger.error(f"Failed to create audit log: {str(e)}")
        db.rollback()
        return None
```

For comparison, the async version correctly uses flush:

```python
# File: rext-backend/src/utils/audit_helper.py
# Lines: 170-180
        db.add(audit_log)
        await db.flush()

        logger.info(f"Audit log created: {action} on {resource_type}:{resource_id} by user:{user_id}")
        return audit_log

    except Exception as e:
        logger.error(f"Failed to create audit log: {str(e)}")
        # DO NOT rollback here - let the decorator handle transaction rollback
        # Rolling back here would cause the entire request transaction to fail
        return None
```

---

## Why This Matters (Context & Reasoning)

Audit logging is a critical compliance and debugging feature that records all significant user actions in the system. The audit log provides an immutable record of who did what and when, which is essential for security audits, debugging production issues, and regulatory compliance.

The `create_audit_log()` function is called from route handlers after performing business operations, such as creating invitations (as seen in `invitation_create.py:171`). The route handlers use `@db_transaction_handler(auto_commit=True)` which expects to manage the transaction lifecycle at the route level.

When the sync `create_audit_log()` commits independently:
1. The audit log is immediately persisted, even before the route completes
2. If the route fails after audit logging, the decorator rolls back all changes EXCEPT the already-committed audit log
3. The database ends up with an audit log entry for an action that never completed
4. This corrupts the audit trail and violates data integrity

The correct behavior is for `create_audit_log()` to use `flush()` so the audit log participates in the same transaction as the business operation it documents. If the business operation fails, both it and its audit log should be rolled back together.

---

## Impact

- **Severity:** Orphaned audit log entries for failed operations; corrupted audit trail; violation of transactional atomicity
- **Affected Users/Flows:** Any route that calls `create_audit_log()` within a transaction-managed context (currently invitation creation/management flows)
- **Blast Radius:** Medium - affects audit log integrity across multiple features that use sync audit logging

---

## Recommended Solution

### Step 1: Replace `db.commit()` with `db.flush()` in sync version

```python
# File: rext-backend/src/utils/audit_helper.py
# Replace lines 84-94 with:

        db.add(audit_log)
        db.flush()  # Changed from db.commit() - let outer transaction manage commit

        logger.info(f"Audit log created: {action} on {resource_type}:{resource_id} by user:{user_id}")
        return audit_log

    except Exception as e:
        logger.error(f"Failed to create audit log: {str(e)}")
        # DO NOT rollback here - let the outer transaction manager handle it
        # Rolling back here would affect the entire request transaction
        return None
```

### Step 2: Remove the explicit `db.refresh()` call

The `db.refresh()` at line 86 is used to reload the object from the database after commit. Since we're no longer committing, we don't need to refresh. If the caller needs the audit log's generated `id`, they can access it after the outer transaction commits, or we can rely on the fact that `flush()` assigns the database-generated ID.

```python
# File: rext-backend/src/utils/audit_helper.py
# Final corrected version of lines 84-94:

        db.add(audit_log)
        db.flush()  # Participate in outer transaction

        logger.info(f"Audit log created: {action} on {resource_type}:{resource_id} by user:{user_id}")
        return audit_log

    except Exception as e:
        logger.error(f"Failed to create audit log: {str(e)}")
        # Let the outer transaction manager handle rollback
        return None
```

### Step 3: Update callers if they rely on standalone usage

If any code uses `create_audit_log()` outside of a transaction-managed context (without `@transactional` or `@db_transaction_handler`), those callers will need to add an explicit `db.commit()` after calling the function. However, based on the codebase search, all current usages are within transaction-managed routes.

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `rext-backend/src/api/routes/workspaces/invitations.py/modules/invitation_create.py` | `171, 268` | Callers of sync `create_audit_log()` - these will now correctly participate in the route's transaction |
| `rext-backend/src/api/routes/workspaces/invitations.py/modules/invitation_manage.py` | `236` | Another caller of sync `create_audit_log()` |
| `rext-backend/src/utils/token_cleanup.py` | N/A | Related issue - also uses sync ORM patterns; identified in TASK-011 |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Set up a scenario where an invitation creation can fail AFTER the audit log is created (e.g., add a deliberate error after the `create_audit_log()` call)
2. Attempt to create an invitation
3. Observe that the audit log entry exists in the database even though the invitation creation failed
4. Check the `audit_logs` table: `SELECT * FROM audit_logs WHERE action = 'invitation.create' ORDER BY created_at DESC LIMIT 5;`

### After Fix (Verify the Solution):
1. Apply the fix
2. Repeat the same scenario (invitation creation that fails after audit log creation)
3. Verify that NO audit log entry exists for the failed operation
4. Confirm that successful operations still have their audit logs persisted correctly
5. Check that the audit log's `id` field is populated after the route completes

### Run Existing Tests:
```bash
cd rext-backend
pytest tests/ -k "audit" -v
pytest tests/ -k "invitation" -v
```

---

## Acceptance Criteria

- [ ] `create_audit_log()` sync function uses `db.flush()` instead of `db.commit()`
- [ ] `db.refresh()` call is removed from the sync function
- [ ] `db.rollback()` in the exception handler is removed (matches async version pattern)
- [ ] Sync version matches the async version's transaction participation pattern
- [ ] Audit logs are only persisted when the outer transaction commits successfully
- [ ] Failed operations do not leave orphan audit log entries
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [SQLAlchemy 2.0 Transactions and Connection Management](https://docs.sqlalchemy.org/en/20/orm/session_transaction.html)
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** [Understanding Flush vs Commit in SQLAlchemy](https://medium.com/@slackermann/understanding-sqlalchemy-flush-the-complete-developers-guide-028b6d55c491)
- **Related Issues/PRs:** N/A

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-011 (token_cleanup.py Uses Synchronous ORM - same sync vs async pattern issue from B1 audit)

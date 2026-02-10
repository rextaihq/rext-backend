# Task 032: Add Missing ondelete Specifications to ~15+ Foreign Key Columns

## Metadata
- **Task ID:** TASK-032
- **Source:** Backend Database & Migrations Audit (Finding #6 under P1 High)
- **Audit Report:** `audit-reports/backend-database-migrations.md`
- **Priority:** P1 High
- **Category:** data-integrity
- **Effort Estimate:** medium (1-4 hours)

---

## Description

Approximately 15+ foreign key columns across the codebase are defined without an explicit `ondelete` specification. In PostgreSQL, when no `ondelete` is specified, the default behavior is `RESTRICT` (or `NO ACTION`), which prevents deletion of the parent row if any child rows reference it. This creates a significant operational problem: attempting to delete a User or Workspace will fail with a foreign key constraint violation error if any related records exist in these tables.

The inconsistency is compounded by the fact that some FK columns in the same codebase DO specify `ondelete` (e.g., `subscriptions.py:35` uses `ondelete="CASCADE"` for `user_id`, and `customer_note.py:24` uses `ondelete="CASCADE"`), while others in the same file or related files do not. This creates unpredictable behavior where deleting a parent record may succeed in some cases and fail in others, depending on which child tables have records.

According to SQLAlchemy 2.x best practices, database-level `ON DELETE` cascades are significantly more efficient than ORM-level cascades because the database can chain cascade operations across many relationships in a single DELETE statement. When using database-level cascades, the `passive_deletes=True` option should be set on the parent relationship to prevent the ORM from interfering with the database's cascade behavior.

The affected columns fall into two categories:
1. **Dependent data that should be deleted with parent:** FK columns like `workspace_id` on `workspace_members`, `user_id` on `user_roles` should use `CASCADE` because these records have no meaning without their parent.
2. **Audit/reference columns that should be preserved:** FK columns like `assigned_by_user_id`, `deleted_by`, `created_by_user_id`, `invited_by_user_id` should use `SET NULL` because they record historical information about who performed an action, and that information should be preserved even if the referenced user is later deleted.

---

## Current Code

```python
# File: src/api/models/workspace_models/workspace_model.py
# Lines: 16, 24
user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)  # Missing ondelete
deleted_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)  # Missing ondelete
```

```python
# File: src/api/models/workspace_models/workspace_member.py
# Lines: 16-18
user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)  # Missing ondelete
workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspace.id"), nullable=False)  # Missing ondelete
invitation_id = Column(UUID(as_uuid=True), ForeignKey("user_invitations.id"), nullable=True)  # Missing ondelete
```

```python
# File: src/api/models/user_models/user_roles.py
# Lines: 17-20
user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)  # Missing ondelete
role_id = Column(UUID(as_uuid=True), ForeignKey("roles.id"), nullable=False)  # Missing ondelete
workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspace.id"), nullable=True)  # Missing ondelete
assigned_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)  # Missing ondelete
```

```python
# File: src/api/models/user_models/invitations.py
# Lines: 13-15
workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspace.id"), nullable=False)  # Missing ondelete
role_id = Column(UUID(as_uuid=True), ForeignKey("roles.id"), nullable=False)  # Missing ondelete
invited_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)  # Missing ondelete
```

```python
# File: src/api/models/workspace_models/email_template.py
# Lines: 30, 40
workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspace.id"), nullable=True)  # Missing ondelete
created_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)  # Missing ondelete
```

```python
# File: src/api/models/subscription_models/subscriptions.py
# Line: 36
plan_id = Column(UUID(as_uuid=True), ForeignKey("subscription_plans.id"), nullable=False)  # Missing ondelete
```

```python
# File: src/api/models/admin_models/customer_note.py
# Lines: 28-32
admin_id = Column(
    PostgresUUID(as_uuid=True),
    ForeignKey("users.id"),  # Missing ondelete (contrast: user_id on line 24 HAS ondelete="CASCADE")
    nullable=False,
    index=True
)
```

```python
# File: src/api/models/admin_models/error_log.py
# Lines: 26-30, 36-40
user_id = Column(
    PostgresUUID(as_uuid=True),
    ForeignKey("users.id"),  # Missing ondelete
    nullable=True
)
resolved_by = Column(
    PostgresUUID(as_uuid=True),
    ForeignKey("users.id"),  # Missing ondelete
    nullable=True
)
```

---

## Why This Matters (Context & Reasoning)

This codebase supports a multi-tenant SaaS application where users can create workspaces, invite members, assign roles, and manage content. User and workspace lifecycle management is a core operational requirement:

1. **User Deletion:** When a user is deleted (account closure, GDPR request, etc.), all their associated records in dependent tables must be handled appropriately. Without proper `ondelete` specifications, the deletion will fail with constraint errors.

2. **Workspace Deletion:** When a workspace is deleted (soft or hard delete), members, roles, invitations, and other workspace-specific data must be cleaned up. The current configuration would block workspace deletion.

3. **Audit Trail Preservation:** Records of who invited a user, who assigned a role, or who deleted something should survive the deletion of the actor. Using `SET NULL` on audit columns preserves the record while allowing the user to be deleted.

4. **Consistency:** The codebase already uses `ondelete` in some places (e.g., `subscriptions.py:35`, `customer_note.py:24`), so fixing the missing specifications aligns with the established pattern and developer expectations.

---

## Impact

- **Severity:** User and workspace deletion operations will fail with PostgreSQL foreign key constraint violations if any related records exist in these tables. This blocks critical account management operations.
- **Affected Users/Flows:** Admin account deletion, user self-deletion (GDPR), workspace deletion, any cleanup operations
- **Blast Radius:** Affects 8+ model files and any code path that deletes Users, Workspaces, Roles, SubscriptionPlans, or Invitations

---

## Recommended Solution

Add appropriate `ondelete` specifications to each affected foreign key column. Use `CASCADE` for dependent data that should be deleted with the parent, and `SET NULL` for audit/reference columns where the historical record should be preserved.

### Step 1: Update workspace_model.py

```python
# File: src/api/models/workspace_models/workspace_model.py
# Replace lines 16 and 24:

user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
# ... other columns ...
deleted_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
```

### Step 2: Update workspace_member.py

```python
# File: src/api/models/workspace_models/workspace_member.py
# Replace lines 16-18:

user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False)
invitation_id = Column(UUID(as_uuid=True), ForeignKey("user_invitations.id", ondelete="SET NULL"), nullable=True)
```

### Step 3: Update user_roles.py

```python
# File: src/api/models/user_models/user_roles.py
# Replace lines 17-20:

user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
role_id = Column(UUID(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), nullable=False)
workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspace.id", ondelete="CASCADE"), nullable=True)
assigned_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
```

### Step 4: Update invitations.py

```python
# File: src/api/models/user_models/invitations.py
# Replace lines 13-15:

workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False)
role_id = Column(UUID(as_uuid=True), ForeignKey("roles.id", ondelete="RESTRICT"), nullable=False)
invited_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=False)
```

Note: `role_id` uses `RESTRICT` because deleting a role that has pending invitations should be blocked - the admin should reassign the invitation to a different role first.

**Important:** After changing `invited_by_user_id` to `ondelete="SET NULL"`, the column must also be changed to `nullable=True`:

```python
invited_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
```

### Step 5: Update email_template.py

```python
# File: src/api/models/workspace_models/email_template.py
# Replace lines 30 and 40:

workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspace.id", ondelete="CASCADE"), nullable=True)
# ... other columns ...
created_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
```

### Step 6: Update subscriptions.py

```python
# File: src/api/models/subscription_models/subscriptions.py
# Replace line 36:

plan_id = Column(UUID(as_uuid=True), ForeignKey("subscription_plans.id", ondelete="RESTRICT"), nullable=False)
```

Note: `RESTRICT` is intentional here - you should not delete a subscription plan that has active subscriptions. Migrate subscriptions first.

### Step 7: Update customer_note.py

```python
# File: src/api/models/admin_models/customer_note.py
# Replace lines 28-32:

admin_id = Column(
    PostgresUUID(as_uuid=True),
    ForeignKey("users.id", ondelete="SET NULL"),
    nullable=True,  # Changed from nullable=False to allow SET NULL
    index=True
)
```

### Step 8: Update error_log.py

```python
# File: src/api/models/admin_models/error_log.py
# Replace lines 26-30 and 36-40:

user_id = Column(
    PostgresUUID(as_uuid=True),
    ForeignKey("users.id", ondelete="SET NULL"),
    nullable=True
)
# ... other columns ...
resolved_by = Column(
    PostgresUUID(as_uuid=True),
    ForeignKey("users.id", ondelete="SET NULL"),
    nullable=True
)
```

### Step 9: Generate and Apply Migration

```bash
cd rext-backend
alembic revision --autogenerate -m "add_ondelete_to_foreign_keys"
alembic upgrade head
```

### Step 10: Update Parent Relationships with passive_deletes (Optional but Recommended)

For relationships where cascade delete is used, add `passive_deletes=True` to the parent side to let the database handle the cascade:

```python
# File: src/api/models/workspace_models/workspace_model.py
# Update relationship declarations:

members = relationship("WorkspaceMembers", back_populates="workspace", cascade="all, delete-orphan", passive_deletes=True)
```

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `src/api/models/knowledge_models/knowledge_model.py` | Various | FK columns for `workspace_id`, `knowledge_base_id` may also need review |
| `src/api/models/content_models/content.py` | TBD | FK columns may need ondelete |
| `src/api/models/media_models/media.py` | TBD | FK columns may need ondelete |
| `src/services/user_service.py` | N/A | Delete user logic may need to be reviewed after migration |
| `src/services/workspace_service.py` | N/A | Delete workspace logic may need to be reviewed after migration |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Create a test user and workspace in the database
2. Create a workspace member record linking the user to the workspace
3. Attempt to delete the user via the API or direct database operation:
   ```sql
   DELETE FROM users WHERE id = '<user_id>';
   ```
4. **Expected:** PostgreSQL error: `update or delete on table "users" violates foreign key constraint`

### After Fix (Verify the Solution):
1. Apply the migration: `alembic upgrade head`
2. Create a test user and workspace
3. Create workspace member, user role, and invitation records
4. Delete the user:
   ```sql
   DELETE FROM users WHERE id = '<user_id>';
   ```
5. **Expected:** User deleted successfully. Related records in `workspace_members`, `user_roles` deleted (CASCADE). Audit columns like `assigned_by_user_id`, `invited_by_user_id` set to NULL.
6. Verify the cascades worked:
   ```sql
   SELECT * FROM workspace_members WHERE user_id = '<deleted_user_id>';  -- Should return 0 rows
   SELECT * FROM user_roles WHERE user_id = '<deleted_user_id>';  -- Should return 0 rows
   SELECT * FROM user_roles WHERE assigned_by_user_id IS NULL;  -- Should include any rows where assigner was deleted
   ```

### Run Existing Tests:
```bash
cd rext-backend
pytest tests/ -v -k "user" --tb=short
pytest tests/ -v -k "workspace" --tb=short
```

---

## Acceptance Criteria

- [ ] All ~15+ FK columns have explicit `ondelete` specification
- [ ] Dependent data columns use `ondelete="CASCADE"`
- [ ] Audit/reference columns use `ondelete="SET NULL"` and are `nullable=True`
- [ ] Columns where deletion should be blocked use `ondelete="RESTRICT"`
- [ ] Alembic migration generated and applies successfully
- [ ] User deletion succeeds when related records exist
- [ ] Workspace deletion succeeds when related records exist
- [ ] Audit columns preserve NULL values after referenced user deletion
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass

---

## References & Resources

- **Official Docs:** [SQLAlchemy 2.1 Cascades Documentation](https://docs.sqlalchemy.org/en/21/orm/cascades.html) - Comprehensive guide on database-level vs ORM-level cascades
- **Security Advisory:** N/A (data integrity issue, not security)
- **Migration Guide:** N/A
- **Best Practice Reference:** [SQLModel Cascade Delete Relationships](https://sqlmodel.tiangolo.com/tutorial/relationship-attributes/cascade-delete-relationships/) - Clear examples of CASCADE vs SET NULL
- **Related Issues/PRs:** [SQLAlchemy GitHub Issue #5349](https://github.com/sqlalchemy/sqlalchemy/issues/5349) - Discussion on passive_deletes default behavior

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-033 (Missing Unique Constraints on Join Tables - same files affected), TASK-035 (TokenBlacklist.user_id Missing FK)

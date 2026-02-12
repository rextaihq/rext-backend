# Task 033: Add Missing Unique Constraints on Join Tables

## Metadata
- **Task ID:** TASK-033
- **Source:** Backend Database & Migrations Audit (Finding #7 under P1 High)
- **Audit Report:** `audit-reports/backend-database-migrations.md`
- **Priority:** P1 High
- **Category:** data-integrity
- **Effort Estimate:** medium (1-4 hours)

---

## Description

Four join/association tables in the codebase lack composite unique constraints to prevent duplicate relationships. In a relational database, join tables that establish many-to-many relationships must have unique constraints on the combination of foreign key columns to prevent duplicate associations.

The affected tables are:

1. **user_roles** - No unique constraint on `(user_id, role_id, workspace_id)`. This allows the same user to be assigned the same role in the same workspace multiple times, creating duplicate role assignments.

2. **role_permissions** - No unique constraint on `(role_id, permission_id)`. This allows the same permission to be granted to the same role multiple times.

3. **workspace_members** - No unique constraint on `(user_id, workspace_id)`. This allows a user to appear as a member of the same workspace multiple times.

4. **content_media** - No unique constraint on `(content_id, media_id)`. This allows the same media file to be linked to the same content piece multiple times.

Without these constraints, application bugs, race conditions during concurrent requests, or manual database operations can create duplicate records. According to SQL standards and SQLAlchemy best practices, composite unique constraints should be defined in `__table_args__` to enforce data integrity at the database level. The database-level constraint is critical because it prevents duplicates regardless of whether the ORM or raw SQL is used to insert data.

Composite unique constraints work by enforcing uniqueness on the combination of columns, not individual columns. For example, with a constraint on `(user_id, workspace_id)` in `workspace_members`, user A can be a member of workspace 1 and workspace 2, and user B can also be a member of workspace 1 - but user A cannot be added to workspace 1 twice.

---

## Current Code

```python
# File: src/api/models/user_models/user_roles.py
# Lines: 13-31
class UserRole(Base, SerializableMixin):
    __tablename__ = "user_roles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    role_id = Column(UUID(as_uuid=True), ForeignKey("roles.id"), nullable=False)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspace.id"), nullable=True)
    assigned_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    # ... no __table_args__ with UniqueConstraint
```

```python
# File: src/api/models/user_models/role_permissions.py
# Lines: 11-22
class RolePermission(Base, SerializableMixin):
    __tablename__ = "role_permissions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False)
    role_id = Column(UUID(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), nullable=False)
    permission_id = Column(UUID(as_uuid=True), ForeignKey("permissions.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(TIMESTAMP, default=datetime.utcnow, nullable=False)
    # ... no __table_args__ with UniqueConstraint
```

```python
# File: src/api/models/workspace_models/workspace_member.py
# Lines: 12-28
class WorkspaceMembers(Base, SerializableMixin):
    __tablename__ = "workspace_members"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspace.id"), nullable=False)
    invitation_id = Column(UUID(as_uuid=True), ForeignKey("user_invitations.id"), nullable=True)
    # ... no __table_args__ with UniqueConstraint
```

```python
# File: src/api/models/content_models/content_media.py
# Lines: 17-67
class ContentMedia(Base, SerializableMixin):
    __tablename__ = "content_media"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, nullable=False)
    content_id = Column(UUID(as_uuid=True), ForeignKey("content.id", ondelete="CASCADE"), nullable=False, index=True)
    media_id = Column(UUID(as_uuid=True), ForeignKey("media.id", ondelete="CASCADE"), nullable=False, index=True)
    usage_type = Column(String(50), nullable=True)
    position = Column(Integer, nullable=True)
    # ... no __table_args__ with UniqueConstraint
```

---

## Why This Matters (Context & Reasoning)

These join tables implement core business logic in the multi-tenant SaaS application:

1. **user_roles** - Controls access to features based on role assignments. Duplicate role assignments can cause:
   - Incorrect permission calculations (permissions counted multiple times)
   - Confusion in admin UIs showing duplicate entries
   - Errors when removing role assignments (which one to delete?)

2. **role_permissions** - Maps permissions to roles. Duplicate permission grants can cause:
   - Inflated permission counts in analytics
   - Unexpected behavior when revoking permissions

3. **workspace_members** - Tracks team membership. Duplicate memberships can cause:
   - Users appearing twice in member lists
   - Double notifications sent to the same user
   - Incorrect member count statistics
   - Billing calculation errors if based on member count

4. **content_media** - Tracks media usage. Duplicate links can cause:
   - Incorrect media usage counts
   - Media appearing multiple times in content galleries
   - Issues with media deletion protection logic

The unique constraints must be at the database level (not just ORM validation) because:
- They catch duplicates from any source: ORM, raw SQL, database tools, migrations
- They handle race conditions where two concurrent requests try to create the same association
- They serve as the single source of truth for data integrity

---

## Impact

- **Severity:** Data corruption through duplicate records. Incorrect counts, duplicate UI entries, authorization calculation errors, and double notifications.
- **Affected Users/Flows:** User role management, team membership, permission management, content-media associations, any reporting/analytics features
- **Blast Radius:** Affects 4 join tables that are used throughout the application. Any feature that lists members, checks permissions, or tracks media usage is potentially affected.

---

## Recommended Solution

Add `UniqueConstraint` declarations to the `__table_args__` tuple for each affected model. Then generate and apply an Alembic migration.

### Step 1: Check for Existing Duplicates

Before adding constraints, check if any duplicates exist in production:

```sql
-- Check user_roles for duplicates
SELECT user_id, role_id, workspace_id, COUNT(*) as cnt
FROM user_roles
GROUP BY user_id, role_id, workspace_id
HAVING COUNT(*) > 1;

-- Check role_permissions for duplicates
SELECT role_id, permission_id, COUNT(*) as cnt
FROM role_permissions
GROUP BY role_id, permission_id
HAVING COUNT(*) > 1;

-- Check workspace_members for duplicates
SELECT user_id, workspace_id, COUNT(*) as cnt
FROM workspace_members
GROUP BY user_id, workspace_id
HAVING COUNT(*) > 1;

-- Check content_media for duplicates
SELECT content_id, media_id, COUNT(*) as cnt
FROM content_media
GROUP BY content_id, media_id
HAVING COUNT(*) > 1;
```

If duplicates exist, remove them before applying the migration:

```sql
-- Example: Remove duplicate user_roles, keeping the oldest
DELETE FROM user_roles a USING user_roles b
WHERE a.id > b.id
  AND a.user_id = b.user_id
  AND a.role_id = b.role_id
  AND COALESCE(a.workspace_id, '00000000-0000-0000-0000-000000000000') = COALESCE(b.workspace_id, '00000000-0000-0000-0000-000000000000');
```

### Step 2: Update user_roles.py

```python
# File: src/api/models/user_models/user_roles.py
# Add import at the top:
from sqlalchemy import Column, String, Boolean, Integer, Text, TIMESTAMP, ForeignKey, UniqueConstraint

# Add __table_args__ inside the class, after the column definitions:
class UserRole(Base, SerializableMixin):
    __tablename__ = "user_roles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    role_id = Column(UUID(as_uuid=True), ForeignKey("roles.id"), nullable=False)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspace.id"), nullable=True)
    assigned_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    is_primary = Column(Boolean, default=True)
    assigned_at = Column(TIMESTAMP, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint('user_id', 'role_id', 'workspace_id', name='uq_user_role_workspace'),
    )

    # Relationships...
```

### Step 3: Update role_permissions.py

```python
# File: src/api/models/user_models/role_permissions.py
# Add import at the top:
from sqlalchemy import Column, String, Boolean, TIMESTAMP, ForeignKey, UniqueConstraint

# Add __table_args__ inside the class:
class RolePermission(Base, SerializableMixin):
    __tablename__ = "role_permissions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False)
    role_id = Column(UUID(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), nullable=False)
    permission_id = Column(UUID(as_uuid=True), ForeignKey("permissions.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(TIMESTAMP, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint('role_id', 'permission_id', name='uq_role_permission'),
    )

    # Relationships...
```

### Step 4: Update workspace_member.py

```python
# File: src/api/models/workspace_models/workspace_member.py
# Add import at the top:
from sqlalchemy import Column, String, Boolean, TIMESTAMP, ForeignKey, UniqueConstraint

# Add __table_args__ inside the class:
class WorkspaceMembers(Base, SerializableMixin):
    __tablename__ = "workspace_members"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspace.id"), nullable=False)
    invitation_id = Column(UUID(as_uuid=True), ForeignKey("user_invitations.id"), nullable=True)
    status = Column(String(50), default="pending")
    is_default = Column(Boolean, default=False)
    joined_at = Column(TIMESTAMP, default=datetime.utcnow, nullable=False)
    last_activity_at = Column(TIMESTAMP, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('user_id', 'workspace_id', name='uq_user_workspace'),
    )

    # Relationships...
```

### Step 5: Update content_media.py

```python
# File: src/api/models/content_models/content_media.py
# Add import at the top:
from sqlalchemy import Column, String, Integer, ForeignKey, TIMESTAMP, UniqueConstraint

# Add __table_args__ inside the class:
class ContentMedia(Base, SerializableMixin):
    __tablename__ = "content_media"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, nullable=False)
    content_id = Column(UUID(as_uuid=True), ForeignKey("content.id", ondelete="CASCADE"), nullable=False, index=True)
    media_id = Column(UUID(as_uuid=True), ForeignKey("media.id", ondelete="CASCADE"), nullable=False, index=True)
    usage_type = Column(String(50), nullable=True)
    position = Column(Integer, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint('content_id', 'media_id', name='uq_content_media'),
    )

    # Relationships...
```

### Step 6: Generate and Apply Migration

```bash
cd rext-backend
alembic revision --autogenerate -m "add_unique_constraints_to_join_tables"
alembic upgrade head
```

### Step 7: Update Application Code to Handle Constraint Violations

Add proper error handling for duplicate insertions:

```python
# Example in a service that assigns roles:
from sqlalchemy.exc import IntegrityError

async def assign_role_to_user(self, user_id: UUID, role_id: UUID, workspace_id: UUID, db: AsyncSession):
    try:
        user_role = UserRole(user_id=user_id, role_id=role_id, workspace_id=workspace_id)
        db.add(user_role)
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        if "uq_user_role_workspace" in str(e.orig):
            raise DuplicateRoleAssignmentError(f"User already has this role in the workspace")
        raise
```

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `src/services/permission_service.py` | Various | Role assignment logic - may need error handling for duplicates |
| `src/services/workspace_service.py` | Various | Member management - may need error handling for duplicates |
| `src/api/routes/roles/roles.py` | Various | Role assignment endpoints - may need 409 Conflict responses |
| `src/api/routes/workspaces/workspace_members.py` | Various | Member endpoints - may need 409 Conflict responses |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Connect to the database and insert a duplicate role assignment:
   ```sql
   -- First, find an existing user_role
   SELECT * FROM user_roles LIMIT 1;

   -- Insert a duplicate (using the same user_id, role_id, workspace_id)
   INSERT INTO user_roles (id, user_id, role_id, workspace_id, is_primary, assigned_at)
   VALUES (gen_random_uuid(), '<user_id>', '<role_id>', '<workspace_id>', false, NOW());
   ```
2. **Expected:** Insert succeeds, creating a duplicate record
3. Query to verify:
   ```sql
   SELECT * FROM user_roles WHERE user_id = '<user_id>' AND role_id = '<role_id>';
   -- Returns 2 rows
   ```

### After Fix (Verify the Solution):
1. Apply the migration: `alembic upgrade head`
2. Attempt to insert a duplicate:
   ```sql
   INSERT INTO user_roles (id, user_id, role_id, workspace_id, is_primary, assigned_at)
   VALUES (gen_random_uuid(), '<user_id>', '<role_id>', '<workspace_id>', false, NOW());
   ```
3. **Expected:** PostgreSQL error: `duplicate key value violates unique constraint "uq_user_role_workspace"`
4. Verify constraint exists:
   ```sql
   SELECT conname FROM pg_constraint WHERE conrelid = 'user_roles'::regclass;
   -- Should show 'uq_user_role_workspace'
   ```

### Run Existing Tests:
```bash
cd rext-backend
pytest tests/ -v -k "role" --tb=short
pytest tests/ -v -k "permission" --tb=short
pytest tests/ -v -k "workspace" --tb=short
pytest tests/ -v -k "media" --tb=short
```

---

## Acceptance Criteria

- [ ] `user_roles` has unique constraint on `(user_id, role_id, workspace_id)`
- [ ] `role_permissions` has unique constraint on `(role_id, permission_id)`
- [ ] `workspace_members` has unique constraint on `(user_id, workspace_id)`
- [ ] `content_media` has unique constraint on `(content_id, media_id)`
- [ ] Any existing duplicate records have been cleaned up before migration
- [ ] Alembic migration generated and applies successfully
- [ ] Duplicate insertions are rejected with constraint violation error
- [ ] Application code handles IntegrityError appropriately (optional but recommended)
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass

---

## References & Resources

- **Official Docs:** [SQLAlchemy 2.1 - Defining Constraints and Indexes](https://docs.sqlalchemy.org/en/21/core/constraints.html) - UniqueConstraint documentation
- **Security Advisory:** N/A (data integrity issue, not security)
- **Migration Guide:** N/A
- **Best Practice Reference:** [SQLAlchemy Unique Constraint on Multiple Columns Guide](https://copyprogramming.com/howto/unique-constraint-on-multiple-columns-in-sqlalchemy) - Comprehensive examples
- **Related Issues/PRs:** [SQLAlchemy Discussion #10464](https://github.com/sqlalchemy/sqlalchemy/discussions/10464) - Naming conventions for composite constraints

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-032 (Missing ondelete specifications - same files affected), TASK-035 (TokenBlacklist missing FK - related to data integrity)

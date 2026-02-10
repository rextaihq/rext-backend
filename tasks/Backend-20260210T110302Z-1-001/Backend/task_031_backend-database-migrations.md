# Task 031: Add Missing Database Indexes to 30+ Foreign Key Columns

## Metadata
- **Task ID:** TASK-031
- **Source:** Database & Migrations Audit (Finding #5 under P1 High)
- **Audit Report:** `audit-reports/backend-database-migrations.md`
- **Priority:** P1 High
- **Category:** performance
- **Effort Estimate:** large (4+ hours)

---

## Description

PostgreSQL does **NOT** automatically create indexes on foreign key columns (unlike MySQL InnoDB which creates indexes automatically). Without explicit indexes, JOIN queries and WHERE clauses filtering on FK columns result in sequential table scans.

The Rext AI backend has over 30 foreign key columns across 15+ model files that are missing the `index=True` parameter. This affects critical queries like:
- "Get all roles for a user" (`WHERE user_id = ?` on `user_roles`)
- "Get all content for a workspace" (`WHERE workspace_id = ?` on content/knowledge models)
- "Get workspace members" (JOIN on `workspace_member.user_id` and `workspace_member.workspace_id`)

As these tables grow, query performance will degrade proportionally. A table with 100,000 rows will require scanning all 100,000 rows for every query on an unindexed FK column.

---

## Current Code - Affected FK Columns

### Priority 1: High-Traffic Join Tables (Fix First)

| File | Line | Column | Table |
|------|------|--------|-------|
| `user_models/user_roles.py` | 17 | `user_id` | `user_roles` |
| `user_models/user_roles.py` | 18 | `role_id` | `user_roles` |
| `user_models/user_roles.py` | 19 | `workspace_id` | `user_roles` |
| `user_models/user_roles.py` | 20 | `assigned_by_user_id` | `user_roles` |
| `user_models/role_permissions.py` | 15 | `role_id` | `role_permissions` |
| `user_models/role_permissions.py` | 16 | `permission_id` | `role_permissions` |
| `workspace_models/workspace_member.py` | 16 | `user_id` | `workspace_members` |
| `workspace_models/workspace_member.py` | 17 | `workspace_id` | `workspace_members` |
| `workspace_models/workspace_member.py` | 18 | `invitation_id` | `workspace_members` |

### Priority 2: Workspace-Scoped Models

| File | Line | Column | Table |
|------|------|--------|-------|
| `workspace_models/workspace_model.py` | 16 | `user_id` | `workspace` |
| `workspace_models/workspace_model.py` | 24 | `deleted_by` | `workspace` |
| `workspace_models/email_template.py` | 30 | `workspace_id` | `email_templates` |
| `workspace_models/email_template.py` | 40 | `created_by_user_id` | `email_templates` |
| `knowledge_models/knowledge_model.py` | 18 | `workspace_id` | `knowledge_base` |
| `knowledge_models/knowledge_model.py` | 76 | `workspace_id` | `brand_voices` |
| `knowledge_models/knowledge_model.py` | 95 | `workspace_id` | `websites` |
| `knowledge_models/knowledge_model.py` | 96 | `knowledge_base_id` | `websites` |
| `knowledge_models/knowledge_model.py` | 123 | `workspace_id` | `knowledge_files` |
| `knowledge_models/knowledge_model.py` | 124 | `knowledge_base_id` | `knowledge_files` |
| `knowledge_models/knowledge_model.py` | 169 | `workspace_id` | `text_knowledge` |
| `knowledge_models/knowledge_model.py` | 170 | `knowledge_base_id` | `text_knowledge` |
| `knowledge_models/persona_model.py` | 15 | `workspace_id` | `personas` |
| `knowledge_models/embedding_model.py` | 62 | `workspace_id` | `embeddings` |
| `knowledge_models/embedding_model.py` | 68 | `knowledge_base_id` | `embeddings` |

### Priority 3: Subscription & Billing

| File | Line | Column | Table |
|------|------|--------|-------|
| `subscription_models/subscriptions.py` | 35 | `user_id` | `user_subscriptions` |
| `subscription_models/subscriptions.py` | 36 | `plan_id` | `user_subscriptions` |
| `subscription_models/refunds.py` | 63 | `user_id` | `refunds` |
| `subscription_models/refunds.py` | 69 | `subscription_id` | `refunds` |
| `subscription_models/trial_conversions.py` | 33 | `user_id` | `trial_conversions` |
| `subscription_models/trial_conversions.py` | 39 | `subscription_id` | `trial_conversions` |
| `subscription_models/trial_conversions.py` | 71 | `plan_id` | `trial_conversions` |

### Priority 4: User & Invitation Tables

| File | Line | Column | Table |
|------|------|--------|-------|
| `user_models/invitations.py` | 13 | `workspace_id` | `user_invitations` |
| `user_models/invitations.py` | 14 | `role_id` | `user_invitations` |
| `user_models/invitations.py` | 15 | `invited_by_user_id` | `user_invitations` |

### Priority 5: Admin & Audit Tables

| File | Line | Column | Table |
|------|------|--------|-------|
| `audit_models/audit_logs.py` | 17 | `user_id` | `audit_logs` |
| `audit_models/audit_logs.py` | 27 | `workspace_id` | `audit_logs` |
| `admin_models/error_log.py` | 28 | `user_id` | `error_logs` |
| `admin_models/error_log.py` | 38 | `resolved_by` | `error_logs` |
| `admin_models/customer_note.py` | 24 | `user_id` | `customer_notes` |
| `admin_models/customer_note.py` | 30 | `admin_id` | `customer_notes` |

### Priority 6: Notification & Content Media

| File | Line | Column | Table |
|------|------|--------|-------|
| `notification/notification_model.py` | 50 | `user_id` | `notifications` |
| `notification/notification_model.py` | 57 | `workspace_id` | `notifications` |
| `content_models/content_media.py` | 34 | `content_id` | `content_media` |
| `content_models/content_media.py` | 41 | `media_id` | `content_media` |

---

## Why This Matters (Context & Reasoning)

PostgreSQL requires explicit indexes on FK columns for performant queries. Without them:

1. **JOIN Performance:** Every JOIN on an unindexed FK requires a sequential scan of the entire table
2. **WHERE Clause Performance:** Filtering by FK (e.g., "get all content for workspace X") scans the entire table
3. **Cascade Delete Performance:** When deleting a parent record, PostgreSQL must find all child records - without an index, this scans the entire child table

**Example Impact:**
- `user_roles` table with 100,000 rows
- Query: `SELECT * FROM user_roles WHERE user_id = 'abc-123'`
- Without index: Scan 100,000 rows (~100ms)
- With index: B-tree lookup (~1ms)

The affected tables include high-traffic join tables (`user_roles`, `role_permissions`, `workspace_member`) that are queried on virtually every authenticated request.

---

## Impact

- **Severity:** Progressively degrading query performance. At scale, queries on unindexed FK columns will add 100ms+ latency per request.
- **Affected Users/Flows:** Every authenticated API request (permission checks hit `user_roles`/`role_permissions`), every workspace operation, every content listing.
- **Blast Radius:** Platform-wide. All users are affected as tables grow.

---

## Recommended Solution

### Approach: Batch All Index Additions in One Migration

Rather than modifying 15+ model files individually, the most efficient approach is:

1. Add `index=True` to each FK column definition in the model files
2. Generate a single Alembic migration that creates all indexes

### Step 1: Update Model Files

For each file listed above, add `index=True` to the FK column definition:

**Example - user_roles.py:**
```python
# File: rext-backend/src/api/models/user_models/user_roles.py
# Change from:
user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
role_id = Column(UUID(as_uuid=True), ForeignKey("roles.id"), nullable=False)
workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspace.id"), nullable=True)
assigned_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

# Change to:
user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
role_id = Column(UUID(as_uuid=True), ForeignKey("roles.id"), nullable=False, index=True)
workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspace.id"), nullable=True, index=True)
assigned_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)
```

**Repeat for all files listed in "Affected FK Columns" section above.**

### Step 2: Generate Migration

```bash
cd rext-backend
alembic revision --autogenerate -m "add_missing_fk_indexes"
```

### Step 3: Review Generated Migration

The migration should contain ~35 `create_index` operations:

```python
def upgrade() -> None:
    # Priority 1: Join tables
    op.create_index('ix_user_roles_user_id', 'user_roles', ['user_id'])
    op.create_index('ix_user_roles_role_id', 'user_roles', ['role_id'])
    op.create_index('ix_user_roles_workspace_id', 'user_roles', ['workspace_id'])
    op.create_index('ix_user_roles_assigned_by_user_id', 'user_roles', ['assigned_by_user_id'])
    op.create_index('ix_role_permissions_role_id', 'role_permissions', ['role_id'])
    op.create_index('ix_role_permissions_permission_id', 'role_permissions', ['permission_id'])
    op.create_index('ix_workspace_members_user_id', 'workspace_members', ['user_id'])
    op.create_index('ix_workspace_members_workspace_id', 'workspace_members', ['workspace_id'])
    op.create_index('ix_workspace_members_invitation_id', 'workspace_members', ['invitation_id'])
    # ... (continue for all columns)


def downgrade() -> None:
    # Drop all indexes in reverse order
    op.drop_index('ix_workspace_members_invitation_id', 'workspace_members')
    # ... (continue for all indexes)
```

### Step 4: Run Migration with Monitoring

For production, run the migration during low-traffic periods:

```bash
# With timing output
time alembic upgrade head
```

**Note:** Creating indexes on large tables can take significant time and may lock the table briefly. For tables with millions of rows, consider using `CREATE INDEX CONCURRENTLY` (requires manual migration editing):

```python
# For very large tables, modify the migration to use CONCURRENTLY:
op.execute('CREATE INDEX CONCURRENTLY ix_audit_logs_user_id ON audit_logs (user_id)')
```

### Step 5: Verify Indexes

```sql
SELECT
    t.relname as table_name,
    i.relname as index_name,
    a.attname as column_name
FROM
    pg_class t,
    pg_class i,
    pg_index ix,
    pg_attribute a
WHERE
    t.oid = ix.indrelid
    AND i.oid = ix.indexrelid
    AND a.attrelid = t.oid
    AND a.attnum = ANY(ix.indkey)
    AND t.relkind = 'r'
    AND t.relname IN ('user_roles', 'role_permissions', 'workspace_members')
ORDER BY t.relname, i.relname;
```

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| All files in Priority 1-6 tables above | Various | FK columns to add `index=True` |

---

## Testing Instructions

### Before Fix (Measure Query Performance):
```sql
-- Enable timing
\timing on

-- Test query on unindexed FK (should be slow on large tables)
EXPLAIN ANALYZE SELECT * FROM user_roles WHERE user_id = (SELECT id FROM users LIMIT 1);
```

Note the "Seq Scan" in the EXPLAIN output - this indicates a full table scan.

### After Fix (Verify Index Usage):
```sql
-- Same query should now use index
EXPLAIN ANALYZE SELECT * FROM user_roles WHERE user_id = (SELECT id FROM users LIMIT 1);
```

Look for "Index Scan" instead of "Seq Scan" in the output.

### Run Existing Tests:
```bash
cd rext-backend
pytest tests/ -v
```

---

## Acceptance Criteria

- [ ] All 35+ FK columns have `index=True` added to their column definitions
- [ ] Alembic migration generated with all index creations
- [ ] Migration runs successfully without errors
- [ ] `EXPLAIN ANALYZE` shows Index Scan (not Seq Scan) for FK column queries
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Query performance improved (measurable with timing)

---

## References & Resources

- **Official Docs:** [PostgreSQL - Indexes and Foreign Keys](https://www.postgresql.org/docs/current/indexes-fk.html) - Explains why FK indexes are NOT automatic in PostgreSQL
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** [PostgreSQL Performance - Index Types](https://www.postgresql.org/docs/current/indexes-types.html) - B-tree index documentation

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-032 (B2 Finding 6 - ondelete specifications) - should be done together with FK indexes, TASK-027/028 (composite indexes for license_activations/discount_usage)

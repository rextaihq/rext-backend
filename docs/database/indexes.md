# Database Index Strategy

## Overview

This document outlines the indexing strategy for the WREXT backend database to optimize query performance.

## Index Types

### 1. Single Column Indexes

Used for queries that filter or sort by a single column.

| Index Name | Table | Column(s) | Purpose | Created In |
|------------|-------|-----------|---------|------------|
| `ix_users_status` | users | status | Filter active/inactive users | Migration 4903202d53ae |
| `ix_content_status` | content | status | Filter content by status | Pre-existing |
| `ix_content_created_at` | content | created_at | Sort content by date | Migration 4903202d53ae |
| `ix_audit_logs_created_at` | audit_logs | created_at | Cleanup jobs & time queries | Migration 2cc855f144c1 |
| `idx_email_logs_status` | email_logs | status | Email status tracking | Pre-existing |
| `idx_email_logs_created_at` | email_logs | created_at | Email log queries | Pre-existing |

### 2. Composite Indexes

Used for queries that filter on multiple columns. The column order matters - put the most selective column first.

| Index Name | Table | Column(s) | Purpose | Query Pattern |
|------------|-------|-----------|---------|---------------|
| `ix_content_workspace_status` | content | workspace_id, status | Dashboard content queries | `WHERE workspace_id = X AND status = 'published'` |
| `ix_content_workspace_created_at` | content | workspace_id, created_at | Recent content by workspace | `WHERE workspace_id = X ORDER BY created_at DESC` |
| `ix_user_roles_user_workspace` | user_roles | user_id, workspace_id | RBAC permission checks | `WHERE user_id = X AND workspace_id = Y` |
| `ix_user_roles_workspace_role` | user_roles | workspace_id, role_id | Workspace member queries | `WHERE workspace_id = X AND role_id = Y` |

## Index Usage Guidelines

### When to Create an Index

✅ **DO create indexes for:**
- Foreign key columns (user_id, workspace_id, etc.)
- Columns frequently used in WHERE clauses
- Columns frequently used in ORDER BY
- Columns used in JOIN conditions
- Status/enum columns with selective filtering

❌ **DON'T create indexes for:**
- Columns with very low cardinality (< 5 distinct values) unless queries are very selective
- Columns rarely used in queries
- Small tables (< 1000 rows) - sequential scans are often faster
- Columns that change frequently (high write overhead)

### Composite Index Column Order

When creating composite indexes, column order matters:

1. **Most selective column first** - The column that filters out the most rows
2. **Equality before range** - Put `=` conditions before `>`, `<`, `BETWEEN`
3. **Support leftmost prefix** - Index on `(a, b, c)` can be used for queries on:
   - `WHERE a = X`
   - `WHERE a = X AND b = Y`
   - `WHERE a = X AND b = Y AND c = Z`
   - But NOT for `WHERE b = Y` or `WHERE c = Z` alone

**Example:**
```sql
-- Good: workspace_id is very selective (filters to one workspace)
CREATE INDEX ON content (workspace_id, status);

-- Query can use this index:
SELECT * FROM content WHERE workspace_id = 'ws-123' AND status = 'published';

-- Query can also use this index (leftmost prefix):
SELECT * FROM content WHERE workspace_id = 'ws-123';
```

## Testing Indexes

### Verify Index Usage

Use `EXPLAIN` or `EXPLAIN ANALYZE` to verify indexes are being used:

```sql
-- Check if index is used
EXPLAIN SELECT * FROM content WHERE workspace_id = 'ws-123' AND status = 'published';

-- See actual execution time
EXPLAIN ANALYZE SELECT * FROM content WHERE workspace_id = 'ws-123' AND status = 'published';
```

**Look for:**
- ✅ `Index Scan using ix_content_workspace_status` - Index is being used
- ⚠️ `Seq Scan on content` - Sequential scan (no index used)

### Test Script

Run the index test script:

```bash
.venv/bin/python3 scripts/test_indexes.py
```

This will verify all indexes exist and show which queries use them.

## Performance Impact

### Benefits
- **Query Speed:** 10-1000x faster for large tables
- **Reduced I/O:** Only read relevant rows
- **Scalability:** Performance stays consistent as data grows

### Costs
- **Disk Space:** ~10-20% additional storage
- **Write Performance:** Slight overhead on INSERT/UPDATE/DELETE
- **Maintenance:** Indexes need occasional reindexing (VACUUM)

## Monitoring Index Usage

### Check Unused Indexes

```sql
-- Find indexes that are never used
SELECT
    schemaname,
    tablename,
    indexname,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch
FROM pg_stat_user_indexes
WHERE idx_scan = 0
AND indexname NOT LIKE 'pg_%'
ORDER BY tablename, indexname;
```

### Check Index Size

```sql
-- See how much space indexes consume
SELECT
    tablename,
    indexname,
    pg_size_pretty(pg_relation_size(indexrelid)) AS index_size
FROM pg_stat_user_indexes
ORDER BY pg_relation_size(indexrelid) DESC;
```

### Check Missing Indexes

```sql
-- Find tables with sequential scans that might need indexes
SELECT
    schemaname,
    tablename,
    seq_scan,
    seq_tup_read,
    idx_scan,
    idx_tup_fetch,
    seq_tup_read / NULLIF(seq_scan, 0) AS avg_seq_tup
FROM pg_stat_user_tables
WHERE seq_scan > 0
ORDER BY seq_tup_read DESC
LIMIT 20;
```

## Maintenance

### Reindexing

Indexes can become bloated over time. Reindex periodically:

```sql
-- Reindex a specific index
REINDEX INDEX ix_content_workspace_status;

-- Reindex all indexes on a table
REINDEX TABLE content;

-- Reindex entire database (during maintenance window)
REINDEX DATABASE wrext;
```

### Vacuum

Run VACUUM to reclaim space and update statistics:

```sql
-- Analyze table statistics (helps query planner)
ANALYZE content;

-- Vacuum and analyze (recommended for regular maintenance)
VACUUM ANALYZE content;
```

## Migration History

| Migration | Date | Indexes Added | Purpose |
|-----------|------|---------------|---------|
| 2cc855f144c1 | Earlier | ix_audit_logs_created_at | Audit log queries |
| 4903202d53ae | 2025-10-16 | 6 new indexes | Performance optimization (Task 4.2) |

## Future Considerations

### Potential Additional Indexes

These may be added in the future if query patterns warrant them:

- `email_logs (user_id, created_at)` - User email history
- `content (author_id, created_at)` - Author's content timeline
- `workspace (owner_id, deleted_at)` - Active workspaces by owner

### Partial Indexes

For very selective queries, consider partial indexes:

```sql
-- Index only published content (saves space)
CREATE INDEX ix_content_published
ON content (workspace_id, created_at)
WHERE status = 'published';
```

### GIN/GiST Indexes

For full-text search and JSON queries:

```sql
-- Full-text search on content title
CREATE INDEX ix_content_title_search
ON content USING GIN (to_tsvector('english', title));

-- JSONB column indexing
CREATE INDEX ix_content_metadata
ON content USING GIN (metadata_json);
```

## References

- [PostgreSQL Index Documentation](https://www.postgresql.org/docs/current/indexes.html)
- [Use The Index, Luke](https://use-the-index-luke.com/) - SQL Indexing Guide
- [PostgreSQL Wiki: Index Maintenance](https://wiki.postgresql.org/wiki/Index_Maintenance)

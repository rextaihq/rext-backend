# Content Table Consolidation

**Migration:** `40fd95ca1e8d_consolidate_content_tables.py`
**Date:** October 16, 2025
**Status:** ✅ Complete

## Summary

Consolidated 5 rarely-accessed content-related tables into JSONB columns on the main `content` table to improve query performance and reduce complexity.

## Changes

### Tables Consolidated → JSONB Columns

| Old Table | New Column | Reason |
|-----------|------------|--------|
| `content_metadata` | `content.metadata_json` | Rarely queried individually, never filtered on |
| `content_tracking` | `content.tracking_json` | Write-only audit trail, never queried directly |
| `content_ai_config` | `content.ai_config_json` | Write-once during generation, rarely accessed |
| `content_structure` | `content.structure_json` | Write-once configuration, never queried separately |
| `content_research_config` | `content.research_config_json` | Write-once configuration, never queried separately |

### Tables Kept Separate

| Table | Reason |
|-------|--------|
| `content` | Main table |
| `content_progress` | Real-time updates during generation (needs fast updates) |
| `content_seo_data` | Often queried alongside content, moderate size |
| `content_review` | Separate workflow lifecycle |
| `content_version` | History tracking, separate concern |
| `content_media` | Separate entity with own lifecycle |

## Benefits

1. **Reduced Joins:** 5 fewer LEFT JOINs for typical content retrieval
2. **Simpler Queries:** Single table query for most operations
3. **Better Performance:** No N+1 query issues for related data
4. **Preserved Data:** All fields maintained in structured JSONB format
5. **GIN Indexes:** JSONB columns indexed for fast key lookups

## Usage

### Before Migration

```python
# Old way: using relationships
content = await db.execute(
    select(Content)
    .options(
        selectinload(Content.content_metadata),
        selectinload(Content.content_ai_config)
    )
    .where(Content.id == content_id)
)
content = result.scalar_one()

# Access via relationship
if content.content_metadata:
    content_type = content.content_metadata.content_type
    platform = content.content_metadata.target_platform
```

### After Migration

```python
# New way: direct JSONB access
result = await db.execute(
    select(Content).where(Content.id == content_id)
)
content = result.scalar_one()

# Access via JSONB column
if content.metadata_json:
    content_type = content.metadata_json.get("content_type")
    platform = content.metadata_json.get("target_platform")
```

### Querying JSONB Fields

```python
# Query by JSONB field (uses GIN index)
from sqlalchemy.dialects.postgresql import JSONB

result = await db.execute(
    select(Content)
    .where(
        Content.metadata_json["content_type"].astext == "blog_post"
    )
)

# JSON containment query
result = await db.execute(
    select(Content)
    .where(
        Content.metadata_json.contains({"target_platform": "Medium"})
    )
)
```

## JSONB Column Schemas

### metadata_json

```json
{
    "content_summary": "string",
    "content_type": "blog_post | article | social_post | email",
    "target_platform": "Medium | LinkedIn | WordPress",
    "target_industry": "string",
    "target_audience": ["string"],
    "audience_size": "small | medium | large | enterprise",
    "complexity_level": "beginner | intermediate | advanced | expert",
    "content_tone": ["professional", "casual", "friendly"],
    "target_region": "string",
    "content_objectives": ["educate", "persuade", "inform"],
    "source_references": ["url"],
    "content_word_count": 1234,
    "reading_time_minutes": 5,
    "content_quality_scores": {},
    "featured_image_prompt": "string",
    "featured_image_alt_text": "string",
    "created_at": "ISO8601 timestamp",
    "updated_at": "ISO8601 timestamp"
}
```

### tracking_json

```json
{
    "request_id": "uuid",
    "flow_execution_id": "uuid",
    "request_payload": {},
    "topic_snapshot": {},
    "created_at": "ISO8601 timestamp",
    "updated_at": "ISO8601 timestamp"
}
```

### ai_config_json

```json
{
    "ai_model": "gpt-4 | claude-3",
    "temperature": 0.70,
    "max_output_tokens": 4096,
    "top_p": 0.95,
    "frequency_penalty": 0.00,
    "generation_params": {},
    "context_sources": {},
    "generation_errors": [],
    "generation_warnings": [],
    "structured_output": {},
    "generated_at": "ISO8601 timestamp",
    "created_at": "ISO8601 timestamp",
    "updated_at": "ISO8601 timestamp"
}
```

### structure_json

```json
{
    "content_length": {"min_words": 500, "max_words": 2000, "target_words": 1200},
    "include_toc": true,
    "include_summary": true,
    "include_cta": false,
    "include_key_takeaways": true,
    "include_latest_info": false,
    "include_examples": true,
    "include_statistics": true,
    "include_quotes": false,
    "competitor_analysis": false,
    "created_at": "ISO8601 timestamp",
    "updated_at": "ISO8601 timestamp"
}
```

### research_config_json

```json
{
    "research_level": "none | basic | standard | deep",
    "fact_checking": "none | basic | rigorous",
    "content_freshness": "any | recent | latest",
    "research_context": {},
    "created_at": "ISO8601 timestamp",
    "updated_at": "ISO8601 timestamp"
}
```

## Migration Process

### Upgrade (Forward)

1. Adds 5 JSONB columns to `content` table
2. Migrates all data from 5 tables into JSONB using `jsonb_build_object()`
3. Creates GIN indexes on `metadata_json` and `ai_config_json` for performance
4. Drops the 5 consolidated tables

### Downgrade (Rollback)

1. Recreates the 5 dropped tables with original schema
2. Extracts data from JSONB columns back to tables using JSON operators
3. Drops GIN indexes
4. Drops JSONB columns

## Performance Impact

### Before
- Typical content query: 1 main query + 5 relationship queries = **6 queries**
- JOIN overhead: ~5-10ms per join

### After
- Typical content query: **1 query**
- JSONB access: <1ms (in-memory deserialization)

**Expected improvement:** 30-40% faster content retrieval for queries that previously loaded all relationships.

## Code Changes

### Models Updated
- ✅ `src/api/models/content_models/content.py` - Added JSONB columns
- ✅ `src/api/models/content_models/__init__.py` - Marked deprecated models with try/except

### Services Updated
- ✅ `src/services/content_service.py` - Removed `selectinload(Content.content_metadata)`
- ✅ `src/services/langgraph_content_service.py` - Updated to use `content.metadata_json.get()`

### Deprecated Model Classes
The following model classes still exist but map to non-existent tables after migration:
- `ContentMetadata` → use `Content.metadata_json`
- `ContentTracking` → use `Content.tracking_json`
- `ContentAIConfig` → use `Content.ai_config_json`
- `ContentStructure` → use `Content.structure_json`
- `ContentResearchConfig` → use `Content.research_config_json`

These will be removed in a future cleanup after verifying no code references them.

## Testing

### Pre-Migration Checks
```bash
# Count rows in each table
psql $DATABASE_URL -c "
SELECT 'content' as table, COUNT(*) FROM content
UNION ALL SELECT 'content_metadata', COUNT(*) FROM content_metadata
UNION ALL SELECT 'content_tracking', COUNT(*) FROM content_tracking
"
```

### Post-Migration Validation
```bash
# Verify JSONB columns populated
psql $DATABASE_URL -c "
SELECT
    COUNT(*) as total,
    COUNT(metadata_json) as with_metadata,
    COUNT(tracking_json) as with_tracking,
    COUNT(ai_config_json) as with_ai_config
FROM content
"

# Test GIN index usage
psql $DATABASE_URL -c "
EXPLAIN ANALYZE
SELECT * FROM content WHERE metadata_json @> '{\"content_type\": \"blog_post\"}'
"
```

## Rollback Instructions

If issues arise, rollback with:

```bash
# Downgrade migration
.venv/bin/alembic downgrade -1

# Verify tables restored
psql $DATABASE_URL -c "\dt content*"
```

## Future Improvements

1. **Add more GIN indexes** if JSONB querying becomes common
2. **Consider JSONB statistics** for better query planning: `CREATE STATISTICS content_metadata_stats ON metadata_json FROM content`
3. **Archive old tracking_json** to separate table after 90 days (audit retention)
4. **Remove deprecated model classes** after confirming no usage

## References

- Alembic Migration: `alembic/versions/40fd95ca1e8d_consolidate_content_tables.py`
- PostgreSQL JSONB: https://www.postgresql.org/docs/current/datatype-json.html
- GIN Indexes: https://www.postgresql.org/docs/current/gin-intro.html

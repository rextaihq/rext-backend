# Task 176: Fix `content.published_at` Reference to Use Correct Field Name `wordpress_published_at`

## Metadata
- **Task ID:** TASK-176
- **Source:** Backend Content Management Audit (Finding #30 under P2 Medium)
- **Audit Report:** `audit-reports/backend-content-management.md`
- **Priority:** P2 Medium
- **Category:** bug
- **Effort Estimate:** small (< 1 hour)

---

## Description

In `src/api/routes/content/modules/sites.py` at line 292, the code references `content.published_at` to record when content was published to WordPress. However, the `Content` model in `src/api/models/content_models/content.py` does not have a `published_at` column. The correct field name is `wordpress_published_at` (defined at line 41 of the model file).

The migration history confirms this: migration `41596bee276b_add_content_workflow_tracking_fields` originally added a `published_at` column to the content table, but a later migration `c9e6ed3c63fa_add_workspace_integrations_and_simplify_` explicitly dropped `published_at` (line 80) and added `wordpress_published_at` (line 61) as a replacement. This rename was done to distinguish general publication status from WordPress-specific publication.

The same `publish_to_site()` function in `sites.py` also has a secondary issue on lines 282-288: it calls `wp_publisher.publish_post()` with positional keyword arguments (`title=content.title`, `content=...`, `status=data.status`, `excerpt=...`, `tags=...`) that don't match the method's signature. The `publish_post()` method in `wordpress_publisher.py` expects `data: ContentCreate` as its first positional argument. However, that's a separate finding (covered by the function signature issue). This task focuses only on the `published_at` field name bug.

Other files in the codebase correctly use `wordpress_published_at`:
- `publish_content.py:204` — `content.wordpress_published_at = datetime.now(timezone.utc)` (correct)
- `publish_content.py:284` — `content.wordpress_published_at = datetime.now(timezone.utc)` (correct)
- `content_schema.py:89` — `wordpress_published_at: Optional[datetime] = None` (correct)
- `content_schema.py:123` — `wordpress_published_at: Optional[datetime] = None` (correct)

Only `sites.py:292` uses the incorrect `published_at` name.

At runtime, assigning `content.published_at = datetime.now(timezone.utc)` does not raise an `AttributeError` in SQLAlchemy — it simply creates a transient Python attribute on the instance that is NOT mapped to any database column. This means the assignment silently succeeds but the value is never persisted to the database. The content's `wordpress_published_at` column remains NULL even after successful WordPress publishing via the site-specific publish endpoint.

---

## Current Code

```python
# File: rext-backend/src/api/routes/content/modules/sites.py
# Lines: 290-292

            # Update content status
            content.status = "published"
            content.published_at = datetime.now(timezone.utc)  # BUG: wrong field name
```

```python
# File: rext-backend/src/api/models/content_models/content.py
# Line 41 — the correct field name

    wordpress_published_at = Column(DateTime(timezone=True), nullable=True)
```

For reference, here is the correct usage in another file:

```python
# File: rext-backend/src/api/routes/content/modules/publish_content.py
# Line 204 — correct field name

        content.wordpress_published_at = datetime.now(timezone.utc)
```

---

## Why This Matters (Context & Reasoning)

The `publish_to_site` endpoint in `sites.py` is the route that publishes a specific content item to a specific connected WordPress site. When a user publishes content to WordPress via this endpoint, the content's `wordpress_published_at` timestamp should be recorded. This timestamp is used to:

1. Display when content was last published to WordPress in the frontend UI.
2. Determine if content has been published or needs republishing after edits.
3. Order content by publication date in the content management dashboard.

Because the code uses the wrong field name (`published_at` instead of `wordpress_published_at`), the timestamp is silently lost. The content shows as published (status = "published") but has no publication timestamp. This creates a data integrity issue where the system knows content was published but doesn't know when.

This is also a subtle bug because SQLAlchemy does not raise an error — it silently creates a non-mapped attribute. This makes the bug particularly dangerous because it passes all unit tests that don't specifically check the database state after publishing.

---

## Impact

- **Severity:** Content published via the site-specific publish endpoint (`POST /sites/{site_id}/publish/{content_id}`) has NULL `wordpress_published_at` in the database. The publication timestamp is silently lost.
- **Affected Users/Flows:** Users who publish content to a specific WordPress site via the sites management endpoint. The multi-site publish endpoint in `publish_content.py` is NOT affected (it uses the correct field name).
- **Blast Radius:** Isolated to the `publish_to_site` route in `sites.py`. The `publish_content.py` routes that handle save-and-publish and multi-site publishing use the correct field name.

---

## Recommended Solution

### Step 1: Fix the field name on line 292

```python
# File: rext-backend/src/api/routes/content/modules/sites.py
# Replace line 292:

# Before:
            content.published_at = datetime.now(timezone.utc)

# After:
            content.wordpress_published_at = datetime.now(timezone.utc)
```

### Step 2: Remove the unnecessary `from datetime import timezone` import inside the function

Line 281 has `from datetime import timezone` as a local import inside the `try` block. This import should be moved to the top of the file. However, looking at the file's existing imports (lines 1-21), `datetime` is not imported at the module level. The `timezone` import is needed for this fix. The cleanest approach is to add the import at the top of the file:

```python
# File: rext-backend/src/api/routes/content/modules/sites.py
# Add to imports at the top of the file (after line 5):

from datetime import datetime, timezone
```

Then remove the local import on line 281:

```python
# Remove line 281:
            from datetime import timezone
```

### Full corrected `publish_to_site` function (lines 280-298):

```python
        try:
            result = await wp_publisher.publish_post(
                title=content.title,
                content=content.body_markdown or content.body_html or "",
                status=data.status,
                excerpt=(content.metadata_json or {}).get("content_summary", ""),
                tags=(content.seo_data.content_primary_keywords if content.seo_data else [])
            )

            # Update content status
            content.status = "published"
            content.wordpress_published_at = datetime.now(timezone.utc)

            return {
                "success": True,
                "wordpress_result": result,
                "content_id": str(content.id)
            }
```

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `rext-backend/src/api/routes/content/modules/publish_content.py` | `204` | Uses correct `content.wordpress_published_at` — no change needed |
| `rext-backend/src/api/routes/content/modules/publish_content.py` | `284` | Uses correct `content.wordpress_published_at` — no change needed |
| `rext-backend/src/api/schema/content_schema.py` | `89, 123` | Declares `wordpress_published_at` in update and response schemas — no change needed |
| `rext-backend/src/api/models/content_models/content.py` | `41` | Defines the column as `wordpress_published_at` — no change needed |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Connect a WordPress site to a workspace via `POST /api/v1/content/sites/connect`.
2. Create a content item via `POST /api/v1/content/save`.
3. Publish the content to the site via `POST /api/v1/content/sites/{site_id}/publish/{content_id}`.
4. Query the database: `SELECT id, status, wordpress_published_at FROM content WHERE id = '<content_id>';`
5. Observe: `status` is `"published"` but `wordpress_published_at` is `NULL`.

### After Fix (Verify the Solution):
1. Same steps as above.
2. Query the database again.
3. Observe: `status` is `"published"` AND `wordpress_published_at` has a UTC timestamp.

### Edge Cases to Test:
1. Publish to multiple sites sequentially — verify `wordpress_published_at` is set after the first successful publish.
2. Publish content that was previously published — verify `wordpress_published_at` is updated to the new timestamp.
3. Failed WordPress publish — verify `wordpress_published_at` remains unchanged (exception is raised before the assignment).

### Run Existing Tests:
```bash
cd rext-backend
pytest tests/ -v -k "content or sites or publish" --no-header
```

---

## Acceptance Criteria

- [ ] `sites.py` line 292 uses `content.wordpress_published_at` instead of `content.published_at`
- [ ] `datetime` and `timezone` are imported at the top of `sites.py` (not inside the function)
- [ ] After publishing via `POST /sites/{site_id}/publish/{content_id}`, the content's `wordpress_published_at` column is populated with a UTC timestamp
- [ ] The `publish_to_site` endpoint still returns the correct success response
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [SQLAlchemy 2.0 — Mapped Column Attributes](https://docs.sqlalchemy.org/en/20/orm/mapping_styles.html#orm-mapped-attributes) — explains that setting non-mapped attributes on ORM instances creates transient Python attributes that are not persisted
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** [Python datetime — timezone-aware datetimes](https://docs.python.org/3/library/datetime.html#datetime.datetime.now) — `datetime.now(timezone.utc)` is the recommended replacement for deprecated `datetime.utcnow()`
- **Related Issues/PRs:** None

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-159 (Missing await on publish_post — B6), TASK-169 (WordPress Publishing Logic in Routes Instead of Service — B6)

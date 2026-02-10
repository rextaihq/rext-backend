# Task 160: Transaction Boundary Issue — Partial State on Multi-Site Publish Failure

## Metadata
- **Task ID:** TASK-160
- **Source:** Content Management Audit (Finding #9 under P1 High)
- **Audit Report:** `audit-reports/backend-content-management.md`
- **Priority:** P1 High
- **Category:** bug
- **Effort Estimate:** medium (1-4 hours)

---

## Description

The `save_and_publish()` endpoint in `src/api/routes/content/modules/publish_content.py` at lines 149-215 has a transaction boundary issue that can leave content in an inconsistent state. The endpoint performs two operations within the same transaction:

1. **Save content to the database** (lines 183-188) — creates a new `Content` record via `ContentService.create_content()`
2. **Publish to all active WordPress sites** (lines 191-196) — calls `_publish_to_all_sites()` which makes HTTP calls to external WordPress instances

If step 1 succeeds but step 2 fails for ALL sites, the content is saved in the database with `status="draft"` (or whatever was set), but the user's intent was to publish. The transaction still commits (via the `@db_transaction_handler` decorator), leaving a "saved but never published" content item with no indication that publishing was attempted and failed.

The code at lines 199-205 only updates the content status to `"published"` if at least one site succeeds:
```python
successful_results = [r for r in results if r.success]
if successful_results:
    first_success = successful_results[0]
    content.wordpress_post_id = first_success.wordpress_post_id
    content.wordpress_url = first_success.wordpress_url
    content.wordpress_published_at = datetime.now(timezone.utc)
    content.status = "published"
```

If `successful_results` is empty (all sites failed), the content remains with `status="draft"`. There is no `else` branch to set `status="publish_failed"` or to roll back the content creation. The `_publish_to_all_sites()` function at line 54 raises an `HTTPException` if NO active sites are found, but it does NOT raise an exception if sites exist but all fail — it simply returns a list of failed results.

This means users can experience:
1. Content appears "saved" with draft status, but the user clicked "Publish"
2. No clear error message indicating that publishing failed
3. The content exists in the database but was never published anywhere
4. The user may not realize they need to retry publishing

The same pattern exists in `publish_existing_content()` at lines 221-296, where existing content's status is only updated on success.

---

## Current Code

```python
# File: src/api/routes/content/modules/publish_content.py
# Lines: 182-215 (save_and_publish endpoint, relevant section)

    # Save content first
    service = ContentService(db)
    content = await service.create_content(
        workspace_id=workspace.id,
        user_id=UUID(user_id),
        data=data
    )

    # Publish to all active sites
    results = await _publish_to_all_sites(
        db=db,
        workspace_id=workspace.id,
        content_data=data,
        status=publish_status
    )

    # Update content with first successful publish info
    successful_results = [r for r in results if r.success]
    if successful_results:
        first_success = successful_results[0]
        content.wordpress_post_id = first_success.wordpress_post_id
        content.wordpress_url = first_success.wordpress_url
        content.wordpress_published_at = datetime.now(timezone.utc)
        content.status = "published"
    # BUG: No else branch — content stays as "draft" if all sites fail

    return {
        "content": content.to_dict(),
        "publish_results": {
            "total_sites": len(results),
            "successful": len(successful_results),
            "failed": len(results) - len(successful_results),
            "results": [r.model_dump() for r in results]
        }
    }
```

---

## Why This Matters (Context & Reasoning)

The "Save & Publish" workflow is the primary content publishing flow in Rext AI. When a user creates content and clicks "Publish," they expect one of two outcomes: (1) content is published successfully, or (2) they receive a clear error indicating failure. The current code creates a third, ambiguous outcome: content is saved but not published, with no error and no indication of the failure.

This is particularly problematic because:
- The content exists in the database and shows up in content lists, potentially confusing the user
- The response still returns HTTP 200 with the content data, giving the impression of success
- The `publish_results` section in the response does include failure details, but there is no error-level signal (HTTP status code, error flag) that the frontend can reliably detect and display to the user
- The content's `status` field is "draft" — identical to content that was intentionally saved as a draft — making it impossible to distinguish "intentional draft" from "publish failed"

The `_publish_to_all_sites()` function intentionally catches exceptions per-site (line 86-93) to allow partial success (e.g., 3 of 5 sites succeed). This is correct for multi-site publishing. However, the calling code does not handle the "all failed" case, which is the true error scenario.

---

## Impact

- **Severity:** Users who attempt to publish content may have their content silently saved as draft with no clear indication that publishing failed. The content appears in their workspace with no way to distinguish it from an intentional draft.
- **Affected Users/Flows:** All users who use `POST /api/v1/content/publish` (save & publish) or `POST /api/v1/content/{content_id}/publish` (publish existing). Both endpoints have the same issue.
- **Blast Radius:** Affects the core publishing workflow. Does not cause data loss (content is saved) but creates a confusing user experience.

---

## Recommended Solution

Add an `else` branch that handles the "all sites failed" case by either setting a distinct status or raising an exception to roll back the transaction. The recommended approach is to set a `"publish_failed"` status and return appropriate error information.

### Step 1: Handle the all-sites-failed case in `save_and_publish()`

```python
# File: src/api/routes/content/modules/publish_content.py
# Replace lines 199-215 with:

    # Update content with first successful publish info
    successful_results = [r for r in results if r.success]
    if successful_results:
        first_success = successful_results[0]
        content.wordpress_post_id = first_success.wordpress_post_id
        content.wordpress_url = first_success.wordpress_url
        content.wordpress_published_at = datetime.now(timezone.utc)
        content.status = "published"
    else:
        # All sites failed — mark content with a distinct status
        content.status = "publish_failed"
        logger.error(
            f"Publishing failed for all sites. Content {content.id} saved with status 'publish_failed'. "
            f"Errors: {[r.error for r in results if r.error]}"
        )

    return {
        "content": content.to_dict(),
        "publish_results": {
            "total_sites": len(results),
            "successful": len(successful_results),
            "failed": len(results) - len(successful_results),
            "results": [r.model_dump() for r in results],
            "all_failed": len(successful_results) == 0
        }
    }
```

### Step 2: Apply the same fix to `publish_existing_content()`

```python
# File: src/api/routes/content/modules/publish_content.py
# Replace lines 279-296 (in publish_existing_content) with:

    # Update content with first successful publish info
    successful_results = [r for r in results if r.success]
    if successful_results:
        first_success = successful_results[0]
        content.wordpress_post_id = first_success.wordpress_post_id
        content.wordpress_url = first_success.wordpress_url
        content.wordpress_published_at = datetime.now(timezone.utc)
        content.status = "published"
    else:
        content.status = "publish_failed"
        logger.error(
            f"Publishing failed for all sites. Content {content.id} status set to 'publish_failed'. "
            f"Errors: {[r.error for r in results if r.error]}"
        )

    return {
        "content": content.to_dict(),
        "publish_results": {
            "content_id": str(content_id),
            "total_sites": len(results),
            "successful": len(successful_results),
            "failed": len(results) - len(successful_results),
            "results": [r.model_dump() for r in results],
            "all_failed": len(successful_results) == 0
        }
    }
```

### Step 3: Add `"publish_failed"` to the status transition map

```python
# File: src/services/content_service.py
# Update the ALLOWED dict in _validate_status_transition (line 232):

    async def _validate_status_transition(self, current: str, new: str) -> None:
        ALLOWED = {
            "generating": ["ready", "archived", "draft"],
            "draft": ["ready", "archived", "generating"],
            "ready": ["published", "draft", "archived", "generating"],
            "published": ["archived", "ready"],
            "archived": [],
            "publish_failed": ["draft", "ready", "archived", "generating"],  # ADD THIS
        }
        if new not in ALLOWED.get(current, []):
            raise RextValidationException(message=f"Invalid transition: {current} -> {new}")
```

### Step 4: Add the `"all_failed"` flag to `PublishToSitesResponse` schema

```python
# File: src/api/schema/content_schema.py
# Update the PublishToSitesResponse class:

class PublishToSitesResponse(BaseModel):
    """Response for publishing to multiple sites"""
    content_id: UUID
    total_sites: int
    successful: int
    failed: int
    results: List[PublishResponse]
    all_failed: bool = False  # ADD THIS
```

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `src/api/routes/content/modules/publish_content.py` | `279-296` | `publish_existing_content()` has the same missing `else` branch |
| `src/services/content_service.py` | `231-233` | Status transition map needs `publish_failed` state added |
| `src/api/schema/content_schema.py` | `201-207` | `PublishToSitesResponse` should include `all_failed` flag |
| `rext-admin/types/content.ts` | `4-12` | Frontend `ContentStatus` type should include `"publish_failed"` (related to TASK-161) |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Connect a WordPress site with intentionally invalid credentials to a workspace
2. Ensure it is the only active site (or all active sites have invalid credentials)
3. Call `POST /api/v1/content/publish` with valid content data
4. **Current behavior:** Response returns HTTP 200. Content is saved with `status="draft"`. The `publish_results` section shows all sites as failed, but there is no clear top-level error indicator.

### After Fix (Verify the Solution):
1. Repeat the same steps with invalid credentials on all sites
2. **Expected behavior:** Content is saved with `status="publish_failed"`. Response includes `"all_failed": true` in the publish_results. Logs contain the error details.
3. Test that the content can be transitioned from `"publish_failed"` back to `"draft"` or `"ready"` for retrying

### Edge Cases:
1. **Partial success:** 2 of 3 sites succeed, 1 fails — content should have `status="published"`, `all_failed=false`
2. **All succeed:** All sites succeed — content should have `status="published"`, `all_failed=false`
3. **All fail:** All sites fail — content should have `status="publish_failed"`, `all_failed=true`
4. **No active sites:** Should raise HTTPException (existing behavior, unchanged)

### Run Existing Tests:
```bash
cd rext-backend
pytest tests/unit/services/test_content_service.py -v
pytest tests/ -k "content" -v
```

---

## Acceptance Criteria

- [ ] Content status is set to `"publish_failed"` when all WordPress sites fail to publish
- [ ] The response includes an `"all_failed"` flag in the publish_results for frontend detection
- [ ] The `_validate_status_transition()` map includes `"publish_failed"` as a valid status with allowed transitions
- [ ] Both `save_and_publish()` and `publish_existing_content()` endpoints handle the all-failed case
- [ ] Partial success (some sites succeed, some fail) still works correctly with `status="published"`
- [ ] Server logs include error details when all sites fail
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [SQLAlchemy Session Transaction Management](https://docs.sqlalchemy.org/en/20/orm/session_transaction.html) — guidance on handling partial failures within transactions
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** [Designing Resilient Systems — Partial Failure Handling](https://docs.microsoft.com/en-us/azure/architecture/patterns/retry) — principles for handling partial failures in distributed operations
- **Related Issues/PRs:** N/A

---

## Dependencies & Related Tasks

- **Depends on:** TASK-159 (B6 — Missing `await` on `publish_post()` must be fixed first, otherwise the publish always "fails")
- **Blocks:** None
- **Related:** TASK-161 (B6 — Status Enum Mismatch; the `"publish_failed"` status must be added to the frontend type as well), TASK-132 (B5 — No Retry Logic on External API Calls)

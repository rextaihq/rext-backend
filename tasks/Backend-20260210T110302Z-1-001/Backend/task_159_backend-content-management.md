# Task 159: Missing `await` on Async `publish_post()` Call — Returns Coroutine Instead of Result

## Metadata
- **Task ID:** TASK-159
- **Source:** Content Management Audit (Finding #8 under P1 High)
- **Audit Report:** `audit-reports/backend-content-management.md`
- **Priority:** P1 High
- **Category:** bug
- **Effort Estimate:** small (< 1 hour)

---

## Description

In `src/api/routes/content/modules/publish_content.py` at line 71, the `wp_publisher.publish_post()` method is called without `await`. The `publish_post()` method is an `async def` method defined at `src/services/wordpress_publisher.py:100`, so calling it without `await` returns a coroutine object rather than executing the HTTP call and returning the actual response dictionary.

The problematic code is inside the `_publish_to_all_sites()` helper function (lines 32-95), which iterates over all active WordPress sites and attempts to publish content to each one. On line 71, the call is:

```python
wp_response = wp_publisher.publish_post(
    data=content_data,
    status=status
)
```

Since `publish_post` is `async`, `wp_response` receives a `<coroutine object WordPressPublisher.publish_post at 0x...>` instead of the expected `dict` containing `{"success": True, "post_id": ..., "link": ...}`. The subsequent code at lines 80-81 then calls `wp_response.get("post_id")` and `wp_response.get("link")` on this coroutine object, which will raise `AttributeError: 'coroutine' object has no attribute 'get'`.

Python 3.11+ generates a `RuntimeWarning: coroutine 'WordPressPublisher.publish_post' was never awaited` when this happens, but the warning is easily missed in production logs. The actual HTTP request to WordPress never executes, so no content is ever published — the function silently fails to publish and returns incorrect results.

Notably, `sites.py:282` correctly uses `await wp_publisher.publish_post(...)` when publishing from the per-site endpoint, confirming this is an oversight specific to the `_publish_to_all_sites()` code path.

---

## Current Code

```python
# File: src/api/routes/content/modules/publish_content.py
# Lines: 59-84
for site in sites:
    try:
        # Initialize WordPress publisher with site credentials
        wp_publisher = WordPressPublisher(
            site_url=site.site_url,
            api_endpoint=site.api_endpoint,
            username=site.username,
            app_password=site.app_password,
            api_key=site.api_key
        )

        # Publish to WordPress
        wp_response = wp_publisher.publish_post(  # BUG: Missing await!
            data=content_data,
            status=status
        )

        results.append(PublishResponse(
            site_id=site.id,
            site_url=site.site_url,
            success=True,
            wordpress_post_id=wp_response.get("post_id"),  # AttributeError on coroutine
            wordpress_url=wp_response.get("link")           # AttributeError on coroutine
        ))
```

The async method being called:

```python
# File: src/services/wordpress_publisher.py
# Lines: 100-108
async def publish_post(
    self,
    data: ContentCreate,
    status: str = "publish",
    excerpt: Optional[str] = None,
    tags: Optional[list] = None,
    categories: Optional[list] = None,
    meta: Optional[Dict] = None
) -> Dict:
```

The correct usage in another file:

```python
# File: src/api/routes/content/modules/sites.py
# Line: 282
result = await wp_publisher.publish_post(  # Correctly awaited
    title=content.title,
    content=content.body_markdown or content.body_html or "",
    status=data.status,
    excerpt=(content.metadata_json or {}).get("content_summary", ""),
    tags=(content.seo_data.content_primary_keywords if content.seo_data else [])
)
```

---

## Why This Matters (Context & Reasoning)

The `_publish_to_all_sites()` function is called by two critical publishing endpoints:

1. `save_and_publish()` at line 191 — `POST /api/v1/content/publish` — the primary endpoint for creating and publishing content in one step
2. `publish_existing_content()` at line 271 — `POST /api/v1/content/{content_id}/publish` — publishes already-saved content

These are the main content publishing workflows in Rext AI. The missing `await` means that **no content is ever actually published to WordPress** through the multi-site publishing flow. The function will either:
- Raise `AttributeError` when trying to call `.get()` on a coroutine (caught by the `except Exception` block at line 86)
- Mark every site as "failed" in the results
- Or produce garbage results if the coroutine object happens to be truthy

The per-site publishing endpoint (`POST /api/v1/content/sites/{site_id}/publish/{content_id}`) in `sites.py` works correctly because it properly awaits the call. So users publishing to a specific site would succeed, but the "publish to all active sites" flow would always fail.

---

## Impact

- **Severity:** The multi-site publishing feature is completely broken — content is never actually published to WordPress through the `_publish_to_all_sites()` code path
- **Affected Users/Flows:** All users who use the `POST /publish` or `POST /{content_id}/publish` endpoints, which are the primary publishing workflows
- **Blast Radius:** Affects the core publishing feature. The per-site publishing via `sites.py` still works correctly.

---

## Recommended Solution

### Step 1: Add `await` to the `publish_post()` call

```python
# File: src/api/routes/content/modules/publish_content.py
# Replace line 71-74:
            wp_response = await wp_publisher.publish_post(
                data=content_data,
                status=status
            )
```

This is a one-word change: add `await` before `wp_publisher.publish_post(`.

The enclosing function `_publish_to_all_sites()` is already declared as `async def` (line 32), so `await` is valid here.

### Step 2 (Optional but recommended): Add `async with` for the httpx client

While fixing the missing await, note that the `WordPressPublisher` creates an `httpx.AsyncClient` in `__init__` but never closes it (tracked separately in a later task). For now, the `await` fix is sufficient to make the publishing work. The resource leak is a separate concern.

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `src/api/routes/content/modules/sites.py` | `282` | Correctly uses `await wp_publisher.publish_post(...)` — reference implementation |
| `src/api/routes/content/modules/sites.py` | `70` | Correctly uses `await wp_publisher.validate_plugin()` |
| `src/api/routes/content/modules/publish_content.py` | `191` | Caller of `_publish_to_all_sites()` in `save_and_publish()` |
| `src/api/routes/content/modules/publish_content.py` | `271` | Caller of `_publish_to_all_sites()` in `publish_existing_content()` |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Ensure at least one WordPress site is connected and active in a workspace
2. Create content via `POST /api/v1/content/publish` with valid title and body
3. **Current behavior:** The response shows all sites as "failed" (or raises an error). No WordPress post is created on any connected site. Check server logs for `RuntimeWarning: coroutine 'WordPressPublisher.publish_post' was never awaited`.

### After Fix (Verify the Solution):
1. Create content via `POST /api/v1/content/publish` with valid title and body
2. **Expected behavior:** Content is published to all active WordPress sites. The response includes `wordpress_post_id` and `wordpress_url` for each successful site.
3. Verify the post exists on the WordPress site by checking the WordPress admin dashboard
4. Test with multiple active sites to confirm all are published to

### Edge Cases:
1. Test with one site active and one inactive — only the active site should receive the publish
2. Test with no active sites — should get error "No active WordPress sites found"
3. Test with a site that has invalid credentials — should get failure result for that site but success for others

### Run Existing Tests:
```bash
cd rext-backend
pytest tests/unit/services/test_content_service.py -v
pytest tests/ -k "publish" -v
```

---

## Acceptance Criteria

- [ ] `await` is added before `wp_publisher.publish_post()` on line 71 of `publish_content.py`
- [ ] Content is successfully published to WordPress when using `POST /api/v1/content/publish`
- [ ] Content is successfully published when using `POST /api/v1/content/{content_id}/publish`
- [ ] The response includes correct `wordpress_post_id` and `wordpress_url` for successful sites
- [ ] No `RuntimeWarning: coroutine ... was never awaited` appears in server logs
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [Python asyncio Coroutines and Tasks](https://docs.python.org/3/library/asyncio-task.html) — explains that calling an async function without `await` returns a coroutine object
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** [FastAPI Async/Await Best Practices](https://fastapi.tiangolo.com/async/) — guidance on using `await` correctly in FastAPI route handlers
- **Related Issues/PRs:** N/A

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-164 (B6 — httpx AsyncClient Resource Leak in WordPressPublisher, same code area), TASK-132 (B5 — No Retry Logic on LemonSqueezy API Calls, same pattern of missing resilience on external calls)

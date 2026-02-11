# Task 177: Refactor Sequential Site Publishing to Use Parallel Execution

## Metadata
- **Task ID:** TASK-177
- **Source:** Backend Content Management Audit (Finding #22 under P2 Medium)
- **Audit Report:** `audit-reports/backend-content-management.md`
- **Priority:** P2 Medium
- **Category:** performance
- **Effort Estimate:** medium (1-4 hours)

---

## Description

The `_publish_to_all_sites()` helper function in `src/api/routes/content/modules/publish_content.py` (lines 32-95) publishes content to multiple WordPress sites sequentially using a `for` loop. Each iteration creates a new `WordPressPublisher` instance and calls `publish_post()` one site at a time. Since each WordPress API call involves an HTTP round-trip with potential network latency, timeouts, and retries, this approach becomes progressively slower as more sites are connected.

For a workspace with 5 active sites, each with a 30-second timeout, the worst case is 2.5+ minutes of sequential execution. This blocks the FastAPI event loop for the duration, degrading response times for all concurrent users. Since `publish_post()` is an async method (defined in `wordpress_publisher.py:100`) and the WordPress API calls are I/O-bound network operations, they are ideal candidates for parallel execution using `asyncio.gather()` or Python 3.11+'s `asyncio.TaskGroup`.

The current code at lines 59-94 iterates through each site, creates a publisher, calls publish, and appends results one by one. According to Python's asyncio documentation and FastAPI best practices, independent I/O-bound coroutines should be dispatched concurrently. Using `asyncio.gather(..., return_exceptions=True)` allows all publishing operations to run in parallel while gracefully handling per-site failures without cancelling the entire batch. Note that the existing code already handles per-site errors individually (lines 86-93), so the `return_exceptions=True` pattern maps cleanly onto the current error handling model.

The project targets Python `>=3.11,<3.12` per `pyproject.toml`, so both `asyncio.gather()` and `asyncio.TaskGroup` are available. However, `asyncio.gather()` with `return_exceptions=True` is the better fit here because it preserves result ordering (matching the input site order) and allows partial failures — which is exactly the current behavior where some sites may succeed and others may fail.

---

## Current Code

```python
# File: src/api/routes/content/modules/publish_content.py
# Lines: 59-95
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
            wp_response = wp_publisher.publish_post(
                data=content_data,
                status=status
            )

            results.append(PublishResponse(
                site_id=site.id,
                site_url=site.site_url,
                success=True,
                wordpress_post_id=wp_response.get("post_id"),
                wordpress_url=wp_response.get("link")
            ))

            logger.info(f"Published to {site.site_url}: post_id={wp_response.get('post_id')}")

        except Exception as e:
            logger.error(f"Failed to publish to {site.site_url}: {str(e)}")
            results.append(PublishResponse(
                site_id=site.id,
                site_url=site.site_url,
                success=False,
                error=str(e)
            ))

    return results
```

---

## Why This Matters (Context & Reasoning)

The `_publish_to_all_sites()` function is called by two endpoints: `save_and_publish()` (line 191) and `publish_existing_content()` (line 271). These are the primary pathways for publishing content to connected WordPress sites. When a user clicks "Publish," they expect reasonably fast feedback. Sequential execution means the user waits for the sum of all site publishing times, while parallel execution means they wait only for the slowest site.

In a multi-tenant SaaS like Rext AI, workspaces may have multiple connected WordPress sites (e.g., a blog, a marketing site, and a documentation portal). Performance degrades linearly with site count in the current implementation. Since these are independent HTTP requests to different WordPress instances, there is no dependency between them and no reason for sequential execution.

Additionally, FastAPI runs on a single-threaded asyncio event loop. Long-running sequential I/O operations block other requests from being processed, reducing overall API throughput.

---

## Impact

- **Severity:** Publishing latency scales linearly with the number of connected sites. With 5 sites and typical WordPress API latency (2-5 seconds), users wait 10-25 seconds instead of 2-5 seconds.
- **Affected Users/Flows:** All users publishing content via `/publish` or `/{content_id}/publish` endpoints.
- **Blast Radius:** Isolated to publishing flow, but the event loop blocking affects all concurrent API requests during publishing.

---

## Recommended Solution

### Step 1: Create a single-site publishing coroutine

Extract the per-site publishing logic into a standalone async function that can be dispatched concurrently.

```python
# File: src/api/routes/content/modules/publish_content.py
# Add after line 26 (after router = APIRouter()):

import asyncio


async def _publish_to_single_site(
    site: WorkspaceIntegration,
    content_data: ContentCreate,
    status: str
) -> PublishResponse:
    """Publish content to a single WordPress site. Returns a PublishResponse."""
    try:
        wp_publisher = WordPressPublisher(
            site_url=site.site_url,
            api_endpoint=site.api_endpoint,
            username=site.username,
            app_password=site.app_password,
            api_key=site.api_key
        )

        wp_response = await wp_publisher.publish_post(
            data=content_data,
            status=status
        )

        logger.info(f"Published to {site.site_url}: post_id={wp_response.get('post_id')}")
        return PublishResponse(
            site_id=site.id,
            site_url=site.site_url,
            success=True,
            wordpress_post_id=wp_response.get("post_id"),
            wordpress_url=wp_response.get("link"),
        )
    except Exception as e:
        logger.error(f"Failed to publish to {site.site_url}: {str(e)}")
        return PublishResponse(
            site_id=site.id,
            site_url=site.site_url,
            success=False,
            error=str(e),
        )
```

### Step 2: Refactor `_publish_to_all_sites()` to use `asyncio.gather()`

Replace the sequential `for` loop with parallel dispatch.

```python
# File: src/api/routes/content/modules/publish_content.py
# Replace lines 42-95 (the body of _publish_to_all_sites after docstring) with:

async def _publish_to_all_sites(
    db: AsyncSession,
    workspace_id: UUID,
    content_data: ContentCreate,
    status: str = "publish"
) -> List[PublishResponse]:
    """
    Publish content to all active WordPress sites in the workspace.
    Returns list of results for each site, in the same order as the sites.
    All sites are published to concurrently using asyncio.gather().
    """
    # Fetch all active sites
    sites_query = select(WorkspaceIntegration).where(
        WorkspaceIntegration.workspace_id == workspace_id,
        WorkspaceIntegration.is_active == True
    )
    sites_result = await db.execute(sites_query)
    sites = sites_result.scalars().all()

    if not sites:
        logger.warning(f"No active sites found for workspace {workspace_id}")
        raise HTTPException(
            status_code=400,
            detail="No active WordPress sites found in this workspace. Please connect a site before publishing."
        )

    # Publish to all sites concurrently
    results = await asyncio.gather(
        *[_publish_to_single_site(site, content_data, status) for site in sites],
        return_exceptions=True,
    )

    # Convert any unexpected exceptions into PublishResponse objects
    final_results: List[PublishResponse] = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error(f"Unexpected error publishing to site index {i}: {result}")
            final_results.append(PublishResponse(
                site_id=sites[i].id,
                site_url=sites[i].site_url,
                success=False,
                error=str(result),
            ))
        else:
            final_results.append(result)

    return final_results
```

### Step 3: Add the `asyncio` import at the top of the file

```python
# File: src/api/routes/content/modules/publish_content.py
# Add to imports at line 1-6 area:
import asyncio
```

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `src/api/routes/content/modules/publish_content.py` | `71` | Missing `await` on `wp_publisher.publish_post()` — related bug (TASK-159). The refactored `_publish_to_single_site` already includes `await`. |
| `src/services/wordpress_publisher.py` | `70-74` | `WordPressPublisher` has no `close()` method, causing resource leaks (TASK-162). Consider using `async with` in `_publish_to_single_site` once TASK-162 is resolved. |
| `src/api/routes/content/modules/sites.py` | `273-301` | The `publish_to_site()` endpoint publishes to a single site and is not affected by this change. |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Connect 3+ WordPress sites to a workspace (or mock them in test).
2. Call `POST /api/v1/content/publish` with valid content data.
3. Observe that publishing happens sequentially — total time is roughly the sum of each individual site's response time.
4. Check logs: publish log entries appear sequentially, not overlapping.

### After Fix (Verify the Solution):
1. Call the same `POST /api/v1/content/publish` endpoint with 3+ active sites.
2. Observe that total time is roughly equal to the slowest single site (not the sum).
3. Check logs: publish log entries for different sites appear at approximately the same timestamp.
4. Verify that if one site fails, other sites still succeed and the response includes both successes and failures.
5. Verify the results list order matches the sites order.

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/unit/services/test_content_service.py -v
```

---

## Acceptance Criteria

- [ ] `_publish_to_all_sites()` uses `asyncio.gather()` instead of a sequential `for` loop
- [ ] Per-site publishing is extracted into `_publish_to_single_site()` coroutine
- [ ] Each `_publish_to_single_site()` call uses `await` on `wp_publisher.publish_post()`
- [ ] `return_exceptions=True` is used to prevent one site's failure from cancelling others
- [ ] Unexpected exceptions from `asyncio.gather` are converted into `PublishResponse` objects with `success=False`
- [ ] Result ordering is preserved (matches input site order)
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [Python asyncio.gather() documentation](https://docs.python.org/3/library/asyncio-task.html#asyncio.gather)
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** [FastAPI Async/Await documentation](https://fastapi.tiangolo.com/async/)
- **Related Issues/PRs:** None

---

## Dependencies & Related Tasks

- **Depends on:** None (can be implemented independently)
- **Blocks:** None
- **Related:** TASK-159 (missing `await` on `publish_post()` — the refactored code fixes this implicitly), TASK-162 (httpx AsyncClient resource leak — once fixed, `_publish_to_single_site` should use `async with`), TASK-173 (retry mechanism for WordPress API calls — retry logic integrates well with the per-site coroutine)

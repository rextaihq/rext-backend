# Task 162: httpx AsyncClient Resource Leak in WordPressPublisher

## Metadata
- **Task ID:** TASK-162
- **Source:** B6 - Content Management (Finding #7 under P1 High)
- **Audit Report:** `audit-reports/backend-content-management.md`
- **Priority:** P1 High
- **Category:** bug
- **Effort Estimate:** medium (1-4 hours)

---

## Description

The `WordPressPublisher` class in `rext-backend/src/services/wordpress_publisher.py` creates an `httpx.AsyncClient` instance during `__init__` (lines 70-74) but provides no mechanism to close it. The class lacks `__aenter__`/`__aexit__` async context manager methods, a `close()` method, or any other cleanup mechanism.

When `WordPressPublisher` is instantiated in `publish_content.py:62-68` inside the `_publish_to_all_sites()` helper, a new `httpx.AsyncClient` is created for every site in every publish operation. Because the clients are never closed, the underlying TCP connections, sockets, and file descriptors remain open until the garbage collector eventually reclaims them (if at all). According to the official httpx documentation, "The recommended way to use a Client is as a context manager, which will ensure that connections are properly cleaned up when leaving the `with` block."

The current instantiation pattern in `publish_content.py` (line 62-74) creates the publisher inside a `for site in sites` loop without any cleanup:

```python
wp_publisher = WordPressPublisher(
    site_url=site.site_url,
    api_endpoint=site.api_endpoint,
    username=site.username,
    app_password=site.app_password,
    api_key=site.api_key
)
wp_response = wp_publisher.publish_post(...)  # Also missing await — see TASK-159
```

Over time — especially for workspaces with multiple WordPress sites and frequent publishing — this leads to connection pool exhaustion, open file descriptor accumulation, and potential memory leaks. The httpx library maintains keep-alive connections by default (`max_keepalive_connections=20`, `max_connections=100`), but without closing clients, these connections are never returned to the pool or cleaned up.

---

## Current Code

```python
# File: rext-backend/src/services/wordpress_publisher.py
# Lines: 16-74
class WordPressPublisher:
    """WordPress REST API client for publishing content."""

    def __init__(
        self,
        site_url: Optional[str] = None,
        api_endpoint: Optional[str] = None,
        username: Optional[str] = None,
        app_password: Optional[str] = None,
        api_key: Optional[str] = None,
        verify_ssl: bool = True
    ):
        # ... parameter assignments ...

        self.client = httpx.AsyncClient(
            verify=self.verify_ssl,
            headers=headers,
            auth=auth,
        )
```

```python
# File: rext-backend/src/api/routes/content/modules/publish_content.py
# Lines: 59-74
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
```

---

## Why This Matters (Context & Reasoning)

The `WordPressPublisher` is the sole integration point between Rext AI and external WordPress sites. Every content publishing operation goes through this class. In a production environment with multiple workspaces, each potentially connected to multiple WordPress sites, publishing operations could create dozens of unclosed HTTP clients per day.

Each unclosed `httpx.AsyncClient` holds onto:
- TCP socket connections in keep-alive state
- SSL/TLS session state (if HTTPS)
- Connection pool internal state
- In-memory buffers

On Linux systems, the default file descriptor limit is typically 1024 per process. With enough unclosed clients, the FastAPI process could hit this limit, causing subsequent HTTP requests (both internal and external) to fail with "Too many open files" errors.

---

## Impact

- **Severity:** Progressive connection pool exhaustion and file descriptor leaks that worsen over time. In high-usage scenarios, can lead to `PoolTimeout` errors or OS-level "Too many open files" errors, causing the application to fail for all users.
- **Affected Users/Flows:** All users who publish content to WordPress sites. The `_publish_to_all_sites()` function is called from `save_and_publish()` and `publish_existing_content()` endpoints.
- **Blast Radius:** Can affect the entire FastAPI process — not just WordPress publishing but all outbound HTTP calls if file descriptors are exhausted.

---

## Recommended Solution

### Step 1: Add async context manager and close methods to WordPressPublisher

```python
# File: rext-backend/src/services/wordpress_publisher.py
# Add these methods to the WordPressPublisher class after __init__:

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def close(self):
        """Close the underlying httpx.AsyncClient and release resources."""
        if self.client:
            await self.client.aclose()
```

### Step 2: Update _publish_to_all_sites() to use async context manager

```python
# File: rext-backend/src/api/routes/content/modules/publish_content.py
# Replace lines 59-94 with:

    for site in sites:
        try:
            # Initialize WordPress publisher with site credentials
            async with WordPressPublisher(
                site_url=site.site_url,
                api_endpoint=site.api_endpoint,
                username=site.username,
                app_password=site.app_password,
                api_key=site.api_key
            ) as wp_publisher:
                # Publish to WordPress
                wp_response = await wp_publisher.publish_post(
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
```

### Step 3: Update publish_existing_content() to also use context manager

Any other location where `WordPressPublisher` is instantiated should use `async with`. Search the codebase for `WordPressPublisher(` to find all instantiation sites and ensure each uses the context manager pattern.

### Step 4: Update sites.py publish endpoint

```python
# File: rext-backend/src/api/routes/content/modules/sites.py
# At the site-specific publish endpoint (sites.py:236+), also use async with:
async with WordPressPublisher(
    site_url=site.site_url,
    api_endpoint=site.api_endpoint,
    username=site.username,
    app_password=site.app_password,
    api_key=site.api_key
) as wp_publisher:
    wp_response = await wp_publisher.publish_post(
        data=content_data,
        status=publish_status
    )
```

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `src/api/routes/content/modules/sites.py` | `236+` | Site-specific publish endpoint also instantiates WordPressPublisher without cleanup |
| `src/api/routes/content/modules/publish_content.py` | `71` | Missing `await` on `publish_post()` — related TASK-159 |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Add temporary logging to `WordPressPublisher.__init__` to log client creation: `logger.debug(f"Created AsyncClient {id(self.client)}")`
2. Add a `__del__` method that logs: `logger.warning(f"WordPressPublisher garbage collected without close: {id(self.client)}")`
3. Publish content to a workspace with 2+ active WordPress sites
4. Observe that the `__del__` warning fires without an explicit close

### After Fix (Verify the Solution):
1. Add temporary logging to `WordPressPublisher.close()`: `logger.debug(f"Closed AsyncClient {id(self.client)}")`
2. Publish content to a workspace with 2+ active WordPress sites
3. Verify that "Closed AsyncClient" appears for every "Created AsyncClient" in the logs
4. Verify that publishing still succeeds (functional regression check)

### Run Existing Tests:
```bash
cd rext-backend
python -m pytest tests/unit/services/test_content_service.py -v
```

---

## Acceptance Criteria

- [ ] `WordPressPublisher` implements `__aenter__` and `__aexit__` methods
- [ ] `WordPressPublisher` has a `close()` method that calls `await self.client.aclose()`
- [ ] All instantiation sites in `publish_content.py` use `async with WordPressPublisher(...)` pattern
- [ ] All instantiation sites in `sites.py` use `async with WordPressPublisher(...)` pattern
- [ ] WordPress publishing still works correctly (functional regression test)
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [httpx Async Client Lifecycle](https://www.python-httpx.org/async/) — Documents the `async with` pattern and `aclose()` requirements
- **Official Docs:** [httpx Client Instances](https://www.python-httpx.org/advanced/clients/) — Explains connection pooling and why clients must be closed
- **Official Docs:** [httpx Resource Limits](https://www.python-httpx.org/advanced/resource-limits/) — Default pool sizes (20 keepalive, 100 max connections)
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** [Python async context manager protocol (PEP 492)](https://peps.python.org/pep-0492/#asynchronous-context-managers-and-async-with)
- **Related Issues/PRs:** [httpx #1461 — Pool connection may not be closed correctly in AsyncClient](https://github.com/encode/httpx/issues/1461)

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-159 (Missing `await` on `publish_post()` in same function), TASK-132 (No retry logic on API calls — B5 finding)

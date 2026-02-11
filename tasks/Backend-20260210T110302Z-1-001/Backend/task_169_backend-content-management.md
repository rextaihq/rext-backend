# Task 169: WordPress Publishing Logic in Routes Instead of Service Layer

## Metadata
- **Task ID:** TASK-169
- **Source:** Content Management Audit (Finding #6 under P1 High)
- **Audit Report:** `audit-reports/backend-content-management.md`
- **Priority:** P1 High
- **Category:** refactoring
- **Effort Estimate:** medium (1-4 hours)

---

## Description

The `_publish_to_all_sites()` helper function at `src/api/routes/content/modules/publish_content.py:32-95` contains significant business logic that belongs in the service layer, not the routes layer. This function queries the database for active sites, iterates over each site, instantiates `WordPressPublisher`, calls `publish_post()`, collects results, and handles errors — all operations that constitute core business logic for the content publishing workflow.

The project has a clearly established architecture: routes handle HTTP concerns (request parsing, response formatting, auth), while services (`src/services/`) handle business logic and database operations. The `ContentService` already exists at `src/services/content_service.py` with methods like `create_content`, `update_content`, `publish_content`, etc. The publishing-to-sites logic is conspicuously absent from this service. Instead, it lives in the routes file where it cannot be reused by other entry points such as Celery background tasks, CLI commands, or internal service-to-service calls.

The current placement also makes the publishing flow harder to test because route-level functions require mocking the full HTTP request/response cycle, while service-level methods can be tested with just a database session mock. Additionally, the function duplicates the error handling pattern (try/except per site) and result collection logic that would be more maintainably located in a dedicated service method.

This function is called from two route handlers: `save_and_publish()` at line 191 and `publish_existing_content()` at line 271. Both handlers also contain post-publish logic (updating `wordpress_post_id`, `wordpress_url`, `wordpress_published_at`, and `status`) that is duplicated across the two endpoints (lines 199-205 and lines 279-285). Moving the entire publish flow to the service layer would eliminate this duplication.

---

## Current Code

```python
# File: src/api/routes/content/modules/publish_content.py
# Lines: 32-95
async def _publish_to_all_sites(
    db: AsyncSession,
    workspace_id: UUID,
    content_data: ContentCreate,
    status: str = "publish"
) -> List[PublishResponse]:
    """
    Publish content to all active WordPress sites in the workspace.
    Returns list of results for each site.
    """
    results = []

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

```python
# File: src/api/routes/content/modules/publish_content.py
# Lines: 198-205 (duplicated post-publish logic in save_and_publish)
    # Update content with first successful publish info
    successful_results = [r for r in results if r.success]
    if successful_results:
        first_success = successful_results[0]
        content.wordpress_post_id = first_success.wordpress_post_id
        content.wordpress_url = first_success.wordpress_url
        content.wordpress_published_at = datetime.now(timezone.utc)
        content.status = "published"
```

```python
# File: src/api/routes/content/modules/publish_content.py
# Lines: 278-285 (same logic duplicated in publish_existing_content)
    # Update content with first successful publish info
    successful_results = [r for r in results if r.success]
    if successful_results:
        first_success = successful_results[0]
        content.wordpress_post_id = first_success.wordpress_post_id
        content.wordpress_url = first_success.wordpress_url
        content.wordpress_published_at = datetime.now(timezone.utc)
        content.status = "published"
```

---

## Why This Matters (Context & Reasoning)

The Rext AI backend follows a layered architecture: routes → services → models. Placing business logic in the routes layer violates this separation and creates multiple practical problems. First, the publishing logic cannot be invoked from background tasks (e.g., scheduled publishing, retry workflows) without duplicating the route-level code or importing route helpers into task files. Second, testing requires setting up the full FastAPI request context instead of simply injecting a mock database session. Third, the duplication of post-publish content updates across two route handlers means every change to the publish flow must be made in two places, increasing the risk of divergence bugs. Moving this to `ContentService` aligns with the existing pattern where `create_content`, `update_content`, and `delete_content` all live in the service.

---

## Impact

- **Severity:** Not a runtime bug, but the architectural violation makes the publish flow untestable in isolation, unreusable from non-HTTP contexts, and fragile due to duplicated post-publish logic.
- **Affected Users/Flows:** All content publishing operations (save-and-publish, publish-existing).
- **Blast Radius:** Primarily structural — affects developer productivity and code maintainability rather than end-user functionality directly.

---

## Recommended Solution

Move the `_publish_to_all_sites()` logic and the post-publish content update logic into `ContentService`, then simplify the route handlers to delegate to the service.

### Step 1: Add Publishing Method to ContentService

```python
# File: src/services/content_service.py
# Add these imports at the top of the file (after existing imports):
from src.api.models.workspace_models.workspace_integration import WorkspaceIntegration
from src.services.wordpress_publisher import WordPressPublisher
from src.api.schema.content_schema import ContentCreate as ContentCreateSchema, PublishResponse
```

```python
# File: src/services/content_service.py
# Add after the publish_content method (after line 208), before _slugify:

    async def publish_to_sites(
        self,
        content: Content,
        content_data: ContentCreateSchema,
        workspace_id: UUID,
        publish_status: str = "publish",
    ) -> dict:
        """
        Publish content to all active WordPress sites in a workspace.

        Fetches active sites, publishes to each, updates content with
        the first successful publish result, and returns a summary.

        Args:
            content: The Content ORM object to update after publishing.
            content_data: The ContentCreate schema with content body for WordPress.
            workspace_id: The workspace whose active sites to publish to.
            publish_status: WordPress post status ('publish', 'draft', 'pending', 'private').

        Returns:
            Dict with publish results summary.

        Raises:
            RextValidationException: If no active sites are found.
        """
        sites_query = select(WorkspaceIntegration).where(
            WorkspaceIntegration.workspace_id == workspace_id,
            WorkspaceIntegration.is_active.is_(True),
        )
        sites_result = await self.db.execute(sites_query)
        sites = sites_result.scalars().all()

        if not sites:
            raise RextValidationException(
                message="No active WordPress sites found in this workspace. Please connect a site before publishing."
            )

        results: list[PublishResponse] = []

        for site in sites:
            try:
                wp_publisher = WordPressPublisher(
                    site_url=site.site_url,
                    api_endpoint=site.api_endpoint,
                    username=site.username,
                    app_password=site.app_password,
                    api_key=site.api_key,
                )

                wp_response = await wp_publisher.publish_post(
                    data=content_data,
                    status=publish_status,
                )

                results.append(PublishResponse(
                    site_id=site.id,
                    site_url=site.site_url,
                    success=True,
                    wordpress_post_id=wp_response.get("post_id"),
                    wordpress_url=wp_response.get("link"),
                ))
                logger.info(f"Published to {site.site_url}: post_id={wp_response.get('post_id')}")

            except Exception as e:
                logger.error(f"Failed to publish to {site.site_url}: {str(e)}")
                results.append(PublishResponse(
                    site_id=site.id,
                    site_url=site.site_url,
                    success=False,
                    error=str(e),
                ))

        # Update content with first successful result
        successful_results = [r for r in results if r.success]
        if successful_results:
            first_success = successful_results[0]
            content.wordpress_post_id = first_success.wordpress_post_id
            content.wordpress_url = first_success.wordpress_url
            content.wordpress_published_at = datetime.now(timezone.utc)
            content.status = "published"

        await self.db.flush()

        return {
            "total_sites": len(results),
            "successful": len(successful_results),
            "failed": len(results) - len(successful_results),
            "results": [r.model_dump() for r in results],
        }
```

### Step 2: Simplify the save_and_publish Route

```python
# File: src/api/routes/content/modules/publish_content.py
# Replace the save_and_publish function body (lines 166-215) with:

@router.post("/publish")
@db_transaction_handler("publish content", "Content published successfully")
@require_permissions("content.create", workspace_scoped=True)
async def save_and_publish(
    data: ContentCreate,
    request: Request,
    workspace_id: str,
    publish_status: str = "publish",
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user)
):
    """
    Save content AND publish to all active WordPress sites.
    """
    user_id = user.get("identity")
    workspace, _ = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

    service = ContentService(db)
    content = await service.create_content(
        workspace_id=workspace.id,
        user_id=UUID(user_id),
        data=data
    )

    publish_results = await service.publish_to_sites(
        content=content,
        content_data=data,
        workspace_id=workspace.id,
        publish_status=publish_status,
    )

    return {
        "content": content.to_dict(),
        "publish_results": publish_results,
    }
```

### Step 3: Simplify the publish_existing_content Route

```python
# File: src/api/routes/content/modules/publish_content.py
# Replace the publish_existing_content function body (lines 224-296) with:

@router.post("/{content_id}/publish")
@db_transaction_handler("publish existing content", "Content published successfully")
@require_permissions("content.create", workspace_scoped=True)
async def publish_existing_content(
    content_id: UUID,
    request: Request,
    workspace_id: str,
    publish_data: PublishToSiteRequest = None,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user)
):
    """
    Publish existing content to all active WordPress sites.
    """
    user_id = user.get("identity")
    workspace, _ = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

    service = ContentService(db)
    content = await service._get_content_or_404(content_id, workspace.id, include_seo=True)

    # Build ContentCreate from existing content for WordPress API
    from src.api.schema.content_schema import ContentSEODataSchema
    seo_data = None
    if content.seo_data:
        seo_data = ContentSEODataSchema(
            meta_title=content.seo_data.meta_title,
            meta_description=content.seo_data.meta_description,
            focus_keyphrase=content.seo_data.focus_keyphrase,
            trust_score=content.seo_data.trust_score,
        )

    content_data = ContentCreate(
        title=content.title,
        introduction=content.introduction,
        body_html=content.body_html,
        body_markdown=content.body_markdown,
        tags=content.tags,
        seo_data=seo_data,
    )

    status = "publish"
    if publish_data and publish_data.status:
        status = publish_data.status

    publish_results = await service.publish_to_sites(
        content=content,
        content_data=content_data,
        workspace_id=workspace.id,
        publish_status=status,
    )

    return {
        "content": content.to_dict(),
        "publish_results": {
            "content_id": str(content_id),
            **publish_results,
        },
    }
```

### Step 4: Remove the `_publish_to_all_sites` Helper and Unused Imports

Remove the `_publish_to_all_sites` function (lines 32-95) from `publish_content.py`. Also remove the now-unused import of `WorkspaceIntegration` from this file if no other code in the file references it. The `HTTPException` import can also be removed if only `_publish_to_all_sites` was using it (the title uniqueness checks also use it, so verify before removing).

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `src/api/routes/content/modules/publish_content.py` | `32-95` | `_publish_to_all_sites` helper to remove |
| `src/api/routes/content/modules/publish_content.py` | `198-205` | Post-publish content update logic (duplicated) — moved to service |
| `src/api/routes/content/modules/publish_content.py` | `278-285` | Post-publish content update logic (duplicated) — moved to service |
| `src/api/routes/content/modules/publish_content.py` | `1, 24` | Imports of `HTTPException` and `WorkspaceIntegration` may become unused |
| `src/services/content_service.py` | top | New imports needed for `WorkspaceIntegration`, `WordPressPublisher`, `PublishResponse` |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Confirm that `_publish_to_all_sites` exists in `publish_content.py` and is a route-level helper
2. Note that the post-publish content update logic (setting `wordpress_post_id`, `wordpress_url`, etc.) is duplicated in both `save_and_publish` and `publish_existing_content`

### After Fix (Verify the Solution):
1. Verify that `_publish_to_all_sites` no longer exists in `publish_content.py`
2. Verify that `ContentService.publish_to_sites()` exists and contains the publishing logic
3. Call `POST /api/v1/content/publish` with valid content data and an active WordPress site — verify publishing works end-to-end
4. Call `POST /api/v1/content/{content_id}/publish` with existing content — verify publishing works
5. Call either publish endpoint with no active sites — verify a proper validation error is returned (not an HTTPException)
6. Verify content is updated with `wordpress_post_id`, `wordpress_url`, `wordpress_published_at`, and `status = "published"` after successful publishing

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/unit/services/test_content_service.py -v
```

---

## Acceptance Criteria

- [ ] `_publish_to_all_sites` function removed from `publish_content.py`
- [ ] `ContentService.publish_to_sites()` method exists and handles the full publish flow
- [ ] Post-publish content update logic (wordpress_post_id, etc.) is in the service, not duplicated in routes
- [ ] Both `save_and_publish` and `publish_existing_content` routes delegate to the service method
- [ ] The `await` keyword is used when calling `wp_publisher.publish_post()` (fixing the existing bug from Finding 8)
- [ ] No `HTTPException` is raised for "no active sites" — uses `RextValidationException` instead (consistent with service layer patterns)
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [FastAPI Bigger Applications — Multiple Files](https://fastapi.tiangolo.com/tutorial/bigger-applications/) — FastAPI's guidance on structuring routes and separating concerns
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** [SQLAlchemy Session Best Practices](https://docs.sqlalchemy.org/en/20/orm/session_basics.html) — guidance on keeping database operations in a consistent layer
- **Related Issues/PRs:** None identified

---

## Dependencies & Related Tasks

- **Depends on:** None (but implementing alongside TASK-159 — Missing await on publish_post — is recommended since this refactor naturally fixes that bug)
- **Blocks:** None
- **Related:** TASK-159 (Missing await on publish_post) — the `await` is correctly included in the service method; TASK-160 (Transaction Boundary Issue on Publish Failure) — moving to service makes it easier to add proper rollback; TASK-162 (httpx AsyncClient Resource Leak) — the service method should eventually use the context manager pattern for WordPressPublisher

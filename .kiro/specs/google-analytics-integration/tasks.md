# Implementation Plan: Google Analytics Integration

## Overview

This plan implements Google Search Console (GSC) and Google Analytics 4 (GA4) integration for Rext AI. The implementation follows a 100% additive approach, adding new models, services, and routes without modifying existing functionality. The system will authenticate via OAuth, allow property selection, sync 16 months of historical data, run daily incremental syncs, and expose metrics through REST APIs.

**Key Technical Approach:**
- Single OAuth flow for both GSC and GA4
- Two new database tables: `WorkspaceGoogleConnection` and `GoogleAnalyticsMetric`
- Background jobs for historical backfill and daily sync
- URL normalization at read time for article matching
- JSONB storage for flexible metrics schema

**Implementation Constraints:**
- Only 3 existing files modified (config.py, routes.py, scheduled_tasks.py)
- All modifications are additive (append-only)
- Reuse existing OAuthAccount and ContentPublishingResult models
- Follow existing patterns from Shopify integration

## Tasks

- [ ] 1. Foundation - Database Models and Configuration
  - [x] 1.1 Create WorkspaceGoogleConnection model
    - Create file `src/api/models/integrations/workspace_google_connection.py`
    - Implement model with all fields: workspace_id, oauth_account_id, gsc_site_url, ga4_property_id, last_synced_at, last_backfill_completed_at
    - Add unique constraint on workspace_id
    - Add foreign key constraints with CASCADE and SET NULL
    - Add indexes on workspace_id and oauth_account_id
    - _Requirements: 15.1, 4.1, 4.2, 8.4_
  
  - [x] 1.2 Create GoogleAnalyticsMetric model
    - Create file `src/api/models/analytics/google_analytics_metric.py`
    - Implement model with fields: workspace_id, article_external_url, date, source, metrics (JSONB), query_keyword
    - Add composite index: (workspace_id, article_external_url, date, source)
    - Add unique constraint: (workspace_id, article_external_url, date, source, query_keyword)
    - Include workspace relationship
    - _Requirements: 15.2, 15.4, 15.5, 6.3, 7.2_
  
  - [x] 1.3 Create Alembic migration for new tables
    - Create migration file in `alembic/versions/` with naming convention: `YYYYMMDD_add_google_analytics_integration.py`
    - Add workspace_google_connections table creation
    - Add google_analytics_metrics table creation
    - Include all indexes and constraints
    - Add upgrade() and downgrade() functions
    - _Requirements: 15.1, 15.2, 13.1_
  
  - [x] 1.4 Add Google OAuth configuration settings
    - Update `src/api/config.py` with GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET settings
    - Add GOOGLE_OAUTH_REDIRECT_PATH setting
    - Add GOOGLE_INTEGRATION_RETURN_PATH setting
    - Add GOOGLE_SYNC_ENABLED boolean flag
    - All modifications must be additive (append to Settings class)
    - _Requirements: 13.4, 9.1_
  
  - [ ] 1.5 Add WorkspaceModel relationship
    - Update `src/api/models/workspace_model.py`
    - Add google_connection relationship (one-to-one with WorkspaceGoogleConnection)
    - Set uselist=False for one-to-one relationship
    - Modification must be additive only
    - _Requirements: 13.1, 2.4_

- [ ] 2. Checkpoint - Foundation complete
  - Ensure all tests pass, verify migration runs successfully, ask user if questions arise.

- [ ] 3. OAuth Authentication Flow
  - [x] 3.1 Create Pydantic schemas for Google integration
    - Create file `src/api/schemas/integrations/google_schema.py`
    - Define GoogleConnectStartRequest schema (return_path field)
    - Define GoogleSelectionsRequest schema (gsc_site_url, ga4_property_id fields)
    - Define GoogleConnectionStatus schema with all status fields
    - Define GoogleSiteResponse and GooglePropertyResponse schemas
    - _Requirements: 1.1, 2.2, 3.2, 12.1, 12.5_
  
  - [ ] 3.2 Implement GoogleOAuthService
    - Create file `src/services/google_oauth_service.py`
    - Implement build_oauth_url() method with GSC and GA4 scopes
    - Use JWT-signed state parameter (similar to Shopify integration pattern)
    - Scopes: webmasters.readonly and analytics.readonly
    - _Requirements: 1.1, 13.5_
  
  - [ ] 3.3 Implement OAuth callback handler in GoogleOAuthService
    - Implement handle_oauth_callback() method
    - Exchange authorization code for access and refresh tokens
    - Store tokens in OAuthAccount table with provider='google'
    - Extract workspace_id and return_path from JWT state
    - Handle OAuth errors gracefully
    - _Requirements: 1.2, 1.3, 1.5, 13.1_
  
  - [ ] 3.4 Implement token refresh in GoogleOAuthService
    - Implement refresh_token() method
    - Check token_expires_at and refresh proactively
    - Update OAuthAccount record with new tokens
    - Handle refresh failures with descriptive errors
    - _Requirements: 1.3_
  
  - [ ] 3.5 Implement get_valid_token() helper in GoogleOAuthService
    - Get valid access token for a workspace
    - Automatically refresh if expired
    - Raise ResourceNotFoundException if no OAuth account exists
    - _Requirements: 1.3, 9.4_
  
  - [ ] 3.6 Create OAuth route handlers
    - Create file `src/api/routes/integrations/google.py`
    - Implement POST /connect/start endpoint
    - Implement GET /connect/callback endpoint with HTTP 302 redirect
    - Build frontend redirect URLs with status parameters
    - Use workspace-scoped authentication for /start
    - _Requirements: 12.1, 12.2, 1.4_

- [ ] 4. Checkpoint - OAuth flow complete
  - Ensure all tests pass, manually test OAuth flow if possible, ask user if questions arise.

- [ ] 5. Connection Management
  - [ ] 5.1 Create GoogleConnectionService
    - Create file `src/services/google_connection_service.py`
    - Initialize with AsyncSession and GoogleOAuthService
    - Set up httpx.AsyncClient for API calls
    - _Requirements: 2.1, 3.1, 13.5_
  
  - [ ] 5.2 Implement list_gsc_sites() method
    - Call Google Search Console API: GET /webmasters/v3/sites
    - Parse siteEntry list from response
    - Return list of dicts with site_url and permission_level
    - Handle API errors with descriptive messages
    - _Requirements: 2.1, 12.3_
  
  - [ ] 5.3 Implement list_ga4_properties() method
    - Call Google Analytics Admin API: GET /v1beta/properties
    - Parse properties list from response
    - Return list of dicts with property_id, display_name, property_type
    - Handle API errors with descriptive messages
    - _Requirements: 3.1, 12.4_
  
  - [ ] 5.4 Implement auto_suggest_gsc_site() method
    - Query workspace.site_url from database
    - Normalize and match against available GSC sites
    - Return matching site_url or None
    - _Requirements: 2.2_
  
  - [ ] 5.5 Implement save_selections() method
    - Create or update WorkspaceGoogleConnection record
    - Store gsc_site_url and ga4_property_id
    - Link to oauth_account_id
    - Check if first connection (no last_backfill_completed_at)
    - Return WorkspaceGoogleConnection instance
    - _Requirements: 2.3, 2.5, 3.2, 3.4, 8.1_
  
  - [ ] 5.6 Implement get_connection_status() method
    - Query WorkspaceGoogleConnection for workspace
    - Join with OAuthAccount to get email
    - Return status dict with all fields
    - Return is_connected=false if no connection exists
    - _Requirements: 4.1, 4.4_
  
  - [ ] 5.7 Implement disconnect() method
    - Delete WorkspaceGoogleConnection record
    - Preserve GoogleAnalyticsMetric historical data
    - Do not delete OAuthAccount (may be used by other workspaces)
    - _Requirements: 4.2, 4.3_
  
  - [ ] 5.8 Create connection management route handlers
    - Implement GET /gsc/sites endpoint
    - Implement GET /ga4/properties endpoint with auto-suggestion
    - Implement POST /connect/select endpoint
    - Implement GET /status endpoint
    - Implement DELETE /disconnect endpoint
    - All endpoints require workspace-scoped authentication
    - _Requirements: 12.3, 12.4, 12.5, 12.6, 12.7, 12.8_

- [ ] 6. Checkpoint - Connection management complete
  - Ensure all tests pass, verify connection endpoints work, ask user if questions arise.

- [ ] 7. URL Normalization Utility
  - [ ] 7.1 Implement URL normalizer function
    - Create file `src/utils/url_normalizer.py`
    - Implement normalize_url() function
    - Convert to lowercase (scheme, netloc, path)
    - Remove trailing slash (except root path "/")
    - Remove URL fragments (# anchors)
    - Preserve query parameters
    - Handle edge cases: empty URL, root URL, relative URLs
    - _Requirements: 14.1, 14.2, 14.3, 14.4, 14.5, 5.2, 5.3_

- [ ] 8. Data Synchronization Service
  - [ ] 8.1 Create GoogleAnalyticsSyncService foundation
    - Create file `src/services/google_analytics_sync_service.py`
    - Initialize with AsyncSession and GoogleOAuthService
    - Set up httpx.AsyncClient with timeout configuration
    - Import normalize_url utility
    - _Requirements: 5.1, 6.1, 7.1, 13.5_
  
  - [ ] 8.2 Implement get_published_articles() helper method
    - Query ContentPublishingResult where external_url IS NOT NULL
    - Join with Content table to filter by workspace_id
    - Return distinct list of external URLs
    - Normalize URLs using url_normalizer
    - Handle case when no published articles exist
    - _Requirements: 5.1, 5.5, 14.1_
  
  - [ ] 8.3 Implement fetch_gsc_metrics() method
    - Call GSC Search Analytics API: POST /webmasters/v3/sites/{site}/searchAnalytics/query
    - Request dimensions: page, query, date
    - Filter by article URLs using dimensionFilterGroups
    - Batch requests for 100 URLs at a time
    - Parse response rows into list of dicts
    - Implement exponential backoff for rate limits (429 responses)
    - Handle timeout and network errors
    - _Requirements: 6.1, 6.2, 6.4, 8.2_
  
  - [ ] 8.4 Implement fetch_ga4_metrics() method
    - Call GA4 Data API: POST /analyticsdata/v1beta/{property}/runReport
    - Request dimensions: date, pagePath
    - Request metrics: sessions, activeUsers, engagementRate, conversions
    - Filter by article URLs using dimensionFilter with inListFilter
    - Batch requests for 100 URLs at a time
    - Parse response rows into list of dicts
    - Implement exponential backoff for rate limits
    - Handle API sampling warnings
    - _Requirements: 7.1, 7.3, 7.4_
  
  - [ ] 8.5 Implement store_metrics() method with UPSERT logic
    - Accept metrics list and source ('gsc' or 'ga4')
    - Build metrics JSONB objects based on source
    - Use PostgreSQL INSERT ON CONFLICT DO UPDATE
    - Update on conflict with unique constraint (workspace, url, date, source, query_keyword)
    - Return count of inserted/updated records
    - Handle IntegrityError with rollback
    - _Requirements: 6.3, 6.5, 7.2, 8.5_
  
  - [ ] 8.6 Implement sync_workspace() orchestration method
    - Get WorkspaceGoogleConnection for workspace
    - Get valid OAuth token
    - Get published articles list
    - Calculate date range (backfill: 16 months, incremental: last_synced_at to today)
    - Call fetch_gsc_metrics() with batching
    - Call fetch_ga4_metrics() with batching
    - Call store_metrics() for GSC data
    - Call store_metrics() for GA4 data
    - Update last_synced_at timestamp
    - Return summary dict with counts
    - _Requirements: 8.1, 8.2, 8.3, 9.1, 9.2, 9.3_

- [ ] 9. Checkpoint - Data sync service complete
  - Ensure all tests pass, verify sync logic with mock data, ask user if questions arise.

- [ ] 10. Background Jobs
  - [ ] 10.1 Create historical backfill task
    - Create file `src/tasks/google_backfill_task.py`
    - Implement run_google_backfill_task(workspace_id) async function
    - Call GoogleAnalyticsSyncService.sync_workspace(backfill=True)
    - Update WorkspaceGoogleConnection.last_backfill_completed_at on success
    - Log errors with workspace context
    - Use AsyncSessionLocal for database session
    - _Requirements: 8.1, 8.4_
  
  - [ ] 10.2 Implement backfill job trigger in save_selections()
    - Check if last_backfill_completed_at is None (first connection)
    - Use APScheduler's add_job() with workspace_id argument
    - Set job ID: f"google_backfill_{workspace_id}"
    - Set replace_existing=True to handle re-connections
    - Import from src.tasks.scheduled_tasks
    - _Requirements: 8.1, 8.5_
  
  - [ ] 10.3 Create daily incremental sync task
    - Create file `src/tasks/google_sync_task.py`
    - Implement run_google_daily_sync_task() async function
    - Query all WorkspaceGoogleConnection records with both gsc_site_url and ga4_property_id
    - Loop through connections and call sync_workspace(backfill=False)
    - Update last_synced_at for each workspace
    - Continue on error (don't fail entire job)
    - Log summary at completion
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_
  
  - [ ] 10.4 Register daily sync job in scheduled_tasks.py
    - Update `src/tasks/scheduled_tasks.py` (additive only)
    - Import run_google_daily_sync_task
    - Add job in ScheduledTaskManager.start() method
    - Use CronTrigger with hour=4, minute=0 (4 AM daily)
    - Check GOOGLE_SYNC_ENABLED config flag
    - Set max_instances=1 to prevent overlap
    - Log registration confirmation
    - _Requirements: 9.1, 13.2_

- [ ] 11. Checkpoint - Background jobs complete
  - Ensure all tests pass, verify job registration, ask user if questions arise.

- [ ] 12. Metrics Query Service
  - [ ] 12.1 Create GoogleMetricsService foundation
    - Create file `src/services/google_metrics_service.py`
    - Initialize with AsyncSession
    - Import normalize_url utility for URL matching
    - Set up base query builders
    - _Requirements: 10.1, 11.1, 5.3_
  
  - [ ] 12.2 Implement get_metrics() query method
    - Accept filters: workspace_id, article_id, source, start_date, end_date, limit, offset
    - Build SQLAlchemy query with filters
    - Apply URL normalization when filtering by article_id
    - Default date range: last 30 days
    - Order by date descending
    - Support pagination with limit/offset
    - Return list of dicts with all metric fields
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5_
  
  - [ ] 12.3 Implement get_article_summary() aggregation method
    - Query GoogleAnalyticsMetric grouped by article_external_url
    - Aggregate GSC metrics: total clicks, impressions, avg CTR, avg position
    - Aggregate GA4 metrics: total sessions, active users, avg engagement rate, total conversions
    - Use JSONB extraction with cast for PostgreSQL
    - Join with ContentPublishingResult and Content to get article_id and title
    - Filter by date range if provided
    - Order by total_clicks descending
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5_
  
  - [ ] 12.4 Implement get_top_queries() method
    - Query GoogleAnalyticsMetric where source='gsc'
    - Filter by workspace_id and optional article_id
    - Filter by date range if provided
    - Group by query_keyword
    - Aggregate: sum clicks, impressions, avg CTR, avg position
    - Order by clicks descending
    - Limit results (default: 20)
    - _Requirements: 6.2, 6.5_

- [ ] 13. Metrics API Endpoints
  - [ ] 13.1 Create GET /metrics endpoint
    - Add route handler in `src/api/routes/integrations/google.py`
    - Accept query parameters: workspace_id, article_id, source, start_date, end_date, limit, offset
    - Call GoogleMetricsService.get_metrics()
    - Return paginated response with total_count
    - Require workspace-scoped authentication
    - _Requirements: 10.1, 12.8_
  
  - [ ] 13.2 Create GET /articles/summary endpoint
    - Add route handler in google.py
    - Accept query parameters: workspace_id, start_date, end_date
    - Call GoogleMetricsService.get_article_summary()
    - Return list of article summaries with both GSC and GA4 metrics
    - Require workspace-scoped authentication
    - _Requirements: 11.1, 12.8_
  
  - [ ] 13.3 Create GET /articles/{article_id}/queries endpoint
    - Add route handler in google.py
    - Accept path parameter: article_id
    - Accept query parameters: workspace_id, start_date, end_date, limit
    - Call GoogleMetricsService.get_top_queries()
    - Return list of top queries with metrics
    - Require workspace-scoped authentication
    - _Requirements: 6.2, 12.8_

- [ ] 14. Checkpoint - Metrics API complete
  - Ensure all tests pass, verify all endpoints return correct data, ask user if questions arise.

- [ ] 15. Route Registration
  - [ ] 15.1 Register Google router in routes.py
    - Update `src/api/registry/routes.py` (additive only)
    - Import google router from src.api.routes.integrations.google
    - Call app.include_router with prefix "/api/v1/integrations/google"
    - Add tags=["Google Integration"]
    - _Requirements: 12.8, 13.2_

- [ ] 16. Integration Testing
  - [ ] 16.1 Write unit tests for URL normalizer
    - Create file `tests/unit/test_url_normalizer.py`
    - Test lowercase transformation
    - Test trailing slash removal
    - Test fragment removal
    - Test root path handling
    - Test query parameter preservation
    - _Requirements: 14.1, 14.2, 14.3, 14.5_
  
  - [ ] 16.2 Write unit tests for GoogleOAuthService
    - Create file `tests/unit/test_google_oauth_service.py`
    - Test build_oauth_url() with correct scopes
    - Test handle_oauth_callback() with mock Google response
    - Test refresh_token() with mock refresh endpoint
    - Test get_valid_token() with expired token auto-refresh
    - _Requirements: 1.1, 1.2, 1.3_
  
  - [ ] 16.3 Write unit tests for GoogleConnectionService
    - Create file `tests/unit/test_google_connection_service.py`
    - Test list_gsc_sites() with mock API response
    - Test list_ga4_properties() with mock API response
    - Test save_selections() creates WorkspaceGoogleConnection
    - Test auto_suggest_gsc_site() URL matching logic
    - Test disconnect() preserves metrics data
    - _Requirements: 2.1, 3.1, 2.3, 2.2, 4.2, 4.3_
  
  - [ ] 16.4 Write unit tests for GoogleAnalyticsSyncService
    - Create file `tests/unit/test_google_analytics_sync_service.py`
    - Test fetch_gsc_metrics() with mock GSC API
    - Test fetch_ga4_metrics() with mock GA4 API
    - Test store_metrics() UPSERT behavior
    - Test sync_workspace() date range calculation
    - Test batching logic for 100+ URLs
    - _Requirements: 6.1, 7.1, 8.5, 9.2_
  
  - [ ] 16.5 Write unit tests for GoogleMetricsService
    - Create file `tests/unit/test_google_metrics_service.py`
    - Test get_metrics() with various filters
    - Test get_article_summary() aggregation
    - Test get_top_queries() ranking
    - Test URL normalization in queries
    - _Requirements: 10.1, 11.1, 6.2_
  
  - [ ] 16.6 Write integration tests for OAuth flow
    - Create file `tests/integration/test_google_oauth_flow.py`
    - Test complete OAuth flow from start to callback
    - Test token refresh on expiration
    - Test error handling for cancelled OAuth
    - Mock all external Google API calls
    - _Requirements: 1.1, 1.2, 1.3, 1.4_
  
  - [ ] 16.7 Write integration tests for data sync
    - Create file `tests/integration/test_google_data_sync.py`
    - Test backfill job with 16-month date range
    - Test incremental sync with last_synced_at
    - Test URL matching between Google data and articles
    - Test handling of unmatched URLs
    - Mock ContentPublishingResult data
    - _Requirements: 8.1, 8.2, 9.1, 5.2, 5.5_
  
  - [ ] 16.8 Write API tests for all endpoints
    - Create file `tests/api/test_google_routes.py`
    - Test POST /connect/start returns auth URL
    - Test GET /connect/callback redirects correctly
    - Test GET /gsc/sites returns site list
    - Test GET /ga4/properties returns property list
    - Test POST /connect/select saves connection
    - Test GET /status returns connection state
    - Test DELETE /disconnect removes connection
    - Test GET /metrics with filters
    - Test GET /articles/summary aggregation
    - Test GET /articles/{id}/queries
    - Use FastAPI TestClient with mocked services
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 12.6, 12.7, 10.1, 11.1_

- [ ] 17. Final Checkpoint - Complete integration
  - Run full test suite
  - Verify migration applies cleanly
  - Test OAuth flow end-to-end
  - Verify data sync with test workspace
  - Confirm all API endpoints work
  - Ask user if questions arise before marking complete

## Notes

- **Additive Implementation Constraint**: Only 3 files are modified (config.py, routes.py, scheduled_tasks.py), and all modifications are append-only additions.
- **URL Normalization**: Applied at read time when querying metrics, not when storing data. This avoids database schema changes.
- **OAuth Token Storage**: Reuses existing OAuthAccount table with provider='google', no new OAuth infrastructure needed.
- **Metrics JSONB Schema**: Flexible structure allows different metrics for GSC (clicks, impressions, CTR, position) vs GA4 (sessions, active_users, engagement_rate, conversions).
- **Query-Level GSC Data**: GoogleAnalyticsMetric stores one row per (article, date, query keyword) for GSC, enabling top queries analysis.
- **Background Job Patterns**: Follows existing scheduled_tasks.py patterns, using APScheduler with CronTrigger for daily sync and one-time backfill jobs.
- **Batching Strategy**: Both GSC and GA4 API calls batch 100 URLs per request to respect API limits and avoid timeouts.
- **Error Handling**: Sync service continues on per-workspace errors to avoid failing entire job. Token refresh is automatic and transparent.
- **Rate Limiting**: Implements exponential backoff on 429 responses from Google APIs.
- **Testing Strategy**: Tasks marked with `*` are optional testing tasks. Core implementation tasks are unmarked and must be completed.

## Task Dependency Graph

```json
{
  "waves": [
    {
      "id": 0,
      "tasks": ["1.1", "1.2", "1.4"]
    },
    {
      "id": 1,
      "tasks": ["1.3", "1.5", "3.1", "7.1"]
    },
    {
      "id": 2,
      "tasks": ["3.2", "3.3", "3.4", "3.5"]
    },
    {
      "id": 3,
      "tasks": ["3.6", "5.1"]
    },
    {
      "id": 4,
      "tasks": ["5.2", "5.3", "5.4"]
    },
    {
      "id": 5,
      "tasks": ["5.5", "5.6", "5.7"]
    },
    {
      "id": 6,
      "tasks": ["5.8", "8.1"]
    },
    {
      "id": 7,
      "tasks": ["8.2", "8.3", "8.4"]
    },
    {
      "id": 8,
      "tasks": ["8.5", "8.6"]
    },
    {
      "id": 9,
      "tasks": ["10.1", "10.3", "12.1"]
    },
    {
      "id": 10,
      "tasks": ["10.2", "10.4", "12.2", "12.3", "12.4"]
    },
    {
      "id": 11,
      "tasks": ["13.1", "13.2", "13.3"]
    },
    {
      "id": 12,
      "tasks": ["15.1"]
    },
    {
      "id": 13,
      "tasks": ["16.1", "16.2", "16.3", "16.4", "16.5", "16.6", "16.7", "16.8"]
    }
  ]
}
```

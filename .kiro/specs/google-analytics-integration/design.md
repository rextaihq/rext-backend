# Technical Design Document: Google Analytics Integration

## Overview

This document specifies the technical design for integrating Google Search Console (GSC) and Google Analytics 4 (GA4) with Rext AI. The integration provides OAuth-based authentication, property selection, automated data synchronization, and REST API access to analytics metrics.

### Design Goals

1. **Single OAuth Flow**: Authenticate both GSC and GA4 services with one user consent
2. **100% Additive Implementation**: No modifications to existing models or business logic
3. **Scalable Data Sync**: Handle 16-month historical backfill + daily incremental updates
4. **URL Normalization**: Match Google data to published articles using normalized URLs
5. **RESTful API Access**: Expose metrics through clean, filterable endpoints

### Key Constraints

- **Additive Only**: Only 3 existing files may be modified (config.py, routes.py, scheduled_tasks.py)
- **Reuse External URL**: Leverage ContentPublishingResult.external_url without modification
- **URL Normalization at Read Time**: No database schema changes for URL storage
- **Follow Existing Patterns**: Mirror shopify.py and scheduled_tasks.py implementations

## Architecture

### High-Level Components

```
┌─────────────────────────────────────────────────────────────┐
│                        Frontend UI                          │
│  (Connection Setup, Property Selection, Metrics Dashboard)  │
└────────────────────┬────────────────────────────────────────┘
                     │ HTTPS
                     ▼
┌─────────────────────────────────────────────────────────────┐
│                   Google Analytics API Routes                │
│        /api/v1/integrations/google/* endpoints              │
└───────────┬────────────────────────────┬────────────────────┘
            │                            │
            ▼                            ▼
┌───────────────────────┐    ┌──────────────────────────────┐
│   OAuth Manager       │    │   Connection Manager         │
│   - Initiate flow     │    │   - List GSC sites          │
│   - Handle callback   │    │   - List GA4 properties     │
│   - Token refresh     │    │   - Save selections         │
│   - Store tokens      │    │   - Connection status       │
└───────┬───────────────┘    └────────┬─────────────────────┘
        │                              │
        ▼                              ▼
┌─────────────────────────────────────────────────────────────┐
│                     Database Models                          │
│  - OAuthAccount (existing, reused)                          │
│  - WorkspaceGoogleConnection (new)                          │
│  - GoogleAnalyticsMetric (new)                              │
│  - ContentPublishingResult.external_url (existing, reused)  │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                 Data Sync Service (Background)               │
│  - 16-month historical backfill (on first connect)          │
│  - Daily incremental sync (scheduled task)                  │
│  - Fetch GSC metrics (clicks, impressions, CTR, position)   │
│  - Fetch GA4 metrics (sessions, users, engagement)          │
│  - URL normalization and article matching                   │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                  Google APIs (External)                      │
│  - Google OAuth 2.0                                         │
│  - Google Search Console API                                │
│  - Google Analytics Data API (GA4)                          │
└─────────────────────────────────────────────────────────────┘
```

### OAuth Flow Architecture

```
User initiates → Frontend redirects → Google OAuth consent
                                           ↓
                                    User grants permission
                                           ↓
                  Callback endpoint ← Google redirects back
                        ↓
              Store tokens in OAuthAccount
                        ↓
              List available properties
                        ↓
         User selects GSC site + GA4 property
                        ↓
       Save to WorkspaceGoogleConnection
                        ↓
              Trigger 16-month backfill
```

### Data Sync Architecture

```
Scheduled Task (daily 4 AM)
         ↓
   For each workspace with connection
         ↓
   ┌─────────────────────────────────────┐
   │ Get published articles (external_url not null) │
   └─────────────────────────────────────┘
         ↓
   ┌─────────────────────────────────────┐
   │ Normalize URLs (lowercase, strip trailing slash) │
   └─────────────────────────────────────┘
         ↓
   ┌─────────────────────────────────────┐
   │ Fetch GSC metrics for each URL     │
   │ - Batch API calls (100 URLs/request) │
   │ - Date range: last_synced_at → today │
   └─────────────────────────────────────┘
         ↓
   ┌─────────────────────────────────────┐
   │ Fetch GA4 metrics for each URL     │
   │ - Batch API calls                   │
   │ - Date range: last_synced_at → today │
   └─────────────────────────────────────┘
         ↓
   ┌─────────────────────────────────────┐
   │ Store metrics in GoogleAnalyticsMetric │
   │ - Deduplicate by (workspace, url, date, source, query) │
   └─────────────────────────────────────┘
         ↓
   Update WorkspaceGoogleConnection.last_synced_at
```

## Database Schema

### New Table: WorkspaceGoogleConnection

Stores workspace-level Google integration configuration.

```python
class WorkspaceGoogleConnection(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    Workspace-level Google integration state.
    Stores selected GSC site and GA4 property.
    """
    __tablename__ = "workspace_google_connections"
    __table_args__ = (
        UniqueConstraint("workspace_id", name="uq_workspace_google_connection"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspace.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        unique=True,
    )

    oauth_account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("oauth_accounts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # GSC configuration
    gsc_site_url: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
        comment="Selected GSC site URL (e.g., https://example.com/)"
    )

    # GA4 configuration
    ga4_property_id: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="Selected GA4 property ID (e.g., properties/123456789)"
    )

    # Sync tracking
    last_synced_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Last successful incremental sync timestamp"
    )

    last_backfill_completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp when 16-month backfill completed"
    )

    # Relationships
    workspace = relationship("WorkspaceModel", back_populates="google_connection")
    oauth_account = relationship("OAuthAccount")
```

**Indexes:**
- Primary key: `id` (UUID)
- Unique: `workspace_id`
- Foreign key indexes: `workspace_id`, `oauth_account_id`

### New Table: GoogleAnalyticsMetric

Stores daily metrics for published articles from GSC and GA4.

```python
class GoogleAnalyticsMetric(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    Daily analytics metrics for published articles.
    Stores both GSC and GA4 data with flexible schema.
    """
    __tablename__ = "google_analytics_metrics"
    __table_args__ = (
        Index(
            "ix_ga_metrics_workspace_url_date_source",
            "workspace_id", "article_external_url", "date", "source"
        ),
        UniqueConstraint(
            "workspace_id", "article_external_url", "date", "source", "query_keyword",
            name="uq_ga_metric_unique"
        ),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspace.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Article identification (using external_url from ContentPublishingResult)
    article_external_url: Mapped[str] = mapped_column(
        String(1000),
        nullable=False,
        comment="Normalized external URL from ContentPublishingResult"
    )

    # Temporal dimension
    date: Mapped[datetime.date] = mapped_column(
        Date,
        nullable=False,
        index=True,
        comment="Date for which metrics are recorded"
    )

    # Source: 'gsc' or 'ga4'
    source: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        comment="Data source: 'gsc' or 'ga4'"
    )

    # Metric storage (flexible JSONB for extensibility)
    metrics: Mapped[Dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        comment="Metrics object: {clicks, impressions, ctr, position} for GSC or {sessions, active_users, engagement_rate, conversions} for GA4"
    )

    # GSC-specific: keyword/query dimension
    query_keyword: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
        comment="Search query keyword (GSC only, NULL for GA4)"
    )

    # Relationships
    workspace = relationship("WorkspaceModel")
```

**Indexes:**
- Primary key: `id` (UUID)
- Composite: `(workspace_id, article_external_url, date, source)` for query performance
- Unique constraint: `(workspace_id, article_external_url, date, source, query_keyword)` for deduplication

**Metrics JSONB Structure:**

For GSC (`source='gsc'`):
```json
{
  "clicks": 42,
  "impressions": 1234,
  "ctr": 0.034,
  "position": 12.5
}
```

For GA4 (`source='ga4'`):
```json
{
  "sessions": 156,
  "active_users": 89,
  "engagement_rate": 0.67,
  "conversions": 3
}
```

### Existing Table: OAuthAccount (Reused, No Modifications)

The existing `OAuthAccount` model stores Google OAuth tokens:

```python
# Existing fields used by this integration:
# - provider: 'google'
# - user_id: Foreign key to users table
# - access_token: OAuth access token (encrypted)
# - refresh_token: OAuth refresh token (encrypted)
# - token_expires_at: Expiration timestamp
# - provider_account_email: Google account email
```

### Existing Table: ContentPublishingResult (Reused, No Modifications)

```python
# Existing field used by this integration:
# - external_url: Published article URL (e.g., https://example.com/blog/my-article)
# - content_id: Foreign key to content table
```

## Components and Interfaces

### 1. OAuth Manager

**File:** `src/services/google_oauth_service.py`

**Responsibilities:**
- Initiate Google OAuth flow with combined GSC + GA4 scopes
- Handle OAuth callback and token exchange
- Store tokens in OAuthAccount table
- Refresh expired tokens automatically

**Public Interface:**

```python
class GoogleOAuthService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def build_oauth_url(
        self,
        *,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        callback_url: str,
        return_path: Optional[str] = None,
    ) -> str:
        """
        Build Google OAuth authorization URL with GSC + GA4 scopes.
        
        Scopes requested:
        - https://www.googleapis.com/auth/webmasters.readonly (GSC)
        - https://www.googleapis.com/auth/analytics.readonly (GA4)
        """

    async def handle_oauth_callback(
        self,
        *,
        code: str,
        state: str,
    ) -> Dict[str, Any]:
        """
        Exchange authorization code for tokens and store in OAuthAccount.
        Returns: {workspace_id, user_id, oauth_account_id, return_path}
        """

    async def refresh_token(
        self,
        oauth_account: OAuthAccount,
    ) -> OAuthAccount:
        """
        Refresh expired access token using refresh token.
        Updates OAuthAccount in database.
        """

    async def get_valid_token(
        self,
        workspace_id: uuid.UUID,
    ) -> str:
        """
        Get a valid access token for a workspace.
        Automatically refreshes if expired.
        Raises: ResourceNotFoundException if no OAuth account exists
        """
```

**Key Implementation Details:**

1. **State Management:** Use JWT-signed state parameter (similar to Shopify integration)
   ```python
   state_payload = {
       "workspace_id": str(workspace_id),
       "user_id": str(user_id),
       "return_path": return_path,
       "exp": datetime.now(timezone.utc) + timedelta(minutes=15),
       "type": "google_oauth_state",
   }
   state = jwt.encode(state_payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
   ```

2. **Token Storage:** Store in OAuthAccount with `provider='google'`

3. **Token Refresh:** Check `token_expires_at`, refresh proactively before expiration

### 2. Connection Manager

**File:** `src/services/google_connection_service.py`

**Responsibilities:**
- List available GSC sites using Google Search Console API
- List available GA4 properties using Google Analytics Admin API
- Save user's property selections to WorkspaceGoogleConnection
- Check connection status
- Disconnect integration

**Public Interface:**

```python
class GoogleConnectionService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.oauth_service = GoogleOAuthService(db)

    async def list_gsc_sites(
        self,
        workspace_id: uuid.UUID,
    ) -> List[Dict[str, str]]:
        """
        List GSC sites accessible with workspace's OAuth token.
        Returns: [{"site_url": "https://example.com/", "permission_level": "owner"}, ...]
        """

    async def list_ga4_properties(
        self,
        workspace_id: uuid.UUID,
    ) -> List[Dict[str, str]]:
        """
        List GA4 properties accessible with workspace's OAuth token.
        Returns: [{"property_id": "properties/123456789", "display_name": "My Website", "property_type": "PROPERTY_TYPE_ORDINARY"}, ...]
        """

    async def save_selections(
        self,
        *,
        workspace_id: uuid.UUID,
        oauth_account_id: uuid.UUID,
        gsc_site_url: str,
        ga4_property_id: str,
    ) -> WorkspaceGoogleConnection:
        """
        Save selected GSC site and GA4 property.
        Creates or updates WorkspaceGoogleConnection.
        Triggers 16-month backfill job if first connection.
        """

    async def get_connection_status(
        self,
        workspace_id: uuid.UUID,
    ) -> Optional[Dict[str, Any]]:
        """
        Get connection status for a workspace.
        Returns: {
            "is_connected": bool,
            "gsc_site_url": str,
            "ga4_property_id": str,
            "last_synced_at": str,
            "last_backfill_completed_at": str,
            "oauth_account_email": str,
        }
        """

    async def disconnect(
        self,
        workspace_id: uuid.UUID,
    ) -> None:
        """
        Remove Google integration for workspace.
        Deletes WorkspaceGoogleConnection but preserves GoogleAnalyticsMetric history.
        """

    async def auto_suggest_gsc_site(
        self,
        workspace_id: uuid.UUID,
        available_sites: List[Dict[str, str]],
    ) -> Optional[str]:
        """
        Auto-suggest GSC site based on workspace.site_url.
        Returns matching site URL if found, else None.
        """
```

**Key Implementation Details:**

1. **GSC Sites API:** `GET https://www.googleapis.com/webmasters/v3/sites`
   ```json
   {
     "siteEntry": [
       {
         "siteUrl": "https://example.com/",
         "permissionLevel": "owner"
       }
     ]
   }
   ```

2. **GA4 Properties API:** `GET https://analyticsadmin.googleapis.com/v1beta/properties`
   ```json
   {
     "properties": [
       {
         "name": "properties/123456789",
         "displayName": "My Website",
         "propertyType": "PROPERTY_TYPE_ORDINARY"
       }
     ]
   }
   ```

3. **Backfill Trigger:** After saving selections, enqueue background job for historical data fetch

### 3. Data Sync Service

**File:** `src/services/google_analytics_sync_service.py`

**Responsibilities:**
- Fetch GSC metrics for published articles
- Fetch GA4 metrics for published articles
- Normalize URLs for matching
- Store metrics in GoogleAnalyticsMetric table
- Handle backfill and incremental sync

**Public Interface:**

```python
class GoogleAnalyticsSyncService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.oauth_service = GoogleOAuthService(db)

    async def sync_workspace(
        self,
        workspace_id: uuid.UUID,
        *,
        backfill: bool = False,
    ) -> Dict[str, Any]:
        """
        Sync metrics for a workspace.
        If backfill=True, fetch 16 months of historical data.
        Otherwise, fetch incrementally from last_synced_at.
        Returns: {"articles_synced": int, "gsc_records": int, "ga4_records": int}
        """

    async def fetch_gsc_metrics(
        self,
        *,
        access_token: str,
        site_url: str,
        article_urls: List[str],
        start_date: datetime.date,
        end_date: datetime.date,
    ) -> List[Dict[str, Any]]:
        """
        Fetch GSC metrics for multiple URLs.
        Returns: [{"url": str, "date": date, "clicks": int, "impressions": int, "ctr": float, "position": float, "query": str}, ...]
        """

    async def fetch_ga4_metrics(
        self,
        *,
        access_token: str,
        property_id: str,
        article_urls: List[str],
        start_date: datetime.date,
        end_date: datetime.date,
    ) -> List[Dict[str, Any]]:
        """
        Fetch GA4 metrics for multiple URLs.
        Returns: [{"url": str, "date": date, "sessions": int, "active_users": int, "engagement_rate": float, "conversions": int}, ...]
        """

    async def store_metrics(
        self,
        *,
        workspace_id: uuid.UUID,
        metrics: List[Dict[str, Any]],
        source: str,
    ) -> int:
        """
        Store metrics in GoogleAnalyticsMetric table.
        Uses UPSERT to handle duplicate (workspace, url, date, source, query) combinations.
        Returns: Number of records inserted/updated
        """
```

**Key Implementation Details:**

1. **Get Published Articles:**
   ```python
   stmt = (
       select(ContentPublishingResult.external_url)
       .where(
           ContentPublishingResult.content_id.in_(
               select(Content.id).where(Content.workspace_id == workspace_id)
           ),
           ContentPublishingResult.external_url.isnot(None),
       )
       .distinct()
   )
   ```

2. **GSC API Request (Search Analytics):**
   ```python
   # POST https://www.googleapis.com/webmasters/v3/sites/{siteUrl}/searchAnalytics/query
   {
     "startDate": "2024-01-01",
     "endDate": "2024-01-31",
     "dimensions": ["page", "query", "date"],
     "rowLimit": 25000,
     "dimensionFilterGroups": [
       {
         "filters": [
           {
             "dimension": "page",
             "expression": "https://example.com/blog/article-1",
             "operator": "equals"
           }
         ]
       }
     ]
   }
   ```

3. **GA4 API Request (Data API):**
   ```python
   # POST https://analyticsdata.googleapis.com/v1beta/{property}/runReport
   {
     "dateRanges": [{"startDate": "2024-01-01", "endDate": "2024-01-31"}],
     "dimensions": [{"name": "date"}, {"name": "pagePath"}],
     "metrics": [
       {"name": "sessions"},
       {"name": "activeUsers"},
       {"name": "engagementRate"},
       {"name": "conversions"}
     ],
     "dimensionFilter": {
       "filter": {
         "fieldName": "pagePath",
         "inListFilter": {
           "values": ["/blog/article-1", "/blog/article-2"]
         }
       }
     }
   }
   ```

4. **Batching Strategy:**
   - GSC: 100 URLs per request (API limit: 25,000 rows)
   - GA4: 100 URLs per request (API limit: 100,000 rows)
   - Date range: Max 16 months for backfill, daily increments for sync

5. **Rate Limiting:**
   - GSC: 1,200 queries per minute per project
   - GA4: 40,000 tokens per day per property
   - Implement exponential backoff on 429 responses

6. **UPSERT Logic:**
   ```python
   # PostgreSQL INSERT ... ON CONFLICT DO UPDATE
   stmt = insert(GoogleAnalyticsMetric).values(records)
   stmt = stmt.on_conflict_do_update(
       constraint="uq_ga_metric_unique",
       set_={
           "metrics": stmt.excluded.metrics,
           "updated_at": datetime.now(timezone.utc),
       }
   )
   ```

### 4. URL Normalizer Utility

**File:** `src/utils/url_normalizer.py`

**Responsibilities:**
- Normalize URLs for consistent matching
- Apply at read time (when querying metrics, not when storing)

**Public Interface:**

```python
def normalize_url(url: str) -> str:
    """
    Normalize URL for consistent matching.
    
    Transformations:
    - Convert to lowercase
    - Remove trailing slash (except root path)
    - Remove URL fragments (# anchors)
    - Preserve protocol (http/https)
    - Preserve query parameters
    
    Examples:
    - "https://Example.com/Blog/" → "https://example.com/blog"
    - "https://example.com/blog#section" → "https://example.com/blog"
    - "https://example.com/" → "https://example.com/"
    - "https://example.com" → "https://example.com/"
    """
```

**Implementation:**

```python
from urllib.parse import urlparse, urlunparse

def normalize_url(url: str) -> str:
    if not url:
        return url
    
    parsed = urlparse(url)
    
    # Lowercase scheme, netloc, and path
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    path = parsed.path.lower()
    
    # Remove trailing slash (except for root)
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    
    # Ensure root path has slash
    if not path and netloc:
        path = "/"
    
    # Remove fragment
    fragment = ""
    
    # Preserve query
    query = parsed.query
    
    return urlunparse((scheme, netloc, path, parsed.params, query, fragment))
```

### 5. Metrics API Service

**File:** `src/services/google_metrics_service.py`

**Responsibilities:**
- Query GoogleAnalyticsMetric table with filters
- Aggregate metrics by article
- Apply URL normalization at read time

**Public Interface:**

```python
class GoogleMetricsService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_metrics(
        self,
        *,
        workspace_id: uuid.UUID,
        article_id: Optional[uuid.UUID] = None,
        source: Optional[str] = None,
        start_date: Optional[datetime.date] = None,
        end_date: Optional[datetime.date] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        Query metrics with filters.
        Returns: [{"date": "2024-01-15", "url": "...", "source": "gsc", "metrics": {...}, "query_keyword": "..."}, ...]
        """

    async def get_article_summary(
        self,
        *,
        workspace_id: uuid.UUID,
        start_date: Optional[datetime.date] = None,
        end_date: Optional[datetime.date] = None,
    ) -> List[Dict[str, Any]]:
        """
        Aggregate metrics by article.
        Returns: [{
            "article_id": uuid,
            "external_url": str,
            "title": str,
            "total_clicks": int,
            "total_impressions": int,
            "avg_ctr": float,
            "avg_position": float,
            "total_sessions": int,
            "total_active_users": int,
            "avg_engagement_rate": float,
            "total_conversions": int,
        }, ...]
        """

    async def get_top_queries(
        self,
        *,
        workspace_id: uuid.UUID,
        article_id: Optional[uuid.UUID] = None,
        start_date: Optional[datetime.date] = None,
        end_date: Optional[datetime.date] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """
        Get top search queries for articles.
        Returns: [{"query": "my keyword", "clicks": 150, "impressions": 5000, "ctr": 0.03, "position": 8.2}, ...]
        """
```

**Key Implementation Details:**

1. **URL Normalization at Read Time:**
   ```python
   # When querying by article_id, normalize ContentPublishingResult.external_url
   article_url = normalize_url(publishing_result.external_url)
   
   # Query metrics where article_external_url matches normalized URL
   stmt = select(GoogleAnalyticsMetric).where(
       GoogleAnalyticsMetric.workspace_id == workspace_id,
       GoogleAnalyticsMetric.article_external_url == article_url,
   )
   ```

2. **Aggregation Queries:**
   ```python
   # PostgreSQL aggregation with JSONB extraction
   stmt = (
       select(
           GoogleAnalyticsMetric.article_external_url,
           func.sum(GoogleAnalyticsMetric.metrics["clicks"].cast(Integer)).label("total_clicks"),
           func.sum(GoogleAnalyticsMetric.metrics["impressions"].cast(Integer)).label("total_impressions"),
           func.avg(GoogleAnalyticsMetric.metrics["ctr"].cast(Float)).label("avg_ctr"),
           func.avg(GoogleAnalyticsMetric.metrics["position"].cast(Float)).label("avg_position"),
       )
       .where(
           GoogleAnalyticsMetric.workspace_id == workspace_id,
           GoogleAnalyticsMetric.source == "gsc",
       )
       .group_by(GoogleAnalyticsMetric.article_external_url)
   )
   ```

## Background Jobs

### 1. Historical Backfill Job

**Trigger:** When user saves GSC site + GA4 property selections for the first time

**File:** `src/tasks/google_backfill_task.py`

**Implementation:**

```python
async def run_google_backfill_task(workspace_id: uuid.UUID) -> None:
    """
    Fetch 16 months of historical data for a workspace.
    Runs once when connection is first established.
    """
    logger.info(f"[GoogleBackfill] Starting for workspace={workspace_id}")
    
    async with AsyncSessionLocal() as db:
        sync_service = GoogleAnalyticsSyncService(db)
        
        try:
            result = await sync_service.sync_workspace(
                workspace_id=workspace_id,
                backfill=True,
            )
            
            # Update last_backfill_completed_at
            stmt = (
                update(WorkspaceGoogleConnection)
                .where(WorkspaceGoogleConnection.workspace_id == workspace_id)
                .values(last_backfill_completed_at=datetime.now(timezone.utc))
            )
            await db.execute(stmt)
            await db.commit()
            
            logger.info(
                f"[GoogleBackfill] Completed for workspace={workspace_id}",
                extra=result
            )
        except Exception as e:
            logger.error(
                f"[GoogleBackfill] Failed for workspace={workspace_id}: {e}",
                exc_info=True
            )
            raise
```

**Execution:** Use APScheduler's `add_job` with `run_date` parameter for one-time execution:

```python
from src.tasks.scheduled_tasks import task_manager

task_manager.scheduler.add_job(
    run_google_backfill_task,
    args=[workspace_id],
    id=f"google_backfill_{workspace_id}",
    name=f"Google Analytics backfill for workspace {workspace_id}",
    replace_existing=True,
)
```

### 2. Daily Incremental Sync Job

**Trigger:** Scheduled daily at 4:00 AM

**File:** `src/tasks/google_sync_task.py`

**Implementation:**

```python
async def run_google_daily_sync_task() -> None:
    """
    Sync Google Analytics metrics for all connected workspaces.
    Runs daily via scheduled task.
    """
    logger.info("[GoogleDailySync] Task fired.")
    
    async with AsyncSessionLocal() as db:
        # Get all workspaces with Google connections
        stmt = select(WorkspaceGoogleConnection).where(
            WorkspaceGoogleConnection.gsc_site_url.isnot(None),
            WorkspaceGoogleConnection.ga4_property_id.isnot(None),
        )
        connections = (await db.execute(stmt)).scalars().all()
        
        if not connections:
            logger.info("[GoogleDailySync] No connected workspaces.")
            return
        
        logger.info(f"[GoogleDailySync] Syncing {len(connections)} workspace(s).")
        
        sync_service = GoogleAnalyticsSyncService(db)
        
        for connection in connections:
            try:
                result = await sync_service.sync_workspace(
                    workspace_id=connection.workspace_id,
                    backfill=False,
                )
                
                # Update last_synced_at
                connection.last_synced_at = datetime.now(timezone.utc)
                
                logger.info(
                    f"[GoogleDailySync] Synced workspace={connection.workspace_id}",
                    extra=result
                )
            except Exception as e:
                logger.error(
                    f"[GoogleDailySync] Failed for workspace={connection.workspace_id}: {e}",
                    exc_info=True
                )
                # Continue syncing other workspaces
        
        await db.commit()
        logger.info("[GoogleDailySync] Cycle complete.")
```

**Registration in scheduled_tasks.py (additive modification):**

```python
# Add to ScheduledTaskManager.start() method
if cleanup_config.GOOGLE_SYNC_ENABLED:  # New env var
    self.scheduler.add_job(
        run_google_daily_sync_task,
        trigger=CronTrigger(hour=4, minute=0),
        id="google_daily_sync",
        name="Daily Google Analytics sync",
        replace_existing=True,
        max_instances=1,
    )
    logger.info("Registered task: google_daily_sync")
else:
    logger.info("Google Analytics sync task disabled (GOOGLE_SYNC_ENABLED=false)")
```

## API Endpoints

**File:** `src/api/routes/integrations/google.py`

### Endpoint Specifications

#### 1. POST /api/v1/integrations/google/connect/start

**Purpose:** Initiate Google OAuth flow

**Authentication:** Workspace-scoped

**Request Body:**
```json
{
  "return_path": "/w/{workspace_slug}/integrations"
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "auth_url": "https://accounts.google.com/o/oauth2/v2/auth?client_id=...&scope=...&redirect_uri=...&state=..."
  },
  "message": "Google OAuth URL generated successfully"
}
```

**Implementation:**
```python
@router.post("/connect/start")
async def start_google_connect(
    workspace_id: uuid.UUID,
    data: GoogleConnectStartRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    _: bool = Depends(PermissionChecker(["user.read"], workspace_scoped=True)),
):
    """Initiate Google OAuth flow with GSC + GA4 scopes."""
    service = GoogleOAuthService(db)
    user_id = current_user.get("identity")
    
    base = (settings.BACKEND_URL or str(request.base_url)).rstrip("/")
    callback_url = f"{base}/api/v1/integrations/google/connect/callback"
    
    auth_url = await service.build_oauth_url(
        workspace_id=workspace_id,
        user_id=user_id,
        callback_url=callback_url,
        return_path=data.return_path,
    )
    
    return success(
        data={"auth_url": auth_url},
        message="Google OAuth URL generated successfully",
    )
```

#### 2. GET /api/v1/integrations/google/connect/callback

**Purpose:** Handle Google OAuth callback

**Authentication:** None (public callback, validated via state parameter)

**Query Parameters:**
- `code`: Authorization code from Google
- `state`: JWT-signed state parameter
- `error` (optional): Error from Google

**Response:** HTTP 302 redirect to frontend with status parameters

**Implementation:**
```python
@router.get("/connect/callback", name="google_oauth_callback")
async def google_connect_callback(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Handle Google OAuth callback and redirect to frontend."""
    service = GoogleOAuthService(db)
    query_params = {key: value for key, value in request.query_params.items()}
    
    try:
        result = await service.handle_oauth_callback(
            code=query_params.get("code"),
            state=query_params.get("state"),
        )
        
        redirect_url = build_frontend_redirect_url(
            status="connected",
            workspace_id=result["workspace_id"],
            return_path=result["return_path"],
        )
    except Exception as exc:
        redirect_url = build_frontend_redirect_url(
            status="error",
            error=str(exc),
        )
    
    return RedirectResponse(url=redirect_url, status_code=302)
```

#### 3. GET /api/v1/integrations/google/gsc/sites

**Purpose:** List available GSC sites

**Authentication:** Workspace-scoped

**Query Parameters:**
- `workspace_id`: UUID

**Response:**
```json
{
  "success": true,
  "data": {
    "sites": [
      {
        "site_url": "https://example.com/",
        "permission_level": "owner"
      }
    ],
    "suggested_site_url": "https://example.com/"
  },
  "message": "GSC sites retrieved successfully"
}
```

#### 4. GET /api/v1/integrations/google/ga4/properties

**Purpose:** List available GA4 properties

**Authentication:** Workspace-scoped

**Query Parameters:**
- `workspace_id`: UUID

**Response:**
```json
{
  "success": true,
  "data": {
    "properties": [
      {
        "property_id": "properties/123456789",
        "display_name": "My Website",
        "property_type": "PROPERTY_TYPE_ORDINARY"
      }
    ]
  },
  "message": "GA4 properties retrieved successfully"
}
```

#### 5. POST /api/v1/integrations/google/connect/select

**Purpose:** Save selected GSC site and GA4 property

**Authentication:** Workspace-scoped

**Request Body:**
```json
{
  "gsc_site_url": "https://example.com/",
  "ga4_property_id": "properties/123456789"
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "connection_id": "uuid",
    "backfill_started": true
  },
  "message": "Google integration configured successfully"
}
```

**Implementation:**
```python
@router.post("/connect/select")
async def save_google_selections(
    workspace_id: uuid.UUID,
    data: GoogleSelectionsRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    _: bool = Depends(PermissionChecker(["user.read"], workspace_scoped=True)),
):
    """Save selected GSC site and GA4 property."""
    service = GoogleConnectionService(db)
    
    # Get OAuth account for workspace
    oauth_account = await get_workspace_oauth_account(db, workspace_id, "google")
    
    connection = await service.save_selections(
        workspace_id=workspace_id,
        oauth_account_id=oauth_account.id,
        gsc_site_url=data.gsc_site_url,
        ga4_property_id=data.ga4_property_id,
    )
    
    # Trigger backfill if first connection
    backfill_started = False
    if not connection.last_backfill_completed_at:
        from src.tasks.scheduled_tasks import task_manager
        task_manager.scheduler.add_job(
            run_google_backfill_task,
            args=[workspace_id],
            id=f"google_backfill_{workspace_id}",
            replace_existing=True,
        )
        backfill_started = True
    
    await db.commit()
    
    return success(
        data={
            "connection_id": str(connection.id),
            "backfill_started": backfill_started,
        },
        message="Google integration configured successfully",
    )
```

#### 6. GET /api/v1/integrations/google/status

**Purpose:** Check connection status

**Authentication:** Workspace-scoped

**Query Parameters:**
- `workspace_id`: UUID

**Response:**
```json
{
  "success": true,
  "data": {
    "is_connected": true,
    "gsc_site_url": "https://example.com/",
    "ga4_property_id": "properties/123456789",
    "last_synced_at": "2024-01-15T10:30:00Z",
    "last_backfill_completed_at": "2024-01-01T04:00:00Z",
    "oauth_account_email": "user@example.com"
  },
  "message": "Connection status retrieved"
}
```

#### 7. DELETE /api/v1/integrations/google/disconnect

**Purpose:** Disconnect Google integration

**Authentication:** Workspace-scoped

**Query Parameters:**
- `workspace_id`: UUID

**Response:**
```json
{
  "success": true,
  "message": "Google integration disconnected"
}
```

#### 8. GET /api/v1/integrations/google/metrics

**Purpose:** Query metrics with filters

**Authentication:** Workspace-scoped

**Query Parameters:**
- `workspace_id`: UUID (required)
- `article_id`: UUID (optional)
- `source`: "gsc" | "ga4" (optional)
- `start_date`: ISO date (optional, default: 30 days ago)
- `end_date`: ISO date (optional, default: today)
- `limit`: integer (optional, default: 100)
- `offset`: integer (optional, default: 0)

**Response:**
```json
{
  "success": true,
  "data": {
    "metrics": [
      {
        "date": "2024-01-15",
        "article_external_url": "https://example.com/blog/my-article",
        "source": "gsc",
        "metrics": {
          "clicks": 42,
          "impressions": 1234,
          "ctr": 0.034,
          "position": 12.5
        },
        "query_keyword": "my keyword"
      }
    ],
    "total_count": 500,
    "limit": 100,
    "offset": 0
  },
  "message": "Metrics retrieved successfully"
}
```

#### 9. GET /api/v1/integrations/google/articles/summary

**Purpose:** Get aggregated per-article metrics

**Authentication:** Workspace-scoped

**Query Parameters:**
- `workspace_id`: UUID (required)
- `start_date`: ISO date (optional, default: 30 days ago)
- `end_date`: ISO date (optional, default: today)

**Response:**
```json
{
  "success": true,
  "data": {
    "articles": [
      {
        "article_id": "uuid",
        "external_url": "https://example.com/blog/my-article",
        "title": "My Article",
        "gsc_metrics": {
          "total_clicks": 1250,
          "total_impressions": 45000,
          "avg_ctr": 0.028,
          "avg_position": 11.3
        },
        "ga4_metrics": {
          "total_sessions": 890,
          "total_active_users": 650,
          "avg_engagement_rate": 0.72,
          "total_conversions": 15
        }
      }
    ]
  },
  "message": "Article summaries retrieved successfully"
}
```

#### 10. GET /api/v1/integrations/google/articles/{article_id}/queries

**Purpose:** Get top search queries for an article

**Authentication:** Workspace-scoped

**Path Parameters:**
- `article_id`: UUID

**Query Parameters:**
- `workspace_id`: UUID (required)
- `start_date`: ISO date (optional, default: 30 days ago)
- `end_date`: ISO date (optional, default: today)
- `limit`: integer (optional, default: 20)

**Response:**
```json
{
  "success": true,
  "data": {
    "queries": [
      {
        "query": "best practices for python",
        "clicks": 150,
        "impressions": 5000,
        "ctr": 0.03,
        "position": 8.2
      }
    ]
  },
  "message": "Top queries retrieved successfully"
}
```

### Route Registration

**File:** `src/api/registry/routes.py` (additive modification)

```python
# Add to route registration function
from src.api.routes.integrations.google import router as google_router

app.include_router(
    google_router,
    prefix="/api/v1/integrations/google",
    tags=["Google Integration"],
)
```

## Configuration

**File:** `src/api/config.py` (additive modification)

Add these settings to the `Settings` class:

```python
class Settings(BaseSettings):
    # ... existing settings ...

    # ============================================================================
    # GOOGLE OAUTH & ANALYTICS
    # ============================================================================
    GOOGLE_CLIENT_ID: Optional[str] = Field(
        default=None,
        description="Google OAuth client ID for GSC and GA4 integration"
    )
    GOOGLE_CLIENT_SECRET: Optional[str] = Field(
        default=None,
        description="Google OAuth client secret for GSC and GA4 integration"
    )
    GOOGLE_OAUTH_REDIRECT_PATH: str = Field(
        default="/api/v1/integrations/google/connect/callback",
        description="Backend OAuth callback path for Google"
    )
    GOOGLE_INTEGRATION_RETURN_PATH: str = Field(
        default="/integrations",
        description="Frontend path to redirect after Google OAuth completes"
    )
    GOOGLE_SYNC_ENABLED: bool = Field(
        default=True,
        description="Enable daily Google Analytics sync scheduled task"
    )
```

## Data Models

### Complete Model Definitions

**File:** `src/api/models/integrations/workspace_google_connection.py`

```python
"""
Workspace Google Connection Model

Stores workspace-level Google Search Console and Google Analytics 4 integration state.
"""

import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship, Mapped, mapped_column

from src.api.database.base import Base
from src.api.models.base import SerializableMixin
from src.api.models.mixins import UUIDPrimaryKeyMixin, TimestampMixin


class WorkspaceGoogleConnection(Base, SerializableMixin, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    Workspace-level Google integration configuration.
    Stores selected GSC site and GA4 property for each workspace.
    """
    __tablename__ = "workspace_google_connections"
    __table_args__ = (
        UniqueConstraint("workspace_id", name="uq_workspace_google_connection"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspace.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        unique=True,
    )

    oauth_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("oauth_accounts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    gsc_site_url: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="Selected GSC site URL"
    )

    ga4_property_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Selected GA4 property ID"
    )

    last_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Last successful incremental sync"
    )

    last_backfill_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When 16-month backfill completed"
    )

    # Relationships
    workspace = relationship("WorkspaceModel", back_populates="google_connection")
    oauth_account = relationship("OAuthAccount")
```

**File:** `src/api/models/analytics/google_analytics_metric.py`

```python
"""
Google Analytics Metric Model

Stores daily metrics from Google Search Console and Google Analytics 4.
"""

import uuid
from datetime import datetime, date
from typing import Dict, Any, Optional
from sqlalchemy import String, Date, DateTime, ForeignKey, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship, Mapped, mapped_column

from src.api.database.base import Base
from src.api.models.base import SerializableMixin
from src.api.models.mixins import UUIDPrimaryKeyMixin, TimestampMixin


class GoogleAnalyticsMetric(Base, SerializableMixin, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    Daily analytics metrics for published articles.
    Stores both GSC (query-level) and GA4 (page-level) data.
    """
    __tablename__ = "google_analytics_metrics"
    __table_args__ = (
        Index(
            "ix_ga_metrics_workspace_url_date_source",
            "workspace_id", "article_external_url", "date", "source"
        ),
        UniqueConstraint(
            "workspace_id", "article_external_url", "date", "source", "query_keyword",
            name="uq_ga_metric_unique"
        ),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspace.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    article_external_url: Mapped[str] = mapped_column(
        String(1000),
        nullable=False,
        comment="Normalized external URL from ContentPublishingResult"
    )

    date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        index=True,
        comment="Date for metrics"
    )

    source: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        comment="'gsc' or 'ga4'"
    )

    metrics: Mapped[Dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        comment="Metrics JSONB: {clicks, impressions, ctr, position} or {sessions, active_users, engagement_rate, conversions}"
    )

    query_keyword: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
        comment="Search query keyword (GSC only)"
    )

    workspace = relationship("WorkspaceModel")
```

## Error Handling

### OAuth Errors

**Scenario:** User cancels OAuth flow or denies permissions

**Handling:**
- Redirect to frontend with `status=error&error=access_denied`
- Display user-friendly message: "Google authorization was cancelled"

**Scenario:** OAuth token expires

**Handling:**
- Detect expired token in `get_valid_token()`
- Automatically call `refresh_token()`
- If refresh fails, mark connection as inactive and notify user

### API Errors

**Scenario:** Google API returns 401 Unauthorized

**Handling:**
```python
if response.status_code == 401:
    # Token likely revoked by user
    logger.warning(f"Google API 401 for workspace={workspace_id}")
    # Mark connection as inactive, require re-authorization
    connection.oauth_account_id = None
    await db.commit()
    raise RextValidationException(
        message="Google authorization expired. Please reconnect."
    )
```

**Scenario:** Google API returns 429 Rate Limit

**Handling:**
```python
if response.status_code == 429:
    retry_after = int(response.headers.get("Retry-After", 60))
    logger.warning(f"Google API rate limit, retry after {retry_after}s")
    await asyncio.sleep(retry_after)
    # Retry request with exponential backoff
```

**Scenario:** Google API returns 403 Forbidden

**Handling:**
- Property may have been deleted or permissions revoked
- Log error and skip this workspace in sync
- Notify workspace owner via email/notification

### Data Sync Errors

**Scenario:** No published articles found

**Handling:**
```python
if not article_urls:
    logger.info(f"No published articles for workspace={workspace_id}")
    return {"articles_synced": 0, "gsc_records": 0, "ga4_records": 0}
```

**Scenario:** URL mismatch (Google data doesn't match any article)

**Handling:**
- Skip storing metrics for unmatched URLs
- Log warning for debugging
- Don't fail the entire sync

**Scenario:** Database deadlock or constraint violation

**Handling:**
```python
try:
    await db.execute(upsert_stmt)
    await db.commit()
except IntegrityError as e:
    logger.error(f"Integrity error storing metrics: {e}")
    await db.rollback()
    # Retry with smaller batch or skip
```

### Network Errors

**Scenario:** Timeout connecting to Google APIs

**Handling:**
```python
try:
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(url, json=payload)
except httpx.TimeoutException:
    logger.error(f"Timeout fetching from Google API")
    # Retry with backoff, max 3 attempts
```

### Validation Errors

**Scenario:** Invalid GSC site URL or GA4 property ID

**Handling:**
```python
# Validate format before saving
if not gsc_site_url.startswith("https://"):
    raise RextValidationException(
        message="GSC site URL must start with https://"
    )

if not ga4_property_id.startswith("properties/"):
    raise RextValidationException(
        message="Invalid GA4 property ID format"
    )
```

## Testing Strategy

### Unit Tests

**File:** `tests/unit/test_google_oauth_service.py`

Test OAuth service methods:
- `test_build_oauth_url()` - Verify URL contains correct scopes and parameters
- `test_handle_oauth_callback()` - Mock Google token exchange, verify OAuthAccount creation
- `test_refresh_token()` - Mock refresh endpoint, verify token update
- `test_get_valid_token_refresh()` - Verify automatic refresh when token expired

**File:** `tests/unit/test_google_connection_service.py`


Test connection management:
- `test_list_gsc_sites()` - Mock GSC API, verify site list parsing
- `test_list_ga4_properties()` - Mock GA4 Admin API, verify property list parsing
- `test_save_selections()` - Verify WorkspaceGoogleConnection creation
- `test_auto_suggest_gsc_site()` - Test URL matching logic
- `test_disconnect()` - Verify connection deletion, metrics preservation

**File:** `tests/unit/test_google_analytics_sync_service.py`

Test sync service:
- `test_fetch_gsc_metrics()` - Mock GSC Search Analytics API
- `test_fetch_ga4_metrics()` - Mock GA4 Data API
- `test_store_metrics_upsert()` - Verify UPSERT behavior on duplicate keys
- `test_sync_workspace_incremental()` - Test date range calculation
- `test_sync_workspace_backfill()` - Test 16-month historical fetch

**File:** `tests/unit/test_url_normalizer.py`

Test URL normalization:
- `test_normalize_lowercase()` - "Example.com" → "example.com"
- `test_normalize_trailing_slash()` - "/blog/" → "/blog"
- `test_normalize_fragment()` - "/blog#section" → "/blog"
- `test_normalize_root()` - "example.com" → "example.com/"
- `test_normalize_preserve_query()` - "/blog?utm_source=x" preserved

**File:** `tests/unit/test_google_metrics_service.py`

Test metrics queries:
- `test_get_metrics_filter_by_date()` - Verify date range filtering
- `test_get_metrics_filter_by_source()` - Filter GSC vs GA4
- `test_get_article_summary()` - Test aggregation queries
- `test_get_top_queries()` - Test query ranking and limiting

### Integration Tests

**File:** `tests/integration/test_google_oauth_flow.py`

Test end-to-end OAuth:
- `test_oauth_start_to_callback()` - Simulate full flow with mock Google
- `test_oauth_token_refresh()` - Test automatic refresh on expiry
- `test_oauth_error_handling()` - Test user cancellation, invalid code

**File:** `tests/integration/test_google_data_sync.py`

Test data synchronization:
- `test_backfill_task()` - Run backfill with mock APIs, verify 16 months of data
- `test_incremental_sync()` - Verify daily sync fetches only new data
- `test_url_matching()` - Create articles, verify metrics linked correctly
- `test_sync_error_recovery()` - Simulate API errors, verify graceful handling

**File:** `tests/integration/test_google_api_endpoints.py`

Test REST API endpoints:
- `test_connect_start_endpoint()` - POST /connect/start returns auth URL
- `test_list_sites_endpoint()` - GET /gsc/sites returns list
- `test_save_selections_endpoint()` - POST /connect/select saves to DB
- `test_status_endpoint()` - GET /status returns connection state
- `test_metrics_endpoint()` - GET /metrics returns filtered data
- `test_article_summary_endpoint()` - GET /articles/summary aggregates correctly

### API Tests

**File:** `tests/api/test_google_routes.py`

Test route handlers with FastAPI TestClient:
- Mock all service layer calls
- Verify request validation (Pydantic schemas)
- Verify response structure
- Verify authentication/authorization

### Database Tests

**File:** `tests/database/test_google_models.py`

Test model constraints:
- `test_workspace_unique_constraint()` - One connection per workspace
- `test_metric_unique_constraint()` - No duplicate (workspace, url, date, source, query)
- `test_cascade_delete()` - Deleting workspace deletes connection and metrics
- `test_set_null_on_oauth_delete()` - Deleting OAuth account sets FK to NULL

### Mock Data Fixtures

**File:** `tests/fixtures/google_fixtures.py`

```python
@pytest.fixture
def mock_gsc_sites_response():
    return {
        "siteEntry": [
            {"siteUrl": "https://example.com/", "permissionLevel": "owner"},
            {"siteUrl": "https://blog.example.com/", "permissionLevel": "owner"},
        ]
    }

@pytest.fixture
def mock_ga4_properties_response():
    return {
        "properties": [
            {
                "name": "properties/123456789",
                "displayName": "Example Website",
                "propertyType": "PROPERTY_TYPE_ORDINARY",
            }
        ]
    }

@pytest.fixture
def mock_gsc_metrics_response():
    return {
        "rows": [
            {
                "keys": ["https://example.com/blog/article-1", "python tutorial", "2024-01-15"],
                "clicks": 42,
                "impressions": 1234,
                "ctr": 0.034,
                "position": 12.5,
            }
        ]
    }

@pytest.fixture
def mock_ga4_metrics_response():
    return {
        "rows": [
            {
                "dimensionValues": [
                    {"value": "2024-01-15"},
                    {"value": "/blog/article-1"}
                ],
                "metricValues": [
                    {"value": "156"},  # sessions
                    {"value": "89"},   # activeUsers
                    {"value": "0.67"}, # engagementRate
                    {"value": "3"},    # conversions
                ]
            }
        ]
    }
```

## Integration Points with Existing Codebase

### 1. OAuthAccount Table (Reuse)

**Location:** `src/api/models/user_models/oauth_accounts.py`

**Usage:**
- Store Google OAuth tokens with `provider='google'`
- Link to `user_id` who authorized the connection
- Use existing token refresh logic

**No modifications needed**

### 2. ContentPublishingResult Table (Reuse)

**Location:** `src/api/models/content_models/publishing_result.py`

**Usage:**
- Read `external_url` field to get published article URLs
- Filter where `external_url IS NOT NULL` to find published articles
- Join with `Content` table to get `workspace_id`

**No modifications needed**

### 3. WorkspaceModel (Add Relationship)

**Location:** `src/api/models/workspace_model.py`

**Modification (additive):**
```python
# Add to WorkspaceModel class
google_connection = relationship(
    "WorkspaceGoogleConnection",
    back_populates="workspace",
    uselist=False,
)
```

### 4. Route Registry (Add Route)

**Location:** `src/api/registry/routes.py`

**Modification (additive):**
```python
from src.api.routes.integrations.google import router as google_router

app.include_router(
    google_router,
    prefix="/api/v1/integrations/google",
    tags=["Google Integration"],
)
```

### 5. Scheduled Tasks (Add Job)

**Location:** `src/tasks/scheduled_tasks.py`

**Modification (additive):**
```python
from src.tasks.google_sync_task import run_google_daily_sync_task

# In ScheduledTaskManager.start() method
if cleanup_config.GOOGLE_SYNC_ENABLED:
    self.scheduler.add_job(
        run_google_daily_sync_task,
        trigger=CronTrigger(hour=4, minute=0),
        id="google_daily_sync",
        name="Daily Google Analytics sync",
        replace_existing=True,
        max_instances=1,
    )
    logger.info("Registered task: google_daily_sync")
```

### 6. Configuration Settings (Add Settings)

**Location:** `src/api/config.py`

**Modification (additive):**
```python
# Add to Settings class
GOOGLE_CLIENT_ID: Optional[str] = Field(default=None, ...)
GOOGLE_CLIENT_SECRET: Optional[str] = Field(default=None, ...)
GOOGLE_OAUTH_REDIRECT_PATH: str = Field(default="/api/v1/integrations/google/connect/callback", ...)
GOOGLE_INTEGRATION_RETURN_PATH: str = Field(default="/integrations", ...)
GOOGLE_SYNC_ENABLED: bool = Field(default=True, ...)
```

### 7. Database Migration

**File:** `alembic/versions/YYYYMMDD_add_google_analytics_integration.py`

**Migration Tasks:**
1. Create `workspace_google_connections` table
2. Create `google_analytics_metrics` table
3. Add indexes and constraints
4. Add relationship to `workspace` table (optional, handled by ORM)

```python
def upgrade():
    # Create workspace_google_connections table
    op.create_table(
        'workspace_google_connections',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('workspace_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('oauth_account_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('gsc_site_url', sa.String(500), nullable=True),
        sa.Column('ga4_property_id', sa.String(100), nullable=True),
        sa.Column('last_synced_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_backfill_completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspace.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['oauth_account_id'], ['oauth_accounts.id'], ondelete='SET NULL'),
        sa.UniqueConstraint('workspace_id', name='uq_workspace_google_connection'),
    )
    op.create_index('ix_wgc_workspace_id', 'workspace_google_connections', ['workspace_id'])
    op.create_index('ix_wgc_oauth_account_id', 'workspace_google_connections', ['oauth_account_id'])
    
    # Create google_analytics_metrics table
    op.create_table(
        'google_analytics_metrics',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('workspace_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('article_external_url', sa.String(1000), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('source', sa.String(10), nullable=False),
        sa.Column('metrics', postgresql.JSONB(), nullable=False),
        sa.Column('query_keyword', sa.String(500), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspace.id'], ondelete='CASCADE'),
        sa.UniqueConstraint(
            'workspace_id', 'article_external_url', 'date', 'source', 'query_keyword',
            name='uq_ga_metric_unique'
        ),
    )
    op.create_index('ix_gam_workspace_id', 'google_analytics_metrics', ['workspace_id'])
    op.create_index('ix_gam_date', 'google_analytics_metrics', ['date'])
    op.create_index(
        'ix_ga_metrics_workspace_url_date_source',
        'google_analytics_metrics',
        ['workspace_id', 'article_external_url', 'date', 'source']
    )

def downgrade():
    op.drop_table('google_analytics_metrics')
    op.drop_table('workspace_google_connections')
```

## File Structure Summary

### New Files to Create

```
src/
├── api/
│   ├── models/
│   │   ├── integrations/
│   │   │   └── workspace_google_connection.py (new)
│   │   └── analytics/
│   │       └── google_analytics_metric.py (new)
│   ├── routes/
│   │   └── integrations/
│   │       └── google.py (new)
│   └── schema/
│       └── google_schema.py (new)
├── services/
│   ├── google_oauth_service.py (new)
│   ├── google_connection_service.py (new)
│   ├── google_analytics_sync_service.py (new)
│   └── google_metrics_service.py (new)
├── tasks/
│   ├── google_backfill_task.py (new)
│   └── google_sync_task.py (new)
└── utils/
    └── url_normalizer.py (new)

alembic/
└── versions/
    └── YYYYMMDD_add_google_analytics_integration.py (new)

tests/
├── unit/
│   ├── test_google_oauth_service.py (new)
│   ├── test_google_connection_service.py (new)
│   ├── test_google_analytics_sync_service.py (new)
│   ├── test_google_metrics_service.py (new)
│   └── test_url_normalizer.py (new)
├── integration/
│   ├── test_google_oauth_flow.py (new)
│   ├── test_google_data_sync.py (new)
│   └── test_google_api_endpoints.py (new)
├── api/
│   └── test_google_routes.py (new)
├── database/
│   └── test_google_models.py (new)
└── fixtures/
    └── google_fixtures.py (new)
```

### Modified Files (Additive Only)

```
src/
├── api/
│   ├── config.py (add Google settings)
│   ├── registry/
│   │   └── routes.py (register Google router)
│   └── models/
│       └── workspace_model.py (add google_connection relationship)
└── tasks/
    └── scheduled_tasks.py (register Google sync job)
```

## Implementation Checklist

### Phase 1: Foundation (Database + Config)
- [ ] Create WorkspaceGoogleConnection model
- [ ] Create GoogleAnalyticsMetric model
- [ ] Create Alembic migration
- [ ] Run migration on dev database
- [ ] Add Google settings to config.py
- [ ] Add WorkspaceModel relationship

### Phase 2: OAuth Flow
- [ ] Implement GoogleOAuthService
- [ ] Create google_schema.py with Pydantic models
- [ ] Implement OAuth routes (start, callback)
- [ ] Test OAuth flow with mock Google
- [ ] Write unit tests for OAuth service

### Phase 3: Connection Management
- [ ] Implement GoogleConnectionService
- [ ] Implement list_gsc_sites()
- [ ] Implement list_ga4_properties()
- [ ] Implement save_selections()
- [ ] Implement connection status endpoint
- [ ] Write unit tests for connection service

### Phase 4: Data Sync
- [ ] Implement URL normalizer utility
- [ ] Implement GoogleAnalyticsSyncService
- [ ] Implement fetch_gsc_metrics()
- [ ] Implement fetch_ga4_metrics()
- [ ] Implement store_metrics() with UPSERT
- [ ] Test sync with mock APIs
- [ ] Write unit tests for sync service

### Phase 5: Background Jobs
- [ ] Implement google_backfill_task.py
- [ ] Implement google_sync_task.py
- [ ] Register daily sync in scheduled_tasks.py
- [ ] Test backfill job
- [ ] Test daily sync job

### Phase 6: Metrics API
- [ ] Implement GoogleMetricsService
- [ ] Implement metrics query endpoint
- [ ] Implement article summary endpoint
- [ ] Implement top queries endpoint
- [ ] Test API endpoints with TestClient
- [ ] Write integration tests

### Phase 7: Testing & Documentation
- [ ] Write all unit tests
- [ ] Write integration tests
- [ ] Write API tests
- [ ] Test end-to-end flow
- [ ] Document API in OpenAPI/Swagger
- [ ] Update README with setup instructions

---

**Design Document Version:** 1.0  
**Last Updated:** 2025-01-XX  
**Status:** Ready for Implementation

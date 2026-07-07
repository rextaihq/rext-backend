# Requirements Document

## Introduction

This document specifies the requirements for integrating Google Search Console (GSC) and Google Analytics 4 (GA4) with Rext AI. The integration enables workspace owners to authorize both GSC and GA4 through a single OAuth flow, select one property for each service per workspace, automatically sync performance data for published articles, and expose the collected data via REST APIs for frontend consumption. The system will perform a 16-month historical backfill on first connection and continue with daily incremental syncs thereafter.

## Glossary

- **GSC**: Google Search Console - Google's service providing search performance data including clicks, impressions, CTR, position, and query keywords
- **GA4**: Google Analytics 4 - Google's analytics platform providing user behavior metrics including sessions, active users, engagement rate, and conversions
- **OAuth_Manager**: The component responsible for managing Google OAuth authentication flows
- **Connection_Manager**: The component managing workspace-level GSC and GA4 property selections and connection state
- **Data_Sync_Service**: The background service responsible for fetching and storing metrics from GSC and GA4
- **Metrics_API**: The REST API endpoints that expose collected analytics data
- **WorkspaceGoogleConnection**: Database table storing the selected GSC site and GA4 property for each workspace
- **GoogleAnalyticsMetric**: Database table storing daily metrics for published articles
- **ContentPublishingResult**: Existing table containing external_url for published articles
- **URL_Normalizer**: Component that normalizes URLs for matching between Google data and internal articles
- **Published_Article**: Content with a non-null external_url in ContentPublishingResult table

## Requirements

### Requirement 1: Google OAuth Authentication

**User Story:** As a workspace owner, I want to authenticate with Google once to authorize both GSC and GA4 access, so that I can connect both services without multiple OAuth flows.

#### Acceptance Criteria

1. WHEN a workspace owner initiates OAuth, THE OAuth_Manager SHALL request both webmasters.readonly and analytics.readonly scopes in a single consent screen
2. WHEN OAuth authorization completes successfully, THE OAuth_Manager SHALL store the access_token and refresh_token in the OAuthAccount table with provider='google'
3. WHEN the access_token expires, THE OAuth_Manager SHALL automatically refresh it using the refresh_token
4. WHEN OAuth authorization fails, THE OAuth_Manager SHALL return a descriptive error message to the user
5. THE OAuth_Manager SHALL link the OAuthAccount record to the user_id who initiated the authorization

### Requirement 2: GSC Property Selection

**User Story:** As a workspace owner, I want to select one GSC property for my workspace, so that I can track search performance for my published content.

#### Acceptance Criteria

1. WHEN a workspace owner requests available GSC properties, THE Connection_Manager SHALL retrieve all GSC sites accessible with the authorized OAuth account
2. WHEN the workspace has a configured site_url, THE Connection_Manager SHALL auto-suggest the GSC property matching that URL
3. WHEN a workspace owner selects a GSC property, THE Connection_Manager SHALL store the selection in WorkspaceGoogleConnection.gsc_site_url
4. THE Connection_Manager SHALL allow only one GSC property per workspace
5. WHEN a workspace owner changes the selected GSC property, THE Connection_Manager SHALL update WorkspaceGoogleConnection.gsc_site_url with the new selection

### Requirement 3: GA4 Property Selection

**User Story:** As a workspace owner, I want to select one GA4 property for my workspace, so that I can track user engagement for my published content.

#### Acceptance Criteria

1. WHEN a workspace owner requests available GA4 properties, THE Connection_Manager SHALL retrieve all GA4 properties accessible with the authorized OAuth account
2. WHEN a workspace owner selects a GA4 property, THE Connection_Manager SHALL store the selection in WorkspaceGoogleConnection.ga4_property_id
3. THE Connection_Manager SHALL allow only one GA4 property per workspace
4. WHEN a workspace owner changes the selected GA4 property, THE Connection_Manager SHALL update WorkspaceGoogleConnection.ga4_property_id with the new selection

### Requirement 4: Connection State Management

**User Story:** As a workspace owner, I want to check my Google integration status, so that I can verify which properties are connected and whether the connection is active.

#### Acceptance Criteria

1. WHEN a workspace owner requests connection status, THE Connection_Manager SHALL return the OAuth account status, selected GSC site, selected GA4 property, and last sync timestamp
2. WHEN a workspace owner disconnects the integration, THE Connection_Manager SHALL delete the WorkspaceGoogleConnection record and mark the connection as inactive
3. THE Connection_Manager SHALL preserve historical GoogleAnalyticsMetric data when a workspace disconnects
4. WHEN no connection exists for a workspace, THE Connection_Manager SHALL return is_connected=false

### Requirement 5: Article-to-URL Mapping

**User Story:** As the system, I want to match Google data to published articles using external_url, so that I can attribute metrics to the correct content.

#### Acceptance Criteria

1. THE Data_Sync_Service SHALL consider an article published if ContentPublishingResult.external_url is not null
2. WHEN matching Google data to articles, THE URL_Normalizer SHALL normalize both the external_url and Google-provided URLs by removing trailing slashes, converting to lowercase, and removing URL fragments
3. THE URL_Normalizer SHALL perform normalization at read time when querying metrics
4. WHEN a published article's external_url is updated, THE Data_Sync_Service SHALL associate future metrics with the new URL without modifying historical data
5. WHEN Google data contains a URL not matching any published article, THE Data_Sync_Service SHALL skip storing metrics for that URL

### Requirement 6: GSC Metrics Collection

**User Story:** As a workspace owner, I want to collect GSC metrics for my published articles, so that I can analyze search performance over time.

#### Acceptance Criteria

1. WHEN Data_Sync_Service syncs GSC data, THE Data_Sync_Service SHALL fetch clicks, impressions, CTR, and position for each published article URL
2. WHEN Data_Sync_Service syncs GSC data, THE Data_Sync_Service SHALL fetch top queries (keywords) for each published article URL
3. THE Data_Sync_Service SHALL store GSC metrics in GoogleAnalyticsMetric with source='gsc' and one record per (article, date, query) combination
4. WHEN GSC returns no data for a published article on a given date, THE Data_Sync_Service SHALL store a record with zero values
5. THE Data_Sync_Service SHALL aggregate keyword-level metrics when returning article-level summaries

### Requirement 7: GA4 Metrics Collection

**User Story:** As a workspace owner, I want to collect GA4 metrics for my published articles, so that I can analyze user engagement over time.

#### Acceptance Criteria

1. WHEN Data_Sync_Service syncs GA4 data, THE Data_Sync_Service SHALL fetch sessions, active_users, engagement_rate, and conversions for each published article URL
2. THE Data_Sync_Service SHALL store GA4 metrics in GoogleAnalyticsMetric with source='ga4' and one record per (article, date) combination
3. WHEN GA4 returns no data for a published article on a given date, THE Data_Sync_Service SHALL store a record with zero values
4. THE Data_Sync_Service SHALL handle GA4 API sampling by using the largest available date range that avoids sampling

### Requirement 8: Historical Data Backfill

**User Story:** As a workspace owner, I want 16 months of historical data when I first connect, so that I can analyze long-term trends immediately.

#### Acceptance Criteria

1. WHEN a workspace first selects GSC and GA4 properties, THE Data_Sync_Service SHALL initiate a backfill job for the previous 16 months
2. THE Data_Sync_Service SHALL fetch data in batches to respect Google API rate limits during backfill
3. THE Data_Sync_Service SHALL store backfilled metrics with the original date from Google's response
4. WHEN backfill completes successfully, THE Data_Sync_Service SHALL update WorkspaceGoogleConnection.last_backfill_completed_at
5. WHEN backfill fails, THE Data_Sync_Service SHALL log the error and allow retry without duplicating already-synced data

### Requirement 9: Daily Incremental Sync

**User Story:** As a workspace owner, I want daily updates to my Google metrics, so that I can monitor recent performance.

#### Acceptance Criteria

1. THE Data_Sync_Service SHALL run a daily scheduled job to fetch metrics for all connected workspaces
2. WHEN the daily sync runs, THE Data_Sync_Service SHALL fetch data from the last_synced_at timestamp to the current date
3. THE Data_Sync_Service SHALL update WorkspaceGoogleConnection.last_synced_at after successful sync
4. WHEN the daily sync encounters an OAuth token error, THE Data_Sync_Service SHALL attempt token refresh before failing
5. WHEN the daily sync fails for a workspace, THE Data_Sync_Service SHALL log the error and continue syncing other workspaces

### Requirement 10: Metrics Query API

**User Story:** As a frontend developer, I want to retrieve metrics with filtering options, so that I can display analytics in the UI.

#### Acceptance Criteria

1. WHEN a client requests metrics, THE Metrics_API SHALL accept filters for date_range, article_id, source (gsc/ga4), and metric_type
2. WHEN a client requests metrics without filters, THE Metrics_API SHALL return the most recent 30 days of data
3. THE Metrics_API SHALL return metrics ordered by date descending
4. THE Metrics_API SHALL support pagination with limit and offset parameters
5. WHEN a client requests metrics for a workspace without a Google connection, THE Metrics_API SHALL return an empty result set

### Requirement 11: Article Summary API

**User Story:** As a frontend developer, I want aggregated per-article performance data, so that I can display a summary dashboard.

#### Acceptance Criteria

1. WHEN a client requests article summaries, THE Metrics_API SHALL aggregate GSC and GA4 metrics by article_id
2. THE Metrics_API SHALL calculate total clicks, impressions, sessions, and average CTR, position, and engagement_rate for each article
3. THE Metrics_API SHALL include the article's external_url and title in the response
4. THE Metrics_API SHALL accept a date_range filter to limit aggregation period
5. THE Metrics_API SHALL return summaries ordered by total clicks descending

### Requirement 12: Connection Management API

**User Story:** As a frontend developer, I want connection management endpoints, so that I can build the integration setup UI.

#### Acceptance Criteria

1. THE Metrics_API SHALL provide POST /google/connect/start to initiate OAuth flow
2. THE Metrics_API SHALL provide GET /google/connect/callback to handle OAuth callback
3. THE Metrics_API SHALL provide GET /google/gsc/sites to list available GSC properties
4. THE Metrics_API SHALL provide GET /google/ga4/properties to list available GA4 properties
5. THE Metrics_API SHALL provide POST /google/connect/select to save selected properties
6. THE Metrics_API SHALL provide GET /google/status to check connection status
7. THE Metrics_API SHALL provide DELETE /google/disconnect to remove the integration
8. THE Metrics_API SHALL require workspace-scoped authentication for all endpoints

### Requirement 13: Additive Implementation Constraint

**User Story:** As a developer, I want the implementation to be 100% additive, so that existing functionality remains unaffected.

#### Acceptance Criteria

1. THE implementation SHALL NOT modify existing models including ContentPublishingResult, Content, WorkspaceIntegration, or OAuthAccount
2. THE implementation SHALL add new lines to src/api/registry/routes.py for route registration
3. THE implementation SHALL add new lines to src/tasks/scheduled_tasks.py for scheduled job registration
4. THE implementation SHALL add new lines to src/api/config.py for configuration settings
5. THE implementation SHALL create new files for models, routes, services, and schemas without modifying existing files

### Requirement 14: URL Normalization

**User Story:** As a developer, I want URL normalization to happen at read time, so that I don't modify existing data structures.

#### Acceptance Criteria

1. THE URL_Normalizer SHALL remove trailing slashes from URLs
2. THE URL_Normalizer SHALL convert URLs to lowercase for comparison
3. THE URL_Normalizer SHALL remove URL fragments (# anchors)
4. THE URL_Normalizer SHALL preserve the protocol (http/https) during normalization
5. THE URL_Normalizer SHALL handle both absolute and relative URLs correctly

### Requirement 15: Data Model Design

**User Story:** As a developer, I want clear database schemas, so that I can implement the data layer correctly.

#### Acceptance Criteria

1. THE WorkspaceGoogleConnection table SHALL include columns: workspace_id, oauth_account_id, gsc_site_url, ga4_property_id, last_synced_at, last_backfill_completed_at, created_at, updated_at
2. THE GoogleAnalyticsMetric table SHALL include columns: id, workspace_id, article_external_url, date, source, metric_type, metric_value, query_keyword, created_at
3. THE WorkspaceGoogleConnection table SHALL have a unique constraint on workspace_id
4. THE GoogleAnalyticsMetric table SHALL have a composite index on (workspace_id, article_external_url, date, source)
5. THE GoogleAnalyticsMetric table SHALL have a composite unique constraint on (workspace_id, article_external_url, date, source, query_keyword) for GSC query-level metrics

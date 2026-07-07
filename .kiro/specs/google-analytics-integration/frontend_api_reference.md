# Frontend API Reference: Google Analytics & Search Console Integration

This document outlines the REST API endpoints available for the Google Analytics integration, including their request parameters and expected response formats. All endpoints are prefixed with `/api/v1/integrations/google` and require standard authentication (along with `workspace_id` in the query).

---

## 1. OAuth & Connection Setup

### Start OAuth Flow
Initiates the OAuth connection with Google.
- **Endpoint**: `POST /connect/start`
- **Request Body**:
  ```json
  {
    "return_path": "/dashboard/integrations/google" // Optional string: the path the user should return to after OAuth completion.
  }
  ```
- **Response**:
  ```json
  {
    "status": "success",
    "data": {
      "oauth_url": "https://accounts.google.com/o/oauth2/v2/auth?..."
    }
  }
  ```
*Frontend Action:* Redirect the user to the `oauth_url` provided in the response.

### OAuth Callback Handler (Backend Use Primarily)
Handles the OAuth response from Google.
- **Endpoint**: `GET /connect/callback`
- **Flow**: The frontend shouldn't call this directly. Google redirects the user here, which subsequently redirects the user back to the `return_path` (provided during `connect/start`) with a `status=success` or `status=error` query parameter.

---

## 2. Configuration & Selections

### List Google Search Console (GSC) Sites
Fetches the list of sites available in the connected GSC account.
- **Endpoint**: `GET /gsc/sites`
- **Query Params**: `?workspace_id={workspace_uuid}`
- **Response**:
  ```json
  {
    "status": "success",
    "data": {
      "sites": [
        {
          "site_url": "sc-domain:example.com",
          "permission_level": "siteOwner"
        },
        {
          "site_url": "https://www.example.com/",
          "permission_level": "siteOwner"
        }
      ]
    }
  }
  ```

### List Google Analytics 4 (GA4) Properties
Fetches the list of properties available in the connected GA4 account and optionally auto-suggests a matching GSC site URL for the workspace.
- **Endpoint**: `GET /ga4/properties`
- **Query Params**: `?workspace_id={workspace_uuid}`
- **Response**:
  ```json
  {
    "status": "success",
    "data": {
      "properties": [
        {
          "property_id": "properties/123456789",
          "display_name": "Example.com - Main Property",
          "property_type": "PROPERTY_TYPE_ORDINARY"
        }
      ],
      "suggested_gsc_site": "https://www.example.com/" // Can be null
    }
  }
  ```

### Save Selections
Saves the user's selected GSC site and GA4 property to the database and kicks off the background data backfill process.
- **Endpoint**: `POST /connect/select`
- **Query Params**: `?workspace_id={workspace_uuid}`
- **Request Body**:
  ```json
  {
    "gsc_site_url": "https://www.example.com/",
    "ga4_property_id": "properties/123456789"
  }
  ```
- **Response**:
  ```json
  {
    "status": "success",
    "message": "Google selections saved successfully"
  }
  ```

### Check Connection Status
Checks if the workspace is currently connected and fetching data.
- **Endpoint**: `GET /status`
- **Query Params**: `?workspace_id={workspace_uuid}`
- **Response**:
  ```json
  {
    "status": "success",
    "data": {
      "is_connected": true,
      "email": "user@example.com",
      "gsc_site_url": "https://www.example.com/",
      "ga4_property_id": "properties/123456789",
      "last_synced_at": "2023-11-01T14:30:00Z", // Can be null if sync hasn't run
      "last_backfill_completed_at": "2023-11-01T15:00:00Z" // Can be null if backfill is running
    }
  }
  ```

### Disconnect
Removes the connection configuration (Historical metrics data will be preserved).
- **Endpoint**: `DELETE /disconnect`
- **Query Params**: `?workspace_id={workspace_uuid}`
- **Response**:
  ```json
  {
    "status": "success",
    "message": "Google integration disconnected successfully"
  }
  ```

---

## 3. Metrics & Analytics

### Fetch Raw Metrics
Fetches paginated, raw metric data points. Useful for time-series charts (e.g. daily traffic).
- **Endpoint**: `GET /metrics`
- **Query Params**: 
  - `workspace_id` (Required)
  - `article_id` (Optional) - Filter by specific Rext content UUID
  - `source` (Optional) - `gsc` or `ga4`
  - `start_date` (Optional) - Format `YYYY-MM-DD`
  - `end_date` (Optional) - Format `YYYY-MM-DD`
  - `limit` (Optional, Default: 50)
  - `offset` (Optional, Default: 0)
- **Response**:
  ```json
  {
    "status": "success",
    "data": {
      "data": [
        {
          "date": "2023-10-31",
          "source": "ga4",
          "article_external_url": "/blog/how-to-do-seo",
          "query_keyword": "",
          "metrics": {
            "sessions": 150,
            "activeUsers": 120,
            "engagementRate": 0.65,
            "conversions": 3.0
          }
        },
        {
          "date": "2023-10-31",
          "source": "gsc",
          "article_external_url": "https://www.example.com/blog/how-to-do-seo",
          "query_keyword": "how to do seo",
          "metrics": {
            "clicks": 45,
            "impressions": 1200,
            "ctr": 0.0375,
            "position": 5.2
          }
        }
      ],
      "total_count": 1420,
      "limit": 50,
      "offset": 0
    }
  }
  ```

### Fetch Article Summary (High-Level Overview)
Fetches aggregated metrics grouped by each article, perfect for an "All Posts" or "Content Performance" table dashboard.
- **Endpoint**: `GET /articles/summary`
- **Query Params**:
  - `workspace_id` (Required)
  - `start_date` (Optional)
  - `end_date` (Optional)
- **Response**:
  ```json
  {
    "status": "success",
    "data": {
      "summaries": [
        {
          "article_url": "https://www.example.com/blog/how-to-do-seo",
          "article_id": "123e4567-e89b-12d3-a456-426614174000",
          "title": "How to Do SEO",
          "gsc_metrics": {
            "clicks": 540,
            "impressions": 12400,
            "avg_ctr": 0.0435,
            "avg_position": 4.5
          },
          "ga4_metrics": {
            "sessions": 850,
            "active_users": 790,
            "avg_engagement_rate": 0.72,
            "conversions": 15.0
          }
        }
      ]
    }
  }
  ```

### Fetch Top Queries for Article
Fetches the top Google Search Console query keywords that drove traffic to a specific article.
- **Endpoint**: `GET /articles/{article_id}/queries`
- **Query Params**:
  - `workspace_id` (Required)
  - `start_date` (Optional)
  - `end_date` (Optional)
  - `limit` (Optional, Default: 20)
- **Response**:
  ```json
  {
    "status": "success",
    "data": {
      "queries": [
        {
          "keyword": "how to do seo",
          "metrics": {
            "clicks": 150,
            "impressions": 3000,
            "avg_ctr": 0.05,
            "avg_position": 3.2
          }
        },
        {
          "keyword": "seo guide for beginners",
          "metrics": {
            "clicks": 85,
            "impressions": 2500,
            "avg_ctr": 0.034,
            "avg_position": 6.8
          }
        }
      ]
    }
  }
  ```

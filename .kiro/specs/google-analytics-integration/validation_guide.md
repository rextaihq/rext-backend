# Validation & Testing Guide: Google Analytics Integration

This guide provides steps for backend developers and QAs to manually validate that the new Google Analytics (GA4) and Google Search Console (GSC) integration is functioning correctly.

## Prerequisites

1. **Environment Variables**:
   Ensure your `.env` contains the newly added configuration vars:
   ```env
   GOOGLE_CLIENT_ID="your_google_client_id"
   GOOGLE_CLIENT_SECRET="your_google_client_secret"
   GOOGLE_OAUTH_REDIRECT_PATH="/api/v1/integrations/google/connect/callback"
   GOOGLE_INTEGRATION_RETURN_PATH="/dashboard/settings/integrations"
   GOOGLE_SYNC_ENABLED=true
   ```

2. **Database Migration**:
   Before running any queries, you must generate and apply the alembic migrations.
   ```bash
   alembic revision --autogenerate -m "Add Google Analytics Integration"
   alembic upgrade head
   ```

## 1. Testing the OAuth Flow

**Step 1: Start Connection**
Using a tool like Postman or a browser, hit the initialization route.
- **GET** `http://localhost:8000/api/v1/integrations/google/connect/start?workspace_id=<YOUR_WORKSPACE_ID>`
- Ensure it redirects you to the Google Consent screen.

**Step 2: Authenticate**
- Log in with a Google account that has access to both GSC sites and GA4 properties.
- Grant the required scopes (`webmasters.readonly` and `analytics.readonly`).

**Step 3: Callback verification**
- After granting permission, verify that Google redirects you back to your `GOOGLE_OAUTH_REDIRECT_PATH` and then subsequently to your `GOOGLE_INTEGRATION_RETURN_PATH` with a `?status=success` parameter.
- **Check the Database**: Verify that a new record was added to the `OAuthAccount` table with `provider='google'`.

## 2. Testing Configuration & Selection

**Step 1: List GSC Sites**
- **GET** `http://localhost:8000/api/v1/integrations/google/gsc/sites?workspace_id=<YOUR_WORKSPACE_ID>`
- Verify that the API returns a list of sites authorized to the authenticated user.

**Step 2: List GA4 Properties**
- **GET** `http://localhost:8000/api/v1/integrations/google/ga4/properties?workspace_id=<YOUR_WORKSPACE_ID>`
- Verify that the API returns a list of GA4 properties.

**Step 3: Save Selections**
- Select one site URL and one GA4 Property ID from the previous responses.
- **POST** `http://localhost:8000/api/v1/integrations/google/connect/select?workspace_id=<YOUR_WORKSPACE_ID>`
  ```json
  {
    "gsc_site_url": "https://www.example.com/",
    "ga4_property_id": "properties/1234567"
  }
  ```
- **Check the Database**:
  - Verify that a `WorkspaceGoogleConnection` row exists for your workspace.
  - Check the application logs. You should see a log indicating `Scheduled backfill job for workspace...`.

## 3. Testing the Background Sync (Backfill)

Because you just made the selection in the previous step, the background historical backfill task should have started.

1. **Verify Logs**: Watch your server terminal for `Starting Google historical backfill task for workspace...` and `Completed Google backfill for workspace...`.
2. **Database Check**: Check the `GoogleAnalyticsMetric` table. It should now contain rows of metrics mapped to your articles (if any articles exist for that workspace and match the domains).

## 4. Testing the Analytics APIs

Once the database has some records populated, you can hit the analytical endpoints to verify JSON structures.

**Step 1: Raw Metrics**
- **GET** `/api/v1/integrations/google/metrics?workspace_id=<YOUR_WORKSPACE_ID>&limit=5`
- Ensure raw GA4 and GSC records are returned correctly in JSON format.

**Step 2: Article Summaries**
- **GET** `/api/v1/integrations/google/articles/summary?workspace_id=<YOUR_WORKSPACE_ID>`
- Verify that metrics are aggregated correctly and grouped by `article_url`.

**Step 3: Keyword Queries**
- First, obtain an `article_id` that has GSC metrics populated.
- **GET** `/api/v1/integrations/google/articles/<ARTICLE_ID>/queries?workspace_id=<YOUR_WORKSPACE_ID>`
- Ensure it returns the top keyword strings and their relative clicks, impressions, CTR, and positions.

## 5. Testing Disconnection

- **DELETE** `http://localhost:8000/api/v1/integrations/google/disconnect?workspace_id=<YOUR_WORKSPACE_ID>`
- **Database Check**: Verify the `WorkspaceGoogleConnection` row is deleted.
- **API Check**: Hit the `GET /status` endpoint and ensure `is_connected` returns `false`.
- **Database Verification**: Ensure `GoogleAnalyticsMetric` data wasn't deleted (preservation rule).

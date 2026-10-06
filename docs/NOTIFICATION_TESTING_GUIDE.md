# Notification Testing Guide

## Overview
This guide explains how to test real-time SSE notifications in your application.

## How Notifications Work

### 1. Backend Flow
When a user updates their profile (one of the events that notify; invitations, roles, billing and finished articles do too):

1. **Profile Update** → `PATCH /api/v1/user/profile` (`src/api/routes/users/profile.py`)
2. **Notification Scheduled** → `schedule_if_allowed()` checks user preferences
3. **Background Task** → `notification_service.send_success_notification()`
4. **SSE Event Published** → Event sent to `user-notifications-{USER_ID}` stream
5. **Event Format**: `notification.success` with payload

### 2. SSE Connection Format

**URL and header:**
```
GET http://127.0.0.1:2024/api/v1/events/user-notifications-{USER_ID}
Authorization: Bearer {JWT_TOKEN}
Accept: text/event-stream
```

The token goes in the `Authorization` header only; the old `?token=` query parameter is no longer accepted (a token in a URL ends up in access logs). The browser's `EventSource` cannot send headers, so read the stream with `fetch` or `@microsoft/fetch-event-source`, as the dashboard does.

**Check it with curl:**
```bash
curl -N -H "Authorization: Bearer $TOKEN" -H "Accept: text/event-stream" \
  http://127.0.0.1:2024/api/v1/events/user-notifications-8f7aae52-8aac-426b-8648-fc144c17ac43
```

### 3. Event Names to Listen For

The notification service publishes these event types:
- `notification.success` - Success notifications (a profile update, an accepted invitation, a finished article)
- `notification.error` - Error notifications
- `notification.warning` - Warning notifications
- `notification.info` - Info notifications
- `notification.new_message` - General messages
- `notification.system` - System notifications

## Testing Steps

### Step 1: Get Your User ID and JWT Token

1. **Login to your application** via the frontend or API
2. **Extract from browser console:**
   ```javascript
   // In browser console
   localStorage.getItem('auth_token') // or 'token'
   ```
3. **Decode JWT to get user ID:**
   - Go to https://jwt.io
   - Paste your token
   - Look for the `id` field in the payload

### Step 2: Open the Test Client

1. Serve the page from an origin listed in the backend's `ALLOWED_ORIGINS` (it sends an `Authorization` header, so the browser checks CORS first), for example `python3 -m http.server 3000 --directory docs` while the dashboard is not on port 3000, then open `http://localhost:3000/notification-test-client.html`
2. Fill in the fields:
   - **Backend URL**: `http://127.0.0.1:2024`
   - **Operation ID**: `user-notifications-{YOUR_USER_ID}` (replace with your actual user ID)
   - **JWT Token**: Paste your token from localStorage

### Step 3: Connect to SSE Stream

1. Click **"Connect to SSE"** button
2. You should see:
   - Status changes to "Connected" (green)
   - A "Connection Opened" event appears
   - A `connection.connected` event in the events list

### Step 4: Trigger a Notification

**Option A: Update your profile with the API**
```bash
curl -X PATCH http://127.0.0.1:2024/api/v1/user/profile \
  -H "Authorization: Bearer {YOUR_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"display_name": "Notification Test"}'
```

**Option B: Use the Frontend**
1. Open your profile settings
2. Change your display name
3. Save

### Step 5: Verify Notification Received

In the test client, you should see:
1. A new event card appears with:
   - **Event Type**: `notification.success`
   - **Event Data**: JSON containing:
     ```json
     {
       "id": "...",
       "operation_id": "user-notifications-{YOUR_USER_ID}",
       "scope": "notification",
       "step": "success",
       "status": "completed",
       "message": "Your profile has been successfully updated.",
       "payload": {
         "user_id": "{YOUR_USER_ID}",
         "updated_fields": ["display_name"]
       },
       "timestamp": "2025-11-27T12:05:10.291382+00:00"
     }
     ```

## Troubleshooting

### Issue 1: Connection Fails (401 Unauthorized)
**Cause**: Invalid or expired JWT token

**Solution**:
1. Get a fresh token by logging in again
2. Make sure you're copying the complete token
3. Verify token is not expired at https://jwt.io

### Issue 2: Connection Fails (403 Forbidden)
**Cause**: User ID doesn't match the token

**Solution**:
1. Decode your JWT token to get the correct user ID
2. Ensure operation_id format is: `user-notifications-{USER_ID}`

### Issue 3: Connected but No Events
**Cause**: User notification preferences disabled

**Solution**:
Check notification preferences in database:
```sql
SELECT * FROM notification_preferences WHERE user_id = '{YOUR_USER_ID}';
```

Ensure `in_app_notifications` (the master switch, which the profile notification also uses) is `true`.

### Issue 4: Wrong Event Name
**Cause**: Not listening for the correct event type

**Solution**:
The test client already listens for `notification.success`. In your React app, make sure you have:
```javascript
eventSource.addEventListener("notification.success", (event) => {
  const data = JSON.parse(event.data);
  console.log("Notification:", data);
});
```

### Issue 5: CORS Error
**Cause**: Frontend running on different origin

**Solution**:
Check `.env` file has correct CORS settings:
```
ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
```

## React Integration Example

The dashboard's real implementation is `providers/sse-provider.tsx` in rext-admin. A minimal version:

```javascript
import { useEffect, useState } from 'react';
import { fetchEventSource } from '@microsoft/fetch-event-source';

function useNotifications(userId, token) {
  const [notifications, setNotifications] = useState([]);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    if (!userId || !token) return;

    const controller = new AbortController();
    const url = `http://127.0.0.1:2024/api/v1/events/user-notifications-${userId}`;

    fetchEventSource(url, {
      headers: { Authorization: `Bearer ${token}`, Accept: 'text/event-stream' },
      signal: controller.signal,
      onopen: async () => setConnected(true),
      onmessage: (event) => {
        if (event.event === 'notification.success' || event.event === 'notification.error') {
          setNotifications(prev => [...prev, JSON.parse(event.data)]);
        }
      },
      onerror: (error) => {
        console.error('SSE Error:', error);
        setConnected(false);
      },
    });

    return () => {
      controller.abort();
      setConnected(false);
    };
  }, [userId, token]);

  return { notifications, connected };
}

export default useNotifications;
```

## Backend Logs to Check

When a notification is sent, you should see these logs:

```
[info] Preparing to send success notification to user {USER_ID}
[info] Persisted notification {NOTIFICATION_ID} for user {USER_ID}
[info] Publishing notification event for user {USER_ID}: {MESSAGE} (attempt 1/2)
[debug] Publishing event to 1 subscribers for operation user-notifications-{USER_ID}
[info] SSE notification sent for notification {NOTIFICATION_ID} to user {USER_ID}
```

If you see "Buffered event for operation (no active subscribers)", it means:
- The notification was sent
- But no one was connected to the SSE stream at that time
- Connect BEFORE triggering the notification

## Quick Test Script

Save this as `test_notification.sh`:

```bash
#!/bin/bash

# Configuration
BACKEND_URL="http://127.0.0.1:2024"
TOKEN="your-jwt-token"

# Update the profile to trigger a notification
curl -X PATCH "$BACKEND_URL/api/v1/user/profile" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"display_name": "Notification Test"}'
```

Make it executable:
```bash
chmod +x test_notification.sh
./test_notification.sh
```

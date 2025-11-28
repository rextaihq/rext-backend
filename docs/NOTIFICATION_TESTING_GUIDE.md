# Notification Testing Guide

## Overview
This guide explains how to test real-time SSE notifications in your application.

## How Notifications Work

### 1. Backend Flow
When a knowledge item is created (web, file, or text):

1. **Knowledge Creation** → `workspace_knowledge.py` endpoint
2. **Notification Scheduled** → `schedule_if_allowed()` checks user preferences
3. **Background Task** → `notification_service.send_success_notification()`
4. **SSE Event Published** → Event sent to `user-notifications-{USER_ID}` stream
5. **Event Format**: `notification.success` with payload

### 2. SSE Connection Format

**Correct URL Format:**
```
http://127.0.0.1:2024/api/v1/events/user-notifications-{USER_ID}?token={JWT_TOKEN}
```

**Example:**
```
http://127.0.0.1:2024/api/v1/events/user-notifications-8f7aae52-8aac-426b-8648-fc144c17ac43?token=eyJhbGc...
```

### 3. Event Names to Listen For

The notification service publishes these event types:
- `notification.success` - Success notifications (knowledge processing completed)
- `notification.error` - Error notifications (knowledge processing failed)
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

1. Open `docs/notification-test-client.html` in your browser
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

**Option A: Create Text Knowledge**
```bash
curl -X POST http://127.0.0.1:2024/api/v1/workspaces/{WORKSPACE_ID}/knowledge/text \
  -H "Authorization: Bearer {YOUR_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Test Notification",
    "content": "This is a test to trigger a notification"
  }'
```

**Option B: Use the Frontend**
1. Go to your workspace
2. Add a new text knowledge item
3. Fill in title and content
4. Submit

**Option C: Create Web Knowledge**
```bash
curl -X POST http://127.0.0.1:2024/api/v1/workspaces/{WORKSPACE_ID}/knowledge/web \
  -H "Authorization: Bearer {YOUR_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://example.com"
  }'
```

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
       "message": "Text knowledge 'Test Notification' processed successfully.",
       "payload": {
         "knowledge_id": "...",
         "type": "text"
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

Ensure these columns are `true`:
- `in_app_notifications` (master switch)
- `kb_processing_completed` (for knowledge notifications)

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

```javascript
import { useEffect, useState } from 'react';

function useNotifications(userId, token) {
  const [notifications, setNotifications] = useState([]);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    if (!userId || !token) return;

    const operationId = `user-notifications-${userId}`;
    const url = `http://127.0.0.1:2024/api/v1/events/${operationId}?token=${token}`;
    
    const eventSource = new EventSource(url);

    eventSource.addEventListener('connection.connected', () => {
      setConnected(true);
      console.log('SSE Connected');
    });

    eventSource.addEventListener('notification.success', (event) => {
      const data = JSON.parse(event.data);
      setNotifications(prev => [...prev, data]);
      console.log('Success notification:', data);
    });

    eventSource.addEventListener('notification.error', (event) => {
      const data = JSON.parse(event.data);
      setNotifications(prev => [...prev, data]);
      console.error('Error notification:', data);
    });

    eventSource.onerror = (error) => {
      console.error('SSE Error:', error);
      setConnected(false);
    };

    return () => {
      eventSource.close();
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
[info] Scheduling notification for user {USER_ID} – flag kb_processing_completed – message: Text knowledge 'xxx' processed successfully.
[info] Notification task scheduled.
[info] Preparing to send success notification to user {USER_ID}
[info] Publishing notification event for user {USER_ID}: {MESSAGE}
[debug] Publishing event to 1 subscribers for operation user-notifications-{USER_ID}
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
WORKSPACE_ID="your-workspace-id"
TOKEN="your-jwt-token"

# Create text knowledge to trigger notification
curl -X POST "$BACKEND_URL/api/v1/workspaces/$WORKSPACE_ID/knowledge/text" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Notification Test",
    "content": "This is a test notification message for SSE testing"
  }'
```

Make it executable:
```bash
chmod +x test_notification.sh
./test_notification.sh
```

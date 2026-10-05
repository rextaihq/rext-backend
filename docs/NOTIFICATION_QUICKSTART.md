# Notification System - Quick Start Guide

## 🔍 Current Status

**Notification events are NOT being received on the frontend**, despite the backend sending them.

## 📋 What I Found

### ✅ Working Components
1. **SSE Infrastructure** - Fully functional for operation-level events
2. **Backend Configuration** - Connected to `http://127.0.0.1:2024`
3. **Notification Preferences** - UI and schemas defined
4. **NotificationsDrawer** - UI exists (but uses mock data)

### ❌ Missing Components
1. **No global notification listener** - No component subscribes to user notifications
2. **No real-time notification handler** - Events aren't connected to UI
3. **No notification state management** - No store for notifications
4. **NotificationsDrawer disconnected** - Shows only sample data

## 🧪 Testing Steps

### Step 1: Test Backend Connection

1. **Open the test client**:
   ```bash
   # Serve it from an origin in ALLOWED_ORIGINS (the page sends an Authorization header,
   # so the browser checks CORS), then open http://localhost:3000/notification-test-client.html
   python3 -m http.server 3000 --directory docs
   ```

2. **Configure the test client**:
   - Backend URL: `http://127.0.0.1:2024`
   - User ID: Try these options:
     - `notifications` (global channel)
     - `user-{your-user-id}` (user-specific)
     - Your actual user ID from the database
   - JWT Token: Get from browser DevTools:
     - Open your app in browser
     - F12 → Application → Local Storage
     - Copy the `auth_token` or `token` value

3. **Click "Connect to SSE"**

4. **Trigger a notification**:
   - Create a knowledge base (web, file, or text)
   - Wait for processing to complete
   - Check if `kb_processing_completed` event appears in test client

### Step 2: Verify Backend Endpoint

If no events appear, try different endpoint patterns:

```javascript
// Try these URLs in the test client:
http://127.0.0.1:2024/api/v1/events/notifications
http://127.0.0.1:2024/api/v1/events/user/{userId}
http://127.0.0.1:2024/api/v1/notifications/stream
http://127.0.0.1:2024/api/v1/sse/notifications
```

### Step 3: Check Backend Logs

Look for:
- Notification publishing logs
- SSE connection attempts
- Authentication errors
- Event channel names

## 🛠️ Implementation Plan

Once you confirm the backend endpoint works, implement these files:

### 1. Create User Notification Hook
**File**: `hooks/use-user-notifications.ts`

```typescript
import { useEffect, useState } from 'react';
import { useSSE } from '@/providers/sse-provider';
import { useAuth } from '@/providers/auth-provider';
import { toast } from 'sonner';

interface Notification {
  id: string;
  type: string;
  title: string;
  message: string;
  timestamp: string;
  read: boolean;
  payload?: any;
}

export function useUserNotifications() {
  const { subscribe } = useSSE();
  const { user } = useAuth();
  const [notifications, setNotifications] = useState<Notification[]>([]);

  useEffect(() => {
    if (!user?.id) return;

    // TODO: Update 'notifications' to match your backend channel name
    const channelId = 'notifications'; // or `user-${user.id}`

    const unsubscribe = subscribe(
      channelId,
      (event) => {
        // Parse notification from SSE event
        const notification: Notification = {
          id: event.id,
          type: event.step || 'info',
          title: event.message || 'Notification',
          message: event.payload?.message || event.message,
          timestamp: event.timestamp,
          read: false,
          payload: event.payload,
        };

        // Add to list
        setNotifications(prev => [notification, ...prev]);

        // Show toast
        if (notification.type.includes('success') || notification.type.includes('completed')) {
          toast.success(notification.title, {
            description: notification.message,
          });
        } else if (notification.type.includes('error') || notification.type.includes('failed')) {
          toast.error(notification.title, {
            description: notification.message,
          });
        } else {
          toast.info(notification.title, {
            description: notification.message,
          });
        }
      }
    );

    return unsubscribe;
  }, [user?.id, subscribe]);

  const markAsRead = (id: string) => {
    setNotifications(prev =>
      prev.map(n => n.id === id ? { ...n, read: true } : n)
    );
  };

  const markAllAsRead = () => {
    setNotifications(prev => prev.map(n => ({ ...n, read: true })));
  };

  return {
    notifications,
    markAsRead,
    markAllAsRead,
    unreadCount: notifications.filter(n => !n.read).length,
  };
}
```

### 2. Create Notification Provider
**File**: `providers/notification-provider.tsx`

```typescript
'use client';

import { createContext, useContext, type ReactNode } from 'react';
import { useUserNotifications } from '@/hooks/use-user-notifications';

interface NotificationContextType {
  notifications: any[];
  markAsRead: (id: string) => void;
  markAllAsRead: () => void;
  unreadCount: number;
}

const NotificationContext = createContext<NotificationContextType | null>(null);

export function NotificationProvider({ children }: { children: ReactNode }) {
  const notificationState = useUserNotifications();

  return (
    <NotificationContext.Provider value={notificationState}>
      {children}
    </NotificationContext.Provider>
  );
}

export function useNotifications() {
  const context = useContext(NotificationContext);
  if (!context) {
    throw new Error('useNotifications must be used within NotificationProvider');
  }
  return context;
}
```

### 3. Update App Layout
**File**: `app/layout.tsx`

```typescript
// Add import
import { NotificationProvider } from '@/providers/notification-provider';

// Update provider hierarchy (inside SSEProvider)
<SSEProvider>
  <NotificationProvider>
    <QueryProvider>
      {/* ... rest of app */}
    </QueryProvider>
  </NotificationProvider>
</SSEProvider>
```

### 4. Update NotificationsDrawer
**File**: `components/notifications-drawer.tsx`

```typescript
// Replace the sample data with real notifications
import { useNotifications } from '@/providers/notification-provider';

export function NotificationsDrawer({ open, onClose }: NotificationsDrawerProps) {
  const { notifications, markAsRead, markAllAsRead, unreadCount } = useNotifications();

  // Use real notifications instead of sampleNotifications
  // ... rest of component
}
```

## 🎯 Expected Behavior After Implementation

1. **User logs in** → SSE connection established
2. **Backend sends notification** → Frontend receives event
3. **Toast appears** → User sees real-time notification
4. **NotificationsDrawer updates** → Shows in notification list
5. **User clicks notification** → Marked as read

## 🐛 Troubleshooting

### No events in test client?
- ✅ Check backend is running on port 2024
- ✅ Verify JWT token is valid
- ✅ Check browser console for errors
- ✅ Try different channel IDs (notifications, user-{id})
- ✅ Check backend logs for connection attempts

### Events received but not showing in app?
- ✅ Verify NotificationProvider is in app layout
- ✅ Check browser console for React errors
- ✅ Verify useUserNotifications hook is being called
- ✅ Check SSE connection in Network tab (EventStream)

### Toast notifications not appearing?
- ✅ Verify Toaster component is in layout
- ✅ Check toast.success/error/info are being called
- ✅ Check browser notification permissions

## 📚 Related Files

- **Analysis**: `NOTIFICATION_ANALYSIS.md` - Detailed technical analysis
- **Test Client**: `notification-test-client.html` - SSE testing tool
- **SSE Provider**: `providers/sse-provider.tsx` - Core SSE infrastructure
- **Notification Schemas**: `schemas/notification-schemas.ts` - Notification types

## 🚀 Quick Commands

```bash
# Start the backend (if not running)
cd ../rext-backend
python -m uvicorn src.main:app --reload --port 2024

# Start the frontend
cd rext-admin
npm run dev

# Open test client
open notification-test-client.html
```

## ❓ Questions to Answer

1. **What is the exact SSE endpoint for user notifications?**
   - Test with: `/api/v1/events/notifications`
   - Or: `/api/v1/events/user/{userId}`

2. **What is the event format?**
   - Check test client to see actual event structure
   - Update notification parsing accordingly

3. **How is authentication handled?**
   - The `Authorization: Bearer <token>` header only; the `?token=` query parameter is no longer accepted
   - The browser's `EventSource` cannot send headers: use `fetch` or `@microsoft/fetch-event-source`

4. **What is the channel/operation ID?**
   - `notifications` (global)
   - `user-{userId}` (user-specific)
   - Something else?

## 📞 Next Steps

1. ✅ **Run test client** - Verify backend is sending events
2. ⏳ **Identify endpoint** - Determine correct SSE URL
3. ⏳ **Implement hook** - Create useUserNotifications
4. ⏳ **Add provider** - Wrap app with NotificationProvider
5. ⏳ **Connect UI** - Update NotificationsDrawer
6. ⏳ **Test end-to-end** - Trigger KB processing and verify notification appears

---

**Need help?** Check the detailed analysis in `NOTIFICATION_ANALYSIS.md`

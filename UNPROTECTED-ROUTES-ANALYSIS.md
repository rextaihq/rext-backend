# Unprotected Routes Analysis

**Generated:** 2025-10-24
**Total Unprotected:** 107 routes
**Current Coverage:** 52.2% (117/224 protected)

---

## Category 1: INTENTIONALLY PUBLIC (No Protection Needed) - 20 routes

These routes are designed to be accessed without authentication or are part of public APIs.

### Health Checks & Monitoring (2 routes)
- ❌ `GET /health/payment` - Public health check endpoint
- ❌ `GET /health/payment/quick` - Public quick health check

### Public Invitation Flow (5 routes)
- ❌ `GET /invitations/{token}/validate` - Public invitation validation
- ❌ `POST /invitations/{token}/accept` - Public invitation acceptance
- ❌ `GET /admin/invitations/{token}/validate` - Admin invitation validation
- ❌ `POST /admin/invitations/{token}/accept` - Admin invitation acceptance
- ❌ `POST /admin/invitations/{token}/decline` - Admin invitation decline

### Webhooks (2 routes)
- ❌ `POST /email/webhooks/resend` - Resend webhook (verified by signature)
- ❌ `POST /subscriptions/webhook/lemonsqueezy` - LemonSqueezy webhook (verified by signature)

### Public Subscription Info (3 routes)
- ❌ `GET /subscriptions/plans/public` - Public plan listing (no auth required)
- ❌ `POST /licenses/validate` - License validation (public API)
- ❌ `GET /subscriptions/trial/eligibility` - Check trial eligibility

### Public Email Preferences (1 route)
- ❌ `POST /users/email-preferences/unsubscribe` - Email unsubscribe link

### Public SSE Test (1 route)
- ❌ `GET /events/sse/test` - SSE test endpoint for debugging

### Invoice Access (1 route)
- ❌ `GET /subscriptions/invoices` - User's own invoices (needs auth but may be token-based)

### Email Template Previews (4 routes)
- ❌ `POST /email/preview/auth` - Preview auth emails
- ❌ `POST /email/preview/workspace` - Preview workspace emails
- ❌ `POST /email/preview/auth/html` - Preview auth emails (HTML)
- ❌ `POST /email/preview/workspace/html` - Preview workspace emails (HTML)

### Knowledge Base Public Query (1 route)
- ❌ `GET /workspaces/{id}/knowledge/text/{text_id}` - May be public for published content

---

## Category 2: PERMISSION SYSTEM INTERNALS (No Decorator Needed) - 10 routes

These routes ARE the permission checking system and shouldn't have permission checks themselves.

### Permission Checking Endpoints (5 routes)
- ❌ `GET /workspaces/{workspace_id}/permissions/me` - Get user's workspace permissions
- ❌ `GET /workspaces/{workspace_id}/permissions/check` - Check specific permission
- ❌ `POST /workspaces/{workspace_id}/permissions/refresh` - Refresh permission cache
- ❌ `GET /workspaces/{workspace_id}/members/{user_id}/permissions` - Get member permissions
- ❌ `GET /users/me/permissions` - Get user's global permissions

### User Role Information (1 route)
- ❌ `GET /users/{user_id}/roles` - Get user roles (used by permission system)

### SSE Progress Streaming (1 route)
- ❌ `GET /events/sse/{operation_id}` - Real-time progress updates (requires auth token in URL)

### Email Template Variables (3 routes)
- ❌ `GET /workspaces/email-templates/variables/{template_type}` - Template variables metadata
- ❌ `POST /workspaces/email-templates/preview` - Preview template
- ❌ `GET /workspaces/email-templates/defaults/{template_type}` - Default templates

---

## Category 3: REQUIRES PROTECTION - Admin Routes (24 routes)

These are admin-only routes that MUST be protected with proper permissions.

### Admin Subscription Analytics (8 routes) - **PRIORITY: HIGH**
- ❌ `GET /admin/subscriptions/stats/overview` → `subscription.analytics.read`
- ❌ `GET /admin/subscriptions/stats/revenue` → `subscription.analytics.read`
- ❌ `GET /admin/subscriptions/stats/churn` → `subscription.analytics.read`
- ❌ `GET /admin/subscriptions/stats/trial-conversion` → `subscription.analytics.read`
- ❌ `GET /admin/subscriptions/analytics/overview` → `subscription.analytics.read`
- ❌ `GET /admin/subscriptions/analytics/revenue-history` → `subscription.analytics.read`
- ❌ `GET /admin/subscriptions/analytics/plan-distribution` → `subscription.analytics.read`
- ❌ `GET /admin/subscriptions/analytics/cohort-retention` → `subscription.analytics.read`

### Admin Subscription Management (4 routes) - **PRIORITY: HIGH**
- ❌ `POST /admin/subscriptions/assign` → `subscription.manage` (super admin)
- ❌ `POST /admin/subscriptions/{subscription_id}/extend` → `subscription.manage` (super admin)
- ❌ `POST /admin/subscriptions/{subscription_id}/reset-usage` → `subscription.manage` (super admin)
- ❌ `GET /admin/subscriptions/{subscription_id}` → `subscription.read` (admin)

### Admin Export Routes (7 routes) - **PRIORITY: HIGH**
- ❌ `GET /admin/export/subscriptions` → `export.subscriptions`
- ❌ `GET /admin/export/invoices` → `export.invoices`
- ❌ `GET /admin/export/usage` → `export.usage`
- ❌ `GET /admin/export/revenue-summary` → `export.revenue`
- ❌ `GET /admin/subscriptions/export/subscriptions` → `export.subscriptions`
- ❌ `GET /admin/subscriptions/export/invoices` → `export.invoices`
- ❌ `GET /admin/subscriptions/export/trial-conversions` → `export.subscriptions`

### Refund Management (3 routes) - **PRIORITY: HIGH**
- ❌ `GET /admin/refunds` → `refund.read`
- ❌ `GET /admin/refunds/{refund_id}` → `refund.read`
- ❌ `POST /admin/refunds/create` → `refund.create`

### User Impersonation (3 routes) - **PRIORITY: CRITICAL**
- ❌ `POST /users/impersonate/start` → `user.impersonate` (super admin only)
- ❌ `POST /users/impersonate/stop` → `user.impersonate` (super admin only)
- ❌ `GET /users/impersonate/status` → `user.impersonate` (super admin only)

---

## Category 4: REQUIRES PROTECTION - User Management (18 routes)

These routes manage user data and should have appropriate permissions.

### User CRUD Operations (4 routes) - **PRIORITY: HIGH**
- ❌ `GET /users/management/users` → `user.read` (admin)
- ❌ `DELETE /users/management/{user_id}` → `user.delete` (admin)
- ❌ `PUT /users/management/{user_id}` → `user.update` (admin)
- ❌ `POST /users/management/export-data` → `user.export` (user's own data or admin)

### User Status Management (4 routes) - **PRIORITY: HIGH**
- ❌ `POST /users/{user_id}/suspend` → `user.suspend` (admin)
- ❌ `POST /users/{user_id}/activate` → `user.activate` (admin)
- ❌ `POST /users/{user_id}/ban` → `user.ban` (admin)
- ❌ `POST /users/deactivate` → `user.deactivate` (self)

### User Profile & Preferences (10 routes) - **PRIORITY: MEDIUM**
- ❌ `GET /users/profile` → Authenticated user (no permission needed, self-service)
- ❌ `PATCH /users/profile` → Authenticated user (no permission needed, self-service)
- ❌ `POST /users/profile/avatar/upload` → Authenticated user
- ❌ `DELETE /users/profile/avatar` → Authenticated user
- ❌ `GET /users/preferences` → Authenticated user
- ❌ `PATCH /users/preferences` → Authenticated user
- ❌ `GET /users/profile/preferences/notifications` → Authenticated user
- ❌ `PATCH /users/profile/preferences/notifications` → Authenticated user
- ❌ `POST /users/password/change-password` → Authenticated user
- ❌ `POST /users/password/verify-password` → Authenticated user

---

## Category 5: REQUIRES PROTECTION - Workspace Management (13 routes)

Workspace CRUD and management routes.

### Workspace CRUD (11 routes) - **PRIORITY: HIGH**
- ❌ `GET /workspaces/all` → Authenticated user (list user's workspaces)
- ❌ `GET /workspaces/detail` → Authenticated user (workspace details)
- ❌ `GET /workspaces/slug/{workspace_slug}` → `workspace.read` (workspace-scoped)
- ❌ `GET /workspaces/{workspace_id}` → `workspace.read` (workspace-scoped)
- ❌ `PUT /workspaces/{workspace_id}` → `workspace.update` (workspace-scoped)
- ❌ `DELETE /workspaces/{workspace_id}` → `workspace.delete` (workspace-scoped)
- ❌ `POST /workspaces/create` → Authenticated user (create own workspace)
- ❌ `DELETE /workspaces/delete` → `workspace.delete` (workspace-scoped)
- ❌ `PUT /workspaces/update` → `workspace.update` (workspace-scoped)
- ❌ `GET /workspaces/{workspace_id}/stats` → `workspace.read` (workspace-scoped)
- ❌ `GET /workspaces/knowledge/{kb_id}` → `knowledge.read` (workspace-scoped)

### Knowledge Base Text Routes (2 routes) - **PRIORITY: MEDIUM**
- ❌ `GET /workspaces/{id}/knowledge/text/{text_id}` → `knowledge.read` (workspace-scoped)
- ❌ `PATCH /workspaces/{id}/knowledge/text/{text_id}` → `knowledge.update` (workspace-scoped)

---

## Category 6: REQUIRES PROTECTION - User Features (12 routes)

Personal user features and invitations.

### User Onboarding (5 routes) - **PRIORITY: MEDIUM**
- ❌ `POST /users/onboarding/update` → Authenticated user (self)
- ❌ `POST /users/onboarding/complete` → Authenticated user (self)
- ❌ `POST /users/onboarding/reset` → Authenticated user (self)
- ❌ `GET /users/onboarding/should-show` → Authenticated user (self)
- ❌ `POST /users/onboarding/marketing` → Authenticated user (self)

### User Invitations (2 routes) - **PRIORITY: MEDIUM**
- ❌ `GET /users/invitations/pending` → Authenticated user (own invitations)
- ❌ `POST /users/invitations/{invitation_id}/decline` → Authenticated user (own invitations)

### User Security (3 routes) - **PRIORITY: MEDIUM**
- ❌ `GET /users/security/stats` → Authenticated user (self)
- ❌ `GET /users/security/login-history` → Authenticated user (self)
- ❌ `GET /users/security/active-sessions-count` → Authenticated user (self)

### User Sessions (4 routes) - **PRIORITY: MEDIUM**
- ❌ `GET /users/sessions` → Authenticated user (self)
- ❌ `DELETE /users/sessions/{session_id}` → Authenticated user (self)
- ❌ `DELETE /users/sessions` → Authenticated user (self)
- ❌ `POST /users/sessions/revoke-all` → Authenticated user (self)

### Workspace Invitations (2 routes) - **PRIORITY: LOW**
- ❌ `GET /workspaces/invitations/sent` → Already may have decorator
- ❌ `GET /workspaces/invitations/received` → Authenticated user

### Audit Logs (1 route) - **PRIORITY: MEDIUM**
- ❌ `GET /audit/user/my-logs` → Authenticated user (self)

---

## Summary by Priority

### 🔴 CRITICAL (3 routes)
- User impersonation routes (super admin only)

### 🟠 HIGH (35 routes)
- Admin subscription analytics (8)
- Admin subscription management (4)
- Admin export routes (7)
- Refund management (3)
- User CRUD operations (4)
- User status management (4)
- Workspace CRUD (11)

### 🟡 MEDIUM (20 routes)
- User profile & preferences (10)
- Knowledge base text routes (2)
- User onboarding (5)
- User security (3)

### 🟢 LOW (9 routes)
- User invitations (2)
- User sessions (4)
- Workspace invitations (2)
- Audit logs (1)

### ✅ NO ACTION NEEDED (30 routes)
- Intentionally public (20)
- Permission system internals (10)

---

## Recommended Action Plan

### Phase 2.4: Protect High-Priority Routes (35 routes)
1. **Admin analytics routes** (8 routes)
2. **Admin subscription management** (4 routes)
3. **Admin export routes** (7 routes)
4. **Refund management** (3 routes)
5. **User impersonation** (3 routes - CRITICAL)
6. **User CRUD** (4 routes)
7. **User status management** (4 routes)
8. **Workspace CRUD** (11 routes)

**Expected Coverage After Phase 2.4:** ~85% (152/224 routes protected)

### Phase 2.5: Protect Medium-Priority Routes (20 routes)
1. User profile & preferences (10 routes) - Self-service, require auth only
2. Knowledge base text routes (2 routes)
3. User onboarding (5 routes) - Self-service
4. User security (3 routes) - Self-service

**Expected Coverage After Phase 2.5:** ~94% (172/224 routes protected)

### Phase 2.6: Protect Low-Priority Routes (9 routes)
Complete remaining business logic routes.

**Expected Coverage After Phase 2.6:** ~98% (181/224 routes protected)

### Final Coverage
**Protected routes:** 181/224 (98%)
**Intentionally public:** 20 routes (documented)
**Permission system internals:** 10 routes (documented)
**Remaining unprotected:** 13 routes (likely health checks, test routes, etc.)

---

## Notes

1. **Self-Service Routes:** Many user routes (profile, preferences, sessions) just need authentication, not specific permissions. They operate on the authenticated user's own data.

2. **Admin Routes:** All admin routes should use either:
   - `@require_permissions(["permission.name"])` with admin-level permissions
   - Direct `is_admin` or `is_super_admin` checks in the service layer (already implemented in some)

3. **Workspace Routes:** Must use `workspace_scoped=True` to ensure workspace membership validation.

4. **Public Routes:** Should be explicitly documented in code comments and in this analysis file.

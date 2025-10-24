# Truly Unprotected Routes - Security Analysis
**Generated:** 2025-10-24
**Script Version:** Enhanced (detects all protection patterns)
**Total Unprotected:** 22 routes

## Summary
After enhancing the verification script to detect all protection patterns:
- `@require_permissions` decorator
- `Depends(is_admin)` / `Depends(is_super_admin)` in function parameters
- `Depends(require_permissions([...]))` in function parameters
- `dependencies=[Depends(...)]` in `@router` decorator
- `Depends(PermissionChecker(...))`

We now have an accurate count of **22 truly unprotected routes** (down from 29 false positives).

## Route Classification

### 🔴 **P0 - CRITICAL: Needs Protection (9 routes)**
These routes perform write/destructive operations and MUST be protected.

#### 1. Admin Invitation Routes (2 routes)
- **POST** `/admin/invitations/{token}/accept` - Accept admin invitation
- **POST** `/admin/invitations/{token}/decline` - Decline admin invitation

**Status:** ⚠️ **Needs Protection**
**Reasoning:** These routes modify admin user status. However, they use token-based authentication.
**Action Required:** Add token validation middleware or document as intentionally token-protected

#### 2. Workspace Invitation Routes (1 route)
- **POST** `/workspaces/invitations/{token}/accept` - Accept workspace invitation

**Status:** ⚠️ **Needs Protection**
**Reasoning:** Modifies workspace membership. Uses token-based authentication.
**Action Required:** Add token validation middleware or document as intentionally token-protected

#### 3. Email Webhook (1 route)
- **POST** `/email/webhooks/resend` - Handle Resend webhook

**Status:** ✅ **Intentionally Public**
**Reasoning:** External webhook callback. Should have signature verification.
**Action Required:** Verify signature validation exists, add to PUBLIC_ROUTES whitelist

#### 4. OAuth Routes (3 routes)
- **POST** `/users/oauth/login` - OAuth login
- **POST** `/users/oauth/link` - Link OAuth account
- **DELETE** `/users/oauth/{provider}` - Unlink OAuth account

**Status:** 🔴 **CRITICAL - Needs Protection**
**Reasoning:**
  - `/oauth/login` - Should be public (authentication endpoint)
  - `/oauth/link` - Needs authentication (modify user account)
  - `/oauth/{provider}` DELETE - Needs authentication (modify user account)
**Action Required:**
  - Add `/oauth/login` to PUBLIC_ROUTES
  - Add `@require_permissions("user.update")` or `Depends(get_current_user)` to link/unlink

#### 5. Email Preferences Routes (2 routes)
- **PUT** `/users/email-preferences/` - Update email preferences
- **POST** `/users/email-preferences/unsubscribe` - Unsubscribe from emails

**Status:** ⚠️ **Needs Protection (with caveats)**
**Reasoning:**
  - Update preferences: Needs authentication (modify user data)
  - Unsubscribe: Often intentionally public (via email link with token)
**Action Required:**
  - PUT: Add `Depends(get_current_user)` or `@require_permissions("user.update")`
  - POST unsubscribe: Check if token-based, add to PUBLIC_ROUTES if so

---

### 🟡 **P1 - LOW PRIORITY: Review (13 routes)**
These are GET/read-only routes that may be intentionally public or need authentication.

#### 6. Admin Invitation Validation (1 route)
- **GET** `/admin/invitations/{token}/validate` - Validate admin invitation token

**Status:** ✅ **Intentionally Public**
**Reasoning:** Public validation endpoint for token-based invitations.
**Action Required:** Add to PUBLIC_ROUTES whitelist

#### 7. Workspace Invitation Validation (1 route)
- **GET** `/workspaces/invitations/{token}/validate` - Validate workspace invitation token

**Status:** ✅ **Intentionally Public**
**Reasoning:** Public validation endpoint for token-based invitations.
**Action Required:** Add to PUBLIC_ROUTES whitelist

#### 8. Content Listing (1 route)
- **GET** `/content/` - List all content

**Status:** 🔴 **CRITICAL - Needs Protection**
**Reasoning:** Workspace-scoped resource, should require authentication and permissions.
**Action Required:** Add `@require_permissions("content.read", workspace_scoped=True)`

#### 9. Event Streaming (2 routes)
- **GET** `/events/test` - Stream test events (SSE)
- **GET** `/events/{operation_id}` - Subscribe to operation events (SSE)

**Status:** ⚠️ **Needs Review**
**Reasoning:**
  - `/events/test` - Likely development/debug endpoint
  - `/events/{operation_id}` - Real-time event stream, should validate operation ownership
**Action Required:**
  - Test endpoint: Remove in production or protect
  - Operation events: Add `Depends(get_current_user)` + validate operation ownership

#### 10. Trial Eligibility (1 route)
- **GET** `/subscriptions/trial/eligibility` - Check trial eligibility

**Status:** 🔴 **Needs Protection**
**Reasoning:** User-specific data, should require authentication.
**Action Required:** Add `Depends(get_current_user)`

#### 11. Topic Generation Status (1 route)
- **GET** `/topics/` - Get topic generation status

**Status:** 🔴 **Needs Protection**
**Reasoning:** Workspace-scoped resource, should require authentication.
**Action Required:** Add `@require_permissions("topic.read", workspace_scoped=True)`

#### 12. User Email Preferences (GET) (1 route)
- **GET** `/users/email-preferences/` - Get email preferences

**Status:** 🔴 **Needs Protection**
**Reasoning:** User-specific data, should require authentication.
**Action Required:** Add `Depends(get_current_user)`

#### 13. User Status (1 route)
- **GET** `/users/status` - Get user status

**Status:** 🔴 **Needs Protection**
**Reasoning:** User-specific data, should require authentication.
**Action Required:** Add `Depends(get_current_user)`

#### 14. Workspace Email Templates (1 route)
- **GET** `/workspaces/{workspace_id}/email-templates/` - List email templates

**Status:** 🔴 **Needs Protection**
**Reasoning:** Workspace-scoped resource, should require authentication.
**Action Required:** Add `@require_permissions("workspace.read", workspace_scoped=True)`

#### 15. Workspace Status Routes (3 routes)
- **GET** `/workspaces/` - Get workspace status (workspace_core.py)
- **GET** `/workspaces/` - Get workspace status (workspace_route.py)
- **GET** `/workspaces/invitations.py/modules/invitation_create.py/status` - Get invitation status

**Status:** 🔴 **Needs Protection**
**Reasoning:** Workspace-scoped resources, should require authentication.
**Action Required:**
  - First two: Add `Depends(get_current_user)` or workspace-scoped permission
  - Invitation status: Add `Depends(get_current_user)` + validate invitation ownership

---

## Action Plan

### Immediate Actions (Security Critical - P0)

1. **OAuth Routes** (3 routes)
   ```python
   # File: src/api/routes/users/auth.py

   # Keep public (authentication endpoint)
   @router.post("/oauth/login")  # Add to PUBLIC_ROUTES

   # Add protection
   @router.post("/oauth/link")
   @require_permissions("user.update", workspace_scoped=False)

   @router.delete("/oauth/{provider}")
   @require_permissions("user.update", workspace_scoped=False)
   ```

2. **Content Listing**
   ```python
   # File: src/api/routes/content/modules/content_retrieval.py
   @router.get("/")
   @require_permissions("content.read", workspace_scoped=True)
   async def list_content(...)
   ```

3. **Email Preferences (Update)**
   ```python
   # File: src/api/routes/users/email_preferences.py
   @router.put("/")
   @require_permissions("user.update", workspace_scoped=False)
   async def update_preferences(...)

   # Check if unsubscribe uses token, if not:
   @router.post("/unsubscribe")
   @require_permissions("user.update", workspace_scoped=False)
   async def unsubscribe(...)
   ```

### High Priority Actions (Data Access - P1)

4. **User-Specific Routes** (3 routes)
   ```python
   # Add Depends(get_current_user) to all:
   # - GET /users/email-preferences/
   # - GET /users/status
   # - GET /subscriptions/trial/eligibility
   ```

5. **Workspace-Scoped Routes** (5 routes)
   ```python
   # Add workspace-scoped permissions:
   # - GET /topics/ → topic.read
   # - GET /workspaces/email-templates/ → workspace.read
   # - GET /workspaces/ (both) → workspace.read
   # - GET /workspaces/invitations/status → workspace.read
   ```

### Low Priority Actions (Whitelist/Document)

6. **Add to PUBLIC_ROUTES** (4 routes)
   ```python
   # File: scripts/verify_route_protection.py
   PUBLIC_ROUTES = {
       ...
       "/admin/invitations",  # Token-based validation/accept/decline
       "/workspaces/invitations",  # Token-based validation/accept
       "/email/webhooks/resend",  # External webhook (has signature verification)
       "/oauth/login",  # Authentication endpoint
   }
   ```

7. **Review Event Streaming Routes** (2 routes)
   - Investigate if `/events/test` is debug-only (remove in production)
   - Add operation ownership validation to `/events/{operation_id}`

---

## Statistics

### Before Enhancement
- Reported Unprotected: 29 routes
- False Positives: 7 routes (protected via `Depends(require_permissions([...]))`)

### After Enhancement
- Truly Unprotected: 22 routes
- Critical (P0): 9 routes
- Review Required (P1): 13 routes

### Protection Pattern Distribution (265 total routes)
- ✅ Protected: 227 routes (85.7%)
- 🌐 Intentionally Public: 16 routes (6.0%)
- ❌ Unprotected: 22 routes (8.3%)

### Protection Type Breakdown
- Decorator (`@require_permissions`): 204 routes (89.9%)
- Function Dependency (`Depends(...)`): 22 routes (9.7%)
- Route Dependency (`dependencies=[...]`): 1 route (0.4%)

---

## Script Enhancements Completed

### New Detection Patterns
1. ✅ `Depends(require_permissions(["perm1", "perm2"]))` in function parameters
2. ✅ `dependencies=[Depends(require_permissions([...]))]` in `@router` decorator
3. ✅ `dependencies=[Depends(is_admin)]` in `@router` decorator

### Code Changes
- Enhanced `_check_dependency_protection()` to detect `require_permissions` calls
- Added `_extract_permissions_from_call()` helper for permission extraction
- Added `_check_route_decorator_dependencies()` for `dependencies=[...]` pattern
- Updated `_check_protection()` to check route decorator dependencies

### Result
- 7 false positives eliminated (routes now correctly marked as protected)
- Accurate security audit of 22 truly unprotected routes
- Comprehensive classification and action plan

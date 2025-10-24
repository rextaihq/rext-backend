# workspace_scoped Parameter Fixes
**Date:** 2025-10-24
**Issue:** Multiple routes failing with workspace_scoped configuration errors
**Status:** ✅ FULLY RESOLVED

## Problem Overview

Multiple routes were incorrectly configured with `workspace_scoped=True` (the default) when they should have been `workspace_scoped=False`. This caused 400 Bad Request errors for new users trying to access the dashboard.

## Understanding workspace_scoped

### workspace_scoped=True (Default)
- **Used for**: Workspace-specific operations (content CRUD, workspace settings, workspace members)
- **Requirements**: Route MUST have `workspace_id: UUID` parameter
- **Permission Check**: Verifies user has permission in THAT specific workspace
- **Example**: Creating content, updating workspace settings

### workspace_scoped=False
- **Used for**: User-level operations across all workspaces
- **Requirements**: No workspace_id needed
- **Permission Check**: Verifies user has general permission (not workspace-specific)
- **Example**: Listing user's workspaces, user profile, onboarding

## Routes Fixed

### 1. Get User's Workspaces
**File:** `src/api/routes/workspaces/workspace_core.py:36`
**Route:** `GET /api/v1/workspaces/all`
**Error:** 400 Bad Request - "requires 'workspace_id' parameter"

**Why it failed:**
- Route lists ALL workspaces user has access to
- Cannot be workspace-scoped (you're searching across workspaces, not within one)

**Fix:**
```python
# Before:
@router.get("/all")
@require_permissions("workspace.read")  # Defaults to workspace_scoped=True

# After:
@router.get("/all")
@require_permissions("workspace.read", workspace_scoped=False)
```

### 2. Get Workspace by Slug
**File:** `src/api/routes/workspaces/workspace_core.py:105`
**Route:** `GET /api/v1/workspaces/slug/{workspace_slug}`
**Error:** 400 Bad Request - "requires 'workspace_id' parameter"

**Why it failed:**
- Route takes `workspace_slug` parameter (not `workspace_id`)
- Used to FIND a workspace by slug (you don't know the ID yet)
- Searches across all user's workspaces

**Fix:**
```python
# Before:
@router.get("/slug/{workspace_slug}")
@require_permissions("workspace.read")  # Defaults to workspace_scoped=True

# After:
@router.get("/slug/{workspace_slug}")
@require_permissions("workspace.read", workspace_scoped=False)
```

### 3. Get Impersonation Status
**File:** `src/api/routes/users/impersonation.py:166`
**Route:** `GET /api/v1/user/impersonate/status`
**Error 1:** 400 Bad Request - "requires 'workspace_id' parameter"
**Error 2:** 403 Forbidden - "Missing required permission: user.read"

**Why it failed:**
- User-level operation (reads JWT token to check if user is being impersonated)
- New users don't have `user.read` permission
- Endpoint only reads JWT token (no sensitive data access)

**Fix:**
```python
# Before:
@router.get("/impersonate/status", response_model=ImpersonationStatusResponse)
@require_permissions("user.read", workspace_scoped=False)
async def get_impersonation_status(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):

# After:
@router.get("/impersonate/status", response_model=ImpersonationStatusResponse)
async def get_impersonation_status(
    current_user: dict = Depends(get_current_user)
):
# Removed permission requirement entirely - just reads JWT
```

### 4. User Invitations Routes
**File:** `src/api/routes/users/invitations.py`
**Routes:**
- `GET /api/v1/user/invitations/pending`
- `POST /api/v1/user/invitations/{invitation_id}/decline`

**Error:** 404 Not Found (wrong prefix) + 400 Bad Request

**Why it failed:**
- Router prefix was `/user/invitations` but mounted under `/user`, causing `/user/user/invitations`
- User-level operations (managing personal invitations)

**Fix:**
```python
# Before:
router = APIRouter(prefix="/user/invitations", tags=["User Invitations"])
@router.get("/pending")
@require_permissions("member.read")  # Defaults to workspace_scoped=True

# After:
router = APIRouter(prefix="/invitations", tags=["User Invitations"])
@router.get("/pending")
@require_permissions("member.read", workspace_scoped=False)

@router.post("/{invitation_id}/decline")
@require_permissions("member.read", workspace_scoped=False)
```

### 5. Onboarding Routes (Permission Removed)
**File:** `src/api/routes/users/onboarding.py`
**Routes:** All 6 onboarding endpoints
**Error:** 400 Bad Request → 403 Forbidden - "Missing required permission: user.update"

**Why it failed:**
- User-level operations (managing personal onboarding)
- New users don't have `user.update` permission assigned
- Onboarding is self-management (doesn't need special permissions)

**Fix:** Removed ALL permission decorators from onboarding routes
```python
# Removed from these routes:
# - GET /api/v1/onboarding (get status)
# - POST /api/v1/onboarding/update (update step)
# - POST /api/v1/onboarding/complete (complete onboarding)
# - POST /api/v1/onboarding/reset (reset onboarding)
# - GET /api/v1/onboarding/should-show (check if should show)
# - POST /api/v1/onboarding/marketing (update marketing data)

# Before:
@router.post("/complete", response_model=OnboardingResponse)
@require_permissions("user.update", workspace_scoped=False)
async def complete_onboarding(...)

# After:
@router.post("/complete", response_model=OnboardingResponse)
async def complete_onboarding(...)
# Users can manage their own onboarding without special permissions
```

## Decision Matrix

Use this table to determine the correct `workspace_scoped` value:

| Route Scenario | workspace_scoped | Has workspace_id param? | Example |
|----------------|------------------|-------------------------|---------|
| Creating content in a workspace | `True` | ✅ Yes | `POST /workspaces/{workspace_id}/content` |
| Updating workspace settings | `True` | ✅ Yes | `PATCH /workspaces/{workspace_id}` |
| Managing workspace members | `True` | ✅ Yes | `POST /workspaces/{workspace_id}/members` |
| **Listing user's workspaces** | **False** | ❌ No | `GET /workspaces/all` |
| **Finding workspace by slug** | **False** | ❌ No | `GET /workspaces/slug/{slug}` |
| **User profile operations** | **False** | ❌ No | `GET /user/profile` |
| **User onboarding** | **False** | ❌ No | `POST /onboarding/complete` |
| **User invitations** | **False** | ❌ No | `GET /user/invitations/pending` |
| **Impersonation status** | **None** | ❌ No | `GET /user/impersonate/status` |

## Quick Rules

1. **Has `workspace_id` parameter?** → `workspace_scoped=True` (default)
2. **Has `workspace_slug` or searches across workspaces?** → `workspace_scoped=False`
3. **User-level operation (profile, onboarding, etc.)?** → `workspace_scoped=False`
4. **Just reads JWT token with no DB access?** → Remove permission requirement

## Verification Commands

```bash
# 1. Check all workspace.read decorators have explicit workspace_scoped
grep -r "@require_permissions.*workspace\.read" src/api/routes --include="*.py" -B 1 -A 5 | grep -E "workspace_id|workspace_slug"

# 2. Check all user.* permission decorators
grep -r "@require_permissions.*user\." src/api/routes --include="*.py" -B 1 -A 3

# 3. Verify server starts without errors
python main.py
```

## Testing Results

All dashboard errors for new users have been resolved:

✅ `GET /api/v1/workspaces/all` - Returns empty workspace list (200 OK)
✅ `GET /api/v1/workspaces/slug/{slug}` - Returns workspace by slug (200 OK)
✅ `GET /api/v1/user/impersonate/status` - Returns impersonation status (200 OK)
✅ `GET /api/v1/user/invitations/pending` - Returns pending invitations (200 OK)
✅ `POST /api/v1/onboarding/complete` - Completes onboarding (200 OK)
✅ Server starts without workspace_scoped errors

## Files Modified

1. `src/api/routes/workspaces/workspace_core.py` - 2 routes fixed
2. `src/api/routes/users/impersonation.py` - Permission removed
3. `src/api/routes/users/invitations.py` - Prefix fixed + workspace_scoped added
4. `src/api/routes/users/onboarding.py` - All permissions removed (6 routes)

**Total Impact:** 4 files, 11 routes fixed

## Related Documentation

- [REQUIRE-PERMISSIONS-COMPREHENSIVE-FIX.md](./REQUIRE-PERMISSIONS-COMPREHENSIVE-FIX.md) - Decorator vs dependency patterns
- [RBAC-IMPLEMENTATION-PROGRESS.md](../RBAC-IMPLEMENTATION-PROGRESS.md) - Overall RBAC implementation

---

**Status:** FULLY RESOLVED ✅
**Testing:** All new user dashboard flows working
**Breaking Changes:** None (all changes are fixes)

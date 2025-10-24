# Multi-Role Architecture in WREXT

## Overview

WREXT implements a sophisticated multi-role RBAC (Role-Based Access Control) system that supports both global (platform-level) and workspace-scoped (tenant-level) roles. This architecture enables fine-grained access control in a multi-tenant SaaS environment.

## Key Concepts

### Multiple Roles Per User

**Yes, users can have multiple roles!**

Each user in WREXT can have:
- **1 global role** (`workspace_id = NULL`) - Typically "user"
- **Multiple workspace-scoped roles** (one per workspace they're a member of)

**Example:**
```
User: john@example.com
├── Global Role: "user" (workspace_id = NULL)
├── Workspace A: "workspace_owner" (workspace_id = ws-123)
├── Workspace B: "editor" (workspace_id = ws-456)
└── Workspace C: "viewer" (workspace_id = ws-789)
```

### Role Scoping

#### Global Roles (`workspace_id = NULL`)
- Apply platform-wide across all workspaces
- Included in JWT token on login
- Examples: `user`, `super_admin`
- Use case: Platform-level permissions (create workspace, etc.)

#### Workspace-Scoped Roles (`workspace_id = <uuid>`)
- Apply only within a specific workspace (tenant)
- **NOT** included in JWT token
- Fetched per-workspace via API
- Examples: `workspace_owner`, `editor`, `viewer`
- Use case: Tenant-specific permissions (manage content, invite members, etc.)

##

 How It Works

### User Signup Flow

```
1. User signs up
   ↓
2. System assigns global "user" role
   - workspace_id = NULL
   - is_primary = true
   ↓
3. User can now create workspaces
```

### Workspace Creation Flow

```
1. User creates workspace
   ↓
2. System assigns "workspace_owner" role
   - workspace_id = <new-workspace-id>
   - is_primary = true
   ↓
3. User becomes workspace member
   - status = "active"
   - is_default = true
```

### Invitation Flow

```
1. Workspace owner invites user
   - Specifies role: admin, editor, reviewer, or viewer
   ↓
2. User accepts invitation
   ↓
3. System assigns specified workspace role
   - workspace_id = <workspace-id>
   - is_primary = true
   ↓
4. User becomes workspace member
```

## Login Response Behavior

### What's in the JWT Token

The login endpoint (`POST /api/v1/auth/login`) returns **ONLY global roles** in the JWT token:

```json
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "user": {
    "id": "user-uuid",
    "email": "john@example.com",
    "roles": ["user"],  // ← Only global roles!
    "permissions": ["workspace.read", "workspace.create", ...]
  }
}
```

### Why Only Global Roles?

1. **JWT Size** - Including all workspace roles would bloat the token
2. **Security** - Workspace roles can change frequently, JWT can't be updated
3. **Performance** - Smaller tokens = faster transmission
4. **Flexibility** - Workspace roles fetched as needed

### How to Get Workspace Roles

To get a user's roles in a specific workspace, call:

```http
GET /api/v1/workspaces/{workspace_id}/me
```

**Response:**
```json
{
  "user_id": "user-uuid",
  "workspace_id": "ws-123",
  "roles": [
    {
      "id": "role-uuid",
      "name": "workspace_owner",
      "display_name": "Workspace Owner",
      "hierarchy_level": 60
    }
  ],
  "permissions": [
    "workspace.read",
    "workspace.update",
    "workspace.delete",
    "content.create",
    ...
  ]
}
```

## Permission Resolution

### How Permissions Are Checked

When checking permissions in a workspace context, the system uses **BOTH**:
1. User's workspace-scoped roles for that workspace
2. User's global roles

```python
# In rbac_utils.py
async def check_permission(
    db: AsyncSession,
    user_id: UUID,
    permission_name: str,
    workspace_id: Optional[UUID] = None
) -> bool:
    # If workspace_id provided:
    # - Check workspace-scoped roles for that workspace
    # - ALSO check global roles
    #
    # User has permission if ANY role grants it
```

**Example:**

```
User has:
- Global "user" role → permissions: ["workspace.create"]
- Workspace A "editor" role → permissions: ["content.create", "content.update"]

In Workspace A context:
✅ workspace.create (from global "user" role)
✅ content.create (from workspace "editor" role)
✅ content.update (from workspace "editor" role)

In Workspace B context (user not a member):
✅ workspace.create (from global "user" role)
❌ content.create (no workspace role in Workspace B)
❌ content.update (no workspace role in Workspace B)
```

## Database Schema

### Relevant Tables

```sql
-- Roles (system roles, reusable across tenants)
CREATE TABLE roles (
    id UUID PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,
    display_name VARCHAR(150),
    hierarchy_level INTEGER DEFAULT 0,
    is_system_role BOOLEAN DEFAULT FALSE,
    ...
);

-- User Role Assignments (can be global or workspace-scoped)
CREATE TABLE user_roles (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id),
    role_id UUID NOT NULL REFERENCES roles(id),
    workspace_id UUID REFERENCES workspace(id),  -- NULL = global role
    is_primary BOOLEAN DEFAULT TRUE,
    assigned_at TIMESTAMP NOT NULL,
    ...
);

-- Workspace Members (separate from roles)
CREATE TABLE workspace_members (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id),
    workspace_id UUID NOT NULL REFERENCES workspace(id),
    status VARCHAR(50) DEFAULT 'pending',
    is_default BOOLEAN DEFAULT FALSE,
    ...
);
```

### Key Points

1. **workspace_id in user_roles determines scope:**
   - `NULL` = global role
   - `<uuid>` = workspace-scoped role

2. **is_primary flag:**
   - Currently always `true`
   - Originally intended for "active" vs "inactive" roles
   - May be deprecated or repurposed in future

3. **Workspace membership vs role assignment:**
   - `workspace_members` = user is a member of workspace
   - `user_roles` = user has a specific role in workspace
   - Both are required for full access

## Role Hierarchy

Roles have a `hierarchy_level` to prevent privilege escalation:

```
super_admin     (100) - Platform owner, all permissions
admin           (80)  - Platform administrator
workspace_owner (60)  - Workspace creator, full control
workspace_admin (50)  - Workspace manager
editor          (30)  - Content creator
viewer          (10)  - Read-only access
user            (1)   - Default global role
```

**Rule:** Users cannot assign roles with higher hierarchy than their own.

## Common Scenarios

### Scenario 1: User Creates First Workspace

```
Initial State:
- Global "user" role (workspace_id = NULL)

After Workspace Creation:
- Global "user" role (workspace_id = NULL)
- Workspace A "workspace_owner" role (workspace_id = ws-123)

Result:
- User has ALL permissions in Workspace A
- User can create MORE workspaces (global permission)
```

### Scenario 2: User Invited as Editor

```
Invitation:
- Workspace owner invites john@example.com
- Specifies role: "editor"

After Acceptance:
- Global "user" role (workspace_id = NULL)
- Workspace B "editor" role (workspace_id = ws-456)

Result:
- User can create/edit content in Workspace B
- User CANNOT manage members or workspace settings
- User can still create their own workspaces (global permission)
```

### Scenario 3: Multi-Workspace User

```
User State:
- Global "user" role
- Workspace A "workspace_owner" role
- Workspace B "editor" role
- Workspace C "viewer" role

Permissions:
Workspace A: Full control (owner)
Workspace B: Create/edit content (editor)
Workspace C: Read-only (viewer)
Platform: Can create new workspaces (user)
```

## API Endpoints for Role Management

### Get My Global Roles

```http
POST /api/v1/auth/login
```

Returns user's global roles in JWT token.

### Get My Workspace Roles

```http
GET /api/v1/workspaces/{workspace_id}/me
```

Returns user's roles and permissions for specific workspace.

### List All My Workspaces with Roles

```http
GET /api/v1/workspaces
```

Returns all workspaces user is a member of, with their role in each.

### Invite User to Workspace

```http
POST /api/v1/workspaces/{workspace_id}/invitations

{
  "email": "user@example.com",
  "role_id": "<role-uuid>",  // workspace_admin, editor, or viewer
  "message": "Join our team!"
}
```

## Security Considerations

### Workspace Isolation

**CRITICAL:** Permission checks MUST include workspace context!

```python
# ✅ CORRECT - Checks permission in specific workspace
await require_permission(
    db, user_id,
    "content.delete",
    workspace_id=workspace_id
)

# ❌ WRONG - Checks global permission only
await require_permission(
    db, user_id,
    "content.delete"
)
```

### Permission Inheritance

Users inherit permissions from ALL their roles:

```
Global Roles: Permissions apply everywhere
Workspace Roles: Permissions apply in that workspace only

Effective Permissions = Global Permissions ∪ Workspace Permissions
```

### Role Assignment Rules

1. Only workspace owners can transfer ownership
2. Only workspace owners/admins can invite members
3. Users cannot assign roles above their hierarchy level
4. Super admins bypass all restrictions

## Troubleshooting

### "I only see 'user' role after login"

**This is expected!** The login endpoint returns only global roles. To see workspace roles:
1. Call `GET /api/v1/workspaces` to list your workspaces
2. Call `GET /api/v1/workspaces/{id}/me` for specific workspace roles

### "User can't access workspace even with role assigned"

Check both:
1. `user_roles` table - User has workspace-scoped role?
2. `workspace_members` table - User is an active member?

Both are required!

### "Dynamic {workspace_id}_admin roles in database"

These are legacy roles from before the migration. Run:
```bash
alembic upgrade head
```

The `cleanup_dynamic_workspace_roles` migration will fix this.

## Best Practices

### For Developers

1. **Always check workspace context** when checking permissions
2. **Use system roles** (workspace_owner, editor, etc.), never create dynamic roles
3. **Cache permission checks** (already implemented with 5-min TTL)
4. **Log role assignments** for audit trail

### For Administrators

1. **Assign least privilege** - Start with viewer, grant more as needed
2. **Review workspace owners** - They have full control including billing
3. **Monitor role assignments** - Watch for unexpected patterns
4. **Use workspace_admin** - For team leads who don't need billing access

### For Users

1. **Check which workspace** you're in before performing actions
2. **Request appropriate role** - Don't ask for owner if editor is enough
3. **Create workspaces sparingly** - Each workspace counts toward subscription limits

## Migration History

### cleanup_dynamic_workspace_roles (2025-01-20)

- Migrated dynamic `{workspace_id}_admin` roles to `workspace_owner` system role
- Deleted orphaned role_permissions
- Prevented future role explosion
- **Non-reversible** migration (forward-only)

## Future Enhancements

1. **Custom Roles** - Allow workspace owners to create custom roles
2. **Role Templates** - Pre-configured role sets for common scenarios
3. **Temporary Roles** - Time-limited role assignments
4. **Role Requests** - Users can request roles, owners approve
5. **ABAC Support** - Attribute-Based Access Control for fine-grained permissions

---

**Last Updated:** January 20, 2025
**Version:** 1.0
**Maintained by:** WREXT Engineering Team

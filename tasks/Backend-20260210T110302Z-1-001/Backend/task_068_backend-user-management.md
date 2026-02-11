# Task 068: Fix Frontend-Backend User Type Mismatch (`username`/`first_name`/`last_name` vs `full_name`/`display_name`)

## Metadata
- **Task ID:** TASK-068
- **Source:** Backend User Management Audit (Finding #8 under P1 High)
- **Audit Report:** `audit-reports/backend-user-management.md`
- **Priority:** P1 High
- **Category:** bug
- **Effort Estimate:** large (4+ hours)

---

## Description

The frontend `User` interface and profile API types include fields that do not exist on the backend `Users` model, causing a systemic frontend-backend type contract mismatch. The frontend expects `username`, `first_name`, and `last_name` as user properties, but the backend `Users` model (at `src/api/models/user_models/users.py`) uses `full_name` (String 200) and `display_name` (String 200) instead. There is no `username`, `first_name`, or `last_name` column in the `users` database table.

**Frontend `User` interface** (`rext-admin/lib/api-client/users.ts:9-23`):
```typescript
export interface User {
  id: string;
  email: string;
  username: string;          // DOES NOT EXIST in backend
  first_name?: string;       // DOES NOT EXIST in backend
  last_name?: string;        // DOES NOT EXIST in backend
  display_name?: string;     // EXISTS
  status: string;
  // ...
}
```

**Backend `Users` model** (`src/api/models/user_models/users.py:16-41`):
```python
class Users(Base, SerializableMixin):
    id = Column(UUID(as_uuid=True), ...)
    email = Column(String(255), ...)
    full_name = Column(String(200))         # No first_name/last_name
    display_name = Column(String(200))      # This field matches
    # ... no username column
```

**Backend `UpdateProfileRequest`** (`src/api/schema/user_schema.py:69-75`) accepts `full_name`, `display_name`, `bio`, `language`, `timezone` — but NOT `first_name`, `last_name`, or `username`.

This mismatch causes three concrete problems:

1. **Profile updates are silently lost.** The frontend `profile-form.tsx` splits the user's name into `first_name` and `last_name` and sends them to `PATCH /api/v1/user/profile` (lines 92-99). The backend's `UpdateProfileRequest` Pydantic schema doesn't include these fields, so Pydantic silently drops them. The user's name change is never persisted.

2. **Profile reads have `undefined` values.** When the frontend calls `GET /api/v1/user/profile`, the backend returns `full_name` and `display_name` but NOT `username`, `first_name`, or `last_name`. The frontend type expects these fields, resulting in `undefined` values that cause rendering issues.

3. **Multiple frontend components reference non-existent fields.** A codebase search reveals 20+ frontend files referencing `first_name`, `last_name`, or `username` on user objects. These include the admin users page, profile form, invitation acceptance pages, auth config, impersonation dialog, and multiple test files.

The mismatch is deeply embedded across the frontend — it's not a simple type error but a fundamental data model disagreement that affects profile editing, user display, invitation UIs, and admin panels.

---

## Current Code

```typescript
// File: rext-admin/lib/api-client/users.ts
// Lines: 9-23 — User interface with non-existent backend fields
export interface User {
  id: string;
  email: string;
  username: string;          // Backend has no username column
  first_name?: string;       // Backend has full_name instead
  last_name?: string;        // Backend has full_name instead
  display_name?: string;
  status: string;
  email_verified: boolean;
  avatar_url?: string | null;
  language?: string;
  timezone?: string;
  created_at?: string;
  updated_at?: string;
}
```

```typescript
// File: rext-admin/lib/api-client/profile.ts
// Lines: 14-32 — Profile GET response type with non-existent fields
get: async () => {
  const response = await client.request<{
    profile: {
      id: string;
      email: string;
      username: string;        // Does not exist
      first_name: string;      // Does not exist
      last_name: string;       // Does not exist
      full_name: string;
      display_name: string;
      email_verified: boolean;
      status: string;
      // ...
    };
  }>("/api/v1/user/profile", { method: "GET" });
```

```typescript
// File: rext-admin/lib/api-client/profile.ts
// Lines: 42-51 — Profile UPDATE sends non-existent fields
update: async (data: {
  first_name?: string;       // Backend ignores — not in UpdateProfileRequest
  last_name?: string;        // Backend ignores — not in UpdateProfileRequest
  full_name?: string;        // Backend accepts
  display_name?: string;     // Backend accepts
  bio?: string;
  // ...
})
```

```typescript
// File: rext-admin/components/profile/profile-form.tsx
// Lines: 92-99 — Splits full_name into first_name/last_name for the API
const nameParts = data.full_name.split(" ");
const first_name = nameParts[0] || "";
const last_name = nameParts.slice(1).join(" ") || "";

await apiClient.profile.update({
  first_name,    // Silently ignored by backend
  last_name,     // Silently ignored by backend
  // ...
});
```

```python
# File: src/api/models/user_models/users.py
# Lines: 16-42 — Backend Users model (truth)
class Users(Base, SerializableMixin):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, ...)
    email = Column(String(255), unique=True, nullable=False)
    full_name = Column(String(200))
    password_hash = Column(String(255), nullable=False)
    display_name = Column(String(200))
    bio = Column(String(500))
    # ... no username, first_name, or last_name columns
```

---

## Why This Matters (Context & Reasoning)

The backend model is the source of truth — the database schema has `full_name` and `display_name`, not separate first/last name fields. Adding `first_name`, `last_name`, and `username` columns to the database would require a migration and a design decision about whether the product actually needs split names (most modern SaaS products use a single "name" field for simplicity). The audit report recommends aligning the frontend to the backend, not the other way around.

The most impactful problem is the profile update flow:
1. User opens their profile settings.
2. The profile form loads and displays the user's `full_name` by combining the (undefined) `first_name` and `last_name` fields.
3. User edits their name and saves.
4. The form splits the name back into `first_name` and `last_name` and sends both to the API.
5. The backend Pydantic schema drops both fields because they're not in `UpdateProfileRequest`.
6. The user's name is never updated. The form appears to save successfully (200 response) but the change doesn't persist.

This silent data loss is confusing and creates support tickets. Users think the app is broken because their name changes don't stick.

---

## Impact

- **Severity:** Profile name updates are silently lost — users cannot change their name through the UI. User display across admin pages, invitations, and impersonation shows `undefined` values for non-existent fields.
- **Affected Users/Flows:** All users who edit their profile name. Admin users viewing user lists. Users receiving or accepting invitations (inviter name shows incorrectly). Any component displaying user details.
- **Blast Radius:** 20+ frontend files reference the mismatched fields. This is a systemic issue affecting user display across the entire frontend application.

---

## Recommended Solution

Update the frontend types and components to use the backend's actual field names (`full_name`, `display_name`). The backend is the source of truth and should not be changed. Remove `username`, `first_name`, and `last_name` from all frontend user type definitions and replace component references with `full_name` and `display_name`.

### Step 1: Update the `User` interface in `users.ts`

```typescript
// File: rext-admin/lib/api-client/users.ts
// Replace the User interface:
export interface User {
  id: string;
  email: string;
  full_name?: string;
  display_name?: string;
  status: string;
  email_verified: boolean;
  avatar_url?: string | null;
  bio?: string;
  language?: string;
  timezone?: string;
  created_at?: string;
  updated_at?: string;
}
```

### Step 2: Update profile GET response type in `profile.ts`

```typescript
// File: rext-admin/lib/api-client/profile.ts
// Lines: 14-32 — update the profile response type:
get: async () => {
  const response = await client.request<{
    profile: {
      id: string;
      email: string;
      full_name: string;
      display_name: string;
      email_verified: boolean;
      status: string;
      avatar_url?: string;
      bio?: string;
      language?: string;
      timezone?: string;
      created_at: string;
      updated_at: string;
    };
  }>("/api/v1/user/profile", { method: "GET" });
  return response.profile;
},
```

### Step 3: Update profile UPDATE request and response types in `profile.ts`

```typescript
// File: rext-admin/lib/api-client/profile.ts
// Lines: 42-67 — update the update method types:
update: async (data: {
  full_name?: string;
  display_name?: string;
  bio?: string;
  language?: string;
  timezone?: string;
}) => {
  return client.request<{
    id: string;
    email: string;
    full_name: string;
    display_name: string;
    avatar_url?: string;
    bio?: string;
    language?: string;
    timezone?: string;
  }>("/api/v1/user/profile", {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
},
```

### Step 4: Update `types/profile.ts`

```typescript
// File: rext-admin/types/profile.ts
// Replace first_name/last_name with full_name/display_name in all type definitions
```

### Step 5: Update `profile-form.tsx` — Send `full_name` directly

```typescript
// File: rext-admin/components/profile/profile-form.tsx
// Lines: 92-99 — Remove the name splitting logic, send full_name directly:
await apiClient.profile.update({
  full_name: data.full_name,
  display_name: data.display_name,
  bio: data.bio,
  language: data.language,
  timezone: data.timezone,
});
```

Also update the form initialization (lines 64-65) to use `full_name` directly instead of combining `first_name`/`last_name`, and the avatar initials (line 123) to use `full_name`.

### Step 6: Update `admin/users/page.tsx`

```typescript
// File: rext-admin/app/admin/users/page.tsx
// Lines: 38-39, 85-108, 127-129
// Replace first_name/last_name/username references with full_name/display_name:
// - Avatar initials: use full_name instead of first_name[0]+last_name[0]
// - Display name: use display_name || full_name || email
// - Remove username references
```

### Step 7: Update `auth.config.ts`

```typescript
// File: rext-admin/auth.config.ts
// Lines: 164, 305 — Replace:
name: `${data.user.first_name || ""} ${data.user.last_name || ""}`.trim(),
// With:
name: data.user.full_name || data.user.display_name || data.user.email,
```

### Step 8: Update invitation-related components

```typescript
// File: rext-admin/app/accept-invitation/page.tsx
// Lines: 270-271 — Replace:
{invitation.invited_by.first_name} {invitation.invited_by.last_name}
// With:
{invitation.invited_by.full_name || invitation.invited_by.display_name || invitation.invited_by.email}

// File: rext-admin/app/invitations/accept/page.tsx
// Lines: 75-76, 318-319 — same replacement pattern

// File: rext-admin/components/signup-form.tsx
// Line: 159 — Replace:
inviterName={`${invitation.invited_by.first_name} ${invitation.invited_by.last_name}`}
// With:
inviterName={invitation.invited_by.full_name || invitation.invited_by.display_name || invitation.invited_by.email}

// File: rext-admin/components/login-form.tsx
// Line: 154 — same replacement pattern
```

### Step 9: Update `impersonation-start-dialog.tsx`

```typescript
// File: rext-admin/components/impersonation/impersonation-start-dialog.tsx
// Line: 83 — Replace:
const displayName = user.display_name || user.username || user.email;
// With:
const displayName = user.display_name || user.full_name || user.email;
```

### Step 10: Update `members.ts` API client

```typescript
// File: rext-admin/lib/api-client/members.ts
// Lines: 117-118 — Replace first_name/last_name with full_name/display_name
// in the member response type
```

### Step 11: Update `use-invitation-validation.ts` hook

```typescript
// File: rext-admin/hooks/use-invitation-validation.ts
// Lines: 22-23 — Replace first_name/last_name with full_name/display_name
```

---

## Other Affected Locations

The following files also reference `first_name`/`last_name` but are related to the topic-builder domain (content generation metadata), NOT the user model. These should be verified separately to determine if they map to different backend columns:

| File | Line(s) | Description |
|------|---------|-------------|
| `types/topic-builder.ts` | 152, 154 | `generated_by_first_name`, `generated_by_last_name` — topic metadata, not User model fields. These may be separate columns on a content/topic model. Verify before changing. |
| `services/backend.ts` | 724-725 | Default values for `generated_by_first_name`/`generated_by_last_name` — related to topic builder, not user type mismatch. |
| `hooks/use-topic-metadata.tsx` | 21 | Displays topic creator name using `generated_by_first_name`/`generated_by_last_name`. |
| `__tests__/` (multiple files) | Various | Test files referencing `generated_by_first_name`/`generated_by_last_name` and `first_name`/`last_name` — tests will need updating after the types change. |
| `services/audit-log-api.ts` | 91 | Uses `username` as a filter parameter for audit log queries. This may map to a different backend field and should be verified. |
| `components/admin/audit/audit-logs-table.tsx` | 164 | Displays `log.username` — this may come from the audit log model, not the User model. Verify. |
| `lib/api-client/admin.ts` | 141 | Uses `username` as a query parameter. Verify against the backend admin routes. |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Log in to the application and navigate to Profile Settings.
2. Edit the name field and save.
3. Refresh the page — observe the name change was not persisted (the old name reappears).
4. Open browser DevTools Network tab and inspect the `PATCH /api/v1/user/profile` request:
   - Request body sends `first_name` and `last_name` (incorrect fields)
   - Backend ignores these fields
5. Navigate to Admin > Users page — observe user names may show as `undefined undefined` or empty strings.

### After Fix (Verify the Solution):
1. Edit the name in Profile Settings and save.
2. Refresh the page — the name change persists.
3. Inspect the `PATCH /api/v1/user/profile` request:
   - Request body sends `full_name` (correct field)
   - Backend accepts and saves the value
4. Navigate to Admin > Users — user names display correctly using `full_name`/`display_name`.
5. Navigate to invitation acceptance page — inviter name displays correctly.
6. Open the impersonation dialog — user names display correctly.

### Run Existing Tests:
```bash
cd rext-admin
npm run test -- --passWithNoTests
npm run build  # Verify TypeScript compilation succeeds with updated types
```

---

## Acceptance Criteria

- [ ] `User` interface in `users.ts` uses `full_name` and `display_name` (no `username`, `first_name`, `last_name`)
- [ ] Profile GET response type in `profile.ts` matches backend fields
- [ ] Profile UPDATE request sends `full_name` instead of `first_name`/`last_name`
- [ ] Profile form saves name changes successfully (verified by page refresh)
- [ ] `profile-form.tsx` no longer splits/joins name — sends `full_name` directly
- [ ] Admin users page displays names correctly using `full_name`/`display_name`
- [ ] Invitation pages display inviter name correctly
- [ ] Auth config uses correct field names for session name
- [ ] Impersonation dialog uses correct field names
- [ ] `members.ts` invitation response types updated
- [ ] TypeScript compilation succeeds with no type errors
- [ ] All existing tests still pass (with necessary test updates)
- [ ] No new warnings or errors introduced
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [Pydantic V2 — Extra Fields Handling](https://docs.pydantic.dev/latest/concepts/models/#extra-fields) — by default, Pydantic V2 ignores extra fields in model input, which is why `first_name`/`last_name` are silently dropped by `UpdateProfileRequest`
- **Official Docs:** [TypeScript Interface Best Practices](https://www.typescriptlang.org/docs/handbook/2/objects.html) — using interfaces to enforce API contracts
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** [API Contract Testing](https://martinfowler.com/bliki/ContractTest.html) — Martin Fowler on ensuring frontend-backend type alignment

---

## Dependencies & Related Tasks

- **Depends on:** None (can be implemented independently, but ideally after TASK-067)
- **Blocks:** None
- **Related:**
  - TASK-062 (B3 Finding 5): "Non-Existent User Model Attributes" — same mismatch on the backend side in `invitations.py:183` where `inviter.first_name`/`inviter.last_name`/`inviter.username` are used. TASK-062 fixes the backend; this task fixes the frontend.
  - TASK-067 (B3 Finding 7): "Frontend Calls `GET /user/{userId}` but No Backend Endpoint" — the new endpoint should return the correct backend fields. This task ensures the frontend consumes them correctly.
  - B3 Finding 28 (P3): "ProfileResponse Schema Defined But Never Used" — the `ProfileResponse` schema in `user_schema.py` uses `full_name`/`display_name` (correct fields) and could be used to enforce the API contract.

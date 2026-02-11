# Task 086: Use `ProfileResponse` Schema in Profile Endpoint Instead of Manual Dict Construction

## Metadata
- **Task ID:** TASK-086
- **Source:** B3 - User Management (Finding #28 under P3 Low)
- **Audit Report:** `audit-reports/backend-user-management.md`
- **Priority:** P3 Low
- **Category:** code-quality
- **Effort Estimate:** small (< 1 hour)

---

## Description

The `ProfileResponse` Pydantic schema is defined in `src/api/schema/user_schema.py` at lines 77-88 with properly typed fields (`id`, `email`, `full_name`, `display_name`, `language`, `timezone`, `status`, `email_verified`, `created_at`, `updated_at`). However, the `get_profile` endpoint in `src/api/routes/users/profile.py` (lines 29-78) does not use this schema. Instead, it manually constructs a dictionary at lines 47-60 with the same fields, performing manual `.isoformat()` conversions and hardcoding default values.

This means the `ProfileResponse` schema class is defined but never imported or referenced anywhere in the codebase — a codebase-wide search for `ProfileResponse` returns only its definition in `user_schema.py`. The profile endpoint's manual dict construction duplicates the field definitions that already exist in the schema, creating a maintenance burden: if a field is added or renamed, both the schema and the manual dict must be updated independently, and they can easily drift apart.

According to FastAPI best practices, using Pydantic `response_model` schemas provides automatic data validation, filtering of extra fields, consistent API documentation generation via OpenAPI/Swagger, and a single source of truth for the response contract. The current approach using `response_model=dict` on the endpoint decorator provides none of these benefits. The existing `ProfileResponse` schema also lacks two fields that the manual dict includes (`bio` and `avatar_url`), indicating the schema and the actual response have already drifted.

---

## Current Code

```python
# File: rext-backend/src/api/schema/user_schema.py
# Lines: 77-88
class ProfileResponse(BaseModel):
    """Schema for profile response"""
    id: str
    email: str
    full_name: Optional[str]
    display_name: Optional[str]
    language: str
    timezone: str
    status: str
    email_verified: bool
    created_at: str
    updated_at: Optional[str]
```

```python
# File: rext-backend/src/api/routes/users/profile.py
# Lines: 29-78
@router.get("/profile", response_model=dict)
async def get_profile(
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get current authenticated user's profile.
    Uses UserService for business logic.
    """
    try:
        user_id = current_user.get("identity")
        service = UserService(db)

        # Get user via service
        user = await service.get_user_by_id(user_id)

        # Build profile response
        profile_data = {
            "id": str(user.id),
            "email": user.email,
            "full_name": user.full_name,
            "display_name": user.display_name,
            "bio": user.bio,
            "language": user.language or "en",
            "timezone": user.timezone or "UTC",
            "status": user.status,
            "email_verified": user.email_verified,
            "avatar_url": user.avatar_url,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "updated_at": user.updated_at.isoformat() if user.updated_at else None
        }

        return success(
            data={"profile": profile_data},
            request=request,
            message="Profile retrieved successfully"
        )

    except ResourceNotFoundException:
        return error(
            message="User not found",
            code=ErrorCode.RESOURCE_NOT_FOUND,
            status_code=404,
            severity=ErrorSeverity.MEDIUM,
            request=request
        )
    except Exception as e:
        logger.error(f"Error fetching profile: {str(e)}")
        raise
```

---

## Why This Matters (Context & Reasoning)

The profile endpoint is one of the most frequently called endpoints in the application — every authenticated page load typically fetches the user's profile. Having a well-defined response schema ensures:

1. **API documentation accuracy:** The Swagger/OpenAPI docs currently show `response_model=dict`, which tells consumers nothing about the expected shape. Using `ProfileResponse` would auto-generate accurate schema documentation.
2. **Data contract enforcement:** If the User model changes (e.g., a field is renamed or removed), the Pydantic schema will catch the mismatch at response time rather than silently returning `None` or missing fields.
3. **Single source of truth:** The schema and the manual dict currently define the same fields in two places, which have already drifted (`bio` and `avatar_url` are in the manual dict but not in the schema).
4. **Frontend parity:** The frontend TypeScript types (`rext-admin/lib/api-client/profile.ts`) are presumably based on the actual response shape. Having a Pydantic schema as the single definition makes it easier to keep frontend types in sync.

---

## Impact

- **Severity:** No runtime errors. The profile endpoint works correctly with the manual dict. However, the `ProfileResponse` schema is dead code, and the endpoint lacks proper response documentation and validation.
- **Affected Users/Flows:** Developers consuming the API, especially frontend developers relying on API documentation for type definitions.
- **Blast Radius:** Isolated to the profile endpoint and the `ProfileResponse` schema definition.

---

## Recommended Solution

There are two valid approaches. The recommended approach is to update `ProfileResponse` to match the actual response and use it in the endpoint. This provides the most value by leveraging Pydantic's validation and documentation capabilities.

### Step 1: Update `ProfileResponse` in `user_schema.py` to include missing fields

```python
# File: rext-backend/src/api/schema/user_schema.py
# Replace lines 77-88 with:
class ProfileResponse(BaseModel):
    """Schema for profile response"""
    id: str
    email: str
    full_name: Optional[str] = None
    display_name: Optional[str] = None
    bio: Optional[str] = None
    language: str = "en"
    timezone: str = "UTC"
    status: str
    email_verified: bool
    avatar_url: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
```

### Step 2: Import `ProfileResponse` in `profile.py` and use it for serialization

```python
# File: rext-backend/src/api/routes/users/profile.py
# Add to the import on line 7 (existing import from user_schema):
from src.api.schema.user_schema import UpdateProfileRequest, DeactivateAccountRequest, ProfileResponse
```

### Step 3: Replace the manual dict construction with `ProfileResponse`

```python
# File: rext-backend/src/api/routes/users/profile.py
# Replace lines 47-60 with:
        # Build profile response using schema
        profile_data = ProfileResponse(
            id=str(user.id),
            email=user.email,
            full_name=user.full_name,
            display_name=user.display_name,
            bio=user.bio,
            language=user.language or "en",
            timezone=user.timezone or "UTC",
            status=user.status,
            email_verified=user.email_verified,
            avatar_url=user.avatar_url,
            created_at=user.created_at.isoformat() if user.created_at else None,
            updated_at=user.updated_at.isoformat() if user.updated_at else None
        ).model_dump()
```

Note: We use `.model_dump()` (Pydantic v2) because the `success()` utility expects a dict for its `data` parameter. This approach validates the data through the Pydantic schema while still producing a dict for the response wrapper.

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `rext-backend/src/api/routes/users/profile.py` | `7` | Existing import from `user_schema` — add `ProfileResponse` to this import |
| `rext-backend/src/api/routes/users/profile.py` | `29` | `response_model=dict` could optionally be left as-is since the `success()` wrapper adds its own envelope |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Confirm `ProfileResponse` is defined in `user_schema.py` but never imported anywhere:
   ```bash
   cd rext-backend && grep -r "ProfileResponse" --include="*.py" src/
   ```
   Expected: only the class definition in `user_schema.py`.
2. Confirm the profile endpoint returns a manually constructed dict by reading `profile.py:47-60`.

### After Fix (Verify the Solution):
1. Confirm `ProfileResponse` is now imported in `profile.py`.
2. Confirm the manual dict construction is replaced with `ProfileResponse(...).model_dump()`.
3. Test the profile endpoint:
   ```bash
   curl -H "Authorization: Bearer <token>" http://localhost:8000/api/users/profile
   ```
4. Verify the response shape is identical to before (same fields, same values).
5. Test with a user that has `None` values for optional fields (`bio`, `avatar_url`, `display_name`) to confirm defaults work correctly.

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/ -k "profile" -v
```

---

## Acceptance Criteria

- [ ] `ProfileResponse` schema in `user_schema.py` includes `bio` and `avatar_url` fields
- [ ] `ProfileResponse` is imported and used in `profile.py`'s `get_profile` endpoint
- [ ] Manual dict construction in `get_profile` is replaced with `ProfileResponse(...).model_dump()`
- [ ] Profile endpoint returns the same response shape as before the change
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [FastAPI Response Model - Return Type](https://fastapi.tiangolo.com/tutorial/response-model/) — documents how `response_model` provides automatic validation, documentation, and filtering
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** [FastAPI Extra Models](https://fastapi.tiangolo.com/tutorial/extra-models/) — demonstrates using separate Pydantic models for different response types
- **Related Issues/PRs:** None

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-084 (Inline Pydantic Schemas in Preferences Route — same pattern of schema organization); TASK-068 (Frontend-Backend User Type Mismatch — the `ProfileResponse` schema should align with frontend expectations)

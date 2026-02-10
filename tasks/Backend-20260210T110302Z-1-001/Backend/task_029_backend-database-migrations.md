# Task 029: Fix WorkspaceIntegration.to_dict() Credential Leakage - Exposes app_password and api_key

## Metadata
- **Task ID:** TASK-029
- **Source:** Database & Migrations Audit (Finding #3 under P0 Critical)
- **Audit Report:** `audit-reports/backend-database-migrations.md`
- **Priority:** P0 Critical
- **Category:** security
- **Effort Estimate:** small (< 1 hour)

---

## Description

The `WorkspaceIntegration` model in `src/api/models/workspace_models/workspace_integration.py` has a critical security vulnerability in its `to_dict()` method. Lines 51-52 return sensitive credentials (`app_password` and `api_key`) in plain text:

```python
"app_password": self.app_password,
"api_key": self.api_key,
```

These fields contain:
- `app_password`: WordPress application password used for REST API authentication
- `api_key`: Rext-AI Plugin API key (Bearer Token) for WordPress integration

Any API endpoint that serializes a `WorkspaceIntegration` model will expose these credentials in the response body. This violates the [OWASP API Security Top 10 - API3:2023 Broken Object Property Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa3-broken-object-property-level-authorization/), which specifically addresses the exposure of sensitive object properties that should not be readable by users.

**Contrast with other models:** The codebase already follows proper patterns elsewhere:
- `Users.to_dict()` properly excludes `password_hash` and `reset_token`
- `OAuthAccount.to_dict()` properly excludes `access_token` and `refresh_token`
- `SerializableMixin.to_dict()` supports an `exclude` parameter specifically for this purpose

The `WorkspaceIntegration.to_dict()` does not follow these established security patterns.

**Additional Issue:** The same method also returns raw `UUID` objects (lines 44-45) and raw `datetime` objects (lines 54-56) without converting to strings/ISO format, which may cause JSON serialization failures and is inconsistent with `SerializableMixin` behavior.

---

## Current Code

```python
# File: rext-backend/src/api/models/workspace_models/workspace_integration.py
# Lines: 41-57

    # to_dict() inherited from SerializableMixin
    def to_dict(self):
        return {
            "id": self.id,                              # Raw UUID - should be str(self.id)
            "workspace_id": self.workspace_id,          # Raw UUID - should be str(self.workspace_id)
            "integration_type": self.integration_type,
            "is_active": self.is_active,
            "site_url": self.site_url,
            "api_endpoint": self.api_endpoint,
            "username": self.username,
            "app_password": self.app_password,          # SECURITY ISSUE: Credential leaked
            "api_key": self.api_key,                    # SECURITY ISSUE: Credential leaked
            "config_json": self.config_json,
            "created_at": self.created_at,              # Raw datetime - should be .isoformat()
            "updated_at": self.updated_at,              # Raw datetime - should be .isoformat()
            "deleted_at": self.deleted_at,              # Raw datetime - should be .isoformat()
        }
```

---

## Why This Matters (Context & Reasoning)

The `WorkspaceIntegration` model stores WordPress integration credentials that enable Rext AI to publish content directly to a user's WordPress site. If these credentials are exposed:

1. **Credential Theft:** Any user with access to workspace integration endpoints can steal WordPress credentials belonging to other workspace members or, in the case of BOLA vulnerabilities, other workspaces entirely.

2. **Unauthorized WordPress Access:** Stolen credentials allow an attacker to:
   - Publish, modify, or delete any content on the WordPress site
   - Install malicious plugins
   - Create backdoor admin accounts
   - Deface the website
   - Use the site for malware distribution

3. **Compliance Violations:** Exposing credentials violates data protection principles and could trigger GDPR/CCPA breach notification requirements if the credentials belong to EU/California residents.

4. **Trust Erosion:** Users who discover their WordPress credentials were exposed via API responses will lose trust in the platform.

---

## Impact

- **Severity:** Any client with access to workspace integration endpoints receives raw WordPress credentials in API responses. This enables credential theft and unauthorized access to customer WordPress sites.
- **Affected Users/Flows:** All workspace integration listing/viewing endpoints, admin endpoints that return integration details, any endpoint that serializes `WorkspaceIntegration` models.
- **Blast Radius:** Every workspace with WordPress integrations is affected. Credentials for all connected WordPress sites are at risk.

---

## Recommended Solution

### Step 1: Update to_dict() to Exclude Sensitive Fields and Fix Type Conversions

Replace the entire `to_dict()` method in `rext-backend/src/api/models/workspace_models/workspace_integration.py`:

```python
# File: rext-backend/src/api/models/workspace_models/workspace_integration.py
# Replace lines 41-57 with:

    def to_dict(self, include_credentials: bool = False, **kwargs) -> dict:
        """
        Convert model to dictionary for JSON serialization.

        By default, sensitive credentials (app_password, api_key) are excluded.
        Only include credentials when explicitly needed (e.g., admin credential management).

        Args:
            include_credentials: If True, include app_password and api_key. Default: False.
            **kwargs: Additional arguments passed to SerializableMixin.to_dict()

        Returns:
            Dictionary representation with UUIDs and datetimes converted to strings.
        """
        # Build exclude list - always exclude credentials unless explicitly requested
        exclude = kwargs.pop('exclude', []) or []
        if not include_credentials:
            exclude.extend(['app_password', 'api_key'])

        # Use parent's to_dict which handles UUID/datetime conversion
        return super().to_dict(exclude=exclude, **kwargs)
```

### Step 2: Create a Separate Method for Credential Access (If Needed)

If there are admin endpoints that legitimately need to return credentials (e.g., for editing integration settings), create a dedicated method:

```python
    def to_dict_with_credentials(self, **kwargs) -> dict:
        """
        Return full model data including sensitive credentials.

        WARNING: Only use this in admin/credential management contexts where
        the requester has explicit authorization to view credentials.
        """
        return self.to_dict(include_credentials=True, **kwargs)
```

### Step 3: Audit All Endpoints Using WorkspaceIntegration

Search for all places that serialize `WorkspaceIntegration`:

```bash
cd rext-backend
grep -rn "\.to_dict\(\)" --include="*.py" | grep -i integration
grep -rn "WorkspaceIntegration" --include="*.py" src/api/routes/
```

Verify each endpoint:
1. Does it need to return credentials? (Usually NO)
2. If YES, add explicit authorization checks before calling `to_dict_with_credentials()`
3. If NO, the updated `to_dict()` will automatically exclude credentials

### Step 4: Add Security Test

Create a test to ensure credentials are never accidentally exposed:

```python
# File: tests/unit/models/test_workspace_integration.py

def test_to_dict_excludes_credentials_by_default():
    """Verify sensitive credentials are excluded from serialization."""
    integration = WorkspaceIntegration(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        integration_type="wordpress",
        is_active=True,
        site_url="https://example.com",
        username="admin",
        app_password="secret_password_123",
        api_key="secret_api_key_456",
    )

    data = integration.to_dict()

    # Credentials must NOT be present
    assert 'app_password' not in data
    assert 'api_key' not in data

    # Other fields should be present and properly typed
    assert isinstance(data['id'], str)  # UUID converted to string
    assert data['site_url'] == "https://example.com"
    assert data['username'] == "admin"


def test_to_dict_with_credentials_includes_secrets():
    """Verify credentials can be explicitly included when needed."""
    integration = WorkspaceIntegration(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        app_password="secret_password_123",
        api_key="secret_api_key_456",
    )

    data = integration.to_dict(include_credentials=True)

    assert data['app_password'] == "secret_password_123"
    assert data['api_key'] == "secret_api_key_456"
```

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `src/api/routes/workspaces/integrations.py` | Various | Routes that return integration data - verify credentials not exposed |
| `src/services/workspace_service.py` | Various | Service methods that return integrations - may need updates |

Search command to find all usages:
```bash
grep -rn "WorkspaceIntegration" rext-backend/src/api/routes/
```

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Create a workspace with a WordPress integration (via API or UI)
2. Call the integration listing endpoint (e.g., `GET /api/workspaces/{id}/integrations`)
3. Inspect the response JSON
4. **VULNERABLE:** `app_password` and `api_key` appear in the response

### After Fix (Verify the Solution):
1. Apply the code change
2. Call the same integration endpoint
3. Inspect the response JSON
4. **FIXED:** `app_password` and `api_key` should NOT appear
5. Verify `id` and `workspace_id` are strings (not UUID objects)
6. Verify timestamps are ISO format strings (not raw datetime objects)

### Run Existing Tests:
```bash
cd rext-backend
pytest tests/ -v -k "integration"
```

---

## Acceptance Criteria

- [ ] `to_dict()` method excludes `app_password` and `api_key` by default
- [ ] `to_dict()` returns UUIDs as strings (not raw UUID objects)
- [ ] `to_dict()` returns datetimes as ISO format strings (not raw datetime objects)
- [ ] `include_credentials=True` parameter allows explicit credential inclusion when needed
- [ ] All existing integration endpoints verified to not expose credentials
- [ ] Unit test added to prevent regression
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass

---

## References & Resources

- **Official Docs:** [SQLAlchemy SerializableMixin pattern](https://docs.sqlalchemy.org/en/20/orm/extensions/serializer.html) - Patterns for model serialization
- **Security Advisory:** [OWASP API3:2023 - Broken Object Property Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa3-broken-object-property-level-authorization/) - This vulnerability is a direct instance of API3:2023
- **Migration Guide:** N/A
- **Best Practice Reference:** [OWASP API Security - Data Exposure](https://owasp.org/www-project-api-security/) - General guidance on preventing sensitive data exposure in APIs

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-001 (B1 - timing attack on API key comparison - both involve credential security), B4 Finding 1 (Integration Credentials Stored in Plaintext - related credential issue in workspace audit)

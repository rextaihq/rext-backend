# Task 089: Integration Credentials Stored in Plaintext and Exposed via `to_dict()`

## Metadata
- **Task ID:** TASK-089
- **Source:** B4 - Workspace Management (Finding #1 under P0 Critical)
- **Audit Report:** `audit-reports/backend-workspace-management.md`
- **Priority:** P0 Critical
- **Category:** security
- **Effort Estimate:** medium (1-4 hours)

---

## Description

The `WorkspaceIntegration` model in `src/api/models/workspace_models/workspace_integration.py` stores WordPress integration credentials — specifically `app_password` (line 27) and `api_key` (line 28) — as plaintext `Text` columns in the database. These are not encrypted at rest, meaning a database breach would expose all WordPress integration credentials for every workspace in the system.

Compounding this issue, the model's custom `to_dict()` method (lines 42-57) includes both `app_password` and `api_key` in its output dictionary without any masking or exclusion. This `to_dict()` method is called directly in **7 different API endpoint handlers** in `src/api/routes/content/modules/sites.py` — including `list_connected_sites` (line 42), `connect_site` (line 95), `get_site_details` (line 119), `update_site` (line 155), `activate_site` (line 208), and `deactivate_site` (line 234). Every one of these endpoints returns the full plaintext credentials to the client over the wire.

According to OWASP A02:2021 (Cryptographic Failures), sensitive data such as API keys and passwords must be encrypted at rest using strong algorithms like AES-256, and must never be transmitted unnecessarily to clients. The current implementation violates both of these principles. The `cryptography` library's `Fernet` implementation provides authenticated symmetric encryption (AES-128-CBC + HMAC-SHA256) that is suitable for encrypting these credential fields, and SQLAlchemy's `TypeDecorator` pattern enables transparent encryption/decryption at the ORM level.

Note that the `SerializableMixin.to_dict()` base class (in `src/api/models/base.py`) already supports an `exclude` parameter that could prevent sensitive fields from appearing in output, but the `WorkspaceIntegration` model overrides `to_dict()` without using the base class at all, bypassing this safety mechanism.

---

## Current Code

```python
# File: src/api/models/workspace_models/workspace_integration.py
# Lines: 27-28, 42-57
class WorkspaceIntegration(Base, SerializableMixin):
    # ...
    app_password = Column(Text, nullable=True, comment="WordPress application password")
    api_key = Column(Text, nullable=True, comment="WordPress Rext-AI API Key (Bearer Token)")
    # ...

    # to_dict() inherited from SerializableMixin
    def to_dict(self):
        return {
            "id": self.id,
            "workspace_id": self.workspace_id,
            "integration_type": self.integration_type,
            "is_active": self.is_active,
            "site_url": self.site_url,
            "api_endpoint": self.api_endpoint,
            "username": self.username,
            "app_password": self.app_password,       # <-- Plaintext credential exposed
            "api_key": self.api_key,                 # <-- Plaintext credential exposed
            "config_json": self.config_json,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "deleted_at": self.deleted_at,
        }
```

```python
# File: src/api/routes/content/modules/sites.py
# Lines: 41-42 (example — same pattern on lines 95, 119, 155, 208, 234)
    return {
        "sites": [site.to_dict() for site in sites],  # Credentials leaked to client
        "total_count": len(sites),
        "workspace_id": str(workspace.id)
    }
```

---

## Why This Matters (Context & Reasoning)

The `WorkspaceIntegration` model stores the credentials needed to connect Rext AI to a user's WordPress site for content publishing. These credentials include the WordPress Application Password (used for Basic Auth) and the Rext-AI Plugin API Key (used as a Bearer token). The `WordPressPublisher` service (`src/services/wordpress_publisher.py`) uses these credentials to authenticate with WordPress sites when publishing content.

If the database is compromised (SQL injection, backup theft, insider threat), all WordPress integration credentials are immediately usable by an attacker to gain write access to every connected WordPress site. This could lead to defacement, malware injection, SEO spam, or data theft on customer WordPress sites.

Even without a database breach, every API call to list, view, create, update, activate, or deactivate site connections returns the full plaintext credentials in the response body. This exposes credentials to browser dev tools, HTTP logs, CDN caches, monitoring tools, and any man-in-the-middle scenarios where TLS is terminated early (e.g., corporate proxies, load balancers).

---

## Impact

- **Severity:** Database breach exposes all WordPress integration credentials, enabling attackers to publish malicious content to every connected WordPress site. API responses leak credentials to browser, logs, and network.
- **Affected Users/Flows:** All users who have connected WordPress sites to their workspaces. Affected endpoints: `GET /sites/list`, `POST /sites/connect`, `GET /sites/{id}`, `PATCH /sites/{id}`, `POST /sites/{id}/activate`, `POST /sites/{id}/deactivate`.
- **Blast Radius:** All workspaces with WordPress integrations. Credential compromise affects external WordPress sites (customer property), not just Rext AI infrastructure.

---

## Recommended Solution

### Step 1: Install the `cryptography` library

The project already has `PyJWT[crypto]>=2.8.0` which pulls in `cryptography` as a dependency, but it should be explicitly listed.

```bash
# Verify cryptography is available
pip show cryptography
```

### Step 2: Create an encrypted column type using SQLAlchemy TypeDecorator

```python
# File: src/utils/encryption.py (NEW FILE)
import os
from typing import Optional
from cryptography.fernet import Fernet
from sqlalchemy import String, TypeDecorator


def _get_fernet() -> Fernet:
    """Get Fernet instance using the encryption key from environment."""
    key = os.environ.get("FIELD_ENCRYPTION_KEY")
    if not key:
        raise RuntimeError(
            "FIELD_ENCRYPTION_KEY environment variable is not set. "
            "Generate one with: python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
        )
    return Fernet(key.encode() if isinstance(key, str) else key)


class EncryptedText(TypeDecorator):
    """
    SQLAlchemy TypeDecorator that transparently encrypts/decrypts text values
    using Fernet symmetric encryption (AES-128-CBC + HMAC-SHA256).

    Values are encrypted before being written to the database and decrypted
    when read. The encryption key is sourced from the FIELD_ENCRYPTION_KEY
    environment variable.

    Usage:
        api_key = Column(EncryptedText, nullable=True)
    """

    impl = String
    cache_ok = True

    def process_bind_param(self, value: Optional[str], dialect) -> Optional[str]:
        """Encrypt value before storing in database."""
        if value is None:
            return None
        fernet = _get_fernet()
        return fernet.encrypt(value.encode("utf-8")).decode("utf-8")

    def process_result_value(self, value: Optional[str], dialect) -> Optional[str]:
        """Decrypt value after reading from database."""
        if value is None:
            return None
        fernet = _get_fernet()
        return fernet.decrypt(value.encode("utf-8")).decode("utf-8")
```

### Step 3: Update the WorkspaceIntegration model to use encrypted columns

```python
# File: src/api/models/workspace_models/workspace_integration.py
# Replace lines 1-57 with:
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from src.api.database.base import Base
from src.api.models.base import SerializableMixin
from src.utils.encryption import EncryptedText
from datetime import datetime, timezone
import uuid


class WorkspaceIntegration(Base, SerializableMixin):
    """
    Connected Site Model

    Stores WordPress integration credentials for workspaces.
    Sensitive fields (app_password, api_key) are encrypted at rest.
    """
    __tablename__ = "integrations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False, index=True)
    integration_type = Column(String(50), nullable=False, default="wordpress", index=True)
    is_active = Column(Boolean, default=True, nullable=False)

    # WordPress specific fields
    site_url = Column(String(500), nullable=True, comment="WordPress site URL")
    api_endpoint = Column(String(500), nullable=True, comment="Rext-AI Plugin Base Endpoint")
    username = Column(String(255), nullable=True, comment="WordPress username")
    app_password = Column(EncryptedText, nullable=True, comment="WordPress application password (encrypted)")
    api_key = Column(EncryptedText, nullable=True, comment="WordPress Rext-AI API Key (encrypted)")

    # Additional configuration (JSON)
    config_json = Column(JSONB, nullable=True, comment="Additional integration configuration and settings")

    # Timestamps
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=True, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    workspace = relationship("WorkspaceModel", back_populates="integrations")

    def to_dict(self, include_credentials: bool = False, **kwargs):
        """
        Serialize integration to dictionary.
        Credentials are excluded by default for safety.

        Args:
            include_credentials: If True, include has_password/has_api_key flags
                                 (never returns actual credential values).
        """
        data = {
            "id": self.id,
            "workspace_id": self.workspace_id,
            "integration_type": self.integration_type,
            "is_active": self.is_active,
            "site_url": self.site_url,
            "api_endpoint": self.api_endpoint,
            "username": self.username,
            "config_json": self.config_json,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "deleted_at": self.deleted_at,
            "has_app_password": self.app_password is not None and len(self.app_password) > 0,
            "has_api_key": self.api_key is not None and len(self.api_key) > 0,
        }
        return data
```

### Step 4: Create a data migration to encrypt existing plaintext values

```python
# File: Create via: alembic revision -m "encrypt_integration_credentials"
"""encrypt integration credentials

Revision ID: <auto-generated>
"""
from alembic import op
import os
from cryptography.fernet import Fernet


def upgrade():
    """Encrypt existing plaintext credential values."""
    conn = op.get_bind()
    key = os.environ.get("FIELD_ENCRYPTION_KEY")
    if not key:
        raise RuntimeError("FIELD_ENCRYPTION_KEY must be set before running this migration")
    fernet = Fernet(key.encode())

    rows = conn.execute(
        "SELECT id, app_password, api_key FROM integrations WHERE app_password IS NOT NULL OR api_key IS NOT NULL"
    ).fetchall()

    for row in rows:
        updates = {}
        if row.app_password:
            updates["app_password"] = fernet.encrypt(row.app_password.encode("utf-8")).decode("utf-8")
        if row.api_key:
            updates["api_key"] = fernet.encrypt(row.api_key.encode("utf-8")).decode("utf-8")

        if updates:
            set_clause = ", ".join(f"{k} = :val_{k}" for k in updates)
            params = {f"val_{k}": v for k, v in updates.items()}
            params["id"] = row.id
            conn.execute(f"UPDATE integrations SET {set_clause} WHERE id = :id", params)


def downgrade():
    """Decrypt credential values back to plaintext."""
    conn = op.get_bind()
    key = os.environ.get("FIELD_ENCRYPTION_KEY")
    if not key:
        raise RuntimeError("FIELD_ENCRYPTION_KEY must be set before running this migration")
    fernet = Fernet(key.encode())

    rows = conn.execute(
        "SELECT id, app_password, api_key FROM integrations WHERE app_password IS NOT NULL OR api_key IS NOT NULL"
    ).fetchall()

    for row in rows:
        updates = {}
        if row.app_password:
            updates["app_password"] = fernet.decrypt(row.app_password.encode("utf-8")).decode("utf-8")
        if row.api_key:
            updates["api_key"] = fernet.decrypt(row.api_key.encode("utf-8")).decode("utf-8")

        if updates:
            set_clause = ", ".join(f"{k} = :val_{k}" for k in updates)
            params = {f"val_{k}": v for k, v in updates.items()}
            params["id"] = row.id
            conn.execute(f"UPDATE integrations SET {set_clause} WHERE id = :id", params)
```

### Step 5: Add FIELD_ENCRYPTION_KEY to environment configuration

```bash
# Generate a new encryption key
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# Add to .env file
FIELD_ENCRYPTION_KEY=<generated-key-here>
```

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `src/api/routes/content/modules/sites.py` | `42, 95, 119, 155, 208, 234` | All 7 endpoints call `site.to_dict()` which currently leaks credentials |
| `src/api/routes/content/modules/publish_content.py` | `66-67` | Reads `site.app_password` and `site.api_key` to construct `WordPressPublisher` — will work transparently with `EncryptedText` |
| `src/services/wordpress_publisher.py` | `24-25, 42-43` | Consumes decrypted credential values — no change needed |
| `src/api/schema/content_schema.py` | `149-150, 164-165` | `WorkspaceIntegrationBase` and `WorkspaceIntegrationUpdate` schemas accept `app_password`/`api_key` for input — no change needed |
| `src/api/schema/content_schema.py` | `169-176` | `WorkspaceIntegrationResponse` schema still includes `app_password`/`api_key` fields — should be updated to exclude them |
| `src/api/models/workspace_models/workspace_integration.py` (B2, TASK-029) | `42-57` | Previously identified in B2 audit — this task supersedes TASK-029's credential exposure fix |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Start the backend server
2. Create a WordPress integration via `POST /sites/connect` with test credentials: `app_password: "test_secret_pass"`, `api_key: "test_api_key_123"`
3. Call `GET /sites/list` for the workspace
4. Observe that the response JSON contains `"app_password": "test_secret_pass"` and `"api_key": "test_api_key_123"` in plaintext
5. Query the database directly: `SELECT app_password, api_key FROM integrations` — values are in plaintext

### After Fix (Verify the Solution):
1. Set `FIELD_ENCRYPTION_KEY` environment variable
2. Run the Alembic migration to encrypt existing data
3. Call `GET /sites/list` for the workspace
4. Verify the response contains `"has_app_password": true` and `"has_api_key": true` instead of actual credential values
5. Query the database directly: `SELECT app_password, api_key FROM integrations` — values should be Fernet-encrypted ciphertext (base64-encoded, starting with `gAAAAA`)
6. Verify publishing to WordPress still works (credentials are decrypted transparently by the ORM)

### Run Existing Tests:
```bash
cd rext-backend
pytest tests/ -v -k "integration or site or workspace"
```

---

## Acceptance Criteria

- [ ] `app_password` and `api_key` columns use `EncryptedText` TypeDecorator
- [ ] Database stores encrypted ciphertext, not plaintext credentials
- [ ] `to_dict()` never returns actual credential values — only boolean indicators
- [ ] `WorkspaceIntegrationResponse` schema excludes credential fields
- [ ] WordPress publishing still works (transparent decryption)
- [ ] Alembic migration encrypts all existing plaintext credentials
- [ ] `FIELD_ENCRYPTION_KEY` environment variable is documented and required
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [Python `cryptography` Fernet Documentation](https://cryptography.io/en/latest/fernet/)
- **Security Advisory:** [OWASP A02:2021 — Cryptographic Failures](https://owasp.org/Top10/2021/A02_2021-Cryptographic_Failures/)
- **Migration Guide:** N/A
- **Best Practice Reference:** [OWASP Cryptographic Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html)
- **SQLAlchemy TypeDecorator:** [SQLAlchemy 2.0 Custom Types Documentation](https://docs.sqlalchemy.org/en/20/core/custom_types.html)
- **Related Blog:** [Encryption at Rest with SQLAlchemy — Miguel Grinberg](https://blog.miguelgrinberg.com/post/encryption-at-rest-with-sqlalchemy)

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-029 (B2: WorkspaceIntegration.to_dict() Leaks Sensitive Credentials — same root issue, this task provides the comprehensive fix including encryption at rest)

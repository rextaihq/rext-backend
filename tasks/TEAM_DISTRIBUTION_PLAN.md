# Authentication System Resolution Plan

This plan outlines the strategy for a 10-member team to resolve four critical authentication-related issues identified in the audit. The work is divided into specialized squads to maximize parallel efficiency and ensure thorough verification.

## Team Organization

| Squad | Members | Focus Area | Task | Priority | Criticality |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Squad 1** | 1, 2 | API Security | TASK-001 | P0 | Critical |
| **Squad 2** | 3, 4 | Authentication Logic | TASK-003 | P0 | Critical |
| **Squad 3** | 5, 6 | OAuth & Data Integrity | TASK-002 | P0 | Critical |
| **Squad 4** | 7, 8 | Python Modernization | TASK-004 | P1 | High |
| **Squad 5 (Lead)** | 9, 10 | QA & Coordination | Overall Review | P0 | Critical |

---

## Proposed Changes

### [Squad 1 & 2] Security & Logic Hardening
Fixing timing attacks and undefined variable crashes.

#### [MODIFY] [auth.py](file:///home/revnix/Desktop/work/wrext-backend/src/api/security/auth.py) [Squad 1]
- Replace `!=` with `hmac.compare_digest()` for API key verification.
- Add `None` guard for `API_KEY` setting.

#### [MODIFY] [auth_service.py](file:///home/revnix/Desktop/work/wrext-backend/src/services/auth_service.py) [Squad 2]
- Replace undefined `user_exists` with `True` in `_auto_accept_pending_invitations` notification payload.

---

### [Squad 3] OAuth & Schema Integrity
Resolving invalid password placeholders for OAuth users.

#### [MODIFY] [users.py](file:///home/revnix/Desktop/work/wrext-backend/src/api/models/user_models/users.py)
- Set `password_hash = Column(String(255), nullable=True)`.

#### [NEW] [Alembic Migration](file:///home/revnix/Desktop/work/wrext-backend/rext-backend/alembic/versions/)
- Create migration to make column nullable and migrate existing `"oauth_no_password"` strings to `NULL`.

#### [MODIFY] [oauth_service.py](file:///home/revnix/Desktop/work/wrext-backend/src/services/oauth_service.py)
- Update user creation to set `password_hash=None`.

#### [MODIFY] [token_utils.py](file:///home/revnix/Desktop/work/wrext-backend/src/api/security/token_utils.py)
- Add null guard to `verify_password`.

---

### [Squad 4] Python 3.12 Readiness
Replacing deprecated `datetime.utcnow()` calls.

#### [MODIFY] Multiple Files
- Replace `datetime.utcnow()` with `datetime.now(timezone.utc)` in:
    - [token_utils.py](file:///home/revnix/Desktop/work/wrext-backend/src/api/security/token_utils.py)
    - [auth_service.py](file:///home/revnix/Desktop/work/wrext-backend/src/services/auth_service.py)
    - [oauth_service.py](file:///home/revnix/Desktop/work/wrext-backend/src/services/oauth_service.py)
    - 7+ User Model files for defaults.

---

## Verification Plan

### Automated Tests
```bash
# General Authentication Tests
cd rext-backend && python -m pytest tests/ -k "auth or oauth or api_key" -v

# Specific verification for Task 003
python -m pytest tests/ -k "invitation" -v
```

### Manual Verification
- **Timing Attack:** Verify that valid API keys still work and invalid ones return 401.
- **OAuth Flow:** 
    1. Sign in via Google/GitHub.
    2. Attempt to verify password for a sensitive action (should return "Not set/Invalid" instead of crashing).
    3. Ensure existing email/password users can still login.
- **Timezone Awareness:** Check database logs to ensure new records have correct UTC timestamps.

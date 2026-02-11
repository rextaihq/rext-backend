# Task 171: Logging Partial API Key in WordPressPublisher

## Metadata
- **Task ID:** TASK-171
- **Source:** Content Management Audit (Finding #29 under P2 Medium)
- **Audit Report:** `audit-reports/backend-content-management.md`
- **Priority:** P2 Medium
- **Category:** security
- **Effort Estimate:** small (< 1 hour)

---

## Description

The `WordPressPublisher.__init__()` method at `src/services/wordpress_publisher.py:60-61` logs a partially masked version of the API key during initialization. The code reveals both the first 10 characters and last 6 characters of the key:

```python
masked_key = f"{self.api_key[:10]}...{self.api_key[-6:]}" if len(self.api_key) > 16 else "***"
logger.info(f"WordPress publisher initialized with API key: {masked_key}")
```

For a typical API key of 32-64 characters, this exposes 16 characters (10 prefix + 6 suffix), which is a significant portion of the key's entropy. An attacker with access to application logs — through log aggregation services, log files on disk, error reporting systems like Sentry, or compromised log management tools — could use the exposed prefix and suffix to narrow down the full key through brute-force or to match it against leaked credential databases.

The OWASP Logging Cheat Sheet explicitly states that application logs should never contain sensitive data such as API keys, access tokens, or passwords. The recommended approach is a whitelist model: only explicitly safe data should be logged, with the default assumption that all credential-related data is sensitive. Even partial exposure violates this principle because:

1. **Prefix exposure reveals key structure** — Many API key schemes use prefixes to identify the key type (e.g., `rxt_live_`, `sk_test_`). Logging 10 characters exposes this prefix fully.
2. **Suffix exposure aids correlation** — If an attacker has a list of candidate keys (from a breach or enumeration), the suffix can be used to confirm which key is in use.
3. **Combined exposure reduces entropy** — Knowing 16 of 32 characters reduces the brute-force search space from 16^32 to 16^16 for a hex-encoded key.

The log message is written at `INFO` level, which means it appears in standard application logs in all environments (development, staging, production). Even in environments with restricted log access, INFO-level messages are typically retained in log aggregation services for weeks or months.

---

## Current Code

```python
# File: src/services/wordpress_publisher.py
# Lines: 58-61
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
            masked_key = f"{self.api_key[:10]}...{self.api_key[-6:]}" if len(self.api_key) > 16 else "***"
            logger.info(f"WordPress publisher initialized with API key: {masked_key}")
```

---

## Why This Matters (Context & Reasoning)

The `WordPressPublisher` is instantiated every time content is published to a WordPress site. This happens in the `_publish_to_all_sites()` function at `publish_content.py:62-68`, which iterates over all active sites and creates a new publisher instance for each. This means the API key is logged every time any content is published to any WordPress site. For a workspace with 3 connected sites publishing daily, that's 3 log entries per day, each containing partial API key material. Over time, this creates a significant log surface area containing credential material.

The API keys stored in `WorkspaceIntegration.api_key` are bearer tokens for the Rext-AI WordPress plugin. These tokens grant the holder the ability to publish, update, and delete content on the connected WordPress site via the plugin's custom REST API. Compromise of these keys would allow an attacker to publish arbitrary content to the user's WordPress site, potentially for SEO spam, malware distribution, or defacement.

---

## Impact

- **Severity:** Partial API key exposure in application logs. Risk is proportional to log access scope — low risk if logs are tightly controlled, elevated risk if logs are sent to third-party services or stored on shared infrastructure.
- **Affected Users/Flows:** All users with connected WordPress sites. The log entry is created every time content is published to any site.
- **Blast Radius:** Isolated to the `WordPressPublisher` initialization log. No other code in the publisher or content management system logs credential material (verified by searching for `api_key`, `app_password`, and `masked` patterns in the codebase).

---

## Recommended Solution

Remove the partial API key from the log message entirely. Replace it with a confirmation that API key authentication is configured, without including any part of the key.

### Step 1: Replace the Logging Statement

```python
# File: src/services/wordpress_publisher.py
# Replace lines 58-61 with:

        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
            logger.info(
                "WordPress publisher initialized with API key authentication",
                extra={"site_url": self.site_url},
            )
```

This replacement:
- Confirms that API key authentication is being used (useful for debugging)
- Includes the `site_url` in the structured log context so operators can identify which site is being configured
- Does NOT include any part of the API key itself
- Uses `extra` dict for structured logging compatibility with the project's `structlog` setup (the project uses `structlog>=25.4.0` per `pyproject.toml:40`)

### Step 2: Verify No Other Credential Logging Exists

Search the codebase for any other instances of credential logging in the WordPress publisher or related code:

```bash
# Verify no other credential logging patterns exist
grep -rn "api_key\|app_password\|masked_key\|credential" src/services/wordpress_publisher.py
grep -rn "api_key\|app_password" src/api/routes/content/modules/sites.py | grep -i "log\|print\|debug\|info\|warn\|error"
```

Note: The `sites.py:64` line `logger.info(f"Validating site connection for {data.site_url} using Rext-AI plugin")` is safe — it logs the site URL but not the credentials. The `sites.py:74` line `logger.error(f"Site connection validation failed: {str(e)}")` should be checked to ensure exception messages don't contain credential material (they shouldn't, as the WordPress API error messages don't include credentials).

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `src/services/wordpress_publisher.py` | `96-97` | `logger.error(error_msg)` in `validate_plugin` — logs error message from WordPress API, which should not contain credentials but should be verified |
| `src/services/wordpress_publisher.py` | `175-176` | `logger.info(f"Publishing post to WordPress: {title}")` — safe, logs title only |
| `src/services/wordpress_publisher.py` | `196, 200, 204` | Error logging in `publish_post` — logs error messages, not credentials |
| `src/api/routes/content/modules/sites.py` | `64, 74` | Site connection logging — logs site URL and error messages, not credentials |
| `src/api/routes/content/modules/publish_content.py` | `84, 87` | Publish result logging — logs site URL and post ID, not credentials |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Connect a WordPress site with an API key (any string longer than 16 characters)
2. Publish content to the site
3. Check application logs for the message `"WordPress publisher initialized with API key: ..."`
4. Observe that the first 10 and last 6 characters of the API key are visible in the log

### After Fix (Verify the Solution):
1. Publish content to a WordPress site configured with API key authentication
2. Check application logs for the message `"WordPress publisher initialized with API key authentication"`
3. Verify that NO part of the API key appears in any log entry
4. Verify the `site_url` is included in the log context
5. Repeat with Basic Auth (username/app_password) — verify no credentials are logged in that path either
6. Verify publishing still works correctly end-to-end

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/ -v -k "wordpress or publish"
```

---

## Acceptance Criteria

- [ ] No part of the API key (prefix, suffix, or full) appears in any log message
- [ ] The log message confirms API key authentication is being used (for debugging purposes)
- [ ] The `site_url` is included in the log context for identifying which site is being initialized
- [ ] Publishing to WordPress sites with API key authentication still works correctly
- [ ] Publishing to WordPress sites with Basic Auth (username/app_password) still works correctly
- [ ] No other credential logging patterns exist in `wordpress_publisher.py`
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [Python structlog — Bound Loggers](https://www.structlog.org/en/stable/bound-loggers.html) — structured logging with `extra` context parameters
- **Security Advisory:** [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html) — explicitly states API keys, passwords, and tokens must not be logged
- **Migration Guide:** N/A
- **Best Practice Reference:** [OWASP Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html) — guidance on handling secrets in application code, including logging restrictions
- **Related Issues/PRs:** None identified

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-029 (WorkspaceIntegration.to_dict() Leaks Credentials) — credential exposure in API responses; TASK-089 (Integration Credentials Stored in Plaintext) — the broader credential security issue; TASK-170 (Response Schema Includes Credentials) — schema-level credential exposure

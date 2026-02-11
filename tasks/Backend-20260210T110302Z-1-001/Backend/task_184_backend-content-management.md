# Task 184: Replace Generic Exception with Custom Exception in WordPress Publisher

## Metadata
- **Task ID:** TASK-184
- **Source:** Backend Content Management Audit (Finding #23 under P2 Medium)
- **Audit Report:** `audit-reports/backend-content-management.md`
- **Priority:** P2 Medium
- **Category:** code-quality
- **Effort Estimate:** small (< 1 hour)

---

## Description

The `WordPressPublisher` class in `src/services/wordpress_publisher.py` catches specific HTTP and connection errors from the `httpx` library but then re-raises them as bare `Exception` instances in 4 locations: lines 93, 98, 200, and 205. This anti-pattern has several problems.

First, it destroys error specificity. Callers cannot distinguish between a WordPress connection timeout, an authentication failure, a rate limit error, or any other failure type — they all arrive as generic `Exception`. This makes it impossible for upstream code (like the `publish_content.py` route at line 299 or `sites.py` at line 299) to implement fine-grained error handling such as retrying on transient errors but failing fast on authentication errors.

Second, the `raise Exception(error_msg)` pattern on line 200 and 205 breaks the exception chain. When a new `Exception` is raised without `from e`, Python sets `__context__` implicitly but the explicit `__cause__` is lost. This means that in logs and stack traces, the relationship between the original `httpx.HTTPStatusError` and the re-raised `Exception` is less clear. PEP 3134 recommends using `raise ... from e` for explicit exception chaining.

Third, the project already has a well-designed custom exception hierarchy in `src/api/middleware/exceptions.py` that includes `RextExternalServiceException` (line 328) — specifically designed for external service errors — with fields for `service_name` and `service_error`. There is also `ExternalServiceTimeoutException` (line 354) for timeout scenarios. These exceptions integrate with the project's error handling middleware, returning proper HTTP 502 responses with structured error payloads. Using bare `Exception` bypasses this entire system.

The same pattern also exists in `validate_plugin()` at lines 93 and 98, where connection validation errors are raised as generic exceptions.

---

## Current Code

```python
# File: src/services/wordpress_publisher.py
# Lines: 85-98 (validate_plugin method)
    async def validate_plugin(self) -> bool:
        endpoint = self.api_endpoint if self.api_endpoint else f"{self.site_url}/wp-json/rext-ai/v1/"

        try:
            response = await self.client.get(endpoint, timeout=15)

            if response.status_code == 200:
                return True
            else:
                error_msg = f"Rext-AI validation failed (Status {response.status_code}): {response.text}"
                logger.error(error_msg)
                raise Exception(error_msg)  # Line 93: Generic Exception

        except httpx.HTTPError as e:
            error_msg = f"Failed to connect to Rext-AI plugin at {endpoint}: {str(e)}"
            logger.error(error_msg)
            raise Exception(error_msg)  # Line 98: Generic Exception
```

```python
# File: src/services/wordpress_publisher.py
# Lines: 195-205 (publish_post method, error handling)
        except httpx.HTTPStatusError as e:
            error_msg = f"WordPress API error: {e}"
            if e.response is not None:
                error_msg += f" - {e.response.text}"
            logger.error(error_msg)
            raise Exception(error_msg)  # Line 200: Generic Exception

        except Exception as e:
            error_msg = f"Failed to publish to WordPress: {str(e)}"
            logger.error(error_msg)
            raise Exception(error_msg)  # Line 205: Generic Exception
```

---

## Why This Matters (Context & Reasoning)

WordPress publishing is an external integration that naturally experiences transient failures (network timeouts, rate limits, DNS issues). The ability to distinguish between different failure types is essential for implementing retry logic (see TASK-173) and providing meaningful error messages to users. When all errors are flattened to `Exception`, the route layer in `sites.py:299-301` can only catch `Exception` generically, preventing it from presenting user-friendly messages like "WordPress site is unreachable" vs "WordPress rejected the content" vs "Authentication with WordPress failed."

The project has already invested in a structured exception hierarchy (16+ exception classes in `exceptions.py`) specifically to avoid this problem. The `RextExternalServiceException` class was designed for exactly this use case, with a `service_name` field to identify which external service failed and a `service_error` field for the underlying error details.

---

## Impact

- **Severity:** Prevents fine-grained error handling and proper error reporting for WordPress publishing failures. Callers cannot retry transient errors or give users actionable error messages.
- **Affected Users/Flows:** Any content publishing flow that publishes to WordPress sites, site connection validation.
- **Blast Radius:** Localized to `wordpress_publisher.py` and its callers (`publish_content.py`, `sites.py`).

---

## Recommended Solution

### Step 1: Add import for custom exceptions in wordpress_publisher.py

```python
# File: src/services/wordpress_publisher.py
# Add to imports (after line 10):
from src.api.middleware.exceptions import (
    RextExternalServiceException,
    ExternalServiceTimeoutException,
)
```

### Step 2: Update `validate_plugin()` error handling

```python
# File: src/services/wordpress_publisher.py
# Replace lines 76-98 with:
    async def validate_plugin(self) -> bool:
        """
        Validate the Rext-AI WordPress plugin connection.

        Returns:
            True if valid, raises an exception if invalid.
        """
        endpoint = self.api_endpoint if self.api_endpoint else f"{self.site_url}/wp-json/rext-ai/v1/"

        try:
            response = await self.client.get(endpoint, timeout=15)

            if response.status_code == 200:
                return True
            else:
                error_msg = f"Rext-AI validation failed (Status {response.status_code})"
                logger.error(error_msg)
                raise RextExternalServiceException(
                    message=error_msg,
                    service_name="WordPress",
                    service_error=response.text,
                )

        except httpx.TimeoutException as e:
            logger.error(f"Timeout connecting to Rext-AI plugin at {endpoint}")
            raise ExternalServiceTimeoutException(
                service_name="WordPress",
                timeout_seconds=15,
            ) from e

        except httpx.HTTPError as e:
            error_msg = f"Failed to connect to Rext-AI plugin at {endpoint}"
            logger.error(error_msg)
            raise RextExternalServiceException(
                message=error_msg,
                service_name="WordPress",
                service_error=str(e),
            ) from e
```

### Step 3: Update `publish_post()` error handling

```python
# File: src/services/wordpress_publisher.py
# Replace lines 195-205 (the except blocks at the end of publish_post) with:
        except httpx.TimeoutException as e:
            logger.error(f"Timeout publishing to WordPress: {endpoint}")
            raise ExternalServiceTimeoutException(
                service_name="WordPress",
                timeout_seconds=30,
            ) from e

        except httpx.HTTPStatusError as e:
            error_msg = f"WordPress API error (Status {e.response.status_code})"
            response_text = e.response.text if e.response is not None else ""
            logger.error(f"{error_msg}: {response_text}")
            raise RextExternalServiceException(
                message=error_msg,
                service_name="WordPress",
                service_error=response_text,
            ) from e

        except httpx.HTTPError as e:
            error_msg = "Failed to publish to WordPress"
            logger.error(f"{error_msg}: {e}")
            raise RextExternalServiceException(
                message=error_msg,
                service_name="WordPress",
                service_error=str(e),
            ) from e
```

### Step 4: Update callers to catch specific exceptions (optional but recommended)

```python
# File: src/api/routes/content/modules/sites.py
# Line 299, update the except clause:
        except RextExternalServiceException:
            raise  # Let the middleware handle it with proper HTTP 502 response
        except Exception as e:
            logger.error(f"Failed to publish to WordPress: {e}")
            raise RextValidationException(message=f"Publishing failed: {str(e)}")
```

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `src/api/routes/content/modules/sites.py` | `73-78` | `connect_site()` catches `Exception` from `validate_plugin()` — could catch `RextExternalServiceException` specifically |
| `src/api/routes/content/modules/sites.py` | `299-301` | `publish_to_site()` catches `Exception` from `publish_post()` — could catch `RextExternalServiceException` specifically |
| `src/api/routes/content/modules/publish_content.py` | Various | Also calls WordPress publisher methods and should handle the new exception types |
| `src/services/email_service.py` | `137` | Also raises bare `Exception` — same anti-pattern but in a different service |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Configure a WordPress publisher with an invalid site URL
2. Call `validate_plugin()` and observe that a bare `Exception` is raised
3. In a debugger or log, confirm that `type(exception)` is `<class 'Exception'>` rather than a custom type

### After Fix (Verify the Solution):
1. Configure a WordPress publisher with an invalid site URL
2. Call `validate_plugin()` and confirm that `RextExternalServiceException` is raised
3. Verify the exception has `service_name="WordPress"` and `service_error` contains the underlying error message
4. Verify the `__cause__` attribute is set (exception chaining with `from e`)
5. Test with a timeout scenario (use a slow endpoint or mock) and confirm `ExternalServiceTimeoutException` is raised

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/unit/services/test_content_service.py -v
cd rext-backend && python -m pytest tests/ -k "wordpress or publish" -v
```

---

## Acceptance Criteria

- [ ] All `raise Exception(...)` in `wordpress_publisher.py` are replaced with `RextExternalServiceException` or `ExternalServiceTimeoutException`
- [ ] All re-raised exceptions use `from e` for proper exception chaining
- [ ] Timeout errors raise `ExternalServiceTimeoutException` specifically
- [ ] HTTP status errors raise `RextExternalServiceException` with status code in the message
- [ ] Connection errors raise `RextExternalServiceException` with the connection error details
- [ ] Callers in `sites.py` can catch specific exception types
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [PEP 3134 — Exception Chaining and Embedded Tracebacks](https://peps.python.org/pep-3134/) — the Python standard for explicit exception chaining with `from e`
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** [Real Python: Effectively Raising Exceptions](https://realpython.com/python-raise-exception/) — covers exception chaining, custom exception design, and when to use `from e` vs `from None`
- **Related Issues/PRs:** N/A

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** TASK-173 (No Retry Mechanism for WordPress API Calls — implementing retry logic requires distinguishable exception types to know which errors are retryable)
- **Related:** TASK-162 (httpx AsyncClient Resource Leak — same file, different issue), TASK-127 (Internal Error Messages Leaked to Clients — generic exceptions may bubble up raw error text)

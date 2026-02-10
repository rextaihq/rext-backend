# Task 006: Fix Forgot-Password Endpoint User Enumeration Vulnerability

## Metadata
- **Task ID:** TASK-006
- **Source:** Backend Authentication & Authorization Audit (Finding #11 under P1 High)
- **Audit Report:** `audit-reports/backend-authentication.md`
- **Priority:** P1 High
- **Category:** security
- **Effort Estimate:** small (< 1 hour)

---

## Description

The `/forgot-password` endpoint in `src/api/routes/users/password.py` (lines 87-94) leaks information about whether a given email address is registered in the system. When a user submits a forgot-password request with an email that does not exist, the endpoint returns an HTTP 404 response with the message `"User with this email does not exist"`. When the email does exist, it returns an HTTP 200 with `"Password reset link has been sent to your email."`. This differential response allows an attacker to enumerate valid email addresses by observing the HTTP status code and response message.

This is a well-documented vulnerability classified under OWASP Top 10:2025 A07 (Authentication Failures) and is explicitly called out in the OWASP Forgot Password Cheat Sheet. The cheat sheet mandates: "Return a consistent message for both existent and non-existent accounts." Additionally, OWASP recommends uniform response timing to prevent timing-based enumeration — the current code returns immediately for non-existent users (skipping token generation and email sending), while legitimate requests take longer due to token generation and background task scheduling.

The correct behavior, per OWASP guidance, is to always return a 200 OK with a generic message such as `"If an account with this email exists, a password reset link has been sent."` regardless of whether the email exists. The endpoint should also maintain consistent response timing by performing similar processing for both code paths.

This vulnerability is compounded by other enumeration vectors in the codebase: the registration endpoint at `src/services/auth_service.py:111-117` raises a `DuplicateResourceException` that includes the email in the `conflicting_value` field, and the `/register-with-invitation` endpoint at `src/api/routes/users/auth.py:458` returns a `user_existed` boolean flag in its response.

---

## Current Code

```python
# File: src/api/routes/users/password.py
# Lines: 69-129
@router.post("/forgot-password")
async def forgot_password(
    request: Request,
    forgot_request: ForgotPasswordRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_async_db),
    _rate_limit: None = Depends(password_reset_rate_limit())
):
    """
    Initiate forgot password process.
    Sends password reset email with token.
    """
    try:
        logger.info(f"Forgot password request for: {forgot_request.email}")
        service = UserService(db)

        # Get user by email
        user = await service.get_user_by_email(forgot_request.email)
        if not user:
            return error(
                message="User with this email does not exist",
                code=ErrorCode.RESOURCE_NOT_FOUND,
                status_code=404,
                severity=ErrorSeverity.MEDIUM,
                request=request
            )

        # Generate reset token
        reset_data = {
            "user_id": str(user.id),
            "email": user.email,
            "jti": str(uuid.uuid4())
        }
        reset_token = create_reset_token(data=reset_data)

        # Set reset token via service
        await service.set_reset_token(user.id, reset_token)

        # Get frontend URL
        frontend_url = settings.FRONTEND_URL

        # Send email in background using professional template
        background_tasks.add_task(
            send_password_reset_email_task,
            email=user.email,
            user_name=user.full_name or user.display_name or user.email,
            reset_token=reset_token,
            user_id=str(user.id),
            frontend_url=frontend_url
        )

        logger.info(f"Password reset email sent to: {user.email}")
        return success(
            data={"message": "Password reset link has been sent to your email."},
            request=request,
            message="Forgot password initiated successfully"
        )

    except Exception as e:
        logger.error(f"Forgot password error: {str(e)}")
        raise
```

---

## Why This Matters (Context & Reasoning)

The forgot-password endpoint is one of the most commonly targeted endpoints for account enumeration attacks. Attackers use automated tools to submit lists of email addresses and observe which ones return "user not found" versus "email sent." This allows them to build a list of valid accounts, which can then be used for credential stuffing, spear phishing, or targeted brute-force attacks.

In a SaaS application like Rext AI, user emails represent business accounts and workspace owners. An attacker enumerating valid emails could target high-value accounts, attempt credential stuffing with leaked password databases, or craft convincing phishing emails knowing the target has an active Rext account.

The risk of not fixing this is that the forgot-password endpoint becomes a free email validation oracle for attackers. Rate limiting (which is present via `password_reset_rate_limit()`) slows down enumeration but does not prevent it — a determined attacker can still enumerate accounts at a reduced rate.

---

## Impact

- **Severity:** Attackers can enumerate all registered email addresses in the system, enabling targeted attacks (credential stuffing, phishing, social engineering)
- **Affected Users/Flows:** All users — any registered email can be discovered through this endpoint
- **Blast Radius:** System-wide. The vulnerability also exists in the registration endpoint (`DuplicateResourceException` with `conflicting_value`) and the invitation registration endpoint (`user_existed` flag), creating multiple enumeration vectors

---

## Recommended Solution

### Step 1: Return a consistent response regardless of email existence

```python
# File: src/api/routes/users/password.py
# Replace lines 69-129 with:
@router.post("/forgot-password")
async def forgot_password(
    request: Request,
    forgot_request: ForgotPasswordRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_async_db),
    _rate_limit: None = Depends(password_reset_rate_limit())
):
    """
    Initiate forgot password process.
    Sends password reset email with token.

    SECURITY: Always returns the same response regardless of whether the email
    exists to prevent user enumeration attacks (OWASP A07:2025).
    """
    try:
        # Use a generic message for all responses
        generic_message = "If an account with this email exists, a password reset link has been sent."

        # Log at debug level only — do not log the email at info level
        logger.debug(f"Forgot password request received")

        service = UserService(db)
        user = await service.get_user_by_email(forgot_request.email)

        if user:
            # Generate reset token
            reset_data = {
                "user_id": str(user.id),
                "email": user.email,
                "jti": str(uuid.uuid4())
            }
            reset_token = create_reset_token(data=reset_data)

            # Set reset token via service
            await service.set_reset_token(user.id, reset_token)

            # Get frontend URL
            frontend_url = settings.FRONTEND_URL

            # Send email in background
            background_tasks.add_task(
                send_password_reset_email_task,
                email=user.email,
                user_name=user.full_name or user.display_name or user.email,
                reset_token=reset_token,
                user_id=str(user.id),
                frontend_url=frontend_url
            )
            logger.info(f"Password reset initiated for user: {user.id}")

        # Always return 200 with the same generic message
        return success(
            data={"message": generic_message},
            request=request,
            message=generic_message
        )

    except Exception as e:
        logger.error(f"Forgot password error: {str(e)}")
        raise
```

### Step 2: Remove the email from the info-level log line

The original code logs `f"Forgot password request for: {forgot_request.email}"` at info level (line 82). This should be changed to debug level to avoid filling production logs with user-submitted email addresses, which could be attacker-generated.

This is already handled in the Step 1 code above — the log line is changed from `logger.info(f"Forgot password request for: {forgot_request.email}")` to `logger.debug(f"Forgot password request received")`.

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `src/services/auth_service.py` | `111-117` | Registration raises `DuplicateResourceException` with `conflicting_value=email`, leaking the email in the error response |
| `src/api/routes/users/auth.py` | `458` | `/register-with-invitation` returns `user_existed: true/false` flag in response |
| `src/api/routes/users/user_status.py` | `105-112, 202-203, 257-264` | Suspend/activate endpoints return "User not found" 404 errors |
| `src/api/middleware/error_handler.py` | `398-426` | `_filter_context()` does not filter `conflicting_value` from error responses |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Start the backend server
2. Send a POST request to `/api/user/forgot-password` with a registered email:
   ```bash
   curl -X POST http://localhost:8000/api/user/forgot-password \
     -H "Content-Type: application/json" \
     -d '{"email": "registered@example.com"}'
   ```
   Observe: HTTP 200 with message "Password reset link has been sent to your email."
3. Send a POST request with a non-existent email:
   ```bash
   curl -X POST http://localhost:8000/api/user/forgot-password \
     -H "Content-Type: application/json" \
     -d '{"email": "nonexistent@example.com"}'
   ```
   Observe: HTTP 404 with message "User with this email does not exist" — **this confirms the vulnerability**

### After Fix (Verify the Solution):
1. Send a POST request with a registered email:
   ```bash
   curl -X POST http://localhost:8000/api/user/forgot-password \
     -H "Content-Type: application/json" \
     -d '{"email": "registered@example.com"}'
   ```
   Observe: HTTP 200 with message "If an account with this email exists, a password reset link has been sent."
2. Send a POST request with a non-existent email:
   ```bash
   curl -X POST http://localhost:8000/api/user/forgot-password \
     -H "Content-Type: application/json" \
     -d '{"email": "nonexistent@example.com"}'
   ```
   Observe: HTTP 200 with the **same** message "If an account with this email exists, a password reset link has been sent."
3. Verify that for the registered email, the reset email is actually sent (check the email inbox or email service logs)
4. Verify that for the non-existent email, no reset email is sent

### Run Existing Tests:
```bash
cd rext-backend
pytest tests/ -k "password" -v
```

---

## Acceptance Criteria

- [ ] The `/forgot-password` endpoint returns HTTP 200 for both existing and non-existing email addresses
- [ ] The response message is identical for both cases: "If an account with this email exists, a password reset link has been sent."
- [ ] Password reset emails are still sent correctly for valid accounts
- [ ] No password reset email is sent for non-existent accounts
- [ ] The email address is not logged at info level (only at debug level)
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [OWASP Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html) — specifically the "Return a consistent message" requirement
- **Security Advisory:** [OWASP Top 10:2025 A07 — Authentication Failures](https://owasp.org/Top10/2025/A07_2025-Authentication_Failures/) — "Ensure registration, credential recovery, and API pathways are hardened against account enumeration attacks by using the same messages for all outcomes"
- **Migration Guide:** N/A
- **Best Practice Reference:** [OWASP Authentication Cheat Sheet — Prevent User Enumeration](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html#authentication-and-error-messages)
- **Related Issues/PRs:** [OWASP Web Security Testing Guide — Account Enumeration](https://owasp.org/www-project-web-security-testing-guide/latest/4-Web_Application_Security_Testing/03-Identity_Management_Testing/04-Testing_for_Account_Enumeration_and_Guessable_User_Account)

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-005 (Password Strength Validation — both are auth hardening tasks)

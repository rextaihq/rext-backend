# Task 020: Fix Registration Route Double-Commit Breaking Transaction Atomicity

## Metadata
- **Task ID:** TASK-020
- **Source:** Backend Authentication & Authorization Audit (Finding #15 under P2 Medium)
- **Audit Report:** `audit-reports/backend-authentication.md`
- **Priority:** P2 Medium
- **Category:** bug
- **Effort Estimate:** small (< 1 hour)

---

## Description

The `/register` endpoint in `src/api/routes/users/auth.py:108-200` calls `await db.commit()` twice within a single request handler — once at line 130 after user creation, and again at line 174 after creating `NotificationPreferences`. This creates two separate database transactions for what should be a single atomic operation.

If the first commit succeeds but the second fails (e.g., a database constraint violation on `NotificationPreferences`, a connection timeout, or a server crash between the two commits), the user is created in the database without notification preferences. This leaves the database in an inconsistent state where the user exists but is missing required associated records.

The same pattern exists in the `/register-with-invitation` endpoint at lines 349 and 390 — the first commit is at line 349 (after invitation acceptance), and the second at line 390 (after creating `NotificationPreferences` for new users).

The comment at line 128-129 states: "IMPORTANT: Commit transaction before background task / Background tasks run immediately and need the user to exist in the database." This comment is misleading. FastAPI's `BackgroundTasks` does NOT execute tasks immediately — tasks are queued and execute after the response is sent to the client. The `background_tasks.add_task()` call at line 136 only adds the task to the queue; it does not execute it. Therefore, there is no need to commit before adding the background task.

According to SQLAlchemy's documentation, the correct approach is to use `flush()` when you need database-generated values (like auto-increment IDs) mid-transaction without committing. `flush()` sends the SQL INSERT to the database and populates the object's ID, but keeps the transaction open so all changes can be committed (or rolled back) atomically at the end.

The SQLAlchemy Unit of Work pattern recommends: "Commit once at the end if everything succeeds; otherwise rollback once. Atomic or nothing."

---

## Current Code

```python
# File: src/api/routes/users/auth.py
# Lines: 108-200 (the /register endpoint — key sections shown)
@router.post("/register")
async def create_user(
    user: RegisterUser,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_async_db),
    _rate_limit: None = Depends(registration_rate_limit())
):
    try:
        auth_service = AuthService(db)
        new_user, verification_token = await auth_service.register_user(
            email=user.email,
            password=user.password,
            full_name=user.full_name
        )

        # IMPORTANT: Commit transaction before background task
        # Background tasks run immediately and need the user to exist in the database
        await db.commit()  # <-- FIRST COMMIT (line 130)

        frontend_url = settings.FRONTEND_URL

        # Send verification email in background
        background_tasks.add_task(
            send_verification_email_task,
            email=new_user.email,
            first_name=new_user.full_name or new_user.display_name,
            verification_token=verification_token,
            user_id=str(new_user.id),
            frontend_url=frontend_url
        )

        # set the notification preferences
        notification_preference = NotificationPreferences(
            user_id=new_user.id,
            # ... all preference fields ...
        )
        db.add(notification_preference)
        await db.commit()  # <-- SECOND COMMIT (line 174)
        await db.refresh(notification_preference)

        # ... build and return response ...
```

```python
# File: src/api/routes/users/auth.py
# Lines: 348-391 (the /register-with-invitation endpoint — relevant section)
        # Commit transaction before background tasks
        await db.commit()  # <-- FIRST COMMIT (line 349)

        # Step 6: Send welcome email for new users only
        if not user_exists:
            # ... background task setup ...

            notification_preference = NotificationPreferences(
                user_id=current_user.id,
                # ... all preference fields ...
            )
            db.add(notification_preference)
            await db.commit()  # <-- SECOND COMMIT (line 390)
            await db.refresh(notification_preference)
```

---

## Why This Matters (Context & Reasoning)

User registration is a critical flow that creates multiple related database records: the user account, role assignments (via `auth_service.register_user`), trial subscription, and notification preferences. These records are interdependent — a user without notification preferences will cause errors in the notification system, and the UI may display incomplete settings.

The double-commit pattern violates the fundamental principle of transaction atomicity. In database terms, atomicity guarantees that either all operations in a transaction succeed or none do. By splitting the registration into two transactions, the code introduces a failure window where partial data can persist.

Consider the failure scenario: the first commit at line 130 succeeds (user created, role assigned, trial subscription created), but then the server crashes or the database connection drops before line 174. The user can now log in, but they have no notification preferences. The notification system will either crash when trying to read preferences (if it expects them to exist) or silently skip notifications (if it handles the missing record gracefully). Either way, the user experience is degraded.

The fix uses `flush()` instead of the first `commit()`. SQLAlchemy's `flush()` sends the SQL to the database and generates IDs without committing the transaction. All operations then share a single transaction boundary, and a single `commit()` at the end makes everything atomic.

---

## Impact

- **Severity:** If the second commit fails, the user is created without notification preferences, leaving the database in an inconsistent state. The user can log in but will have broken notification settings.
- **Affected Users/Flows:** Every new user registration (both direct registration and invitation-based registration). The double-commit pattern affects the `/register` and `/register-with-invitation` endpoints.
- **Blast Radius:** Isolated to the registration flow. Other endpoints do not exhibit this pattern for user creation.

---

## Recommended Solution

### Step 1: Fix the `/register` endpoint — replace first commit with flush, reorder operations

```python
# File: src/api/routes/users/auth.py
# Replace lines 119-175 with:
    try:
        # Use auth service
        auth_service = AuthService(db)
        new_user, verification_token = await auth_service.register_user(
            email=user.email,
            password=user.password,
            full_name=user.full_name
        )

        # Flush to get database-generated ID without committing the transaction
        await db.flush()

        # Create notification preferences within the same transaction
        notification_preference = NotificationPreferences(
            user_id=new_user.id,
            email_notifications=True,
            in_app_notifications=True,
            ws_invite_received=True,
            ws_invite_accepted=True,
            ws_role_changed=True,
            ws_member_removed=True,
            gen_started=True,
            gen_completed=True,
            gen_failed=True,
            gen_published=True,
            billing_payment_success=True,
            billing_payment_failed=True,
            billing_subscription_cancelled=True,
            billing_subscription_expiring=True,
            billing_trial_ending=True,
            billing_usage_limit_warning=True,
            billing_usage_limit_exceeded=True,
            kb_processing_completed=True,
            kb_processing_failed=True,
            digest_enabled=True,
            digest_frequency="daily",
            marketing_updates=False
        )
        db.add(notification_preference)

        # Single atomic commit — user + notification preferences
        await db.commit()
        await db.refresh(new_user)
        await db.refresh(notification_preference)

        # Get frontend URL from environment
        frontend_url = settings.FRONTEND_URL

        # Send verification email in background
        # Note: BackgroundTasks execute AFTER the response is sent, not immediately.
        # The commit above ensures the user exists in the database before the task runs.
        background_tasks.add_task(
            send_verification_email_task,
            email=new_user.email,
            first_name=new_user.full_name or new_user.display_name,
            verification_token=verification_token,
            user_id=str(new_user.id),
            frontend_url=frontend_url
        )
```

**Key changes:**
1. `await db.commit()` at line 130 → `await db.flush()` (gets ID without committing)
2. `NotificationPreferences` creation moved before the single `commit()`
3. Second `await db.commit()` at line 174 becomes the only `commit()` — now atomic
4. `background_tasks.add_task()` moved AFTER the single commit (background tasks execute after response anyway)
5. Misleading comment about "Background tasks run immediately" corrected

### Step 2: Fix the `/register-with-invitation` endpoint — same pattern

```python
# File: src/api/routes/users/auth.py
# In the register_with_invitation function, apply the same fix:
# Replace the section around lines 348-391:

        # Step 5: Auto-accept invitation
        acceptance_result = await invitation_service.accept_invitation(
            invitation_id=invitation.id,
            user_id=current_user.id
        )

        # Create notification preferences for new users (within same transaction)
        if not user_exists:
            notification_preference = NotificationPreferences(
                user_id=current_user.id,
                email_notifications=True,
                in_app_notifications=True,
                ws_invite_received=True,
                ws_invite_accepted=True,
                ws_role_changed=True,
                ws_member_removed=True,
                gen_started=True,
                gen_completed=True,
                gen_failed=True,
                gen_published=True,
                billing_payment_success=True,
                billing_payment_failed=True,
                billing_subscription_cancelled=True,
                billing_subscription_expiring=True,
                billing_trial_ending=True,
                billing_usage_limit_warning=True,
                billing_usage_limit_exceeded=True,
                kb_processing_completed=True,
                kb_processing_failed=True,
                digest_enabled=True,
                digest_frequency="daily",
                marketing_updates=False
            )
            db.add(notification_preference)

        # Single atomic commit — invitation acceptance + notification preferences
        await db.commit()

        # Background tasks execute after response is sent
        if not user_exists:
            frontend_url = settings.FRONTEND_URL
            background_tasks.add_task(
                send_welcome_email_task,
                email=current_user.email,
                first_name=current_user.full_name or current_user.display_name,
                user_id=str(current_user.id),
                frontend_url=frontend_url
            )
```

**Key changes:**
1. Move `NotificationPreferences` creation BEFORE the commit at line 349
2. Remove the second `await db.commit()` at line 390
3. Move `background_tasks.add_task()` AFTER the single commit

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `src/api/routes/users/auth.py` | 348-391 | `/register-with-invitation` — same double-commit pattern for new users |
| `src/api/routes/users/auth.py` | 857-883 | `/oauth/login` — commits for NotificationPreferences but only one commit (OAuthService handles its own commit) — review for consistency |
| `src/services/auth_service.py` | - | `register_user` uses `flush()` internally (verify) — the service method should NOT commit, leaving that to the route handler |
| B3 Finding 19 | - | "Notification Preferences Created in Route Layer Instead of Service" — the NotificationPreferences creation should ideally be moved to a service method; this task fixes the atomicity but doesn't refactor the architecture |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Set a debugger breakpoint after line 130 (`await db.commit()`) and before line 174 (`await db.commit()`)
2. Register a new user via `POST /register`
3. When the breakpoint hits (between the two commits), query the database:
   - The `users` table should have the new user (first commit succeeded)
   - The `notification_preferences` table should NOT have an entry for this user (second commit hasn't happened)
4. This confirms the window of inconsistency between the two commits

### After Fix (Verify the Solution):
1. Register a new user via `POST /register`
2. Immediately after registration completes, query the database:
   - The `users` table should have the new user
   - The `notification_preferences` table should have an entry for this user
   - Both records should have been created in the same transaction
3. Test the failure case: temporarily introduce an error in `NotificationPreferences` creation (e.g., set a required field to `None`)
   - Verify that the user is NOT created when notification preferences fail (atomic rollback)
4. Verify the verification email is still sent in the background after registration
5. Test `/register-with-invitation` with a new user to verify the same fix works

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/ -v -k "register or registration or auth" --no-header
```

---

## Acceptance Criteria

- [ ] `/register` endpoint uses a single `db.commit()` for user creation and notification preferences
- [ ] `/register-with-invitation` endpoint uses a single `db.commit()` for user creation, invitation acceptance, and notification preferences
- [ ] `db.flush()` is used to get database-generated IDs before the single commit
- [ ] Background email tasks are queued AFTER the single commit
- [ ] Misleading "Background tasks run immediately" comment is corrected or removed
- [ ] If notification preferences creation fails, the user is NOT created (atomic rollback)
- [ ] Verification/welcome emails are still sent after successful registration
- [ ] The new user's notification preferences are accessible immediately after registration
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [SQLAlchemy 2.0: Session Basics — Flushing](https://docs.sqlalchemy.org/en/20/orm/session_basics.html#flushing) — explains the difference between `flush()` (sends SQL without committing) and `commit()` (makes changes permanent)
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** [SQLAlchemy 2.0: Transactions and Connection Management](https://docs.sqlalchemy.org/en/20/orm/session_transaction.html) — recommends the Unit of Work pattern: "Commit once at the end if everything succeeds; otherwise rollback once"
- **Related Issues/PRs:** [FastAPI BackgroundTasks documentation](https://fastapi.tiangolo.com/tutorial/background-tasks/) — confirms that background tasks run after the response is returned, not immediately when `add_task()` is called

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-015 (Login Error Response Leaks Details — same file `auth.py`), B3 Finding 19 (Notification Preferences Created in Route Layer Instead of Service — the NotificationPreferences creation is in the route layer rather than the service layer, which is a separate architectural concern), B3 Finding 15 (Service Layer Commits Transactions — related pattern of transaction boundary management)

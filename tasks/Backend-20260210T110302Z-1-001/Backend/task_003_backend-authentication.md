# Task 003: Fix Undefined Variable `user_exists` in Auto-Accept Invitations

## Metadata
- **Task ID:** TASK-003
- **Source:** Authentication & Authorization Audit (Finding #1 under P0 Critical)
- **Audit Report:** `audit-reports/backend-authentication.md`
- **Priority:** P0 Critical
- **Category:** bug
- **Effort Estimate:** small (< 1 hour)

---

## Description

The method `_auto_accept_pending_invitations` in `src/services/auth_service.py` references the variable `user_exists` on line 895 inside a notification payload, but this variable is never defined within the method's scope. The variable is defined in the route handler `register_with_invitation` (`src/api/routes/users/auth.py:299,309`), where it indicates whether the user already had an account or was newly created during invitation registration. However, it is not passed to the `_auto_accept_pending_invitations` method, which has a separate calling context.

When `_auto_accept_pending_invitations` is called during regular login (via `auth_service.py:268`), the `user_exists` reference at line 895 raises a `NameError`. The error is caught by the inner `except Exception as e` block at line 955, which logs the error, increments `skipped_count`, and continues to the next invitation. This means the `schedule_if_allowed` notification call is never executed, and the invitation is skipped entirely — the `accept_invitation` call at line 910 (which actually creates the workspace membership) is never reached.

The practical impact is significant: any user who logs in with pending workspace invitations will have those invitations silently fail to auto-accept. The user will not see the workspace they were invited to. The error will appear in logs as `NameError: name 'user_exists' is not defined`, but since it's caught and suppressed, it may go unnoticed.

This method is called during every login for users with pending invitations. The `_auto_accept_pending_invitations` method is always called in the context of an existing user logging in (line 268), which means the user always exists — so the correct value for `user_existed` in the notification payload is always `True`.

---

## Current Code

```python
# File: src/services/auth_service.py
# Lines: 886-898
                    #  send the notification to user
                    await schedule_if_allowed(
                        db=db,
                        user_id=str(invitation.invited_by_user_id),
                        background_tasks=background_tasks,
                        pref_flag="ws_invite_accepted",
                        message=f"{user.email} has accepted an invitation to join a workspace.",
                        payload = {
                            "user_id": str(user.id),
                            "invitation_id": str(invitation.id),
                            "user_existed": user_exists  # <-- NameError: 'user_exists' is not defined
                        },
                        workspace_id=str(invitation.workspace_id),
                    )
```

```python
# File: src/services/auth_service.py
# Lines: 955-968 (inner catch-all that silently swallows the NameError)
                except Exception as e:
                    # Unexpected error - log but don't fail login
                    logger.error(
                        f"[AUTO-ACCEPT] ❌ Unexpected error auto-accepting invitation: {str(e)}",
                        exc_info=True,
                        extra={
                            "user_id": str(user.id),
                            "invitation_id": str(invitation.id),
                            "workspace_id": str(invitation.workspace_id),
                            "error": str(e),
                            "error_type": type(e).__name__
                        }
                    )
                    skipped_count += 1
```

---

## Why This Matters (Context & Reasoning)

The auto-accept invitations feature is a core part of the user onboarding flow. When a user is invited to a workspace via email, they receive an invitation link. If they already have an account, they can log in and the pending invitations should be automatically accepted, immediately giving them access to the invited workspaces.

Because the `NameError` occurs before the `accept_invitation` call (line 910), the entire invitation processing for each pending invitation is skipped. This means:
1. The notification to the inviter is never sent
2. The invitation is never accepted (no `WorkspaceMembers` or `UserRole` records are created)
3. The user doesn't see the workspace they were invited to after login
4. The error is silently logged and swallowed — no user-facing error message

This creates a confusing user experience: the inviter thinks the invitation was sent, the invitee logs in expecting to see the workspace, but nothing happens. Both parties are unaware of the silent failure.

---

## Impact

- **Severity:** Auto-accept invitations feature is completely broken. Every login with pending invitations silently fails to accept them due to `NameError`.
- **Affected Users/Flows:** All users who log in with pending workspace invitations. This affects the core invitation-to-workspace-access flow.
- **Blast Radius:** Isolated to the auto-accept during login. Manual invitation acceptance (if available through other routes) is not affected.

---

## Recommended Solution

The fix is straightforward: replace `user_exists` with the literal `True`. This method is only called during login (`auth_service.py:268`), which means the user always exists at this point — it's an existing user logging in, not a new registration.

### Step 1: Replace `user_exists` with `True` in the notification payload

```python
# File: src/services/auth_service.py
# Replace line 895:
#   "user_existed": user_exists
# With:
                            "user_existed": True
```

The full corrected block (lines 886-898):

```python
                    #  send the notification to user
                    await schedule_if_allowed(
                        db=db,
                        user_id=str(invitation.invited_by_user_id),
                        background_tasks=background_tasks,
                        pref_flag="ws_invite_accepted",
                        message=f"{user.email} has accepted an invitation to join a workspace.",
                        payload = {
                            "user_id": str(user.id),
                            "invitation_id": str(invitation.id),
                            "user_existed": True
                        },
                        workspace_id=str(invitation.workspace_id),
                    )
```

**Why `True` instead of passing as a parameter:** The `_auto_accept_pending_invitations` method is exclusively called during login (line 268), where the user necessarily already exists. Adding a parameter would add unnecessary complexity for a value that is always `True` in this context. The route handler `register_with_invitation` has its own separate notification calls (lines 435, 449, 458) that already correctly use the local `user_exists` variable.

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `src/api/routes/users/auth.py` | `299, 309` | `user_exists` is correctly defined here in `register_with_invitation` route — not related to this bug |
| `src/api/routes/users/auth.py` | `435, 449, 458` | Route handler uses `user_exists` correctly in its own notification payloads |
| `src/services/auth_service.py` | `268` | The only call site for `_auto_accept_pending_invitations` — called during login |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Create two users (User A and User B) with email/password accounts
2. As User A, invite User B to a workspace via email
3. Log in as User B
4. Check server logs for `NameError: name 'user_exists' is not defined` in `[AUTO-ACCEPT]` log entries
5. Verify that User B does NOT see the invited workspace (the auto-accept silently failed)

### After Fix (Verify the Solution):
1. Repeat the above scenario
2. Log in as User B
3. Verify that User B now sees the invited workspace immediately after login
4. Check server logs for `[AUTO-ACCEPT] ✅ Successfully auto-accepted invitation during login` entries
5. Verify the notification was sent to User A (the inviter)

### Edge Cases:
1. User with no pending invitations — login should complete without errors
2. User with multiple pending invitations — all should be auto-accepted
3. User with expired invitations — should be skipped (status set to "expired")

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/ -k "invitation or auto_accept or login" -v
```

---

## Acceptance Criteria

- [ ] `user_exists` replaced with `True` on line 895 of `src/services/auth_service.py`
- [ ] Auto-accept invitations feature works correctly during login
- [ ] Notifications are sent to inviters when invitations are auto-accepted
- [ ] No `NameError` appears in server logs during login with pending invitations
- [ ] Users see invited workspaces immediately after login
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [Python NameError documentation](https://docs.python.org/3/library/exceptions.html#NameError)
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** N/A (internal logic bug)
- **Related Issues/PRs:** None

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** None

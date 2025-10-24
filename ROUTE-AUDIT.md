# Route Permission Coverage Audit Report

**Generated:** 2025-10-24 10:14:38

## Summary

- **Total Files:** 78
- **Total Routes:** 278
- **Public Routes:** 54
- **Protected Routes:** 191
- **Unprotected Routes:** 33
- **Coverage:** 85.3%

## Unprotected Routes

These routes need permission protection:

### api/routes/admin/admin_invitation_routes.py

- ❌ `GET /{token}/validate`
  - Function: `validate_admin_invitation_token` (line 317)
- ❌ `POST /{token}/accept`
  - Function: `accept_admin_invitation` (line 367)
- ❌ `POST /{token}/decline`
  - Function: `decline_admin_invitation` (line 408)

### api/routes/audit/modules/audit_user.py

- ❌ `GET /user/my-logs`
  - Function: `get_my_audit_logs` (line 21)

### api/routes/email/preview.py

- ❌ `POST /auth`
  - Function: `preview_auth_email` (line 70)
- ❌ `POST /workspace`
  - Function: `preview_workspace_email` (line 149)
- ❌ `POST /auth/html`
  - Function: `preview_auth_email_html` (line 253)
- ❌ `POST /workspace/html`
  - Function: `preview_workspace_email_html` (line 270)

### api/routes/email/webhooks.py

- ❌ `POST /resend`
  - Function: `handle_resend_webhook` (line 166)

### api/routes/events/sse_routes.py

- ❌ `GET /{operation_id}`
  - Function: `subscribe_to_operation_events` (line 25)

### api/routes/events/sse_test_route.py

- ❌ `GET /test`
  - Function: `stream_test_events` (line 71)

### api/routes/health.py

- ❌ `GET /payment`
  - Function: `payment_health_check` (line 40)
- ❌ `GET /payment/quick`
  - Function: `payment_quick_health_check` (line 178)

### api/routes/invitations.py

- ❌ `GET /{token}/validate`
  - Function: `validate_invitation` (line 45)
- ❌ `POST /{token}/accept`
  - Function: `accept_invitation` (line 172)

### api/routes/subscriptions/license_routes.py

- ❌ `POST /validate`
  - Function: `validate_license` (line 39)

### api/routes/subscriptions/plan_routes.py

- ❌ `GET /public`
  - Function: `list_public_plans` (line 30)

### api/routes/subscriptions/subscription_routes.py

- ❌ `GET /invoices`
  - Function: `get_invoices` (line 561)

### api/routes/subscriptions/trial_routes.py

- ❌ `GET /eligibility`
  - Function: `check_trial_eligibility_endpoint` (line 55)

### api/routes/subscriptions/webhook_routes.py

- ❌ `POST /lemonsqueezy`
  - Function: `handle_lemonsqueezy_webhook` (line 26)

### api/routes/users/email_preferences.py

- ❌ `POST /unsubscribe`
  - Function: `unsubscribe` (line 127)

### api/routes/users/user_permissions.py

- ❌ `GET /me/permissions`
  - Function: `get_current_user_permissions` (line 25)

### api/routes/users/user_security.py

- ❌ `GET /security/stats`
  - Function: `get_current_user_security_stats` (line 22)
- ❌ `GET /security/login-history`
  - Function: `get_current_user_login_history` (line 48)
- ❌ `GET /security/active-sessions-count`
  - Function: `get_active_sessions_count` (line 81)

### api/routes/workspaces/email_template_route.py

- ❌ `GET /variables/{template_type}`
  - Function: `get_template_variables` (line 34)
- ❌ `POST /preview`
  - Function: `preview_email_template` (line 50)
- ❌ `GET /defaults/{template_type}`
  - Function: `get_default_template_for_type` (line 180)

### api/routes/workspaces/workspace_route.py

- ❌ `GET /all`
  - Function: `get_workspaces` (line 37)
- ❌ `GET /detail`
  - Function: `get_workspace_by_id` (line 56)
- ❌ `POST /create`
  - Function: `create_workspace` (line 89)
- ❌ `DELETE /delete`
  - Function: `delete_workspace` (line 134)
- ❌ `PUT /update`
  - Function: `update_workspace` (line 161)

## Protected Routes

Total protected routes: 191


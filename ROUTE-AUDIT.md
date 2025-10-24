# Route Permission Coverage Audit Report

**Generated:** 2025-10-24 07:39:58

## Summary

- **Total Files:** 78
- **Total Routes:** 278
- **Public Routes:** 54
- **Protected Routes:** 128
- **Unprotected Routes:** 96
- **Coverage:** 57.1%

## Unprotected Routes

These routes need permission protection:

### api/routes/admin/admin_invitation_routes.py

- ❌ `GET /{token}/validate`
  - Function: `validate_admin_invitation_token` (line 317)
- ❌ `POST /{token}/accept`
  - Function: `accept_admin_invitation` (line 367)
- ❌ `POST /{token}/decline`
  - Function: `decline_admin_invitation` (line 408)

### api/routes/admin/export_routes.py

- ❌ `GET /export/subscriptions`
  - Function: `export_subscriptions` (line 34)
- ❌ `GET /export/invoices`
  - Function: `export_invoices` (line 84)
- ❌ `GET /export/usage`
  - Function: `export_usage_data` (line 131)
- ❌ `GET /export/revenue-summary`
  - Function: `export_revenue_summary` (line 175)

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

### api/routes/subscriptions/admin/admin_subscription_management.py

- ❌ `POST /assign`
  - Function: `assign_subscription` (line 34)
- ❌ `POST /{subscription_id}/extend`
  - Function: `extend_subscription` (line 61)
- ❌ `POST /{subscription_id}/reset-usage`
  - Function: `reset_usage` (line 87)

### api/routes/subscriptions/admin/admin_subscription_retrieval.py

- ❌ `GET /{subscription_id}`
  - Function: `get_subscription_admin` (line 55)

### api/routes/subscriptions/admin/export_routes.py

- ❌ `GET /export/subscriptions`
  - Function: `export_subscriptions_csv` (line 40)
- ❌ `GET /export/invoices`
  - Function: `export_invoices_csv` (line 160)
- ❌ `GET /export/revenue-summary`
  - Function: `export_revenue_summary_csv` (line 192)
- ❌ `GET /export/trial-conversions`
  - Function: `export_trial_conversions_csv` (line 328)

### api/routes/subscriptions/admin/refund_routes.py

- ❌ `GET /refunds`
  - Function: `list_refunds` (line 62)
- ❌ `GET /refunds/{refund_id}`
  - Function: `get_refund` (line 114)
- ❌ `POST /refunds/create`
  - Function: `create_refund` (line 149)

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

### api/routes/users/invitations.py

- ❌ `GET /pending`
  - Function: `get_pending_invitations` (line 42)
- ❌ `POST /{invitation_id}/decline`
  - Function: `decline_invitation` (line 213)

### api/routes/users/management.py

- ❌ `GET /users`
  - Function: `get_users` (line 90)
- ❌ `DELETE /delete/{user_id}`
  - Function: `delete_user` (line 127)
- ❌ `PUT /update/{user_id}`
  - Function: `update_user` (line 190)
- ❌ `POST /export-data`
  - Function: `export_user_data` (line 257)

### api/routes/users/onboarding.py

- ❌ `POST /update`
  - Function: `update_onboarding_step` (line 62)
- ❌ `POST /complete`
  - Function: `complete_onboarding` (line 105)
- ❌ `POST /reset`
  - Function: `reset_onboarding` (line 129)
- ❌ `GET /should-show`
  - Function: `should_show_onboarding` (line 160)
- ❌ `POST /marketing`
  - Function: `update_marketing_data` (line 188)

### api/routes/users/password.py

- ❌ `POST /change-password`
  - Function: `change_password` (line 192)
- ❌ `POST /verify-password`
  - Function: `verify_password` (line 283)

### api/routes/users/preferences.py

- ❌ `GET /preferences`
  - Function: `get_user_preferences` (line 46)
- ❌ `PATCH /preferences`
  - Function: `update_user_preferences` (line 76)

### api/routes/users/profile.py

- ❌ `GET /profile`
  - Function: `get_profile` (line 27)
- ❌ `PATCH /profile`
  - Function: `update_profile` (line 80)
- ❌ `POST /avatar/upload`
  - Function: `upload_avatar` (line 156)
- ❌ `DELETE /avatar`
  - Function: `delete_avatar` (line 256)
- ❌ `GET /preferences/notifications`
  - Function: `get_notification_preferences` (line 324)
- ❌ `PATCH /preferences/notifications`
  - Function: `update_notification_preferences` (line 365)

### api/routes/users/roles.py

- ❌ `GET /{user_id}/roles`
  - Function: `list_user_roles` (line 137)

### api/routes/users/sessions.py

- ❌ `GET /sessions`
  - Function: `list_user_sessions` (line 22)
- ❌ `DELETE /sessions/{session_id}`
  - Function: `revoke_session` (line 62)
- ❌ `DELETE /sessions`
  - Function: `revoke_all_sessions` (line 87)
- ❌ `POST /sessions/revoke-all`
  - Function: `revoke_all_sessions_post` (line 134)

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

### api/routes/users/user_status.py

- ❌ `POST /{user_id}/suspend`
  - Function: `suspend_user` (line 28)
- ❌ `POST /{user_id}/activate`
  - Function: `activate_user` (line 124)
- ❌ `POST /{user_id}/ban`
  - Function: `ban_user` (line 218)
- ❌ `POST /deactivate`
  - Function: `deactivate_account` (line 314)

### api/routes/workspaces/email_template_route.py

- ❌ `GET /variables/{template_type}`
  - Function: `get_template_variables` (line 34)
- ❌ `POST /preview`
  - Function: `preview_email_template` (line 50)
- ❌ `GET /defaults/{template_type}`
  - Function: `get_default_template_for_type` (line 180)

### api/routes/workspaces/invitations.py/modules/invitation_list.py

- ❌ `GET /sent`
  - Function: `list_sent_invitations` (line 25)
- ❌ `GET /received`
  - Function: `list_received_invitations` (line 69)

### api/routes/workspaces/invitations.py/modules/invitation_manage.py

- ❌ `POST /accept`
  - Function: `accept_invitation` (line 93)
- ❌ `POST /{invitation_id}/revoke`
  - Function: `revoke_invitation` (line 162)

### api/routes/workspaces/workspace_core.py

- ❌ `GET /all`
  - Function: `get_workspaces` (line 37)
- ❌ `GET /detail`
  - Function: `get_workspace_by_id` (line 56)
- ❌ `GET /slug/{workspace_slug}`
  - Function: `get_workspace_by_slug` (line 104)
- ❌ `GET /{workspace_id}`
  - Function: `get_workspace_by_id_path` (line 149)
- ❌ `PUT /{workspace_id}`
  - Function: `update_workspace` (line 201)
- ❌ `DELETE /{workspace_id}`
  - Function: `delete_workspace_endpoint` (line 257)

### api/routes/workspaces/workspace_knowledge.py

- ❌ `GET /text/{text_id}`
  - Function: `get_text_knowledge` (line 513)
- ❌ `PATCH /text/{text_id}`
  - Function: `update_text_knowledge` (line 539)

### api/routes/workspaces/workspace_knowledge_bases.py

- ❌ `GET /{kb_id}`
  - Function: `get_knowledge_base` (line 114)

### api/routes/workspaces/workspace_permissions.py

- ❌ `GET /{workspace_id}/permissions/me`
  - Function: `get_my_workspace_permissions` (line 34)
- ❌ `GET /{workspace_id}/permissions/check`
  - Function: `check_workspace_permission` (line 123)
- ❌ `POST /{workspace_id}/permissions/refresh`
  - Function: `refresh_workspace_permissions` (line 210)
- ❌ `GET /{workspace_id}/members/{user_id}/permissions`
  - Function: `get_member_workspace_permissions` (line 244)

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

### api/routes/workspaces/workspace_stats.py

- ❌ `GET /{workspace_id}/stats`
  - Function: `get_workspace_stats` (line 28)

## Protected Routes

Total protected routes: 128


from fastapi import FastAPI


def register_routes(app: FastAPI) -> None:
    """
    Lazily register all API routes.
    This prevents heavy imports during app startup.
    """

    # ---- Core routes ----
    # ---- Admin ----
    from src.api.routes.admin.account_creation_allowlist_routes import (
        router as admin_account_creation_allowlist_router,
    )
    from src.api.routes.admin.account_recovery_routes import (
        router as admin_account_recovery_routes_router,
    )
    from src.api.routes.admin.admin_invitation_routes import (
        admin_router as admin_invitation_admin_router,
    )
    from src.api.routes.admin.admin_invitation_routes import (
        public_router as admin_invitation_public_router,
    )
    from src.api.routes.admin.email_analytics_routes import (
        router as admin_email_analytics_routes_router,
    )
    from src.api.routes.admin.invitation_analytics_routes import (
        router as invitation_analytics_router,
    )
    from src.api.routes.admin.monitoring_routes import router as admin_monitoring_routes_router
    from src.api.routes.admin.webhook_monitoring_routes import (
        router as admin_webhook_monitoring_routes_router,
    )

    # ---- System & Security ----
    from src.api.routes.audit.modules import router as audit_router
    from src.api.routes.combine_user.combine_data import router as dashboard_router
    from src.api.routes.combine_user.recent_activities import router as recent_activities

    # ---- Content & RBAC ----
    from src.api.routes.content.modules import router as content_router

    # ---- User & Communications ----
    from src.api.routes.email import webhook_router as email_webhook_router
    from src.api.routes.events import router as events_router
    from src.api.routes.health import router as health_router
    from src.api.routes.integrations.shared import router as integrations_router
    from src.api.routes.integrations.shopify import router as shopify_integration_router
    from src.api.routes.integrations.wordpress import (
        router as wordpress_integration_router,
    )
    from src.api.routes.invitations import router as invitations_router

    # ---- Misc & Tools ----
    from src.api.routes.notifications.notification_routes import router as notification_router
    from src.api.routes.permissions.modules import router as permissions_router
    from src.api.routes.roles.modules import router as roles_router

    # ---- Shopify ----
    from src.api.routes.subscriptions.admin import router as admin_subscription_routes_router

    # ---- Subscriptions ----
    from src.api.routes.subscriptions.plan_routes import catalog_router as plan_catalog_router
    from src.api.routes.subscriptions.plan_routes import router as plan_routes_router
    from src.api.routes.subscriptions.subscription_routes import (
        router as subscription_routes_router,
    )
    from src.api.routes.subscriptions.webhook_routes import router as webhook_routes_router
    from src.api.routes.users import router as users_router
    from src.api.routes.users.email_preferences import router as email_prefs_router
    from src.api.routes.users.onboarding import router as onboarding_router

    # ---- Workspace routes ----
    from src.api.routes.workspaces import workspace_router, workspaces_router
    from src.api.routes.workspaces.workspace_knowledge import (
        router as workspace_knowledge_router,
    )
    from src.api.routes.workspaces.workspace_knowledge_bases import (
        router as workspace_knowledge_bases_router,
    )
    from src.api.tool.routes import router as tools_router

    # ============================================================================
    # ROUTER REGISTRATION
    # ============================================================================

    app.include_router(users_router, prefix="/api/v1", tags=["Authentication"])
    app.include_router(health_router, prefix="/api/v1", tags=["Health"])
    app.include_router(events_router, prefix="/api/v1", tags=["Events"])

    app.include_router(workspaces_router, prefix="/api/v1", tags=["Workspaces"])
    app.include_router(workspace_router, prefix="/api/v1", tags=["Workspaces"])
    app.include_router(workspace_knowledge_router, prefix="/api/v1", tags=["Workspace Knowledge"])
    app.include_router(workspace_knowledge_bases_router, prefix="/api/v1", tags=["Knowledge Bases"])

    app.include_router(content_router, prefix="/api/v1", tags=["Content"])
    app.include_router(roles_router, prefix="/api/v1", tags=["Roles"])
    app.include_router(permissions_router, prefix="/api/v1", tags=["Permissions"])

    app.include_router(plan_routes_router, prefix="/api/v1", tags=["Subscription Plans"])
    app.include_router(plan_catalog_router, prefix="/api/v1", tags=["Plans"])
    app.include_router(subscription_routes_router, prefix="/api/v1", tags=["Subscriptions"])
    app.include_router(webhook_routes_router, prefix="/api/v1", tags=["Subscriptions", "Webhooks"])
    app.include_router(admin_subscription_routes_router, prefix="/api/v1")

    app.include_router(
        admin_account_creation_allowlist_router,
        prefix="/api/v1/admin",
        tags=["Admin - Account Creation Allowlist"],
    )
    app.include_router(
        admin_account_recovery_routes_router,
        prefix="/api/v1/admin",
        tags=["Admin - Account Recovery"],
    )
    app.include_router(
        admin_monitoring_routes_router, prefix="/api/v1/admin", tags=["Admin - Monitoring"]
    )
    app.include_router(
        admin_email_analytics_routes_router, prefix="/api/v1", tags=["Admin - Email Analytics"]
    )
    app.include_router(
        admin_webhook_monitoring_routes_router, prefix="/api/v1/admin", tags=["Admin - Webhooks"]
    )
    app.include_router(
        admin_invitation_admin_router, prefix="/api/v1", tags=["Admin - Platform Invitations"]
    )
    app.include_router(
        admin_invitation_public_router, prefix="/api/v1", tags=["Public - Admin Invitations"]
    )
    app.include_router(
        invitation_analytics_router,
        prefix="/api/v1/admin/analytics",
        tags=["Admin - Invitation Analytics"],
    )

    app.include_router(audit_router, prefix="/api/v1", tags=["Audit Logs"])

    app.include_router(email_webhook_router, prefix="/api/v1/email", tags=["Email Webhooks"])
    app.include_router(email_prefs_router, prefix="/api/v1", tags=["Email Preferences"])
    app.include_router(onboarding_router, prefix="/api/v1", tags=["Onboarding"])
    app.include_router(invitations_router, prefix="/api/v1", tags=["Invitations"])

    app.include_router(notification_router, prefix="/api/v1", tags=["Notifications"])
    app.include_router(tools_router, prefix="/api/v1", tags=["Tools"])
    app.include_router(
        dashboard_router,
        prefix="/api/v1",
        tags=["Dashboard"],
    )
    app.include_router(recent_activities, prefix="/api/v1", tags=["recent activity"])

    # ---- Shopify integration ----
    app.include_router(integrations_router, prefix="/api/v1/integrations", tags=["Integrations"])
    app.include_router(
        shopify_integration_router, prefix="/api/v1/integrations", tags=["Shopify Integration"]
    )
    app.include_router(
        wordpress_integration_router,
        prefix="/api/v1/integrations",
        tags=["WordPress Integration"],
    )

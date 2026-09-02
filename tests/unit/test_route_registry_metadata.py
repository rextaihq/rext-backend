from fastapi import FastAPI

from src.api.registry.routes import register_routes
from src.api.routes.admin.email_admin_routes import router as admin_email_routes_router


def test_admin_email_router_declares_prefix_and_tags() -> None:
    assert admin_email_routes_router.prefix == "/api/v1/admin/emails"
    assert "Admin - Emails" in (admin_email_routes_router.tags or [])


def test_admin_email_routes_are_prefixed_and_tagged_in_openapi() -> None:
    app = FastAPI()
    register_routes(app)

    schema = app.openapi()
    assert "/api/v1/admin/emails/failed" in schema["paths"]

    failed_get = schema["paths"]["/api/v1/admin/emails/failed"]["get"]
    assert "Admin - Emails" in failed_get.get("tags", [])

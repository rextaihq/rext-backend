"""One Lemon Squeezy provider, and so one HTTP client, for the refund paths too (G80a); and the
generation graph never reaches it, since its jobs run on event loops of their own."""

import ast
from pathlib import Path

from src.providers.payment import provider_factory

ROOT = Path(__file__).resolve().parents[3]
# What reaches the payment provider's HTTP client.
PAYMENT_MODULES = (
    "src.providers.payment",
    "src.services.subscription_service",
    "src.services.webhook_handlers",
    "src.services.duplicate_subscriptions",
    "src.services.subscription_reconciler",
    "src.services.refund_cancellation",
    "src.api.routes.subscriptions",
)


def test_refund_webhooks_use_the_shared_provider():
    from src.services.webhook_handlers import order_handlers

    assert order_handlers.get_payment_provider is provider_factory.get_payment_provider_singleton


async def test_the_admin_refund_route_uses_the_shared_provider(monkeypatch):
    from src.api.routes.subscriptions.admin import refund_routes

    shared = object()
    monkeypatch.setattr(provider_factory, "_provider_instance", shared)
    monkeypatch.setattr(refund_routes.payment_settings, "lemonsqueezy_api_key", "key")
    monkeypatch.setattr(refund_routes.payment_settings, "lemonsqueezy_store_id", "1")

    assert await refund_routes.get_lemonsqueezy_provider() is shared
    assert await refund_routes.get_lemonsqueezy_provider() is shared


def test_the_generation_graph_never_imports_the_payment_provider():
    """The provider's HTTP client belongs to the serving loop, where every caller runs today: the
    routes, the webhook handlers and the scheduler. The graph's jobs run on loops of their own
    (BG_JOB_ISOLATED_LOOPS), where that client would fail as bound to a different event loop."""
    found = []
    for path in sorted((ROOT / "src" / "flow").rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            elif isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            else:
                continue
            found += [
                f"{path.relative_to(ROOT)}: {n}" for n in names if n.startswith(PAYMENT_MODULES)
            ]
    assert found == []

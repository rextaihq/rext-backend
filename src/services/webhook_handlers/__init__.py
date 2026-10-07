"""
LemonSqueezy Webhook Handlers

This package contains individual handler functions for each LemonSqueezy webhook event type.
Each handler is responsible for processing a specific event and updating the database accordingly.

Handler Structure:
    - Each handler is an async function
    - Receives webhook_data and webhook_event as parameters
    - Updates database and sends notifications as needed
    - Raises exceptions on failure (logged by webhook service)

Usage:
    from src.services.webhook_handlers import subscription_handlers

    webhook_service.register_handler(
        WebhookEventTypes.SUBSCRIPTION_CREATED,
        subscription_handlers.handle_subscription_created
    )
"""

__all__ = [
    "subscription_handlers",
    "order_handlers",
    "register_default_handlers",
]


def register_default_handlers(webhook_service) -> None:
    """
    Register all subscription and order handlers on a webhook service.

    This is the single source of truth for the handler registry so that every
    entry point that needs to process (or reprocess) LemonSqueezy webhooks
    - the live webhook receiver and the admin retry/monitoring flow - routes
    events through exactly the same handlers.
    """
    from src.services.webhook_handlers import (
        order_handlers,
        renewal_refund_handlers,
        subscription_handlers,
    )

    # Subscription handlers (10)
    webhook_service.register_handler(
        "subscription_created", subscription_handlers.handle_subscription_created
    )
    webhook_service.register_handler(
        "subscription_updated", subscription_handlers.handle_subscription_updated
    )
    webhook_service.register_handler(
        "subscription_cancelled", subscription_handlers.handle_subscription_cancelled
    )
    webhook_service.register_handler(
        "subscription_resumed", subscription_handlers.handle_subscription_resumed
    )
    webhook_service.register_handler(
        "subscription_expired", subscription_handlers.handle_subscription_expired
    )
    webhook_service.register_handler(
        "subscription_paused", subscription_handlers.handle_subscription_paused
    )
    webhook_service.register_handler(
        "subscription_payment_success", subscription_handlers.handle_subscription_payment_success
    )
    webhook_service.register_handler(
        "subscription_payment_failed", subscription_handlers.handle_subscription_payment_failed
    )
    webhook_service.register_handler(
        "subscription_payment_recovered",
        subscription_handlers.handle_subscription_payment_recovered,
    )
    # A refunded renewal (an invoice, not an order): F8b, revnix/rext-control#537.
    webhook_service.register_handler(
        "subscription_payment_refunded",
        renewal_refund_handlers.handle_subscription_payment_refunded,
    )

    # Order handlers (2)
    webhook_service.register_handler("order_created", order_handlers.handle_order_created)
    webhook_service.register_handler("order_refunded", order_handlers.handle_order_refunded)

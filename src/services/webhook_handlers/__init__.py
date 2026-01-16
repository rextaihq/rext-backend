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
]

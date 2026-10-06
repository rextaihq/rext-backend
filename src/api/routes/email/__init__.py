"""
Email Routes

API routes for email operations: the webhook handlers for email events.
"""

from .webhooks import router as webhook_router

__all__ = ["webhook_router"]

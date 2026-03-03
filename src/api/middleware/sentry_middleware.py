"""
Sentry User Context Middleware

This middleware extracts user information from JWT tokens and adds it
to the Sentry scope for all error reports in that request.
"""

import logging
from starlette.requests import Request
from typing import Callable

from src.api.lib.sentry_config import set_user_context, clear_user_context, add_breadcrumb
from src.api.security.token_utils import decode_and_verify_token

logger = logging.getLogger(__name__)



class SentryUserContextMiddleware:
    """
    Middleware to enrich Sentry events with user context.
    Using pure ASGI interface to avoid BaseHTTPMiddleware issues with streaming responses.
    """
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Use starlette Request to help with header extraction if needed,
        # but try to avoid reading body.
        from starlette.requests import Request
        request = Request(scope, receive)

        try:
            # Extract JWT token from Authorization header
            auth_header = request.headers.get("Authorization", "")

            if auth_header.startswith("Bearer "):
                token = auth_header.replace("Bearer ", "")

                try:
                    # Decode token to get user info
                    payload = decode_and_verify_token(token)

                    if payload:
                        user_id = payload.get("sub")
                        email = payload.get("email")
                        username = payload.get("username")

                        # Set user context in Sentry
                        set_user_context(user_id=user_id, email=email, username=username)

                        # Add breadcrumb for authentication
                        add_breadcrumb(
                            message=f"Authenticated user: {user_id}",
                            category="auth",
                            level="info",
                            data={"user_id": user_id}
                        )

                except Exception as e:
                    # Don't crash on token decode errors
                    logger.debug(f"Failed to decode token for Sentry context: {e}")

        except Exception as e:
            # Never crash the request due to Sentry middleware
            logger.warning(f"Sentry user context middleware error: {e}")

        try:
            await self.app(scope, receive, send)
        finally:
            # Clear user context after request (prevent leakage)
            try:
                clear_user_context()
            except Exception:
                pass

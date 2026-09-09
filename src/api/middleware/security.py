"""
Security Headers Middleware

Adds security-related HTTP headers to all responses.
"""


class SecurityHeadersMiddleware:
    """
    Middleware to add security headers to all responses.
    Using pure ASGI interface to avoid BaseHTTPMiddleware issues with streaming responses.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))

                # Helper to set header
                def set_header(name, value):
                    # Remove existing if any
                    for i, (k, v) in enumerate(headers):
                        if k.lower() == name.lower().encode():
                            headers[i] = (k, value.encode())
                            return
                    headers.append((name.encode(), value.encode()))

                # Prevent MIME type sniffing
                set_header("X-Content-Type-Options", "nosniff")

                # Content Security Policy
                csp = (
                    "default-src 'self'; "
                    "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net; "
                    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.jsdelivr.net; "
                    "img-src 'self' data: https://fastapi.tiangolo.com; "
                    "font-src 'self' https://fonts.gstatic.com; "
                    "frame-ancestors 'none';"
                )
                set_header("Content-Security-Policy", csp)

                # Referrer Policy
                set_header("Referrer-Policy", "strict-origin-when-cross-origin")

                # Permissions Policy
                set_header("Permissions-Policy", "geolocation=(), camera=(), microphone=()")

                # HSTS (only apply on HTTPS)
                if scope.get("scheme") == "https":
                    set_header("Strict-Transport-Security", "max-age=31536000; includeSubDomains")

                message["headers"] = headers

            await send(message)

        await self.app(scope, receive, send_wrapper)

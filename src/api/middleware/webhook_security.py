"""
Webhook Security Middleware

Provides IP whitelist validation for webhook endpoints to add defense-in-depth
alongside signature verification.

Security Layers:
1. IP Whitelist: Validates request comes from known webhook source IPs
2. Signature Verification: Validates HMAC signature (handled in routes)

Phase 2, Task CRITICAL-4
"""

from typing import List
from ipaddress import ip_address, ip_network, AddressValueError
from fastapi import Request, HTTPException, status
from src.utils.logger import logger


class WebhookIPWhitelist:
    """IP whitelist validation for webhooks."""

    # LemonSqueezy webhook IP ranges
    # Note: These should be verified with LemonSqueezy documentation
    # For development, includes localhost and private ranges
    LEMONSQUEEZY_IPS = [
        "159.223.172.0/24",  # LemonSqueezy webhook servers (example - verify with LS)
        # Add more IP ranges from LemonSqueezy documentation
    ]

    # Development IPs (for testing)
    DEVELOPMENT_IPS = [
        "127.0.0.1",
        "::1",
        "localhost",
        "10.0.0.0/8",      # Private network
        "172.16.0.0/12",   # Private network
        "192.168.0.0/16",  # Private network
    ]

    @staticmethod
    def is_ip_in_whitelist(client_ip: str, whitelist: List[str]) -> bool:
        """
        Check if IP address is in whitelist.

        Supports both single IPs and CIDR notation ranges.

        Args:
            client_ip: Client IP address (e.g., "159.223.172.45")
            whitelist: List of IP addresses or CIDR ranges

        Returns:
            True if IP is in whitelist, False otherwise

        Examples:
            >>> is_ip_in_whitelist("159.223.172.45", ["159.223.172.0/24"])
            True
            >>> is_ip_in_whitelist("192.168.1.1", ["159.223.172.0/24"])
            False
        """
        try:
            client_ip_obj = ip_address(client_ip)

            for allowed in whitelist:
                try:
                    # Handle CIDR notation (e.g., "159.223.172.0/24")
                    if "/" in allowed:
                        if client_ip_obj in ip_network(allowed, strict=False):
                            return True
                    # Handle single IP
                    else:
                        if client_ip_obj == ip_address(allowed):
                            return True
                except (AddressValueError, ValueError) as e:
                    logger.warning(
                        f"Invalid IP in whitelist: {allowed}",
                        extra={"error": str(e)}
                    )
                    continue

            return False

        except (AddressValueError, ValueError) as e:
            logger.error(
                f"Invalid client IP address: {client_ip}",
                extra={"error": str(e)}
            )
            return False

    @staticmethod
    def _get_client_ip(request: Request) -> str:
            """
            Extract client IP from request.

            Uses request.client.host which is set correctly by ProxyHeadersMiddleware
            when behind a trusted reverse proxy. Do NOT read X-Forwarded-For directly
            as it is spoofable.

            Args:
                request: FastAPI request object

            Returns:
                Client IP address as string
            """
            client_ip = request.client.host if request.client else "unknown"
            logger.debug(
                f"Client IP resolved: {client_ip}",
                extra={"client_ip": client_ip}
            )
            return client_ip


    @staticmethod
    def validate_lemonsqueezy_ip(request: Request) -> None:
        """
        Validate that request comes from LemonSqueezy IP.

        This provides defense-in-depth alongside signature verification.
        Even if signature key is compromised, only whitelisted IPs can send webhooks.

        Args:
            request: FastAPI request object

        Raises:
            HTTPException: 403 if IP not in whitelist

        Security Note:
            This is the FIRST layer of defense. Signature verification
            should still be performed after this check passes.
        """
        from src.config.payment_config import payment_settings
        from src.api.config import get_settings
        settings = get_settings()

        # Allow bypass in development if configured
        if not payment_settings.webhook_ip_validation_enabled:
            logger.warning(
                "⚠️  Webhook IP validation DISABLED (development mode)",
                extra={
                    "endpoint": str(request.url),
                    "security_warning": "IP validation bypassed"
                }
            )
            return

        # Get client IP (handles proxies)
        client_ip = WebhookIPWhitelist._get_client_ip(request)

        # Build whitelist from configuration
        configured_ips = [
            ip.strip()
            for ip in payment_settings.lemonsqueezy_webhook_ips.split(",")
            if ip.strip()
        ]
        whitelist = configured_ips.copy()

        # Add development IPs if in development mode
        if settings.ENVIRONMENT in ["development", "local", "staging"]:
            whitelist.extend(WebhookIPWhitelist.DEVELOPMENT_IPS)
            logger.debug(
                "Development mode: Added development IPs to whitelist",
                extra={"environment": settings.ENVIRONMENT, "total_ips": len(whitelist)}
            )

        # Validate IP
        if not WebhookIPWhitelist.is_ip_in_whitelist(client_ip, whitelist):
            logger.warning(
                "🚨 Webhook request from UNAUTHORIZED IP",
                extra={
                    "client_ip": client_ip,
                    "endpoint": str(request.url),
                    "method": request.method,
                    "user_agent": request.headers.get("User-Agent"),
                    "x_forwarded_for": request.headers.get("X-Forwarded-For"),
                    "x_real_ip": request.headers.get("X-Real-IP"),
                    "security_event": "unauthorized_webhook_ip",
                    "severity": "high"
                }
            )

            # Return 403 Forbidden
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Webhook source IP not authorized"
            )

        # IP validation passed
        logger.info(
            "✓ Webhook IP validation passed",
            extra={
                "client_ip": client_ip,
                "endpoint": str(request.url),
                "security_check": "ip_whitelist_passed"
            }
        )


async def validate_lemonsqueezy_webhook_ip(request: Request):
    """
    FastAPI dependency for LemonSqueezy webhook IP validation.

    This dependency validates that incoming webhook requests originate from
    known LemonSqueezy IP addresses. This provides defense-in-depth alongside
    signature verification.

    Usage:
        @router.post(
            "/webhooks/lemonsqueezy",
            dependencies=[Depends(validate_lemonsqueezy_webhook_ip)]
        )
        async def handle_webhook(request: Request):
            # IP validation passed, now verify signature
            ...

    Security Architecture:
        Layer 1: IP Whitelist (this function) - Validates source IP
        Layer 2: Signature Verification (in route handler) - Validates HMAC

    Configuration:
        - WEBHOOK_IP_VALIDATION_ENABLED: Set to false to disable (dev only)
        - ENVIRONMENT: Determines if development IPs are allowed

    Raises:
        HTTPException: 403 if IP not in whitelist
    """
    WebhookIPWhitelist.validate_lemonsqueezy_ip(request)


# Convenience alias for other webhook providers (future use)
validate_webhook_ip = validate_lemonsqueezy_webhook_ip

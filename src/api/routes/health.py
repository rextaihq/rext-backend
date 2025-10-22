"""
Health Check Endpoints

Provides health check endpoints for monitoring system status,
including payment system health checks.

Phase 4, Task 4.2.5
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from typing import Dict, Any
import httpx
import time

from src.api.database.deps import get_db_dependency
from src.api.config import get_settings
from src.providers.payment.provider_factory import get_payment_provider_singleton

router = APIRouter(prefix="/health", tags=["health"])


@router.get("")
async def health_check():
    """
    Basic health check endpoint.

    Returns:
        200 OK if service is running
    """
    return {
        "status": "healthy",
        "service": "wrext-backend",
        "timestamp": time.time()
    }


@router.get("/payment")
async def payment_health_check(
    db: AsyncSession = Depends(get_db_dependency)
) -> Dict[str, Any]:
    """
    Comprehensive payment system health check (Phase 4, Task 4.2.5).

    Checks:
    - Database connectivity
    - LemonSqueezy API connectivity
    - Payment provider configuration

    Returns:
        Dict with health status for each component

    Example Response:
        {
            "status": "healthy",  # or "degraded" or "unhealthy"
            "timestamp": 1234567890.123,
            "checks": {
                "database": {"status": "healthy", "latency_ms": 12},
                "lemonsqueezy_api": {"status": "healthy", "latency_ms": 145},
                "payment_provider": {"status": "healthy", "configured": true}
            }
        }
    """
    settings = get_settings()
    checks = {}
    overall_status = "healthy"

    # Check 1: Database Connectivity
    try:
        start = time.time()
        await db.execute(text("SELECT 1"))
        latency_ms = int((time.time() - start) * 1000)

        checks["database"] = {
            "status": "healthy",
            "latency_ms": latency_ms
        }
    except Exception as e:
        checks["database"] = {
            "status": "unhealthy",
            "error": str(e)
        }
        overall_status = "unhealthy"

    # Check 2: LemonSqueezy API Connectivity
    try:
        if settings.LEMONSQUEEZY_API_KEY:
            start = time.time()

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    "https://api.lemonsqueezy.com/v1/stores",
                    headers={
                        "Authorization": f"Bearer {settings.LEMONSQUEEZY_API_KEY}",
                        "Accept": "application/vnd.api+json",
                    }
                )

            latency_ms = int((time.time() - start) * 1000)

            if response.status_code == 200:
                checks["lemonsqueezy_api"] = {
                    "status": "healthy",
                    "latency_ms": latency_ms,
                    "api_version": "v1"
                }
            else:
                checks["lemonsqueezy_api"] = {
                    "status": "degraded",
                    "status_code": response.status_code,
                    "latency_ms": latency_ms
                }
                overall_status = "degraded" if overall_status == "healthy" else overall_status
        else:
            checks["lemonsqueezy_api"] = {
                "status": "not_configured",
                "message": "API key not configured"
            }
            overall_status = "degraded" if overall_status == "healthy" else overall_status

    except httpx.TimeoutException:
        checks["lemonsqueezy_api"] = {
            "status": "unhealthy",
            "error": "Request timeout (> 10s)"
        }
        overall_status = "unhealthy"
    except Exception as e:
        checks["lemonsqueezy_api"] = {
            "status": "unhealthy",
            "error": str(e)
        }
        overall_status = "unhealthy"

    # Check 3: Payment Provider Configuration
    try:
        provider = get_payment_provider_singleton()

        if provider:
            checks["payment_provider"] = {
                "status": "healthy",
                "configured": True,
                "provider_type": "lemonsqueezy"
            }
        else:
            checks["payment_provider"] = {
                "status": "not_configured",
                "configured": False
            }
            overall_status = "degraded" if overall_status == "healthy" else overall_status

    except Exception as e:
        checks["payment_provider"] = {
            "status": "unhealthy",
            "error": str(e)
        }
        overall_status = "unhealthy"

    # Build response
    response = {
        "status": overall_status,
        "timestamp": time.time(),
        "checks": checks
    }

    # Return appropriate status code
    if overall_status == "healthy":
        return response
    elif overall_status == "degraded":
        # Still return 200 but indicate degraded state
        return response
    else:
        # Return 503 Service Unavailable for unhealthy
        raise HTTPException(status_code=503, detail=response)


@router.get("/payment/quick")
async def payment_quick_health_check() -> Dict[str, Any]:
    """
    Quick payment health check without external dependencies.

    Checks only configuration without making external calls.
    Useful for load balancer health checks.

    Returns:
        Dict with basic health status
    """
    settings = get_settings()

    # Check if payment system is configured
    is_configured = bool(
        settings.LEMONSQUEEZY_API_KEY and
        settings.LEMONSQUEEZY_STORE_ID
    )

    if is_configured:
        return {
            "status": "healthy",
            "configured": True,
            "timestamp": time.time()
        }
    else:
        return {
            "status": "not_configured",
            "configured": False,
            "timestamp": time.time()
        }

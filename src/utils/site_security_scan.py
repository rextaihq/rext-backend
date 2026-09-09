"""Lightweight site security-header and cookie-consent-platform detection.

Runs as part of workspace website analysis, alongside (not instead of) the
main Crawl4AI/Playwright scrape. This is a single plain HTTP GET used only to
inspect response headers and raw HTML for known CMP (Cookie Management
Platform) signatures — it doesn't render JS and isn't a content source.

Added specifically to make cookie-wall/bot-protection interference with
persona/brand-voice extraction diagnosable instead of silent: if
``cookie_consent.detected`` is True and personas come back empty for a
reported site, that's the first thing to check before assuming the extraction
prompt itself is at fault.
"""

from __future__ import annotations

from typing import Any, Dict

import httpx

from src.api.lib.logger import auto_logger

logger = auto_logger()

_SECURITY_HEADERS = (
    "content-security-policy",
    "strict-transport-security",
    "x-frame-options",
    "x-content-type-options",
    "referrer-policy",
    "permissions-policy",
    "x-xss-protection",
)

# platform name -> signature substrings to look for in raw HTML/script tags
_CMP_SIGNATURES: Dict[str, tuple[str, ...]] = {
    "OneTrust": ("cdn.cookielaw.org", "onetrust-consent-sdk", "optanon"),
    "Cookiebot": ("consent.cookiebot.com", "cookiebot"),
    "Osano": ("cmp.osano.com", "osano-cm"),
    "Didomi": ("sdk.privacy-center.org", "didomi"),
    "TrustArc": ("consent.trustarc.com", "trustarc"),
    "Quantcast Choice": ("quantcast.mgr.consensu.org", "__cmp", "__tcfapi"),
    "Cookie-Script": ("cdn.cookie-script.com",),
    "Termly": ("app.termly.io",),
    "Iubenda": ("cdn.iubenda.com",),
    "CookieYes": ("cdn-cookieyes.com", "cookieyes"),
    "Complianz": ("complianz",),
}

_GENERIC_CONSENT_PHRASES = (
    "cookie consent",
    "manage cookie preferences",
    "we use cookies",
    "manage your privacy choices",
)

_DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


async def analyze_site_security(url: str, *, timeout: float = 15.0) -> Dict[str, Any]:
    """Fetch ``url`` once and report security headers + cookie-consent platform.

    Best-effort and non-fatal: any failure (timeout, connection error, TLS
    issue, etc.) is caught and reported as an inconclusive result rather than
    raised, since this is a diagnostic addition to the onboarding pipeline,
    not a blocking requirement.
    """
    result: Dict[str, Any] = {
        "checked": False,
        "status_code": None,
        "security_headers": {},
        "missing_security_headers": [],
        "cookie_consent": {"detected": False, "platform": None},
        "error": None,
    }
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=timeout) as client:
            response = await client.get(url, headers={"User-Agent": _DEFAULT_USER_AGENT})

        result["checked"] = True
        result["status_code"] = response.status_code

        headers_lower = {k.lower(): v for k, v in response.headers.items()}
        result["security_headers"] = {
            header: headers_lower[header] for header in _SECURITY_HEADERS if header in headers_lower
        }
        result["missing_security_headers"] = [
            header for header in _SECURITY_HEADERS if header not in headers_lower
        ]

        # Cap how much HTML we scan — we're only looking for a CMP <script> tag
        # or a handful of stock consent-banner phrases, not parsing the page.
        haystack = (response.text or "")[:200_000].lower()

        detected_platform = None
        for platform, signatures in _CMP_SIGNATURES.items():
            if any(sig in haystack for sig in signatures):
                detected_platform = platform
                break

        if detected_platform:
            result["cookie_consent"] = {"detected": True, "platform": detected_platform}
        elif any(phrase in haystack for phrase in _GENERIC_CONSENT_PHRASES):
            # A consent banner exists but doesn't match a known vendor
            # signature (custom-built, or a vendor not in our list yet).
            result["cookie_consent"] = {"detected": True, "platform": "unknown"}

    except Exception as exc:  # noqa: BLE001 - diagnostic only, never fatal
        result["error"] = str(exc)
        logger.warning(
            "Site security/cookie-consent scan failed (non-fatal)",
            extra={"url": url, "error": str(exc)},
        )

    return result

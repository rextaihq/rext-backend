from typing import Any, Dict

import httpx

SECURITY_HEADERS = [
    "content-security-policy",
    "x-frame-options",
    "strict-transport-security",
    "x-content-type-options",
    "referrer-policy",
    "permissions-policy",
]

CONSENT_PROVIDERS = [
    "osano",
    "onetrust",
    "optanon",
    "cookiebot",
    "cookieyes",
    "didomi",
    "quantcast",
    "iubenda",
    "termly",
    "klaro",
    "complianz",
    "trustarc",
]

GENERIC_CONSENT_SIGNALS = [
    "cookie consent",
    "accept all cookies",
    "we use cookies",
    "cookie preferences",
    "manage cookies",
    "gdpr consent",
    "cookie-banner",
    "cookie_banner",
    "consent-banner",
    "consent_banner",
    "cookieconsent",
    "cc-window",
]


async def get_security_headers(url: str) -> Dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            response = await client.get(url)
        found = {h: response.headers.get(h) for h in SECURITY_HEADERS if h in response.headers}
        return {"checked": True, "headers_present": found}
    except httpx.HTTPError as exc:
        return {"checked": False, "error": str(exc)}


def detect_cookie_consent(raw_html: str) -> Dict[str, Any]:
    if not raw_html:
        return {"has_consent_banner": False, "provider": None, "detection_method": None}

    lowered = raw_html.lower()

    for provider in CONSENT_PROVIDERS:
        if provider in lowered:
            return {
                "has_consent_banner": True,
                "provider": provider,
                "detection_method": "known_provider",
            }

    for signal in GENERIC_CONSENT_SIGNALS:
        if signal in lowered:
            return {
                "has_consent_banner": True,
                "provider": "unknown",
                "detection_method": "generic_pattern",
            }

    return {"has_consent_banner": False, "provider": None, "detection_method": None}


async def assess_site_compliance(url: str, raw_html: str) -> Dict[str, Any]:
    headers = await get_security_headers(url)
    consent = detect_cookie_consent(raw_html)
    return {"security_headers": headers, "cookie_consent": consent}

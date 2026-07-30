import httpx
from typing import Any, Dict

SECURITY_HEADERS = [
    "content-security-policy",
    "x-frame-options",
    "strict-transport-security",
    "x-content-type-options",
    "referrer-policy",
    "permissions-policy",
]

CONSENT_PROVIDERS = [
    "osano", "onetrust", "cookiebot", "cookieyes", "didomi",
    "quantcast", "iubenda", "termly", "klaro", "complianz", "trustarc",
]


async def get_security_headers(url: str) -> Dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            response = await client.head(url)
        found = {h: response.headers.get(h) for h in SECURITY_HEADERS if h in response.headers}
        return {"checked": True, "headers_present": found}
    except httpx.HTTPError as exc:
        return {"checked": False, "error": str(exc)}


def detect_cookie_consent(raw_html: str) -> Dict[str, Any]:
    if not raw_html:
        return {"has_consent_banner": False, "provider": None}
    lowered = raw_html.lower()
    for provider in CONSENT_PROVIDERS:
        if provider in lowered:
            return {"has_consent_banner": True, "provider": provider}
    return {"has_consent_banner": False, "provider": None}


async def assess_site_compliance(url: str, raw_html: str) -> Dict[str, Any]:
    headers = await get_security_headers(url)
    consent = detect_cookie_consent(raw_html)
    return {"security_headers": headers, "cookie_consent": consent}
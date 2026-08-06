"""Root-domain helpers for grouping SERP result URLs by owning domain."""
import re
from urllib.parse import urlparse

import tldextract


def normalize_domain(domain: str) -> str:
    domain = domain.strip().lower()
    domain = re.sub(r"^https?://", "", domain)
    return domain.split("/")[0]


def get_root_domain(url_or_domain: str) -> str:
    """Return the registrable root domain (handles multi-part TLDs like .co.uk)."""
    ext = tldextract.extract(url_or_domain)
    if ext.domain and ext.suffix:
        return f"{ext.domain}.{ext.suffix}"
    netloc = urlparse(
        url_or_domain if "://" in url_or_domain else f"http://{url_or_domain}"
    ).netloc
    parts = netloc.split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else netloc

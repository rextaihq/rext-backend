"""Root-domain normalization and domain matching utilities."""

import re
import tldextract


def normalize_domain(url: str) -> str:
    ext = tldextract.extract(url)
    return ".".join(p for p in [ext.domain, ext.suffix] if p)


def is_same_brand_or_domain(candidate: str, self_url: str, company_name: str = "") -> bool:
    """Check if candidate is the same domain, a subdomain, a sibling TLD, or matches company brand.

    Examples:
    - candidate='revnix.net' and self_url='https://revnix.com' -> True (same SLD 'revnix')
    - candidate='www.revnix.net' and self_url='https://revnix.net' -> True
    - candidate='revnix.net' and company_name='Revnix' -> True
    - candidate='sanity.io' and self_url='https://nextlyhq.com' -> False
    """
    if not candidate:
        return False

    cand_norm = normalize_domain(candidate).lower()
    if not cand_norm:
        return False

    cand_ext = tldextract.extract(cand_norm)
    cand_sld = cand_ext.domain.lower() if cand_ext.domain else ""

    if self_url:
        self_norm = normalize_domain(self_url).lower()
        # Exact normalized domain match (e.g. revnix.net == revnix.net)
        if cand_norm == self_norm:
            return True

        self_ext = tldextract.extract(self_norm)
        self_sld = self_ext.domain.lower() if self_ext.domain else ""

        # Same second-level domain / brand root (e.g. revnix.net vs revnix.com)
        if self_sld and cand_sld and self_sld == cand_sld:
            return True

    # Company name match if available (e.g. company_name="Revnix", candidate="revnix.net")
    if company_name:
        company_slug = re.sub(r"[^a-z0-9]", "", company_name.lower())
        if len(company_slug) >= 3 and cand_sld == company_slug:
            return True

    return False


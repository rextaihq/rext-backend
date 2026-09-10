"""Root-domain normalization, ported verbatim from the reference Colab notebook."""

import tldextract


def normalize_domain(url: str) -> str:
    ext = tldextract.extract(url)
    return ".".join(p for p in [ext.domain, ext.suffix] if p)

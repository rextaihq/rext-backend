ugc_keywords = ["reddit.com", "quora.com", "stackexchange.com", "stackoverflow.com"]

DOMAIN_AUTHORITY_MAP = {
    "gov": 100,
    "edu": 90,
    "publisher": 80,
    "brand": 70,
    "ugc": 55,
    "other": 30,
}

def classify_domain_type(domain: str) -> str:
    domain = domain.lower()

    if domain.endswith(".gov") or ".gov." in domain:
        return "gov"
    if domain.endswith(".edu") or ".edu." in domain:
        return "edu"

    publisher_keywords = [
        "wikipedia", "forbes", "nytimes", "bbc", "cnn",
        "techcrunch", "medium", "investopedia", "coursera",
        "datacamp", "geeksforgeeks", "ibm", "sap", "mit",
    ]
    if any(p in domain for p in publisher_keywords):
        return "publisher"

    brand_keywords = ["google", "microsoft", "amazon", "ibm", "sap", "oracle"]
    if any(b in domain for b in brand_keywords):
        return "brand"

    if any(u in domain for u in ugc_keywords):
        return "ugc"

    return "other"

# Task 193: Fix SSRF Vulnerability in Web Scraping Function

## Metadata
- **Task ID:** TASK-193
- **Source:** Backend Knowledge Base (Finding #1 under P0 Critical)
- **Audit Report:** `audit-reports/backend-knowledge-base.md`
- **Priority:** P0 Critical
- **Category:** security
- **Effort Estimate:** medium (1-4 hours)

---

## Description

The `web_page_scraper()` function in `src/utils/helper.py` (lines 184-227) accepts arbitrary URLs from users and passes them directly to the `crawl4ai` `AsyncWebCrawler` without any validation of the target address. This creates a Server-Side Request Forgery (SSRF) vulnerability classified as CWE-918. An authenticated user can supply a URL pointing to internal network resources — including private IP ranges (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`), localhost (`127.0.0.1`, `::1`), and cloud metadata endpoints (`169.254.169.254` for AWS/GCP/Azure) — causing the server to make requests on behalf of the attacker.

While the route layer uses Pydantic's `HttpUrl` type for basic URL format validation (see `workspace_knowledge.py:23`), this only verifies that the URL has a valid HTTP/HTTPS scheme and syntactically correct hostname — it does **not** validate the resolved IP address against blocked ranges. The `crawl4ai` library (version >=0.7.2 per `pyproject.toml`) does not provide built-in SSRF protection; it launches a Chromium browser that will happily navigate to any reachable address including internal services.

The function is called from 4 different locations in the codebase: `knowledge_service.py:511`, `workspace_pipeline.py:507`, `workspace_service.py:1042`, and imported (though potentially unused) in `members_routes.py:17`. Each of these call sites represents an attack surface. According to the OWASP SSRF Prevention Cheat Sheet, the recommended approach for applications that must accept external URLs is a blocklist of private IP ranges combined with DNS resolution validation to prevent DNS rebinding attacks.

---

## Current Code

```python
# File: rext-backend/src/utils/helper.py
# Lines: 184-227
async def web_page_scraper(urls: List[HttpUrl]) -> Tuple[List[Document], list]:
    """
    Asynchronously crawls given URLs and returns LangChain Documents with extracted content.

    Args:
        urls (List[HttpUrl]): List of URLs to crawl.

    Returns:
        Tuple[List[Document], list]: (Chunked Documents, Raw crawl results)
    """

    logger.info("Scrapping States")
    browser_config = GetBrowserConfig()
    run_config = GetCrawlerRunConfig()

    # if len(url)
    urls = [str(url) for url in urls]
    async with AsyncWebCrawler(config=browser_config) as crawler:
        results = await crawler.arun(url=urls[0], config=run_config)
    logger.info("DOne")
    documents = []
    for result in results:
        if result.success:
            doc = Document(
                page_content=result.markdown,
                metadata={
                    "id": str(uuid.uuid4()),
                    "url": result.url,
                    "title": result.metadata.get("title", "No title found"),
                    "description": result.metadata.get("description", "No description found"),
                    "keywords": result.metadata.get("keywords", "No keywords found"),
                    "summary": result.metadata.get("summary", "No summary found"),
                }
            )
            documents.append(doc)
        else:
            logger.info(f"Scraping failed for {result.url}: {result.error_message}")

    chunks_data = split_data(documents)

    return chunks_data, results
```

---

## Why This Matters (Context & Reasoning)

The web scraping feature is a core part of the Knowledge Base module. Users provide URLs to scrape content from public websites, which is then chunked, embedded, and stored in the vector store for RAG (Retrieval-Augmented Generation). This is a user-facing feature exposed via the `POST /workspaces/{workspace_id}/knowledge/web` endpoint, meaning any authenticated user with `knowledge.create` permission can trigger URL fetching.

Without SSRF protection, an attacker can:
- **Access cloud metadata endpoints** (e.g., `http://169.254.169.254/latest/meta-data/iam/security-credentials/`) to steal IAM role credentials, potentially gaining full access to the cloud account.
- **Probe internal services** on private networks to discover running services, open ports, and internal API endpoints.
- **Access internal APIs** that are not exposed to the internet but are accessible from the server's network.
- **Cause denial of service** by directing requests to internal services that cannot handle the load.

This is one of the most severe vulnerabilities in the codebase because it can lead to full cloud account compromise in a single request.

---

## Impact

- **Severity:** Full cloud account compromise possible via metadata endpoint access. Internal network reconnaissance and data exfiltration. Potential lateral movement within the infrastructure.
- **Affected Users/Flows:** Any authenticated user with `knowledge.create` permission in any workspace can exploit this via the web knowledge creation endpoint.
- **Blast Radius:** Affects the entire cloud infrastructure. The vulnerability exists in a shared utility function called from 4 different code paths, meaning all web scraping flows are vulnerable.

---

## Recommended Solution

### Step 1: Create a URL Validator Utility

```python
# File: rext-backend/src/utils/url_validator.py
"""
SSRF Prevention Utility

Validates URLs before server-side requests to prevent Server-Side Request Forgery.
Implements OWASP SSRF Prevention Cheat Sheet recommendations.

Reference: https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html
"""

import ipaddress
import socket
from urllib.parse import urlparse
from typing import Optional

from src.utils.logger import logger


# Private and reserved IP ranges that must be blocked
BLOCKED_IP_NETWORKS = [
    # Loopback
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
    # Private networks (RFC 1918)
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    # Link-local / Cloud metadata (AWS, GCP, Azure)
    ipaddress.ip_network("169.254.0.0/16"),
    # IPv6 link-local
    ipaddress.ip_network("fe80::/10"),
    # IPv6 unique local
    ipaddress.ip_network("fc00::/7"),
    # Multicast
    ipaddress.ip_network("224.0.0.0/4"),
    ipaddress.ip_network("ff00::/8"),
    # Reserved for documentation
    ipaddress.ip_network("192.0.2.0/24"),
    ipaddress.ip_network("198.51.100.0/24"),
    ipaddress.ip_network("203.0.113.0/24"),
    # Broadcast
    ipaddress.ip_network("255.255.255.255/32"),
]

# Allowed URL schemes
ALLOWED_SCHEMES = {"http", "https"}

# Maximum URL length to prevent abuse
MAX_URL_LENGTH = 2048


class SSRFValidationError(ValueError):
    """Raised when a URL fails SSRF validation."""
    pass


def validate_url_for_ssrf(url: str) -> str:
    """
    Validate a URL to prevent SSRF attacks.

    Performs the following checks:
    1. URL length limit
    2. Scheme allowlist (http/https only)
    3. Hostname presence and format
    4. DNS resolution to get actual IP addresses
    5. IP address validation against blocked ranges

    Args:
        url: The URL to validate.

    Returns:
        The validated URL string (unchanged).

    Raises:
        SSRFValidationError: If the URL fails any validation check.
    """
    if len(url) > MAX_URL_LENGTH:
        raise SSRFValidationError(f"URL exceeds maximum length of {MAX_URL_LENGTH} characters")

    parsed = urlparse(url)

    # Check scheme
    if parsed.scheme not in ALLOWED_SCHEMES:
        raise SSRFValidationError(f"URL scheme '{parsed.scheme}' is not allowed. Only {ALLOWED_SCHEMES} are permitted.")

    # Check hostname exists
    hostname = parsed.hostname
    if not hostname:
        raise SSRFValidationError("URL must contain a valid hostname")

    # Check for IP address directly in URL
    try:
        ip = ipaddress.ip_address(hostname)
        _check_ip_blocked(ip)
        return url
    except ValueError:
        # Not a raw IP address — it's a hostname, resolve it
        pass

    # Resolve hostname to IP addresses and validate each one
    resolved_ips = _resolve_hostname(hostname)
    if not resolved_ips:
        raise SSRFValidationError(f"Could not resolve hostname: {hostname}")

    for ip_str in resolved_ips:
        try:
            ip = ipaddress.ip_address(ip_str)
            _check_ip_blocked(ip)
        except ValueError:
            raise SSRFValidationError(f"Invalid IP address from DNS resolution: {ip_str}")

    logger.info(
        "URL passed SSRF validation",
        extra={"url_host": hostname, "resolved_ips": resolved_ips},
    )
    return url


def _check_ip_blocked(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> None:
    """
    Check if an IP address falls within any blocked network range.

    Args:
        ip: The IP address to check.

    Raises:
        SSRFValidationError: If the IP is in a blocked range.
    """
    if ip.is_private or ip.is_reserved or ip.is_loopback or ip.is_link_local or ip.is_multicast:
        raise SSRFValidationError(
            f"URL resolves to blocked IP address: {ip} "
            f"(private={ip.is_private}, reserved={ip.is_reserved}, "
            f"loopback={ip.is_loopback}, link_local={ip.is_link_local})"
        )

    for network in BLOCKED_IP_NETWORKS:
        if ip in network:
            raise SSRFValidationError(
                f"URL resolves to blocked IP range {network}: {ip}"
            )


def _resolve_hostname(hostname: str) -> list[str]:
    """
    Resolve a hostname to its IP addresses using DNS.

    Uses socket.getaddrinfo for both IPv4 and IPv6 resolution.

    Args:
        hostname: The hostname to resolve.

    Returns:
        List of resolved IP address strings.
    """
    try:
        addr_info = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
        ips = list({info[4][0] for info in addr_info})
        return ips
    except socket.gaierror as e:
        logger.warning(f"DNS resolution failed for {hostname}: {e}")
        return []
```

### Step 2: Integrate Validation into `web_page_scraper()`

```python
# File: rext-backend/src/utils/helper.py
# Add import at the top of the file (after existing imports):
from src.utils.url_validator import validate_url_for_ssrf, SSRFValidationError

# Replace the web_page_scraper function (lines 184-227) with:
async def web_page_scraper(urls: List[HttpUrl]) -> Tuple[List[Document], list]:
    """
    Asynchronously crawls given URLs and returns LangChain Documents with extracted content.

    Args:
        urls (List[HttpUrl]): List of URLs to crawl.

    Returns:
        Tuple[List[Document], list]: (Chunked Documents, Raw crawl results)

    Raises:
        SSRFValidationError: If any URL fails SSRF validation.
    """
    logger.info("Scraping started")
    browser_config = GetBrowserConfig()
    run_config = GetCrawlerRunConfig()

    # Validate all URLs for SSRF before scraping
    validated_urls = []
    for url in urls:
        url_str = str(url)
        validate_url_for_ssrf(url_str)
        validated_urls.append(url_str)

    async with AsyncWebCrawler(config=browser_config) as crawler:
        results = await crawler.arun(url=validated_urls[0], config=run_config)
    logger.info("Scraping completed")

    documents = []
    for result in results:
        if result.success:
            doc = Document(
                page_content=result.markdown,
                metadata={
                    "id": str(uuid.uuid4()),
                    "url": result.url,
                    "title": result.metadata.get("title", "No title found"),
                    "description": result.metadata.get("description", "No description found"),
                    "keywords": result.metadata.get("keywords", "No keywords found"),
                    "summary": result.metadata.get("summary", "No summary found"),
                }
            )
            documents.append(doc)
        else:
            logger.warning(f"Scraping failed for {result.url}: {result.error_message}")

    chunks_data = split_data(documents)

    return chunks_data, results
```

### Step 3: Handle SSRFValidationError in Route Layer

```python
# File: rext-backend/src/api/routes/workspaces/workspace_knowledge.py
# Add import at the top (after existing imports):
from src.utils.url_validator import SSRFValidationError

# The existing try/except block in create_web_knowledge (line 169-208) will
# catch SSRFValidationError since it inherits from ValueError, but for
# clearer error messages, add an explicit handler before the generic Exception handler.
# Insert before line 197 ("except Exception as e:"):

    except SSRFValidationError as e:
        raise RextValidationException(
            message="The provided URL is not allowed",
            field_errors={"url": [str(e)]}
        )
```

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `rext-backend/src/services/knowledge_service.py` | `511` | Calls `web_page_scraper(urls=[url])` — protected by the fix since it goes through the same function |
| `rext-backend/src/services/workspace_pipeline.py` | `507` | Calls `web_page_scraper(urls=[url])` — protected by the fix |
| `rext-backend/src/services/workspace_service.py` | `1042` | Calls `web_page_scraper(urls=[url])` — protected by the fix |
| `rext-backend/src/api/routes/workspaces/members/members_routes.py` | `17` | Imports `web_page_scraper` — verify if actually used or can be removed |
| `rext-backend/src/api/tasks/knowledge_task.py` | `30` | Calls `web_page_scraper(url)` directly — protected by the fix |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Start the backend server locally
2. Create a workspace and obtain an auth token
3. Send a POST request to create web knowledge with an internal URL:
   ```bash
   curl -X POST "http://localhost:8000/api/workspaces/<workspace_id>/knowledge/web" \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json" \
     -d '{"url": "http://169.254.169.254/latest/meta-data/"}'
   ```
4. Observe that the server attempts to fetch the URL (or returns a scraping failure but still makes the request)

### After Fix (Verify the Solution):
1. Repeat the same request — should return a 422 validation error: `"The provided URL is not allowed"`
2. Test with other blocked addresses:
   ```bash
   # Localhost
   curl -X POST ... -d '{"url": "http://127.0.0.1:8080/"}'
   # Private network
   curl -X POST ... -d '{"url": "http://10.0.0.1/"}'
   # IPv6 loopback
   curl -X POST ... -d '{"url": "http://[::1]/"}'
   ```
3. All should return validation errors
4. Test with a valid public URL:
   ```bash
   curl -X POST ... -d '{"url": "https://example.com"}'
   ```
5. Should succeed and return scraped content

### Run Existing Tests:
```bash
cd rext-backend
python -m pytest tests/ -v -k "knowledge" --no-header
```

---

## Acceptance Criteria

- [ ] `validate_url_for_ssrf()` function blocks all private IP ranges (127.0.0.0/8, 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16)
- [ ] Cloud metadata endpoint (169.254.169.254) is blocked
- [ ] IPv6 loopback (::1) and link-local (fe80::/10) addresses are blocked
- [ ] DNS resolution is performed and resolved IPs are validated against blocklist
- [ ] Valid public URLs continue to work without errors
- [ ] SSRFValidationError returns a user-friendly 422 error response
- [ ] All 4 call sites of `web_page_scraper()` are protected (since fix is in the function itself)
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [OWASP SSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html)
- **Security Advisory:** [CWE-918: Server-Side Request Forgery](https://cwe.mitre.org/data/definitions/918.html)
- **Migration Guide:** N/A
- **Best Practice Reference:** [Python ipaddress module documentation](https://docs.python.org/3/library/ipaddress.html)
- **Related Issues/PRs:** [OWASP SSRF Bible (PDF)](https://cheatsheetseries.owasp.org/assets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet_SSRF_Bible.pdf)

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-089 (B4 — Integration Credentials Stored in Plaintext), TASK-029 (B2 — WorkspaceIntegration.to_dict() Leaks Credentials)

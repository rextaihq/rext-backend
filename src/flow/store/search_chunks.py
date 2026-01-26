# ----------------------------
# Async search function
# ----------------------------
import asyncio
from typing import Dict
from urllib.parse import urlparse
from src.flow.store.postgress_store import create_long_term_store  # correct async store import

# -------------------------
# Helper function
# -------------------------
def extract_internal_links(meta: dict) -> set[str]:
    """
    Extract internal links from page metadata
    """
    internal_links = set()
    domain = meta.get("domain")
    if not domain:
        return internal_links

    for link in meta.get("links_detail", []):
        href = link.get("href")
        if not href:
            continue
        parsed = urlparse(href)
        if parsed.netloc == domain:
            internal_links.add(href)

    return internal_links

# -------------------------
# Async search function
# -------------------------
async def search_scraped_chunks(
    user_id: str,
    workspace_id: str,
    query: str,
    limit: int = 5
) -> Dict:
    """
    Async search stored scraped chunks
    """
    namespace = ("scraped_chunks", user_id, workspace_id)

    async with create_long_term_store() as store:
        # Optional setup
        await store.setup()

        results = await store.asearch(
            namespace,
            query=query,
            limit=limit
        )

    all_texts = []
    main_urls = set()
    internal_links = set()

    for r in results:
        value = r.value
        meta = value.get("metadata", {})

        all_texts.append(value.get("text", ""))
        page_url = meta.get("url")
        if page_url:
            main_urls.add(page_url)
        internal_links.update(extract_internal_links(meta))

    return {
        "text": " ".join(all_texts).strip(),
        "metadata": {
            "main_urls": list(main_urls),
            "internal_links": list(internal_links),
        },
    }

# -------------------------
# Run standalone
# -------------------------
if __name__ == "__main__":
    result = asyncio.run(search_scraped_chunks(
        "user1",
        "workspace1",
        "wordpress help and support",
        limit=5
    ))
    print(result)

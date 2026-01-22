# from typing import List, Dict
# from langchain_core.documents import Document
# from src.flow.store.postgress_store import create_long_term_store

# def search_scraped_chunks(user_id: str, workspace_id: str, query: str, limit: int = 5) -> Dict:
#     """
#     Search stored scraped chunks for a user + workspace.

#     Returns a dict:
#         {
#             "text": "concatenated text of all relevant chunks",
#             "metadata": {
#                 "main_urls": [...],
#                 "internal_urls": [...],
#                 "external_urls": [...]
#             }
#         }
#     """
#     namespace = ("scraped_chunks", user_id, workspace_id)

#     with create_long_term_store() as store:
#         # Perform semantic search
#         results = store.search(namespace, query=query, limit=limit)

#     # Initialize aggregation
#     all_texts = []
#     main_urls = set()
#     other_urls = set()

#     for r in results:
#         value = r.value
#         meta = value.get("metadata", {})

#         all_texts.append(value.get("text", ""))

#         url = meta.get("url")
#         if url:
#             main_urls.add(url)

#     return {
#         "text": " ".join(all_texts).strip(),
#         "metadata": {
#             "main_urls": list(main_urls),
#             "other_urls": list(other_urls),
#         }
#     }


# if __name__ == "__main__":
#     user_id = "test-user-123"
#     workspace_id = "test-workspace-456"
#     query = "wordpress support and maintenance"
#     limit = 5

#     result = search_scraped_chunks(user_id, workspace_id, query, limit)
#     print(result)
from typing import Dict
from urllib.parse import urlparse
from src.flow.store.postgress_store import create_long_term_store


def extract_internal_links(meta: dict) -> set[str]:
    """
    Extract internal hrefs from metadata.links_detail
    """
    other_urls = set()
    domain = meta.get("domain")

    if not domain:
        return other_urls

    for link in meta.get("links_detail", []):
        href = link.get("href")
        if not href:
            continue

        parsed = urlparse(href)

        # Absolute internal links only
        if parsed.netloc == domain:
            other_urls.add(href)

    return other_urls


def search_scraped_chunks(
    user_id: str,
    workspace_id: str,
    query: str,
    limit: int = 5
) -> Dict:
    """
    Search stored scraped chunks for a user + workspace.

    Returns:
        {
            "text": "...",
            "metadata": {
                "main_urls": [...],
                "internal_urls": [...]
            }
        }
    """
    namespace = ("scraped_chunks", user_id, workspace_id)

    with create_long_term_store() as store:
        results = store.search(namespace, query=query, limit=limit)

    all_texts = []
    main_urls = set()
    other_urls = set()

    for r in results:
        value = r.value
        meta = value.get("metadata", {})

        # Collect text
        all_texts.append(value.get("text", ""))

        # Main page URL
        page_url = meta.get("url")
        if page_url:
            main_urls.add(page_url)

        # 🔥 Internal hrefs
        other_urls.update(extract_internal_links(meta))

    return {
        "text": " ".join(all_texts).strip(),
        "metadata": {
            "main_urls": list(main_urls),
            "other_urls": list(other_urls),
        },
    }


if __name__ == "__main__":
    user_id = "test-user-123"
    workspace_id = "test-workspace-456"
    query = "wordpress support and maintenance"

    result = search_scraped_chunks(user_id, workspace_id, query, limit=5)
    print(result)

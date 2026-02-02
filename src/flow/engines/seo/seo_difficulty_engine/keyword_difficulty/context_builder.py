from .models.context import CompetitorContext

def build_competitor_context(keyword, intent, comp, rext_data):
    serp_normalized = rext_data["serp_normalized"]
    serp_results = serp_normalized.get("normalize_results", [])

    serp_entry = next(
        (r for r in serp_results if r["domain"] == comp["domain"]),
        {}
    )

    scrape_doc = None
    for doc in rext_data.get("scrape_context", {}).get("documents", []):
        if doc["document"].metadata.get("domain") == comp["domain"]:
            scrape_doc = doc
            break

    return CompetitorContext(
        keyword=keyword,
        intent=intent,
        competitor=comp,
        serp_entry=serp_entry,
        serp_results=serp_results,
        serp_normalized=serp_normalized,
        competitors=rext_data["competitors"],
        scrape_doc=scrape_doc,
    )

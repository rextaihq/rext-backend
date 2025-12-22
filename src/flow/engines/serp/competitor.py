import re
import logging
from urllib.parse import urlparse
from collections import Counter
from typing import List, Dict, Any
from src.flow.states.wrext import WREXT, Competitor

logger = logging.getLogger(__name__)

def extract_competitors_from_serp(state: WREXT) -> Dict[str, Any]:
    """
    Extract competitor information from SERP results by grouping data by domain.

    Args:
        state (WREXT): The current state containing the raw serp_result.

    Returns:
        Dict[str, Any]: A dictionary containing the list of extracted competitors.
    """
    logger.info("Starting competitor extraction from SERP")
    serp_result = state.get("serp_result", {})
    organic = serp_result.get("organic_results", [])

    domain_groups = {}

    for item in organic:
        url = item.get("link", "")
        domain = urlparse(url).netloc.replace("www.", "")
        if not domain:
            continue

        if domain not in domain_groups:
            domain_groups[domain] = {
                "top_positions": [],
                "total_occurrences": 0,
                "has_sitelinks": False,
                "intent_distribution": {"informational": 0, "commercial": 0},
                "freshness": {"recent": 0, "older": 0},
                "avg_snippet_length": 0.0,
                "featured_snippet": False
            }

        group = domain_groups[domain]
        group["top_positions"].append(item.get("position", 0))
        group["total_occurrences"] += 1
        if item.get("sitelinks"):
            group["has_sitelinks"] = True

        # Snippet length
        snippet = item.get("snippet", "")
        group["avg_snippet_length"] += len(snippet)

        # Freshness
        date = item.get("date")
        if date:
            match = re.search(r"\b(20\d{2})\b", date)
            if match:
                year = match.group(1)
                if year.isdigit() and int(year) >= 2024:  # consider recent
                    group["freshness"]["recent"] += 1
                else:
                    group["freshness"]["older"] += 1
            else:
                group["freshness"]["older"] += 1
        else:
            group["freshness"]["older"] += 1

        # Featured snippet (position 1)
        if item.get("position") == 1:
            group["featured_snippet"] = True

    competitors: List[Competitor] = []

    for domain, data in domain_groups.items():
        total_snippets = data["total_occurrences"]
        data["avg_snippet_length"] = data["avg_snippet_length"] / total_snippets if total_snippets else 0.0
        competitors.append(
            Competitor(
                domain=domain,
                top_positions=data["top_positions"],
                total_occurrences=data["total_occurrences"],
                has_sitelinks=data["has_sitelinks"],
                intent_distribution=data["intent_distribution"],
                freshness=data["freshness"],
                avg_snippet_length=data["avg_snippet_length"],
                featured_snippet=data["featured_snippet"]
            )
        )

    # Sort competitors by top position (optional)
    competitors.sort(key=lambda x: min(x["top_positions"]))
    
    logger.info(f"Extracted {len(competitors)} competitors from SERP")
    return {
        "competitors": competitors
    }
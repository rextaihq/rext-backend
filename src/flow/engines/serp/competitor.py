import re
import logging
from urllib.parse import urlparse
from collections import Counter
from typing import List, Dict, Any
from src.flow.states.rext import REXT, Competitor
from datetime import datetime, timezone
from src.flow.model.llm_manager import load_model
from src.flow.prompts.system.intent import SEO_INTENT_SYSTEM_PROMPT
from src.flow.model.structure.intent import BatchSEOIntentOutput
from langchain.messages import SystemMessage,HumanMessage

logger = logging.getLogger(__name__)

async def extract_competitors_from_serp(state: REXT) -> Dict[str, Any]:
    """
    Extract competitor information from SERP results by grouping data by domain.

    Args:
        state (REXT): The current state containing the raw serp_result.

    Returns:
        Dict[str, Any]: A dictionary containing the list of extracted competitors.
    """
    logger.info("Starting competitor extraction from SERP")
    serp_result = state.get("serp_result", {})
    organic = serp_result.get("organic_results", [])
    query = state.get("serp_payload", {}).get("query", "")
    
    # We'll initialize the model later with batch output structure

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
                # "has_sitelinks": False,
                "intent_distribution": {
                    "INFORMATIONAL": 0, 
                    "COMMERCIAL": 0,
                    "NAVIGATIONAL": 0,
                    "TRANSACTIONAL": 0
                },
                "freshness": {"recent": 0, "older": 0},
                "avg_snippet_length": 0.0,
                "featured_snippet": False,
                "is_brand": False,
                "top_result": item # Store top result for classification
            }

        group = domain_groups[domain]
        group["top_positions"].append(item.get("position", 0))
        group["total_occurrences"] += 1
        
        # Update top result if this one is higher
        if item.get("position", 999) < group["top_result"].get("position", 999):
            group["top_result"] = item


        # Snippet length
        snippet = item.get("snippet", "")
        group["avg_snippet_length"] += len(snippet) if snippet else 0

        # Freshness
        date = item.get("date")
        if date:
            match = re.search(r"\b(20\d{2})\b", date)
            if match:
                year = match.group(1)
                if year.isdigit() and int(year) >= datetime.now(timezone.utc).year - 2:  # consider recent
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

    # Collect all competitor data for batch processing
    competitor_data_list = []
    for domain, data in domain_groups.items():
        top_item = data["top_result"]
        competitor_data_list.append({
            "domain": domain,
            "title": top_item.get("title", ""),
            "snippet": top_item.get("snippet", "")
        })

    final_intent_type = "UNKNOWN"

    if competitor_data_list:
        try:
            batch_model = load_model().with_structured_output(BatchSEOIntentOutput)
            human_content = f"Query: {query}\n\nClassify the following competitors:\n"
            for i, comp in enumerate(competitor_data_list):
                human_content += f"--- Competitor {i+1} ---\nDomain: {comp['domain']}\nTitle: {comp['title']}\nSnippet: {comp['snippet']}\n\n"

            classification_results = await batch_model.ainvoke([
                SystemMessage(content=SEO_INTENT_SYSTEM_PROMPT + f"\nClassify each competitor in the list provided and also return the primary intent of the keyword. here is keyword: {query}"),
                HumanMessage(content=human_content)
            ])

            final_intent_type = classification_results.final_intent_type

            # Map results back to domain_groups
            results_map = {res.domain: res for res in classification_results.results}
            for domain, data in domain_groups.items():
                res = results_map.get(domain)
                if res:
                    intent = res.intent.upper()
                    if intent in data["intent_distribution"]:
                        data["intent_distribution"][intent] = 1
                    data["is_brand"] = res.is_brand
                else:
                    logger.warning(f"No classification result found for domain: {domain}")
        except Exception as e:
            logger.error(f"Error in batch classification: {e}")
    
    


    else:
        # ── Branch 2: no competitors — derive intent from query alone ──
        try:
            batch_model = load_model().with_structured_output(BatchSEOIntentOutput)
            classification_results = await batch_model.ainvoke([
                SystemMessage(
                    content=(
                        SEO_INTENT_SYSTEM_PROMPT
                        + f"\nNo competitor data is available. Your only task is to "
                        f"determine the primary search intent for the keyword. "
                        f"Return an empty results list and populate "
                        f"final_intent_type only. Keyword: {query}"
                    )
                ),
                HumanMessage(
                    content=(
                        f"Query: {query}\n\n"
                        f"No SERP competitors were found. "
                        f"Based on the query alone, classify its primary intent "
                        f"and return an empty results list."
                    )
                ),
            ])
            final_intent_type = classification_results.final_intent_type
            logger.info(
                f"Intent derived from query only (no competitors): {final_intent_type}"
            )
        except Exception as e:
            logger.error(f"Error in query-only intent classification: {e}")


    competitors: List[Competitor] = []
    for domain, data in domain_groups.items():
        total_snippets = data["total_occurrences"]
        data["avg_snippet_length"] = data["avg_snippet_length"] / total_snippets if total_snippets else 0.0
        
        competitors.append(
            Competitor(
                domain=domain,
                top_positions=data["top_positions"],
                total_occurrences=data["total_occurrences"],
                # has_sitelinks=data["has_sitelinks"],
                intent_distribution=data["intent_distribution"],
                freshness=data["freshness"],
                avg_snippet_length=data["avg_snippet_length"],
                featured_snippet=data["featured_snippet"],
                is_brand=data["is_brand"]
            )
        )

    # Sort competitors by top position (optional)
    competitors.sort(key=lambda x: min(x["top_positions"]))
    
    logger.info(f"Extracted {len(competitors)} competitors from SERP")
    
    return {
       "competitors": competitors,
       "seo_result":{
        "intent_type":final_intent_type
       }
    }
import logging
from typing import List, Dict, Any, Optional
from src.flow.states.rext import Competitor

logger = logging.getLogger(__name__)

def get_consensus_intent(
    api_intent: str, 
    competitors: List[Competitor], 
    threshold: float = 0.6
) -> str:
    """
    Determine the real search intent by looking at both the API-provided intent
    and the LLM-classified intents of the top SERP competitors.
    
    Args:
        api_intent: The primary intent from a tool like DataForSEO.
        competitors: List of competitor analytics including intent_distribution.
        threshold: The dominance threshold for consensus (default 60%).
        
    Returns:
        str: The most reliable search intent (informational, commercial, etc.)
    """
    if not competitors:
        return api_intent or "informational"
        
    intent_counts = {}
    total_samples = 0
    
    for comp in competitors:
        dist = comp.get("intent_distribution", {})
        # We assume each competitor has exactly one the strongest intent (marked as 1)
        for intent_name, value in dist.items():
            if value > 0:
                name = intent_name.lower()
                intent_counts[name] = intent_counts.get(name, 0) + 1
                total_samples += 1
                
    if total_samples == 0:
        return api_intent or "informational"
        
    # Find the most frequent intent among competitors
    sorted_intents = sorted(intent_counts.items(), key=lambda x: x[1], reverse=True)
    top_intent, count = sorted_intents[0]
    
    # If a single intent dominates (>60% by default), override the API value
    if count / total_samples >= threshold:
        logger.info(f"Consensus intent reached: {top_intent.upper()} ({count}/{total_samples})")
        return top_intent
        
    # Fallback to API intent if no consensus
    logger.info(f"No clear consensus, using API intent: {api_intent}")
    return api_intent or "informational"
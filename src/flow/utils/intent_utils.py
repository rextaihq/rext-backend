import logging
from typing import List, Dict, Any, Optional
from src.flow.states.rext import Competitor

logger = logging.getLogger(__name__)

def get_consensus_intent(
    api_intent: str, 
    competitors: List[Competitor], 
    threshold: float = 0.51  # ✅ Lowered to majority (51%) instead of 60%
) -> str:
    if not competitors:
        return api_intent or "informational"
        
    intent_counts = {}
    total_samples = 0
    
    for comp in competitors:
        dist = comp.get("intent_distribution", {})
        # Find the winner for this specific competitor
        max_val = 0
        winner = None
        for i_name, val in dist.items():
            if val > max_val:
                max_val = val
                winner = i_name.lower()
        
        if winner:
            intent_counts[winner] = intent_counts.get(winner, 0) + 1
            total_samples += 1
                
    if total_samples == 0:
        return api_intent or "informational"
        
    # Sort byproduct counts
    sorted_intents = sorted(intent_counts.items(), key=lambda x: x[1], reverse=True)
    top_intent, count = sorted_intents[0]
    
    api_intent_lower = (api_intent or "unknown").lower()
    
    # 🔴 LOGIC REFINEMENT:
    # 1. If majority (51%+) detected, trust the competitors.
    # 2. If API says 'unknown', trust the plurality winner (top_intent).
    # 3. If API intent is NOT present at all in top competitors, trust plurality.
    
    is_majority = (count / total_samples) >= threshold
    api_has_support = intent_counts.get(api_intent_lower, 0) > 0
    
    if is_majority or api_intent_lower == "unknown" or not api_has_support:
        if api_intent_lower != top_intent:
            logger.info(f"Conflict Override: API says '{api_intent}', but {count}/{total_samples} competitors say '{top_intent.upper()}'. Using consensus.")
        return top_intent
        
    return api_intent

import logging
from typing import List, Dict, Any, Optional
from src.flow.states.rext import Competitor
from src.flow.model.llm_manager import load_model
from src.flow.model.structure.intent import KeywordIntentResponse
from src.flow.prompts.human.intent import get_intent_prompt

logger = logging.getLogger(__name__)

def get_consensus_intent(
    api_intent: str, 
    competitors: List[Competitor], 
    threshold: float = 0.6
) -> tuple[str, float]:
    """
    Determine the real search intent using a weighted consensus model.
    Weights are assigned based on the SERP position of competitors:
    - Positions 1-3: 3x weight
    - Positions 4-6: 2x weight
    - Positions 7-10: 1x weight
    
    Args:
        api_intent: The primary intent from DataForSEO.
        competitors: List of competitor analytics including intent_distribution and top_positions.
        threshold: The dominance threshold for consensus (default 60%).
    """
    if not competitors:
        return (api_intent or "unknown"), 0.0
        
    weighted_counts = {}
    total_weighted_samples = 0
    
    for comp in competitors:
        dist = comp.get("intent_distribution", {})
        top_pos = min(comp.get("top_positions", [999]))
        
        # Determine weight based on position
        if top_pos <= 3:
            weight = 3
        elif top_pos <= 6:
            weight = 2
        else:
            weight = 1
            
        # We assume each competitor has exactly one the strongest intent (value 1)
        for intent_name, value in dist.items():
            if value > 0:
                name = (intent_name or "unknown").lower()
                weighted_counts[name] = weighted_counts.get(name, 0) + weight
                total_weighted_samples += weight
                
    if not weighted_counts or total_weighted_samples == 0:
        return (api_intent or "unknown"), 0.0
        
    # Find the most frequent weighted intent
    sorted_intents = sorted(weighted_counts.items(), key=lambda x: x[1], reverse=True)
    top_intent, weighted_count = sorted_intents[0]
    
    # Check weighted confidence
    confidence = weighted_count / total_weighted_samples
        
    return top_intent, confidence

async def calculate_intent_with_llm(
    query: str, 
    organic_results: List[Dict[str, Any]]
) -> KeywordIntentResponse:
    """
    Calculate keyword intent using LLM based on top SERP results.
    """
    try:
        # Format SERP data for the prompt
        serp_items = []
        for i, res in enumerate(organic_results[:5], 1):
            title = res.get("title", "No Title")
            snippet = res.get("snippet", "No Snippet")
            serp_items.append(f"{i}. Title: {title}\n   Snippet: {snippet}")
        
        serp_data = "\n\n".join(serp_items)
        
        # Load model and prepare messages
        model = load_model().with_structured_output(KeywordIntentResponse)
        prompt = get_intent_prompt().format_messages(query=query, serp_data=serp_data)
        
        logger.info(f"Invoking LLM for intent prediction: {query}")
        response = await model.ainvoke(prompt)
        
        return response
    except Exception as e:
        logger.error(f"Error calculating intent with LLM: {str(e)}")
        # Fallback response in case of error
        return KeywordIntentResponse(
            intent="unknown",
            probability=0.0,
            explanation=f"LLM calculation failed: {str(e)}"
        )

def get_intent_consensus(
    api_intent: Optional[str],
    serp_intent: str,
    serp_confidence: float,
    llm_predicted: KeywordIntentResponse
) -> Dict[str, Any]:
    """
    Determine final intent based on API, SERP (Competitor), and LLM predictions.
    
    Refined logic:
    1. If api_intent is "unknown", use serp_intent as the primary baseline.
    2. If api_intent != serp_intent and serp_confidence > 60%, prioritize serp_intent.
    3. If the refined api_intent matches LLM intent -> Success.
    4. If LLM probability > 60% -> Prioritize LLM.
    5. Fallback to refined api_intent.
    """
    # Normalize and establish refined API intent
    api_intent_val = (api_intent or "unknown").lower()
    serp_intent_val = serp_intent.lower()
    llm_intent_val = llm_predicted.intent.lower()
    
    baseline_intent = api_intent_val
    
    # Rule 1: Replace unknown API intent with SERP
    if api_intent_val == "unknown" or not api_intent_val:
        logger.info(f"API intent unknown, using SERP intent: '{serp_intent_val}'")
        baseline_intent = serp_intent_val
    
    # Rule 2: Prioritize SERP if strong mismatch
    elif api_intent_val != serp_intent_val and serp_confidence > 0.6:
        logger.info(f"SERP consensus is strong ({serp_confidence:.1%}) and differs from API '{api_intent_val}'. Using SERP: '{serp_intent_val}'")
        baseline_intent = serp_intent_val

    final_intent = ""
    
    # Intent Consensus with LLM
    if baseline_intent == llm_intent_val:
        logger.info(f"Intent Match: Baseline and LLM both predicted '{baseline_intent}'")
        final_intent = baseline_intent
    elif llm_predicted.probability > 0.6:
        logger.info(f"LLM Intent dominant ({llm_predicted.probability:.1%}): Using '{llm_intent_val}'")
        final_intent = llm_intent_val
    else:
        logger.info(f"Falling back to baseline intent: '{baseline_intent}'")
        final_intent = baseline_intent

    return {
        "api_intent": api_intent_val,
        "serp_intent": serp_intent_val,
        "serp_confidence": f"{serp_confidence:.1%}",
        "llm_intent": llm_intent_val,
        "llm_probability": f"{llm_predicted.probability:.1%}",
        "consensus_intent": final_intent,
        "explanation": llm_predicted.explanation
    }

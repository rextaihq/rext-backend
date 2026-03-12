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
) -> str:
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
        return api_intent or "unknown"
        
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
                
    if total_weighted_samples == 0:
        return api_intent or "unknown"
        
    # Find the most frequent weighted intent
    sorted_intents = sorted(weighted_counts.items(), key=lambda x: x[1], reverse=True)
    top_intent, weighted_count = sorted_intents[0]
    
    # Check if a single intent dominates weighted votes
    confidence = weighted_count / total_weighted_samples
    
    if confidence >= threshold:
        logger.info(f"Consensus intent reached: {top_intent.upper()} (weighted {weighted_count}/{total_weighted_samples}, {confidence:.1%})")
        return top_intent
        
    # Fallback to API intent if no consensus, unless API intent is unknown/empty
    if api_intent and api_intent.lower() != "unknown":
        logger.info(f"No clear consensus ({confidence:.1%}), using API intent: {api_intent}")
        return api_intent
        
    logger.info(f"No API intent and no clear consensus, using most frequent competitor intent: {top_intent}")
    return top_intent

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
    top_intent: str,
    llm_predicted: KeywordIntentResponse
) -> Dict[str, str]:
    """
    Determine final intent based on API, Top (Competitor), and LLM predictions.
    
    Logic:
    - If api_intent matches LLM predicted intent -> Return that intent.
    - Else if LLM probability > 60% -> Return LLM intent.
    - Otherwise -> Return API intent (if exists & known) else Top intent.
    """
    api_intent_val = (api_intent or "unknown").lower()
    llm_intent_val = llm_predicted.intent.lower()
    
    final_intent = ""
    
    if api_intent_val != "unknown" and api_intent_val == llm_intent_val:
        logger.info(f"Intent Match: API and LLM both predicted '{api_intent_val}'")
        final_intent = api_intent_val
    elif llm_predicted.probability > 0.6:
        logger.info(f"LLM Intent dominant ({llm_predicted.probability:.1%}): Using '{llm_intent_val}'")
        final_intent = llm_intent_val
    else:
        if api_intent_val != "unknown":
            logger.info(f"No strong LLM consensus, falling back to API intent: '{api_intent_val}'")
            final_intent = api_intent_val
        else:
            logger.info(f"No API intent and no strong LLM consensus, falling back to Top intent: '{top_intent}'")
            final_intent = top_intent

    return {
        "api_intent": api_intent_val,
        "top_intent": top_intent,
        "llm_intent": llm_intent_val,
        "consensus_intent": final_intent,
        "llm_probability": f"{llm_predicted.probability:.1%}",
        "explanation": llm_predicted.explanation
    }

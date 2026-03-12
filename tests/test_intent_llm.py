import asyncio
import logging
import sys
import os

# Add src to path
sys.path.append(os.getcwd())

from src.flow.utils.intent_utils import calculate_intent_with_llm, get_intent_consensus, KeywordIntentResponse

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def run_verification():
    print("=== Testing Intent Calculation Logic ===")
    
    # Mock data
    query = "best mechanical keyboards 2026"
    organic_results = [
        {"title": "Best Mechanical Keyboards of 2026: Reviews and Buying Guide", "snippet": "We tested dozens of mechanical keyboards to help you find the best one for typing and gaming in 2026."},
        {"title": "The Best Mechanical Keyboards for 2026 | PCMag", "snippet": "Compare the top-rated mechanical keyboards for programmers, gamers, and office workers."},
        {"title": "Mechanical Keyboard Comparison - 2026 Edition", "snippet": "A detailed comparison showing the pros and cons of the latest mechanical keyboards on the market."}
    ]
    
    # 1. Test LLM Prediction (Mocking if needed, but let's try calling it if API key is present)
    print("\n1. Testing LLM Prediction...")
    try:
        # Note: This will actually call OpenAI if the environment is set up.
        # If it fails due to missing API key, we will catch and proceed with mock for logic testing.
        llm_predicted = await calculate_intent_with_llm(query, organic_results)
        print(f"LLM Predicted Intent: {llm_predicted.intent}")
        print(f"LLM Probability: {llm_predicted.probability}")
        print(f"LLM Explanation: {llm_predicted.explanation}")
    except Exception as e:
        print(f"LLM Call failed (likely missing API key): {e}")
        llm_predicted = KeywordIntentResponse(intent="COMMERCIAL", confidence="high", probability=0.85, explanation="Mocked for logic test")

    # 2. Test Consensus Logic - Scenario: Match
    print("\n2. Scenario: Match (API: commercial, LLM: commercial)")
    serp_intent, serp_conf = "commercial", 0.5
    results = get_intent_consensus("commercial", serp_intent, serp_conf, llm_predicted)
    print(f"Final Intent: {results['consensus_intent']}")
    assert results['consensus_intent'] == "commercial"

    # 3. Test Consensus Logic - Scenario: No Match, LLM > 60%
    print("\n3. Scenario: No Match, High LLM Confidence (API: informational, LLM: commercial @ 85%)")
    high_conf_llm = KeywordIntentResponse(intent="COMMERCIAL", confidence="high", probability=0.85, explanation="Review/Comparison results")
    serp_intent, serp_conf = "informational", 0.5
    results = get_intent_consensus("informational", serp_intent, serp_conf, high_conf_llm)
    print(f"Final Intent: {results['consensus_intent']}")
    assert results['consensus_intent'] == "commercial"

    # 4. Test Consensus Logic - Scenario: No Match, Low LLM Confidence (API: informational, LLM: commercial @ 45%)
    print("\n4. Scenario: No Match, Low LLM Confidence (API: informational, LLM: commercial @ 45%)")
    low_conf_llm = KeywordIntentResponse(intent="COMMERCIAL", confidence="low", probability=0.45, explanation="Unclear results")
    serp_intent, serp_conf = "informational", 0.4
    results = get_intent_consensus("informational", serp_intent, serp_conf, low_conf_llm)
    print(f"Final Intent: {results['consensus_intent']}")
    assert results['consensus_intent'] == "informational"

    # 5. Test Consensus Logic - Scenario: No API intent
    print("\n5. Scenario: No API Intent (API: None, LLM: commercial @ 45%, SERP: transactional @ 70%)")
    serp_intent, serp_conf = "transactional", 0.7
    results = get_intent_consensus(None, serp_intent, serp_conf, low_conf_llm)
    print(f"Final Intent: {results['consensus_intent']}")
    assert results['consensus_intent'] == "transactional"

    # 6. Test Consensus Logic - Scenario: API Mismatch, High SERP Confidence
    print("\n6. Scenario: API Mismatch, High SERP Confidence (API: informational, SERP: commercial @ 80%)")
    serp_intent, serp_conf = "commercial", 0.8
    results = get_intent_consensus("informational", serp_intent, serp_conf, low_conf_llm)
    print(f"Final Intent: {results['consensus_intent']}")
    assert results['consensus_intent'] == "commercial"

    print("\n=== All Tests Passed (Logic Verified) ===")

if __name__ == "__main__":
    asyncio.run(run_verification())

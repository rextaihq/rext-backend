import logging
from typing import List
from src.flow.utils.intent_utils import get_consensus_intent
from src.flow.states.rext import Competitor

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_weighted_consensus():
    # Test Case 1: Dominant intent in top positions
    competitors_1: List[Competitor] = [
        {"top_positions": [1], "intent_distribution": {"COMMERCIAL": 1}}, # weight 3
        {"top_positions": [2], "intent_distribution": {"COMMERCIAL": 1}}, # weight 3
        {"top_positions": [3], "intent_distribution": {"INFORMATIONAL": 1}}, # weight 3
        {"top_positions": [4], "intent_distribution": {"INFORMATIONAL": 1}}, # weight 2
        {"top_positions": [5], "intent_distribution": {"INFORMATIONAL": 1}}, # weight 2
    ]
    # Commercial: 3+3 = 6
    # Informational: 3+2+2 = 7
    # Total: 13. Threshold 0.6 of 13 is 7.8. No consensus if strictly 0.6.
    
    # Test Case 2: Clear commercial dominance in top 3
    competitors_2: List[Competitor] = [
        {"top_positions": [1], "intent_distribution": {"COMMERCIAL": 1}}, # weight 3
        {"top_positions": [2], "intent_distribution": {"COMMERCIAL": 1}}, # weight 3
        {"top_positions": [3], "intent_distribution": {"COMMERCIAL": 1}}, # weight 3
        {"top_positions": [10], "intent_distribution": {"INFORMATIONAL": 1}}, # weight 1
    ]
    # Commercial: 3+3+3 = 9
    # Informational: 1
    # Total 10. Commercial is 0.9. Should return commercial.
    
    print("\n--- Running Test Case 2 (Commercial Dominance) ---")
    result_2 = get_consensus_intent("unknown", competitors_2)
    assert result_2 == "commercial", f"Expected commercial, got {result_2}"
    print(f"✅ Test Case 2 Passed: {result_2}")

    # Test Case 3: Mixed intent, falling back to position 1
    competitors_3: List[Competitor] = [
        {"top_positions": [1], "intent_distribution": {"TRANSACTIONAL": 1}}, # weight 3
        {"top_positions": [8], "intent_distribution": {"INFORMATIONAL": 1}}, # weight 1
        {"top_positions": [9], "intent_distribution": {"INFORMATIONAL": 1}}, # weight 1
    ]
    # Transactional: 3
    # Informational: 2
    # Total 5. Transactional is 0.6. Should return transactional.
    
    print("\n--- Running Test Case 3 (Mixed, positional weight wins) ---")
    result_3 = get_consensus_intent("unknown", competitors_3)
    assert result_3 == "transactional", f"Expected transactional, got {result_3}"
    print(f"✅ Test Case 3 Passed: {result_3}")

    # Test Case 4: API fallback
    print("\n--- Running Test Case 4 (API Fallback) ---")
    result_4 = get_consensus_intent("commercial", [])
    assert result_4 == "commercial", f"Expected commercial, got {result_4}"
    print(f"✅ Test Case 4 Passed: {result_4}")

if __name__ == "__main__":
    test_weighted_consensus()

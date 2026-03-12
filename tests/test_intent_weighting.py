import sys
import os
sys.path.append(os.getcwd())

from src.flow.utils.intent_utils import get_consensus_intent
from src.flow.states.rext import Competitor

def test_get_consensus_intent():
    print("=== Testing get_consensus_intent ===")
    
    # Mock competitors
    competitors = [
        {
            "domain": "comp1.com",
            "top_positions": [1],
            "intent_distribution": {"commercial": 1}
        },
        {
            "domain": "comp2.com",
            "top_positions": [4],
            "intent_distribution": {"informational": 1}
        }
    ]
    
    # comp1 weight: 3, comp2 weight: 2
    # Total weighted: 5. commercial: 3/5 = 60%, informational: 2/5 = 40%
    
    print("\nScenario 1: Mixed competitors")
    intent, conf = get_consensus_intent("informational", competitors)
    print(f"Intent: {intent}, Confidence: {conf:.1%}")
    assert intent == "commercial"
    assert conf == 0.6
    
    print("\nScenario 2: No competitors")
    intent, conf = get_consensus_intent("informational", [])
    print(f"Intent: {intent}, Confidence: {conf:.1%}")
    assert intent == "informational"
    assert conf == 0.0

    print("\nScenario 3: Empty results from competitors")
    competitors_empty = [{"domain": "none.com", "top_positions": [1], "intent_distribution": {}}]
    intent, conf = get_consensus_intent("unknown", competitors_empty)
    print(f"Intent: {intent}, Confidence: {conf:.1%}")
    assert intent == "unknown"
    assert conf == 0.0

    print("=== All tests passed! ===")

if __name__ == "__main__":
    test_get_consensus_intent()

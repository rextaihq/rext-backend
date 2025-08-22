from langgraph.types import Send
from src.states.State import AgentState

# Fan out  Node for parallel workflow
def continue_retrieval(state: AgentState):
    sends = []
    for article in state['selected_articles']:
        refine_title = article["refine_title"]

        # Send to 3 different retrieval strategies in parallel
        sends.append(Send("GetRelevantDoc", {"refine_title": refine_title}))
        sends.append(Send("QueryExpansion", {"refine_title": refine_title}))
        sends.append(Send("QueryDecomposition", {"refine_title": refine_title}))

    return sends


def continue_generation(state: AgentState):
    return [
        Send(
            "BlogGeneration",
            {
                "refine_title": context["refine_title"],
                "docs": context["docs"]
            }
        )
        for context in state["context"]
    ]
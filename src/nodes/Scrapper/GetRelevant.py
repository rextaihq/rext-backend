from src.states.State import AgentState
import pandas as pd

def get_relevant_articles(state: AgentState) -> AgentState:
    """
    Get relevant articles based on user selection.
    """
    try:
        print("Process Selected Articles..")
        selected_articles = state.get('selected_articles', [])
        # print(pd.DataFrame(selected_articles))

        return state
    except Exception as e:
        state["error"] = str(e)
        return str(e)
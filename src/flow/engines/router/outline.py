import logging
from langgraph.graph import StateGraph, START, END
from src.flow.states.wrext import WREXT

def outline_router(state: WREXT) -> WREXT:
    # get the outline status
    content_state = state.get("content", {})
    print("contnet state", content_state)
    outline_status = content_state.get("outline", {}).get("status", "")
    print("outline status", outline_status)
    if outline_status == "approved":
        return "generate_content"
    elif outline_status == "rejected":
        return "generate_outline"
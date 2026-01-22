import logging
from langgraph.graph import StateGraph, START, END
from src.flow.states.wrext import WREXT

def outline_router(state: WREXT) -> str:
    # get the outline status
    content_state = state.get("content", {})
    outline_status = content_state.get("outline", {}).get("status", "")
    if outline_status == "approved":
        return "generate_content"
    
    return "generate_outline"
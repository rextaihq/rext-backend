import logging
from langgraph.graph import StateGraph, START, END
from src.flow.states.wrext import WREXT

def keyword_router(state: WREXT)->str:
    if state["seo_result"]["keyword_recommendations"]["is_changed"]:
        return "SEO_ENGINE"
    return "END"
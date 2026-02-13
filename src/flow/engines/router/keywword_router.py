from src.flow.states.rext import REXT


def keyword_router(state: REXT) -> str:
    if state["seo_result"]["keyword_recommendations"]["is_changed"]:
        return "SEO_ENGINE"
    return "END"

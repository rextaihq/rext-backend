from src.flow.states.rext import REXT


def outline_router(state: REXT) -> str:
    content_state = state.get("content", {})
    outline_status = content_state.get("outline", {}).get("status", "")
    if outline_status == "approved":
        return "generate_content"

    return "generate_outline"

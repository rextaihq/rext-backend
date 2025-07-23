from langgraph.types import interrupt, Command
from src.states.State import AgentState
from src.prompts.prompt import outline_prompt_template
from src.states.State import ArticleOutline
from src.model.model import LoadModel

def outline_generator(state: AgentState):
    """
    Generates an outline for the currently selected article using a language model.
    This function retrieves the current article based on the approval index from the agent state,
    constructs a prompt using the article's title, summary, raw content, and any approval feedback,
    and then invokes a model to generate a structured outline. If all articles have been processed,
    it returns a command to proceed to the next node. Otherwise, it updates the state with the
    generated outline and moves to the outline approval step.
    Args:
        state (AgentState): The current state of the agent, containing selected articles,
                            approval index, and feedback.
    Returns:
        Command: A command to either proceed to the next node or update the state with the
                 generated outline and move to outline approval.
    """
    
    print("🔄 Running OutlineGenerator Node...")

    selected = state.get("selected_articles", [])
    idx = state.get("current_approval_index", 0)
    feedback = state.get("approval_feedback", "")

    if idx >= len(selected):
        print("✅ All articles processed. Proceeding to BlogGeneration.")
        return Command(goto="BlogGeneration")

    article = selected[idx]
    title = article.get("title", "")
    summary = article.get("summary", "")
    raw = article.get("Raw Blog Content", "")[:10000]

    print(f"📄 Processing article #{idx + 1}: {title}")

    prompt = outline_prompt_template().format(
        title=title,
        summary=summary,
        raw_content=raw,
        feedback=feedback
    )

    print("🧠 Generating outline with model...")
    result = LoadModel().with_structured_output(ArticleOutline).invoke(prompt)

    return Command(
        goto='OutlineApproval',
        update={"generated_outline": result}
    )
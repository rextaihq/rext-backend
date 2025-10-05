from src.states.State import AgentState
from langgraph.types import Command
from src.prompts.prompt import blog_post_prompt_template
from src.states.schemas import BlogArticle
from src.model.model import load_model
from langgraph.types import Send

from src.api.lib.logger import auto_logger

logger = auto_logger()

def blog_generation(state:AgentState):
    """
    Generates a blog article based on the current state, using an approved outline and selected article context.
    This function retrieves the current blog index, approved outlines, and selected articles from the provided state.
    It constructs a prompt for a language model using the outline's title, summary, and reference content, then invokes
    the model to generate a blog article. The generated blog is then returned for approval. If all blogs have been
    generated, the function transitions to the draft blog stage.
    Args:
        state (AgentState): The current agent state containing outlines, articles, and progress indices.
    Returns:
        Command: A command object indicating the next step in the workflow, either to draft a blog or proceed to blog approval.
    
    """
    
    logger.info("\n🔁 === BlogGeneration Node Triggered ===")

    refine_title = state.get("refine_title")
    docs = state.get("docs", [])
    reference_url = state.get("reference_url", [])
    blog_feedback = state.get("blog_feedback", [])

    logger.info(f"📝 Generating blog for: {refine_title}")
    logger.info(f"📚 Number of context docs: {len(docs)}")

    # ✅ Construct prompt
    logger.info("🧠 Constructing prompt for the LLM...")
    combined_context = "\n\n".join([d.page_content if hasattr(d, "page_content") else str(d) for d in docs])
    
    prompt = blog_post_prompt_template().format(
        topic_title=refine_title,
        reference_content=combined_context,
        reference_url=reference_url,
        blog_feedback=blog_feedback
    )

    # ✅ Send to LLM
    logger.info("🤖 Sending prompt to LLM for blog generation...")
    blog_model = load_model().with_structured_output(BlogArticle)
    blog_result: BlogArticle = blog_model.invoke(prompt)
    logger.info("✅ Blog content received from LLM.")

    # ✅ Fan out the state
    return Send(
        "BlogApproval",
        {"generated_blog": blog_result}
    )
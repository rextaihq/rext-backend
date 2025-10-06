from src.states.State import AgentState
from langgraph.types import Command, interrupt
from src.states.schemas import BlogArticle

from src.api.lib.logger import auto_logger

logger = auto_logger()

# Blog Approval
def blog_approval(state:AgentState):
    """
    Handles the human approval workflow for a generated blog post.
    This function presents the generated blog content to a human for approval via an interrupt.
    If approved, the blog is added to the list of approved blogs and the workflow proceeds to the next blog.
    If rejected, the function collects feedback for improvement and returns to the blog generation step.
    Args:
        state (AgentState): The current agent state containing blog generation data and workflow progress.
    Returns:
        Command: An instruction to update the agent state and control workflow navigation.
            - If approved: updates approved blogs, advances the blog index, and clears feedback.
            - If rejected: updates feedback and returns to blog generation.
    Side Effects:
        - Prints status messages to the console.
        - Uses `interrupt` to pause execution for human input.
    """
    blog_result: BlogArticle = state.get("generated_blog")
    blog_feedback = state.get("blog_feedback", "")
    approved_blogs = state.get("approved_blogs", [])

    # print("Blog Result:", blog_result)

    formatted_sections = "\n\n".join(
        [f"### {s.heading}\n{s.content}" for s in blog_result.sections]
    )
    logger.info("Formatted Sections:", formatted_sections)
    decision = interrupt(
        f"""
📄 **Blog Title:** {blog_result.title}

📝 **Meta Description:**
{blog_result.meta_description}

📝 **Introduction:**
{blog_result.introduction}

📑 **Sections:**
{formatted_sections}

📝 **Conclusion:**
{blog_result.conclusion}

🗣️ **Previous Feedback:** {blog_feedback or "None"}

✅ Approve this blog post? (yes/no)
"""
    )

    if decision.strip().lower() == "yes":
        logger.info("✅ Human approved the blog.")

        new_approved_blog = blog_result.model_dump()
        new_approved_blog["approved"] = True

        approved_blogs.append(new_approved_blog)

        return Command(
            update={"approved_blogs": [approved_blogs], "blog_feedback": [""]},
            goto="DraftBlog"
        )

    else:
        logger.info("❌ Human rejected the blog.")
        feedback = interrupt("📝 Provide feedback for improving the blog:")
        return Command(
            update={"blog_feedback": [feedback]},
            goto="BlogGeneration"
        )
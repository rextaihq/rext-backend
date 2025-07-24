from src.states.State import AgentState
from langgraph.types import Command, interrupt

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
    # Retrieve state
    current_index = state.get("current_blog_index", 0)
    approved_blogs = state.get("approved_blogs", [])
    blog_feedback = state.get("blog_feedback", "")
    blog_result  = state['generated_blog']
    if "generated_blog" not in state:
        print("❌ Error: 'generated_blog' missing from state. Redirecting to BlogGeneration.")
        return Command(goto="BlogGeneration")

    # ✅ Precompute formatted sections (to avoid backslash in f-string)
    formatted_sections = "\n\n".join(
        [f"### {s.heading}\n{s.content}" for s in blog_result.sections]
    )
    references_list = ", ".join(blog_result.references) or "None"

    print("🛑 Awaiting human approval for the generated blog...")

    decision = interrupt(
        f"""
📄 **Blog Title:** {blog_result.title}

📝 **Generated Blog Meta Description:**
{blog_result.meta_description}

📝 **Introduction:**
{blog_result.introduction}

📑 **Sections:**
{formatted_sections}

📝 **Conclusion:**
{blog_result.conclusion}

🔗 **References:**
{references_list}

🗣️ **Previous Feedback:** {blog_feedback or "None"}

✅ Approve this blog post? (yes/no)
"""
    )

    # ✅ Handle human decision
    if decision.strip().lower() == "yes":
        print("✅ Human approved the blog.")

        new_approved_blog = {
            "title": blog_result.title,
            "meta_description": blog_result.meta_description,
            "keywords": blog_result.keywords,
            "introduction": blog_result.introduction,
            "sections": [s.model_dump() for s in blog_result.sections],
            "conclusion": blog_result.conclusion,
            "references": blog_result.references,
            "approved": True
        }

        approved_blogs.append(new_approved_blog)
        print(f"🗂️ Blog appended to approved list. Total approved: {len(approved_blogs)}")

        return Command(
            update={
                "approved_blogs": approved_blogs,
                "current_blog_index": current_index + 1,
                "blog_feedback": ""
            },
            goto="BlogGeneration"
        )

    else:
        print("❌ Human rejected the blog.")
        feedback = interrupt("📝 Provide feedback for improving the blog:")
        print(f"🗣️ Feedback collected: {feedback}")

        return Command(
            update={"blog_feedback": feedback},
            goto="BlogGeneration"
        )
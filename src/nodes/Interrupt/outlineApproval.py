from src.states.State import AgentState
from langgraph.types import Command, interrupt

def outline_approval(state:AgentState):
    """
    Handles the approval process for a generated article outline by interacting with a human user.

    This function displays the generated outline (title, introduction, sections, and conclusion) to the user,
    along with any previous feedback, and prompts for approval. If the outline is approved, it updates the
    state with the approved outline and advances the approval index. If rejected, it collects user feedback
    for further improvement and updates the state accordingly.

    Args:
        state (AgentState): The current state containing selected articles, approval index, approved outlines,
                            feedback, and the generated outline.

    Returns:
        Command: An object specifying state updates and the next node to transition to in the workflow.
    """

    idx = state.get("current_approval_index", 0)
    approved = state.get("approved_outlines", [])
    feedback = state.get("approval_feedback", "")
    result = state['generated_outline']

    # Format sections for display
    section_texts = ""
    for i, section in enumerate(result.sections, 1):
        section_texts += f"\n\n🔹 **Section {i}: {section.heading}**\n"
        for bullet in section.bullet_points:
            section_texts += f"   - {bullet}\n"

    print("🛑 Awaiting human approval...")
    decision = interrupt(f"""
    📄 **Title:** {result.title}

    📝 **Introduction:**
    {result.introduction}

    📚 **Sections:** {section_texts}

    🧾 **Conclusion:**
    {result.conclusion}

    🗣️ **Previous Feedback:** {feedback or "None"}

    ✅ Approve this outline? (yes/no)
    """)

    if decision.strip().lower() == "yes":
        print("✅ Outline approved.")
        approved.append({
            "title": result.title,
            "Intro": result.introduction,
            "Sections": result.sections,
            "Conclusion": result.conclusion,
            "approved": True
        })

        return Command(
            update={
                "approved_outlines": approved,
                "current_approval_index": idx + 1,
                "approval_feedback": ""
            },
            goto="OutlineGenerator"
        )

    else:
        print("❌ Outline rejected.")
        # get user feedback
        user_fb = interrupt("📝 Provide the feedback for improving the outline?")
        print(f"User feedback: {user_fb}")

        return Command(
            update={"approval_feedback": user_fb},
            goto="OutlineGenerator"
        )
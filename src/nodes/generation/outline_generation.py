from langgraph.types import interrupt, Command
from src.states.State import AgentState
from src.prompts.prompt import outline_prompt_template
from src.states.State import ArticleOutline
from src.model.model import LoadModel

def outline_generator(state: AgentState):
    print("🔄 Running OutlineGenerator Node...")

    selected = state.get("selected_articles", [])
    idx = state.get("current_approval_index", 0)
    approved = state.get("approved_outlines", [])
    feedback = state.get("approval_feedback", "")

    if idx >= len(selected):
        print("✅ All articles processed. Proceeding to BlogGeneration.")
        return Command(update={
                "approved_outlines": approved,
            }, goto="BlogGeneration")

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

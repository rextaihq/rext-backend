from src.states.State import AgentState
from langgraph.types import Command, interrupt
from src.prompts.prompt import blog_post_prompt_template
from src.states.State import BlogArticle
from src.model.model import LoadModel

def blog_generation(state:AgentState):
    print("\n🔁 === BlogGeneration Node Triggered ===")

    # Retrieve state
    approved_outlines = state.get("approved_outlines", [])
    selected_articles = state.get("selected_articles", [])
    current_index = state.get("current_blog_index", 0)
    approved_blogs = state.get("approved_blogs", [])
    blog_feedback = state.get("blog_feedback", "")

    print(f"📌 Current Index: {current_index}")
    print(f"✅ Approved Blogs So Far: {len(approved_blogs)}")
    print(f"🧾 Total Articles to Process: {len(approved_outlines)}")

    # ✅ Stop condition: all blogs generated
    if current_index >= len(approved_outlines):
        print("🎉 All blogs have been generated and approved.")
        return Command(
            # update={"approved_blogs": approved_blogs},
            goto="DraftBlog"
        )

    # ✅ Get the current outline + selected article context
    outline = approved_outlines[current_index]
    article = selected_articles[current_index]
    print(f"📝 Generating blog for: {outline['title']}")

    # ✅ Extract context for blog generation
    summary = article.get("summary", "")
    raw_reference_content = article.get("Raw Blog Content", "")[:10000]

    # ✅ Format the blog generation prompt
    print("🧠 Constructing prompt for the LLM...")
    prompt = blog_post_prompt_template().format(
        topic_title=outline["title"],
        summary=summary,
        approved_outline="\n".join(
            [f"- {sec['heading']}" for sec in outline.get("sections", [])]
        ),
        reference_content=raw_reference_content
    )

    print("🤖 Sending prompt to LLM for blog generation...")
    blog_model = LoadModel().with_structured_output(BlogArticle)
    blog_result: BlogArticle = blog_model.invoke(prompt)
    print("✅ Blog content received from LLM.")

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
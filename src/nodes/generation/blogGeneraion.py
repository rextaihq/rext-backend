from src.states.State import AgentState
from langgraph.types import Command, interrupt
from src.prompts.prompt import blog_post_prompt_template
from src.states.State import BlogArticle
from src.model.model import LoadModel

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
    
    print("\n🔁 === BlogGeneration Node Triggered ===")

    # Retrieve state
    approved_outlines = state.get("approved_outlines", [])
    selected_articles = state.get("selected_articles", [])
    current_index = state.get("current_blog_index", 0)
    blog_feedback = state.get("blog_feedback", "")

    print(f"📌 Current Index: {current_index}")
    print(f"🧾 Total Articles to Process: {len(approved_outlines)}")

    # ✅ Stop condition: all blogs generated
    if current_index >= len(approved_outlines):
        print("🎉 All blogs have been generated and approved.")
        return Command(
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

    return Command(
        goto='BlogApproval',
        update={'generated_blog':blog_result}
    )
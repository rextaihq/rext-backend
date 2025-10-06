from src.langgraph_flow.states.content_state import ContentState
from src.langgraph_flow.prompts.prompt import blog_prompt_template
from src.langgraph_flow.states.blog_state import BlogArticle
from src.model.model import load_model


def generate_blog(state: ContentState):
    print("\n🔁 === BlogGeneration Node Triggered ===")

    # ✅ Topics
    topics = state.get("topics", [])
    print(f"📝 Topics in state: {len(topics)} found")
    title = topics[0]["title"] if topics else "Untitled"
    print(f"🏷️ Using title: '{title}'")

    # ✅ Context docs
    docs = state.get("relavant_context", [])
    blog_feedback = state.get("blog_feedback", "")
    payload = state.get("payload", {})  # ✅ full payload

    print(f"📝 Generating blog for: {title}")
    print(f"📚 Number of context docs: {len(docs)}")

    # ✅ Prepare combined reference context
    combined_context = "\n\n".join(
        [d.page_content if hasattr(d, "page_content") else str(d) for d in docs]
    )

    # ✅ Construct prompt safely
    try:
        print("🧠 Constructing prompt for the LLM...")
        prompt = blog_prompt_template().format(
            topic_title=title,
            reference_content=combined_context,
            blog_feedback=blog_feedback,
            # unpack payload values with defaults
            platform=payload.get("platform", "Website"),
            contentType=payload.get("contentType", "Article"),
            industry=payload.get("industry", "General"),
            audienceSize=payload.get("audienceSize", "General"),
            audienceType=", ".join(payload.get("audienceType", [])),
            readingLevel=payload.get("readingLevel", "Intermediate"),
            region=payload.get("region", "Global"),
            language=payload.get("language", "English"),
            goals=", ".join(payload.get("goals", [])),
            tone=", ".join(payload.get("tone", [])),
            primaryKeywords=", ".join(payload.get("primaryKeywords", [])),
            contentLength=str(payload.get("contentLength", {})),
            researchLevel=payload.get("researchLevel", "Basic"),
            competitorAnalysis=payload.get("competitorAnalysis", False),
            factChecking=payload.get("factChecking", "Standard"),
            contentFreshness=payload.get("contentFreshness", "Recent"),
            includeKeyTakeaways=payload.get("includeKeyTakeaways", False),
        )
    except Exception as e:
        print(f"❌ Error while constructing prompt: {e}")
        return [{"error": f"Prompt construction failed: {str(e)}"}]

    # ✅ Send to LLM safely
    try:
        print("🤖 Sending prompt to LLM for blog generation...")
        blog_model = load_model().with_structured_output(BlogArticle)
        blog_result: BlogArticle = blog_model.invoke(prompt)
        print("✅ Blog content received from LLM.")
    except Exception as e:
        print(f"❌ LLM invocation failed: {e}")
        return {"error": f"Blog generation failed: {str(e)}"}

    # ✅ Return state update
    return [{
        "generated_blog": blog_result
    }]

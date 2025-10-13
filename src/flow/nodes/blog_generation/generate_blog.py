from src.flow.states.content_state import ContentState
from src.flow.prompts.prompt_manager import PromptManager
from src.flow.states.blog_state import BlogArticle
from src.flow.model.llm_manager import load_model
from langsmith import traceable,trace
from dotenv import load_dotenv
load_dotenv()

@traceable(
    name="Blog Generation",
    metadata={
        "description": "Generates a blog post by constructing a contextualized prompt and invoking the LLM.",
        "inputs": ["workspace_id", "topics", "payload"],
        "outputs": ["generated_blog"],
        "source": "FAISS Vector Store",
    },
    tags=["LLM", "Blog", "ContentGeneration"],
    project_name="WREXT"
)
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
     # 🧠 Build prompt inside a trace block
    try:
        with trace(name="Prompt Construction", inputs={"title": title, "context_docs": len(docs)}) as prompt_trace:
            prompt_data = {
                "title": title,
                "content_language": payload.get("content_language", "English"),
                "content_format": payload.get("content_format", "Article"),
                "status": payload.get("status", "draft"),
                "author_id": payload.get("author_id", "N/A"),
                "workspace_id": payload.get("workspace_id", "N/A"),
                "topic_id": payload.get("topic_id", "N/A"),
                "created_at": payload.get("created_at", "N/A"),
                "updated_at": payload.get("updated_at", "N/A"),
                "content_type": payload.get("content_metadata", {}).get("content_type", "Blog"),
                "target_platform": payload.get("content_metadata", {}).get("target_platform", "Website"),
                "target_industry": payload.get("content_metadata", {}).get("target_industry", "General"),
                "target_audience": payload.get("content_metadata", {}).get("target_audience", "General Audience"),
                "audience_size": payload.get("content_metadata", {}).get("audience_size", "Medium"),
                "complexity_level": payload.get("content_metadata", {}).get("complexity_level", "Intermediate"),
                "content_tone": payload.get("content_metadata", {}).get("content_tone", "Conversational"),
                "target_region": payload.get("content_metadata", {}).get("target_region", "Global"),
                "content_objectives": payload.get("content_metadata", {}).get("content_objectives", "Engage and Inform"),
                "content_word_count": payload.get("content_metadata", {}).get("content_word_count", "1000"),
                "content_primary_keywords": ", ".join(payload.get("seo_data", {}).get("content_primary_keywords", [])),
                "content_secondary_keywords": ", ".join(payload.get("seo_data", {}).get("content_secondary_keywords", [])),
                "content_meta_description": payload.get("seo_data", {}).get("content_meta_description", ""),
                "content_search_intent": payload.get("seo_data", {}).get("content_search_intent", "Informational"),
                "reference_content": combined_context,
                "blog_feedback": blog_feedback,
            }

            prompt_manager = PromptManager()
            prompt_template = prompt_manager.get_prompt('blog_generation_v1')
            prompt = prompt_template.format_prompt(**prompt_data).to_messages()

            # Record structured output in LangSmith trace
            prompt_trace.outputs = {"prompt_preview": str(prompt)[:500]}

    except Exception as e:
        print(f"❌ Prompt construction failed: {e}")
        return {"error": f"Prompt construction failed: {str(e)}"}

   # 🤖 LLM Invocation
    try:
        with trace(name="LLM Invocation", inputs={"model": "blog_model", "title": title}) as llm_trace:
            print("🤖 Sending prompt to LLM...")
            blog_model = load_model().with_structured_output(BlogArticle)
            blog_result: BlogArticle = blog_model.invoke(prompt)
            print("✅ Blog content received.")
            llm_trace.outputs = {"blog_result_summary": str(blog_result)[:500]}

    except Exception as e:
        print(f"❌ LLM invocation failed: {e}")
        return {"error": f"Blog generation failed: {str(e)}"}

    # ✅ Return state update
    return {
        "generated_blog": blog_result
    }

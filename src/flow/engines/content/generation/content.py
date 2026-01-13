import logging
import json
from src.flow.states.wrext import WREXT
from src.flow.model.llm_manager import load_model
from src.flow.model.structure.content import GeneratedContent
from src.flow.prompts.human.content import get_content_prompt
from src.flow.model.personas import get_eeat_persona

logger = logging.getLogger(__name__)

def generate_content(state: WREXT):
    """
    Generates SEO content using an LLM, integrating outline, context, and EEAT persona.
    Now includes E-E-A-T persona data in a single pass to save 1 LLM call.
    """
    try:
        # 1️⃣ Get content state and outline
        content_state = state.get("content", {})
        topic = content_state.get("selected_topic", "")

        # if not topic:
        #     logger.error("No topic found in state")
        #     return {
        #         "content": {
        #             **state.get("content", {}),
        #             "error": "No topic found in state",
        #         }
        #     }

        logger.info(f"Generating content for: {topic}")

        
        outline = content_state.get("outline", {})
        if not outline:
            logger.warning("No outline found in state. Proceeding without it.")
        outline_str = json.dumps(outline, indent=2) if outline else "NO OUTLINE FOUND"

        logger.info(f"Outline extracted: {outline_str}")

        # 2️⃣ Get E-E-A-T persona (merged into content generation)
        persona = get_eeat_persona("eeat_persona_001")
        logger.info(f"Using E-E-A-T persona: {persona['name']} - {persona['role']}")

        # 3️⃣ Get relevant context
        relevant_context = state.get("relevant_context", [])
        page_content = "\n\n".join(
            chunk.get("chunk", "") for chunk in relevant_context
        )
        logger.info(f"Page content length: {len(page_content.split())} words")

        # 4️⃣ Get primary keyword from outline
        primary_keyword = outline.get("keywords_to_include", [""])[0] if outline.get("keywords_to_include") else topic

        # 5️⃣ Extract Competitor Insights
        competitors = state.get("competitors", [])
        competitor_insights = "No competitor data available."
        target_word_count = 1500  # Default fallback

        if competitors:            
            scraped_docs = state.get("scrape_context", {}).get("documents", [])
            if scraped_docs:
                # scraped_docs is a list of dicts: {"document": Document, "content_length": int, ...}
                lengths = [d.get("content_length", 0) for d in scraped_docs if d.get("content_length", 0) > 0]
                if lengths:
                    avg_length = sum(lengths) / len(lengths)
                    target_word_count = int(avg_length * 1.1)  # Aim for 10% more than average
            
            competitor_insights = "\n".join([
                f"- {c.get('domain')}: Rank {c.get('top_positions', ['?'])[0]}" 
                for c in competitors[:5]
            ])

        logger.info(f"Target word count: {target_word_count}")

        # 6️⃣ Prepare prompt data with persona information & competitor insights
        prompt_data = {
            "topic": topic,
            "outline": outline_str,
            "reference_text": page_content,
            # E-E-A-T persona data (merged)
            "persona_name": persona["name"],
            "persona_role": persona["role"],
            "years_experience": persona["years_experience"],
            "focus_areas": ", ".join(persona["focus_areas"]),
            "primary_keyword": primary_keyword,
            # Competitor Data
            "competitor_insights": competitor_insights,
            "target_word_count": target_word_count,
        }

        # 6️⃣ Load model and prepare messages
        content_model = load_model().with_structured_output(GeneratedContent)
        messages = get_content_prompt().format_messages(**prompt_data)
        logger.info(f"Number of messages sent to LLM: {len(messages)}")

        # 7️⃣ Invoke LLM
        generated_content = content_model.invoke(messages)
        content_dict = generated_content.model_dump()
        logger.info(f"Content generated successfully. Keys: {content_dict.keys()}")

        # 8️⃣ Return structured content
        return {
            "content": {
                "outline": outline,
                "final_content": {
                    **content_dict,
                    "status": "reviewing",
                    "rejected_reason": ""
                },
                "status": "content_generation"
            }
        }

    except Exception as e:
        logger.exception(f"Error generating content: {str(e)}")
        return {
            "content": {
                **content_state,
                "error": f"Generation failed: {str(e)}"
            }
        }

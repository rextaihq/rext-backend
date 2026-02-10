"""
Pure Content Generation Node

This module generates SEO-optimized content without E-E-A-T signals.
E-E-A-T injection and humanization are handled in separate nodes.
"""

import logging
import json
from src.flow.states.rext import REXT
from src.flow.model.llm_manager import load_model
from src.flow.model.structure.content import GeneratedContent
from src.flow.prompts.human.content import get_content_prompt

logger = logging.getLogger(__name__)


async def generate_content(state: REXT) -> dict:
    """
    Generates SEO-optimized content using an LLM.
    
    This node focuses on pure content generation based on outline and context.
    E-E-A-T signals and humanization are applied in subsequent nodes.
    
    Args:
        state: REXT state containing outline and context
    
    Returns:
        dict: Updated state with generated content
    """
    try:
        # 1️⃣ Get content state, topic, and content type
        content_state = state.get("content", {})
        topic = content_state.get("selected_topic", "")
        content_type = content_state.get("content_type", "article")

        logger.info(f"Generating content for: {topic} (content type: {content_type})")

        outline = content_state.get("outline", {})
        if not outline:
            logger.warning("No outline found in state. Proceeding without it.")
        outline_str = json.dumps(outline, indent=2) if outline else "NO OUTLINE FOUND"

        logger.info(f"Outline extracted: {outline_str[:20]}...")

        # 2️⃣ Get relevant context from RextStore
        serp_payload = state.get("serp_payload", {})
        user_id = str(serp_payload.get("user_id", ""))
        workspace_id = str(serp_payload.get("workspace_id", ""))
        
        page_content = ""
        context_items = []
        
        if user_id and workspace_id:
            try:
                from src.flow.store.rext_store import RextStore
                store = RextStore()
                # Use the topic as the search query
                search_query = topic
                
                logger.info(f"Searching RextStore for context on: '{search_query}' (User: {user_id}, Workspace: {workspace_id})")
                
                results = await store.search_knowledge(
                    user_id=user_id, 
                    workspace_id=workspace_id, 
                    query=search_query,
                    limit=10 
                )
                
                if results:
                    # RextStore returns a list of SearchItem objects, accessing .value['text']
                    for res in results:
                        text = res.value.get('text', '')
                        if text:
                            context_items.append(text)
                    
                    page_content = "\n\n".join(context_items)
                    logger.info(f"Retrieved {len(results)} context items from store.")
                else:
                    logger.warning("No relevant context found in RextStore.")
                    
            except Exception as e:
                logger.error(f"Failed to retrieve context from RextStore: {e}")
                # Fallback to existing relevant_context if available (legacy support)
                relevant_context = state.get("relevant_context", [])
                page_content = "\n\n".join(
                    chunk.get("chunk", "") for chunk in relevant_context
                )
        else:
             logger.warning("Missing user_id or workspace_id. Skipping RextStore context retrieval.")
             # Fallback
             relevant_context = state.get("relevant_context", [])
             page_content = "\n\n".join(
                 chunk.get("chunk", "") for chunk in relevant_context
             )
        logger.info(f"Page content length: {len(page_content.split())} words")

        # 3️⃣ Get primary keyword from outline
        primary_keyword = outline.get("keywords_to_include", [""])[0] if outline.get("keywords_to_include") else topic

        # 4️⃣ Extract Competitor Insights
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
        # get tone from outline
        tone = outline.get("tone", "Professional")
        logger.info(f"Tone: {tone}")
        # 5️⃣ Prepare prompt data
        prompt_data = {
            "content_type": content_type,
            "topic": topic,
            "outline": outline_str,
            "reference_text": page_content,
            "primary_keyword": primary_keyword,
            "competitor_insights": competitor_insights,
            "target_word_count": target_word_count,
            "tone": tone,
        }

        # 6️⃣ Load model and prepare messages
        content_model = load_model().with_structured_output(GeneratedContent)
        messages = get_content_prompt().format_messages(**prompt_data)
        logger.info(f"Number of messages sent to LLM: {len(messages)}")

        # 7️⃣ Invoke LLM
        logger.info("Invoking LLM for content generation...")
        generated_content = await content_model.ainvoke(messages)
        content_dict = generated_content.model_dump()
        logger.info(f"Content generated successfully. Word count: {content_dict.get('word_count', 0)}")

        # 8️⃣ Return structured content
        return {
            "content": {
                "outline": outline,
                "final_content": {
                    **content_dict,
                    "status": "generated",
                    "rejected_reason": ""
                },
                "status": "content_generated"
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

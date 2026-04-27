import logging
import json
from langchain_core.messages import SystemMessage, HumanMessage
from src.flow.states.rext import REXT
from src.flow.prompts.system.humanize import HUMANIZE_SYSTEM_PROMPT
from src.flow.model.llm_manager import load_content_model

logger = logging.getLogger(__name__)


async def humanize_content(state: REXT) -> dict:
    """
    Humanizes AI-generated content to bypass AI detectors.

    Args:
        state: REXT state containing generated content

    Returns:
        dict: Updated state with humanized content
    """
    content_state = state.get("content", {})
    try:
        # 1️⃣ Get generated content
        final_content = content_state.get("final_content", {})
        if not final_content:
            logger.warning("No final_content found in state")
            return {
                "content": {
                    **content_state,
                    "error": "No generated content found in state",
                }
            }

        # 2️⃣ Extract content to humanize
        introduction = final_content.get("introduction", "")
        body_markdown = final_content.get("body_markdown", "")

        if not introduction and not body_markdown:
            logger.warning("No content found in final_content to humanize")
            return {
                "content": {
                    **content_state,
                    "error": "No content found to humanize",
                }
            }

        logger.info("Humanizing AI-generated content...")
        model = load_content_model()

        async def humanize_text(text: str, part_name: str) -> str:
            if not text or len(text.strip()) < 50:  # Skip very short snippets
                return text

            # Additional instructions to preserve facts, urls, and images as requested by user
            preservation_instruction = (
                "\n\nCRITICAL CONSTRAINTS:\n"
                "1. DO NOT remove, alter, or hallucinate facts, statistics, or specific data points.\n"
                "2. DO NOT remove or alter any URLs or Markdown links (e.g., [text](url)).\n"
                "3. DO NOT remove or alter any Markdown images (e.g., ![alt](url)).\n"
                "4. Maintain the Markdown structure (headings, lists, bold/italic) while humanizing the prose."
            )

            messages = [
                SystemMessage(content=HUMANIZE_SYSTEM_PROMPT + preservation_instruction),
                HumanMessage(
                    content=f"Humanize the following {part_name} of the article. Follow the output format (Draft, Analysis, Final rewrite):\n\n{text}"
                ),
            ]

            response = await model.ainvoke(messages)
            llm_output = response.content

            # Extract the final humanized version
            if "Final rewrite" in llm_output:
                final_version = llm_output.split("Final rewrite")[-1].strip()
                # Clean up leading colons or noise
                if final_version.startswith(":"):
                    final_version = final_version[1:].strip()
                return final_version

            return llm_output.strip()

        # Humanize introduction and body separately to maintain state structure
        humanized_intro = await humanize_text(introduction, "introduction")
        humanized_body = await humanize_text(body_markdown, "body_markdown")

        logger.info("Content humanization complete")

        # 3️⃣ Update state with humanized content
        return {
            "content": {
                **content_state,
                "final_content": {
                    **final_content,
                    "introduction": humanized_intro,
                    "body_markdown": humanized_body,
                },
                "humanization_progress": 100,
                "humanizing": False,
            }
        }

    except Exception as e:
        logger.error(f"Error humanizing content: {str(e)}")
        return {
            "content": {
                **content_state,
                "error": f"Humanization failed: {str(e)}",
                "humanizing": False,
            }
        }
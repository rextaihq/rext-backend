import asyncio
import logging
import re
from typing import Any, Optional

from langchain.agents.middleware import AgentMiddleware
from langgraph.runtime import Runtime
from pydantic import BaseModel
from sqlalchemy import select

from src.flow.model.llm_manager import load_humanize_model
from src.flow.model.structure.contents.base import BaseGeneratedContent
from src.flow.prompts.human.humanize import get_humanize_prompt
from src.flow.states.rext import REXT

logger = logging.getLogger(__name__)

DEFAULT_WORD_TARGET = 3000
SECTION_MIN_RATIO = 0.12  # section min = 12% of target_word_count, floor 300


class HumanizeMiddleware(AgentMiddleware):
    """
    Post-processes agent structured output through a dedicated humanization model.

    Runs after the agent completes, applies the humanization prompt, and updates
    `structured_response`. Also injects length expansion instructions when the
    content is under the word target so humanization and expansion happen in one call.

    Awaits `counters["image_task"]` (fired by generate_image tool) and prepends
    the resolved URL to body_markdown after humanization.
    """

    state_schema = REXT

    def __init__(self, counters: dict | None = None):
        super().__init__()
        self._counters = counters

    HUMANIZED_FIELDS = {
        "introduction",
        "body_markdown",
    }

    async def aafter_agent(self, state: REXT, runtime: Runtime) -> dict[str, Any] | None:
        structured_response = state.get("structured_response")
        if not structured_response:
            logger.debug("HumanizeMiddleware: no structured_response found; skipping.")
            return None

        original_payload = self._to_dict(structured_response)
        if not original_payload:
            logger.warning("HumanizeMiddleware: structured_response is not serializable; skipping.")
            return None

        body_markdown = (original_payload.get("body_markdown") or "").strip()
        if not body_markdown:
            logger.info("HumanizeMiddleware: body_markdown missing; skipping.")
            return None

        # Await image task BEFORE humanization so stream starts with URL already resolved
        image_task = (self._counters or {}).get("image_task")
        image_url: str | None = None
        if image_task is not None:
            logger.info("HumanizeMiddleware: awaiting background image task before humanization.")
            try:
                image_url = await image_task
            except Exception:
                logger.exception("HumanizeMiddleware: image task raised an error; skipping image injection.")

        schema = self._resolve_schema(structured_response)
        word_target = (state.get("content") or {}).get("outline", {}).get("target_word_count", DEFAULT_WORD_TARGET)
        workspace_id = (state.get("serp_payload") or {}).get("workspace_id")
        brand_voice = await self._fetch_brand_voice(workspace_id)
        prompt_data = self._build_prompt_data(
            content_payload=original_payload,
            word_target=word_target,
            brand_voice=brand_voice,
        )
        model = load_humanize_model().with_structured_output(schema)
        messages = get_humanize_prompt().format_messages(**prompt_data)

        logger.info("HumanizeMiddleware: invoking humanization model.")
        try:
            humanized_obj = await model.ainvoke(messages, config={"tags": ["__humanize__"]})
        except Exception:
            logger.exception("HumanizeMiddleware: humanization model failed; keeping original output.")
            return None

        humanized_payload = self._to_dict(humanized_obj)
        if not humanized_payload:
            logger.warning("HumanizeMiddleware: empty humanized payload; keeping original output.")
            return None

        merged_payload = dict(original_payload)
        for key in self.HUMANIZED_FIELDS:
            if key not in humanized_payload:
                continue
            value = humanized_payload.get(key)
            if value is None:
                continue
            if isinstance(value, str) and not value.strip():
                continue
            if isinstance(value, (list, dict)) and not value:
                continue
            merged_payload[key] = value

        # Inject resolved image URL into humanized output
        if image_url and image_url.startswith("http"):
            title = (state.get("content") or {}).get("selected_topic") or ""
            alt = f"Featured image for {title}"
            merged_payload["body_markdown"] = (
                f"![{alt}]({image_url})\n\n"
                + (merged_payload.get("body_markdown") or "")
            )
            images_list = list(merged_payload.get("images") or [])
            images_list.insert(0, {
                "url": image_url,
                "alt_text": alt,
                "context": "AI-generated featured image for the article.",
                "placement": "introduction",
            })
            merged_payload["images"] = images_list
            logger.info("HumanizeMiddleware: image injected → %s", image_url)
        elif image_task is not None:
            logger.info("HumanizeMiddleware: image task returned no valid URL; skipping injection.")

        updated_structured_response = self._rebuild_output(structured_response, merged_payload)
        if updated_structured_response is None:
            logger.warning("HumanizeMiddleware: failed to rebuild structured_response; skipping update.")
            return None

        logger.info("HumanizeMiddleware: content humanization applied successfully.")
        return {"structured_response": updated_structured_response}

    def _build_prompt_data(
        self,
        *,
        content_payload: dict[str, Any],
        word_target: int = DEFAULT_WORD_TARGET,
        brand_voice: Optional[Any] = None,
    ) -> dict[str, Any]:
        introduction = content_payload.get("introduction") or ""
        body_markdown = content_payload.get("body_markdown") or ""
        title = content_payload.get("title") or ""
        total_words = len((introduction + " " + body_markdown).split())
        total_target = word_target + 200
        section_min = max(300, int(word_target * SECTION_MIN_RATIO))
        deficit = total_target - total_words

        logger.info("HumanizeMiddleware: word count = %d / %d", total_words, total_target)

        if deficit > 0:
            sections = re.split(r'(?=^## )', body_markdown, flags=re.MULTILINE)
            short_headings = [
                re.match(r'^## (.+)', s.strip()).group(1)
                for s in sections
                if s.strip() and len(s.split()) < section_min and re.match(r'^## (.+)', s.strip())
            ]
            if short_headings:
                expand_note = (
                    f"These sections are under {section_min} words — expand each one: "
                    f"{', '.join(short_headings)}. "
                    "Add a real example, step-by-step breakdown, common mistakes, or a persona anecdote to each."
                )
            else:
                expand_note = f"Add {deficit} more words spread across sections — deepen explanations with examples or anecdotes."

            length_instruction = (
                f"LENGTH REQUIREMENT: Article has {total_words} words. Target is {total_target}. "
                f"While rewriting, also EXPAND the content by {deficit} words. {expand_note} "
                "Do not pad with filler — expand with substance."
            )
        else:
            length_instruction = f"Article has {total_words} words — target met. Rewrite for human tone only."

        brand_vocab_instruction = self._build_brand_vocab_instruction(brand_voice)

        return {
            # "title": title,
            "introduction": introduction,
            "body_markdown": body_markdown,
            "length_instruction": length_instruction,
            "brand_vocab_instruction": brand_vocab_instruction,
        }

    @staticmethod
    def _build_brand_vocab_instruction(brand_voice: Optional[Any]) -> str:
        """
        Build a brand vocabulary preservation block for the humanizer.

        Prevents the humanizer from replacing brand-specific terms with generic
        synonyms — a common failure mode that strips product-led voice from content.
        """
        if not brand_voice:
            return ""

        lines = []

        vocab = getattr(brand_voice, "product_vocabulary", None) or []
        forbidden = getattr(brand_voice, "forbidden_words", None) or []
        product_name = getattr(brand_voice, "product_name", None)
        brand_tone = getattr(brand_voice, "brand_voice", None) or []
        ctas = getattr(brand_voice, "brand_ctas", None) or []

        if not any([vocab, forbidden, product_name, brand_tone, ctas]):
            return ""

        lines.append("BRAND VOICE PRESERVATION — APPLY DURING REWRITE:")

        if product_name:
            lines.append(f"- Keep the product/brand name exactly as written: \"{product_name}\" — do not rephrase or genericise it.")

        if isinstance(vocab, list) and vocab:
            lines.append("- Preserve these exact brand terms (do NOT replace with synonyms):")
            for item in vocab:
                if isinstance(item, dict):
                    use_term = item.get("use", "")
                    avoid_term = item.get("not", "")
                    if use_term:
                        lines.append(f'    Keep: "{use_term}"' + (f' (never write "{avoid_term}")' if avoid_term else ""))

        if isinstance(forbidden, list) and forbidden:
            lines.append(f"- Do NOT introduce these words during rewrite: {', '.join(str(w) for w in forbidden)}")

        if isinstance(brand_tone, list) and brand_tone:
            lines.append(f"- The brand tone is: {', '.join(str(t) for t in brand_tone)} — apply these traits while rewriting.")

        if isinstance(ctas, list) and ctas:
            lines.append("- Preserve these call-to-action phrases exactly as written (do not rephrase):")
            for cta in ctas:
                lines.append(f'    "{cta}"')

        return "\n".join(lines) if lines else ""

    async def _fetch_brand_voice(self, workspace_id: Optional[Any]) -> Optional[Any]:
        """Fetch workspace BrandVoice for vocabulary preservation during humanization."""
        if not workspace_id:
            return None
        try:
            from src.api.models.knowledge_models.knowledge_model import BrandVoice
            from src.api.database.async_database import SyncSessionLocal

            def _sync_fetch():
                db = SyncSessionLocal()
                try:
                    result = db.execute(
                        select(BrandVoice).where(BrandVoice.workspace_id == workspace_id)
                    )
                    return result.scalar_one_or_none()
                finally:
                    db.close()

            return await asyncio.to_thread(_sync_fetch)
        except Exception:
            logger.debug("HumanizeMiddleware: brand voice fetch failed (non-fatal); skipping.")
            return None

    @staticmethod
    def _resolve_schema(structured_response: Any) -> type[BaseModel]:
        if isinstance(structured_response, BaseModel):
            return structured_response.__class__
        return BaseGeneratedContent

    @staticmethod
    def _to_dict(value: Any) -> dict[str, Any]:
        if isinstance(value, BaseModel):
            return value.model_dump()
        if isinstance(value, dict):
            return value
        if hasattr(value, "model_dump"):
            try:
                return value.model_dump()
            except Exception:
                return {}
        return {}

    @staticmethod
    def _rebuild_output(original: Any, merged_payload: dict[str, Any]) -> Any:
        if isinstance(original, BaseModel):
            try:
                return original.__class__.model_validate(merged_payload)
            except Exception:
                return original.model_copy(update=merged_payload)
        if isinstance(original, dict):
            return merged_payload
        return None

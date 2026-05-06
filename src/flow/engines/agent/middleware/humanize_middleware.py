import logging
import re
from typing import Any, Optional

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.runtime import Runtime
from pydantic import BaseModel
from sqlalchemy import select

from src.api.database.async_database import AsyncSessionLocal
from src.api.models.knowledge_models.persona_model import Persona
from src.flow.model.llm_manager import load_content_model, load_humanize_model
from src.flow.model.structure.contents.base import BaseGeneratedContent
from src.flow.prompts.human.humanize import get_humanize_prompt
from src.flow.states.rext import REXT

logger = logging.getLogger(__name__)

WORD_TARGET = 3000
SECTION_MIN_WORDS = 350


class HumanizeMiddleware(AgentMiddleware):
    """
    Post-processes agent structured output through a dedicated humanization model.

    Runs after the agent completes, fetches persona context, applies the
    humanization prompt, and updates `structured_response`.
    """

    state_schema = REXT

    HUMANIZED_FIELDS = {
        "title",
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

        schema = self._resolve_schema(structured_response)

        # Expand content if under word target before humanizing
        original_payload = await self._expand_if_short(original_payload, schema)

        prompt_data = self._build_prompt_data(
            content_payload=original_payload,
        )
        model = load_humanize_model().with_structured_output(schema)
        messages = get_humanize_prompt().format_messages(**prompt_data)

        logger.info("HumanizeMiddleware: invoking dedicated humanization model.")
        try:
            humanized_obj = await model.ainvoke(messages)
        except Exception:
            logger.exception(
                "HumanizeMiddleware: humanization model failed; keeping original output."
            )
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
        updated_structured_response = self._rebuild_output(structured_response, merged_payload)
        if updated_structured_response is None:
            logger.warning(
                "HumanizeMiddleware: failed to rebuild structured_response; skipping update."
            )
            return None

        logger.info("HumanizeMiddleware: content humanization applied successfully.")
        return {"structured_response": updated_structured_response}

    async def _expand_if_short(self, payload: dict[str, Any], schema: type[BaseModel]) -> dict[str, Any]:
        intro = (payload.get("introduction") or "").strip()
        body = (payload.get("body_markdown") or "").strip()
        total_words = len((intro + " " + body).split())

        logger.info("HumanizeMiddleware: word count before expansion: %d / %d", total_words, WORD_TARGET)

        for pass_num in range(1, 3):
            if total_words >= WORD_TARGET:
                break

            deficit = WORD_TARGET - total_words

            # Identify short H2 sections
            sections = re.split(r'(?=^## )', body, flags=re.MULTILINE)
            short_headings = [
                re.match(r'^## (.+)', s.strip()).group(1)
                for s in sections
                if s.strip() and len(s.split()) < SECTION_MIN_WORDS and re.match(r'^## (.+)', s.strip())
            ]

            if short_headings:
                target_note = (
                    f"These sections are under {SECTION_MIN_WORDS} words and must be expanded: "
                    f"{', '.join(short_headings)}. "
                    f"Expand each with: a real example, step-by-step breakdown, common mistakes, or a persona anecdote."
                )
            else:
                target_note = (
                    f"The article needs {deficit} more words overall. "
                    "Add depth to any section: more examples, comparisons, or persona anecdotes."
                )

            logger.info("HumanizeMiddleware expansion pass %d: deficit=%d, short_sections=%s", pass_num, deficit, short_headings)

            messages = [
                SystemMessage(content=(
                    "You are expanding an existing article to meet a minimum word count. "
                    "Return the COMPLETE expanded article — preserve all existing content, facts, links, headings, and the persona voice. "
                    "Do not truncate any section. Do not add filler — expand with substance."
                )),
                HumanMessage(content=(
                    f"The article currently has {total_words} words. Target: {WORD_TARGET} words (deficit: {deficit}).\n"
                    f"{target_note}\n\n"
                    f"CURRENT ARTICLE:\n\n"
                    f"Title: {payload.get('title', '')}\n\n"
                    f"Introduction:\n{intro}\n\n"
                    f"Body:\n{body}"
                )),
            ]

            try:
                model = load_content_model().with_structured_output(schema)
                expanded = await model.ainvoke(messages)
                expanded_dict = self._to_dict(expanded)
                if expanded_dict:
                    for field in ("introduction", "body_markdown"):
                        val = expanded_dict.get(field)
                        if val and str(val).strip():
                            payload[field] = val
                    intro = (payload.get("introduction") or "").strip()
                    body = (payload.get("body_markdown") or "").strip()
                    total_words = len((intro + " " + body).split())
                    logger.info("HumanizeMiddleware expansion pass %d done: %d words", pass_num, total_words)
            except Exception:
                logger.exception("HumanizeMiddleware expansion pass %d failed — keeping current content", pass_num)
                break

        return payload

    def _build_prompt_data(
        self,
        *,
        content_payload: dict[str, Any],
    ) -> dict[str, Any]:

        introduction = content_payload.get("introduction") or ""
        body_markdown = content_payload.get("body_markdown") or ""

        prompt_data: dict[str, Any] = {
            "title": content_payload.get("title") or "",
            "introduction": introduction,
            "body_markdown": body_markdown,
        }
        return prompt_data

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

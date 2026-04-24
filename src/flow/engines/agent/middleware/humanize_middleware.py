# import logging
# from typing import Any, Optional

# from langchain.agents.middleware import AgentMiddleware
# from langgraph.runtime import Runtime
# from pydantic import BaseModel
# from sqlalchemy import select

# from src.api.database.async_database import AsyncSessionLocal
# from src.api.models.knowledge_models.persona_model import Persona
# from src.flow.model.llm_manager import load_humanize_model
# from src.flow.model.structure.contents.base import BaseGeneratedContent
# from src.flow.prompts.human.humanize import get_humanize_prompt
# from src.flow.states.rext import REXT

# logger = logging.getLogger(__name__)


# class HumanizeMiddleware(AgentMiddleware):
#     """
#     Post-processes agent structured output through a dedicated humanization model.

#     Runs after the agent completes, fetches persona context, applies the
#     humanization prompt, and updates `structured_response`.
#     """

#     state_schema = REXT

#     HUMANIZED_FIELDS = {
#         "title",
#         "introduction",
#         "body_markdown",
#     }

#     async def aafter_agent(self, state: REXT, runtime: Runtime) -> dict[str, Any] | None:
#         structured_response = state.get("structured_response")
#         if not structured_response:
#             logger.debug("HumanizeMiddleware: no structured_response found; skipping.")
#             return None

#         original_payload = self._to_dict(structured_response)
#         if not original_payload:
#             logger.warning("HumanizeMiddleware: structured_response is not serializable; skipping.")
#             return None

#         body_markdown = (original_payload.get("body_markdown") or "").strip()
#         if not body_markdown:
#             logger.info("HumanizeMiddleware: body_markdown missing; skipping.")
#             return None
        
#         prompt_data = self._build_prompt_data(
#             content_payload=original_payload,
#         )

#         schema = self._resolve_schema(structured_response)
#         model = load_humanize_model().with_structured_output(schema)
#         messages = get_humanize_prompt().format_messages(**prompt_data)

#         logger.info("HumanizeMiddleware: invoking dedicated humanization model.")
#         try:
#             humanized_obj = await model.ainvoke(messages)
#         except Exception:
#             logger.exception(
#                 "HumanizeMiddleware: humanization model failed; keeping original output."
#             )
#             return None

#         humanized_payload = self._to_dict(humanized_obj)
#         if not humanized_payload:
#             logger.warning("HumanizeMiddleware: empty humanized payload; keeping original output.")
#             return None

#         merged_payload = dict(original_payload)
#         for key in self.HUMANIZED_FIELDS:
#             if key not in humanized_payload:
#                 continue
#             value = humanized_payload.get(key)
#             if value is None:
#                 continue
#             if isinstance(value, str) and not value.strip():
#                 continue
#             if isinstance(value, (list, dict)) and not value:
#                 continue
#             merged_payload[key] = value
#         updated_structured_response = self._rebuild_output(structured_response, merged_payload)
#         if updated_structured_response is None:
#             logger.warning(
#                 "HumanizeMiddleware: failed to rebuild structured_response; skipping update."
#             )
#             return None

#         logger.info("HumanizeMiddleware: content humanization applied successfully.")
#         return {"structured_response": updated_structured_response}

#     def _build_prompt_data(
#         self,
#         *,
#         content_payload: dict[str, Any],
#     ) -> dict[str, Any]:

#         introduction = content_payload.get("introduction") or ""
#         body_markdown = content_payload.get("body_markdown") or ""

#         prompt_data: dict[str, Any] = {
#             "title": content_payload.get("title") or "",
#             "introduction": introduction,
#             "body_markdown": body_markdown,
#         }
#         return prompt_data

#     @staticmethod
#     def _resolve_schema(structured_response: Any) -> type[BaseModel]:
#         if isinstance(structured_response, BaseModel):
#             return structured_response.__class__
#         return BaseGeneratedContent

#     @staticmethod
#     def _to_dict(value: Any) -> dict[str, Any]:
#         if isinstance(value, BaseModel):
#             return value.model_dump()
#         if isinstance(value, dict):
#             return value
#         if hasattr(value, "model_dump"):
#             try:
#                 return value.model_dump()
#             except Exception:
#                 return {}
#         return {}

#     @staticmethod
#     def _rebuild_output(original: Any, merged_payload: dict[str, Any]) -> Any:
#         if isinstance(original, BaseModel):
#             try:
#                 return original.__class__.model_validate(merged_payload)
#             except Exception:
#                 return original.model_copy(update=merged_payload)
#         if isinstance(original, dict):
#             return merged_payload
#         return None



import logging
from typing import Any, Optional

from langchain.agents.middleware import AgentMiddleware
from langgraph.runtime import Runtime
from pydantic import BaseModel
from sqlalchemy import select

from src.api.database.async_database import AsyncSessionLocal
from src.api.models.knowledge_models.persona_model import Persona
from src.flow.model.llm_manager import load_humanize_model
from src.flow.model.structure.contents.base import BaseGeneratedContent
from src.flow.prompts.human.humanize import get_humanize_prompt
from src.flow.states.rext import REXT

logger = logging.getLogger(__name__)


class HumanizeMiddleware(AgentMiddleware):
    """
    Post-processes agent structured output through a dedicated humanization model.

    Runs after the agent completes, fetches persona context, applies the
    humanization prompt, and updates `structured_response`.
    """

    state_schema = REXT

    DEFAULT_PERSONA = {
        "persona_full_name": "Writer",
        "persona_professional_title": "Subject Matter Expert",
        "persona_areas_of_expertise": "Industry Expertise",
        "persona_bio": "A seasoned professional with deep industry knowledge.",
        "persona_tone_of_voice": "Professional and authoritative",
        "persona_description": "Expert writer",
        "persona_goals": "Provide high-quality, actionable insights",
        "persona_behaviors": "Conversational, direct, and insightful",
    }
    HUMANIZED_FIELDS = {
        "title",
        "introduction",
        "body_markdown"
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

        content_state = state.get("content", {}) or {}
        outline = content_state.get("outline", {}) or {}

        workspace_id = (state.get("serp_payload", {}) or {}).get("workspace_id")
        persona_data = await self._fetch_persona_data(workspace_id)
        prompt_data = self._build_prompt_data(
            content_state=content_state,
            outline=outline,
            content_payload=original_payload,
            persona_data=persona_data,
        )

        schema = self._resolve_schema(structured_response)
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

    def after_agent(self, state: REXT, runtime: Runtime) -> dict[str, Any] | None:
        # Async implementation is used; sync fallback is intentionally a no-op.
        return None

    async def _fetch_persona_data(self, workspace_id: Optional[str]) -> dict[str, str]:
        if not workspace_id:
            return dict(self.DEFAULT_PERSONA)

        try:
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(Persona)
                    .where(Persona.workspace_id == workspace_id)
                    .order_by(Persona.created_at.desc())
                    .limit(1)
                )
                persona = result.scalar_one_or_none()
        except Exception:
            logger.exception(
                "HumanizeMiddleware: error fetching persona for workspace %s; using defaults.",
                workspace_id,
            )
            return dict(self.DEFAULT_PERSONA)

        if not persona:
            logger.info(
                "HumanizeMiddleware: no persona found for workspace %s; using defaults.",
                workspace_id,
            )
            return dict(self.DEFAULT_PERSONA)

        persona_data = {
            "persona_full_name": persona.full_name or persona.name or "Writer",
            "persona_professional_title": persona.professional_title or "Subject Matter Expert",
            "persona_areas_of_expertise": persona.areas_of_expertise or "Industry Expertise",
            "persona_bio": persona.bio or "A seasoned professional with deep industry knowledge.",
            "persona_tone_of_voice": persona.tone_of_voice or "Professional and authoritative",
            "persona_description": persona.description or "Expert writer",
            "persona_goals": persona.goals or "Provide high-quality, actionable insights",
            "persona_behaviors": persona.behaviors or "Conversational, direct, and insightful",
        }
        return persona_data

    def _build_prompt_data(
        self,
        *,
        content_state: dict[str, Any],
        outline: dict[str, Any],
        content_payload: dict[str, Any],
        persona_data: dict[str, str],
    ) -> dict[str, Any]:
        target_audience = outline.get("target_audience", "")
        if isinstance(target_audience, list):
            target_audience = ", ".join(target_audience)

        introduction = content_payload.get("introduction") or ""
        body_markdown = content_payload.get("body_markdown") or ""

        prompt_data: dict[str, Any] = {
            "title": content_payload.get("title") or "",
            "introduction": introduction,
            "body_markdown": body_markdown,
            "html_content": content_payload.get("html_content") or "",
            "selected_topic": (
                content_state.get("selected_topic")
                or content_payload.get("title")
                or ""
            ),
            "content_type": content_state.get("content_type") or "blog",
            "word_count": content_payload.get("word_count")
            or self._estimate_word_count(introduction, body_markdown),
            "target_audience": target_audience or "[exact persona + skill level]",
            "content_tone": outline.get("tone") or "[casual/direct/spicy/calm]",
            **persona_data,
        }

        prompt_data["persona_full_name"] = (
            prompt_data.get("persona_full_name") or "[Writer name]"
        )
        prompt_data["persona_professional_title"] = (
            prompt_data.get("persona_professional_title")
            or "[e.g., WordPress dev, Security engineer, SaaS founder]"
        )
        prompt_data["persona_areas_of_expertise"] = (
            prompt_data.get("persona_areas_of_expertise")
            or "[e.g., WP-CLI, Git, Nginx, Cloudflare, Woo, etc]"
        )
        prompt_data["persona_goals"] = (
            prompt_data.get("persona_goals") or "[what they should know/do after]"
        )
        prompt_data["persona_behaviors"] = (
            prompt_data.get("persona_behaviors") or "[Behaviors]"
        )
        prompt_data["persona_tone_of_voice"] = (
            prompt_data.get("persona_tone_of_voice") or "Personal Tone"
        )

        return prompt_data

    @staticmethod
    def _estimate_word_count(introduction: str, body_markdown: str) -> int:
        return len(f"{introduction}\n{body_markdown}".split())

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
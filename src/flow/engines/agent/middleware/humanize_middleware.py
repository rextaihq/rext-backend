import logging
import re
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langgraph.runtime import Runtime
from pydantic import BaseModel

from src.flow.model.llm_manager import load_humanize_model
from src.flow.model.structure.contents.base import BaseGeneratedContent
from src.flow.prompts.human.brand_repair import get_brand_repair_prompt
from src.flow.prompts.human.humanize import get_humanize_prompt
from src.flow.states.rext import REXT

logger = logging.getLogger(__name__)

DEFAULT_WORD_TARGET = 3000
TARGET_BUFFER_RATIO = 0.12  # upper-bound tolerance, as a fraction of target_word_count
SECTION_MIN_FRACTION = 0.5  # a section is "too short" if under 50% of its proportional share of the target


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
        outline = (state.get("content") or {}).get("outline", {}) or {}
        word_target = outline.get("target_word_count", DEFAULT_WORD_TARGET)
        brand_context = self._extract_brand_context(outline)
        prompt_data = self._build_prompt_data(
            content_payload=original_payload, word_target=word_target, brand_context=brand_context,
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

        # Guarantee the user-approved brand mention survived humanization — the
        # rewrite pass above has no awareness of it, so it can silently drop or
        # relocate it. Verify deterministically and do one surgical repair pass
        # if it's missing, rather than trusting the rewrite prompt alone.
        if brand_context:
            combined_text = f"{merged_payload.get('introduction', '')}\n\n{merged_payload.get('body_markdown', '')}"
            if not self._mention_present(combined_text, brand_context["brand_name"]):
                logger.warning(
                    "HumanizeMiddleware: brand mention '%s' missing after humanization — attempting repair.",
                    brand_context["brand_name"],
                )
                repaired = await self._repair_missing_brand_mention(
                    payload=merged_payload, brand_context=brand_context, schema=schema,
                )
                if repaired:
                    merged_payload = repaired
                    logger.info("HumanizeMiddleware: brand mention repaired successfully.")
                else:
                    logger.warning(
                        "HumanizeMiddleware: brand mention repair failed — final content will be missing "
                        "the approved '%s' mention.", brand_context["brand_name"],
                    )

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
        brand_context: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        introduction = content_payload.get("introduction") or ""
        body_markdown = content_payload.get("body_markdown") or ""
        total_words = len((introduction + " " + body_markdown).split())

        raw_sections = re.split(r'(?=^## )', body_markdown, flags=re.MULTILINE)
        section_bodies = [
            s.strip() for s in raw_sections
            if s.strip() and re.match(r'^## (.+)', s.strip())
        ]
        num_sections = len(section_bodies) or 1

        # The target itself is the floor and target+buffer is the ceiling — no
        # flat offsets, since a fixed +200/floor-of-200 is negligible on a
        # 3000-word article but a huge relative overshoot on a 500-word one.
        total_target = word_target
        buffer = max(30, round(word_target * TARGET_BUFFER_RATIO))
        total_max = total_target + buffer
        # Per-section floor scales with each section's proportional share of
        # the target, not a flat 300 — otherwise a 500-word/6-section article
        # gets every section flagged "too short" and over-expanded.
        section_min = max(40, round((word_target / num_sections) * SECTION_MIN_FRACTION))
        deficit = total_target - total_words
        excess = total_words - total_max

        logger.info(
            "HumanizeMiddleware: word count = %d / range %d-%d (section_min=%d, sections=%d)",
            total_words, total_target, total_max, section_min, num_sections,
        )

        if deficit > 0:
            short_headings = [
                re.match(r'^## (.+)', s).group(1)
                for s in section_bodies
                if len(s.split()) < section_min
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
                f"LENGTH REQUIREMENT: Article has {total_words} words. Target range is {total_target}-{total_max}. "
                f"While rewriting, also EXPAND the content by {deficit} words. {expand_note} "
                "Do not pad with filler — expand with substance."
            )
        elif excess > 0:
            length_instruction = (
                f"LENGTH REQUIREMENT: Article has {total_words} words. Target range is {total_target}-{total_max}. "
                f"While rewriting, also TRIM the content by roughly {excess} words — cut filler, redundant transitions, "
                "and repeated points. Keep every fact, citation, and link intact; tighten prose, don't remove substance."
            )
        else:
            length_instruction = (
                f"Article has {total_words} words — within the {total_target}-{total_max} target range. "
                "Rewrite for human tone only."
            )

        brand_preservation_instruction = ""
        if brand_context:
            brand_name = brand_context["brand_name"]
            link_clause = (
                f" It is hyperlinked to {brand_context['brand_url']} — keep that link intact and attached to the brand name."
                if brand_context.get("brand_url")
                else " It is plain text with no link — do not add one."
            )
            brand_preservation_instruction = (
                f"BRAND MENTION — DO NOT DELETE OR RELOCATE: this article contains exactly one approved, "
                f'required product mention of "{brand_name}", woven into a body-section paragraph as a short '
                f"explanatory aside.{link_clause} Keep it in the same section, attached to the same surrounding "
                f"sentence — do NOT delete it as a 'generic line', do NOT move it into the introduction, and do "
                f"NOT turn it into a standalone closing sentence or CTA at the end of the article. If you rewrite "
                f'the sentence around it, keep "{brand_name}"{" and its link" if brand_context.get("brand_url") else ""} '
                f"and its explanatory clause intact."
            )

        return {
            "title": content_payload.get("title") or "",
            "introduction": introduction,
            "body_markdown": body_markdown,
            "length_instruction": length_instruction,
            "brand_preservation_instruction": brand_preservation_instruction,
        }

    @staticmethod
    def _extract_brand_context(outline: dict[str, Any]) -> dict[str, str] | None:
        """Pull brand promotion info out of the outline, if the user approved a mention."""
        if not outline.get("promote_brand"):
            return None
        promo = outline.get("brand_voice_promotion") or {}
        brand_name = (promo.get("brand_name") or "").strip()
        if not brand_name:
            return None
        return {
            "brand_name": brand_name,
            "brand_url": (promo.get("brand_url") or "").strip(),
            "about": promo.get("about") or "",
            "selling_position": promo.get("selling_position") or "",
        }

    @staticmethod
    def _mention_present(text: str, brand_name: str) -> bool:
        return bool(brand_name) and brand_name.strip().lower() in (text or "").lower()

    async def _repair_missing_brand_mention(
        self, *, payload: dict[str, Any], brand_context: dict[str, str], schema: type[BaseModel],
    ) -> dict[str, Any] | None:
        """Surgically reinsert a missing brand mention via a narrow, single-purpose edit call.

        Deliberately uses a different (non-rewriting) prompt than humanization —
        re-running the same broad rewrite risks dropping the mention again.
        """
        about = brand_context.get("about") or ""
        selling_position = brand_context.get("selling_position") or ""
        brand_url = brand_context.get("brand_url") or ""

        prompt_data = {
            "brand_name": brand_context["brand_name"],
            "about_line": f"About: {about}\n" if about else "",
            "selling_position_line": f"Selling position: {selling_position}\n" if selling_position else "",
            "url_line": f"URL (hyperlink the mention with this exact URL): {brand_url}\n" if brand_url else "URL: none — mention as plain text, do not invent a URL.\n",
            "title": payload.get("title") or "",
            "introduction": payload.get("introduction") or "",
            "body_markdown": payload.get("body_markdown") or "",
        }

        try:
            model = load_humanize_model().with_structured_output(schema)
            messages = get_brand_repair_prompt().format_messages(**prompt_data)
            repaired_obj = await model.ainvoke(messages, config={"tags": ["__brand_repair__"]})
        except Exception:
            logger.exception("HumanizeMiddleware: brand repair model call failed.")
            return None

        repaired_payload = self._to_dict(repaired_obj)
        if not repaired_payload:
            return None

        combined_text = f"{repaired_payload.get('introduction', '')}\n\n{repaired_payload.get('body_markdown', '')}"
        if not self._mention_present(combined_text, brand_context["brand_name"]):
            logger.warning("HumanizeMiddleware: repair pass still did not include the brand mention.")
            return None

        merged = dict(payload)
        for key in self.HUMANIZED_FIELDS:
            value = repaired_payload.get(key)
            if isinstance(value, str) and value.strip():
                merged[key] = value
        return merged

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
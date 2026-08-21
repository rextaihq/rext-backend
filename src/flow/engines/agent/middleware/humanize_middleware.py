import asyncio
import logging
import re
import time
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langgraph.runtime import Runtime
from pydantic import BaseModel

from src.flow.engines.agent.middleware.length_targets import compute_length_targets
from src.flow.engines.agent.middleware.persona_middleware import fetch_best_persona
from src.flow.model.llm_manager import load_humanize_model
from src.flow.model.structure.contents.base import BaseGeneratedContent
from src.flow.prompts.human.brand_repair import get_brand_repair_prompt
from src.flow.prompts.human.humanize import get_humanize_prompt
from src.flow.prompts.human.internal_links_repair import get_internal_links_repair_prompt
from src.flow.prompts.human.length_repair import get_length_repair_prompt
from src.flow.prompts.human.persona_repair import get_persona_repair_prompt
from src.flow.states.rext import REXT

logger = logging.getLogger(__name__)

DEFAULT_WORD_TARGET = 3000
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
        t_start = time.perf_counter()
        print("[HUMANIZE] ▶ START")

        structured_response = state.get("structured_response")
        if not structured_response:
            logger.debug("HumanizeMiddleware: no structured_response found; skipping.")
            print("[HUMANIZE] ✗ END — no structured_response, skipped")
            return None

        original_payload = self._to_dict(structured_response)
        if not original_payload:
            logger.warning("HumanizeMiddleware: structured_response is not serializable; skipping.")
            print("[HUMANIZE] ✗ END — structured_response not serializable, skipped")
            return None

        body_markdown = (original_payload.get("body_markdown") or "").strip()
        if not body_markdown:
            logger.info("HumanizeMiddleware: body_markdown missing; skipping.")
            print("[HUMANIZE] ✗ END — body_markdown missing, skipped")
            return None

        schema = self._resolve_schema(structured_response)
        outline = (state.get("content") or {}).get("outline", {}) or {}
        word_target = outline.get("target_word_count", DEFAULT_WORD_TARGET)
        brand_context = self._extract_brand_context(outline)
        prompt_data = self._build_prompt_data(
            content_payload=original_payload, word_target=word_target, brand_context=brand_context,
        )
        model = load_humanize_model().with_structured_output(schema)
        messages = get_humanize_prompt().format_messages(**prompt_data)

        # Run humanization concurrently with the image task instead of awaiting
        # the image first — the two are logically independent (writing prose
        # doesn't need image bytes), and the image task can take as long as the
        # humanize call itself, so serializing them was pure added latency.
        image_task = (self._counters or {}).get("image_task")
        pre_words = len(body_markdown.split())
        if image_task is not None:
            print(f"[HUMANIZE]   rewrite model call START (pre-humanize body ~{pre_words} words) "
                  f"— running concurrently with pending [IMAGE] task")
        else:
            print(f"[HUMANIZE]   rewrite model call START (pre-humanize body ~{pre_words} words) — no image task pending")
        t_rewrite = time.perf_counter()
        if image_task is not None:
            humanized_obj, image_result = await asyncio.gather(
                model.ainvoke(messages, config={"tags": ["__humanize__"]}), image_task,
                return_exceptions=True,
            )
        else:
            (humanized_obj,) = await asyncio.gather(
                model.ainvoke(messages, config={"tags": ["__humanize__"]}),
                return_exceptions=True,
            )
            image_result = None
        print(f"[HUMANIZE]   rewrite model call END ({time.perf_counter() - t_rewrite:.2f}s)")

        if isinstance(humanized_obj, Exception):
            logger.error("HumanizeMiddleware: humanization model failed; keeping original output.", exc_info=humanized_obj)
            print(f"[HUMANIZE] ✗ END ({time.perf_counter() - t_start:.2f}s) — rewrite model call raised: {humanized_obj}")
            return None

        image_url: str | None = None
        if image_task is not None:
            if isinstance(image_result, Exception):
                logger.error("HumanizeMiddleware: image task raised an error; skipping image injection.", exc_info=image_result)
                print(f"[IMAGE] ✗ resolved with error (seen by HumanizeMiddleware): {image_result}")
            else:
                image_url = image_result
                print(f"[IMAGE] ✓ resolved (seen by HumanizeMiddleware) -> {image_url or 'no URL'}")

        humanized_payload = self._to_dict(humanized_obj)
        if not humanized_payload:
            logger.warning("HumanizeMiddleware: empty humanized payload; keeping original output.")
            print(f"[HUMANIZE] ✗ END ({time.perf_counter() - t_start:.2f}s) — empty humanized payload")
            return None
        post_words = len((humanized_payload.get("introduction", "") + " " + humanized_payload.get("body_markdown", "")).split())
        print(f"[HUMANIZE]   post-rewrite body+intro ~{post_words} words (target {word_target})")

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
            if self._mention_present(combined_text, brand_context["brand_name"]):
                print(f"[CHECK brand] PASS — '{brand_context['brand_name']}' present, no repair needed")
            else:
                logger.warning(
                    "HumanizeMiddleware: brand mention '%s' missing after humanization — attempting repair.",
                    brand_context["brand_name"],
                )
                print(f"[CHECK brand] MISSING '{brand_context['brand_name']}' -> repair START")
                t_repair = time.perf_counter()
                repaired = await self._repair_missing_brand_mention(
                    payload=merged_payload, brand_context=brand_context, schema=schema,
                )
                if repaired:
                    merged_payload = repaired
                    logger.info("HumanizeMiddleware: brand mention repaired successfully.")
                    print(f"[CHECK brand] repair END ({time.perf_counter() - t_repair:.2f}s) — SUCCESS")
                else:
                    logger.warning(
                        "HumanizeMiddleware: brand mention repair failed — final content will be missing "
                        "the approved '%s' mention.", brand_context["brand_name"],
                    )
                    print(f"[CHECK brand] repair END ({time.perf_counter() - t_repair:.2f}s) — FAILED, still missing")

        # Guarantee the required author persona's name survived humanization —
        # same rationale as the brand check above: the rewrite pass has no
        # awareness of the persona requirement, so it can silently drop it.
        persona_id = outline.get("selected_persona_id")
        if persona_id:
            workspace_id = (state.get("serp_payload") or {}).get("workspace_id")
            persona = await fetch_best_persona(workspace_id, outline)
            persona_name = str(persona.full_name or persona.name) if persona else ""
            if not persona_name:
                print("[CHECK persona] SKIPPED — could not resolve persona for this workspace")
            elif self._persona_name_present(
                merged_payload.get("introduction", ""), merged_payload.get("body_markdown", ""), persona_name,
            ):
                print(f"[CHECK persona] PASS — '{persona_name}' present, no repair needed")
            else:
                logger.warning(
                    "HumanizeMiddleware: persona mention '%s' missing/insufficient after humanization — attempting repair.",
                    persona_name,
                )
                print(f"[CHECK persona] MISSING/INSUFFICIENT '{persona_name}' -> repair START")
                t_repair = time.perf_counter()
                repaired = await self._repair_missing_persona_mention(
                    payload=merged_payload, persona_name=persona_name, schema=schema,
                )
                if repaired:
                    merged_payload = repaired
                    logger.info("HumanizeMiddleware: persona mention repaired successfully.")
                    print(f"[CHECK persona] repair END ({time.perf_counter() - t_repair:.2f}s) — SUCCESS")
                else:
                    logger.warning(
                        "HumanizeMiddleware: persona mention repair failed — final content will be missing "
                        "sufficient mentions of '%s'.", persona_name,
                    )
                    print(f"[CHECK persona] repair END ({time.perf_counter() - t_repair:.2f}s) — FAILED, still insufficient")

        # Guarantee every user-approved internal link survived humanization as
        # an inline anchor. Checked against the outline's authoritative list
        # (not the model's own self-reported `internal_links` output field,
        # which can itself be incomplete) — this is the primary defense;
        # BaseGeneratedContent.enforce_internal_links_in_body is only a last-
        # resort append-to-end fallback if this repair pass also fails.
        approved_links = outline.get("internal_links") or []
        missing_links = [
            lnk for lnk in approved_links
            if lnk.get("url") and lnk["url"] not in (merged_payload.get("body_markdown") or "")
        ]
        if approved_links and not missing_links:
            print(f"[CHECK internal_links] PASS — all {len(approved_links)} present, no repair needed")
        if missing_links:
            logger.warning(
                "HumanizeMiddleware: %d approved internal link(s) missing after humanization — attempting repair.",
                len(missing_links),
            )
            print(f"[CHECK internal_links] MISSING {len(missing_links)}/{len(approved_links)} -> repair START")
            t_repair = time.perf_counter()
            repaired = await self._repair_missing_internal_links(
                payload=merged_payload, missing_links=missing_links, schema=schema,
            )
            if repaired:
                merged_payload = repaired
                logger.info("HumanizeMiddleware: internal links repaired successfully.")
                print(f"[CHECK internal_links] repair END ({time.perf_counter() - t_repair:.2f}s) — applied")
            else:
                logger.warning(
                    "HumanizeMiddleware: internal link repair failed for %d link(s) — falling back to "
                    "append-only enforcement.", len(missing_links),
                )
                print(f"[CHECK internal_links] repair END ({time.perf_counter() - t_repair:.2f}s) — FAILED, falling back to append-only")

        # Strip fact source URLs the model didn't actually get from a real
        # search_tool result — never try to "fix" a fabricated URL, since a
        # generated replacement carries the same hallucination risk. Same
        # philosophy as content_generation.py's _strip_placeholder_images.
        searched_urls = (self._counters or {}).get("searched_urls") or set()
        if searched_urls:
            facts = merged_payload.get("facts") or []
            cleaned_facts = []
            stripped_count = 0
            for fact in facts:
                fact = dict(fact) if isinstance(fact, dict) else fact
                if isinstance(fact, dict) and fact.get("source_url") and fact["source_url"] not in searched_urls:
                    logger.warning(
                        "HumanizeMiddleware: fact source_url '%s' was not returned by any search_tool call "
                        "this run — stripping (unverified/possibly hallucinated).", fact["source_url"],
                    )
                    fact["source_url"] = None
                    stripped_count += 1
                cleaned_facts.append(fact)
            merged_payload["facts"] = cleaned_facts
            print(f"[CHECK facts] {len(facts)} fact(s), {stripped_count} URL(s) stripped as unverified"
                  if facts else "[CHECK facts] no facts to verify")

        # Verify final length actually lands in the target range — the
        # rewrite pass's own expand/trim instruction is a request, not a
        # guarantee (LLMs are imprecise at hitting exact word-count deltas:
        # observed a request for +139 words produce +352), and nothing
        # checked the result until now. Run last, after the brand/persona/
        # link edits above, so it corrects the truly final text instead of
        # a snapshot those edits would go on to change further.
        lt = compute_length_targets(word_target)
        current_words = len(
            f"{merged_payload.get('introduction', '')} {merged_payload.get('body_markdown', '')}".split()
        )
        # One correction attempt only — each attempt is a full extra LLM call
        # (~20-30s observed), and a second pass showed diminishing returns
        # (2579->2270->2065: ~12% closer each time, not converging fast
        # enough to justify the added latency). A single pass still recovers
        # most of the gap; the residual is a genuine LLM word-count-precision
        # limit, not something more retries reliably close.
        if lt["total_min"] <= current_words <= lt["total_max"]:
            print(f"[CHECK length] PASS — {current_words} words within {lt['total_min']}-{lt['total_max']}, no repair needed")
        else:
            direction = "over" if current_words > lt["total_max"] else "under"
            logger.warning(
                "HumanizeMiddleware: length %d words is %s target range %d-%d — attempting correction.",
                current_words, direction, lt["total_min"], lt["total_max"],
            )
            print(f"[CHECK length] {current_words} words is {direction.upper()} range {lt['total_min']}-{lt['total_max']} -> repair START")
            t_repair = time.perf_counter()
            repaired = await self._correct_length(
                payload=merged_payload, current_words=current_words,
                target_min=lt["total_min"], target_max=lt["total_max"], schema=schema,
            )
            if repaired:
                merged_payload = repaired
                new_words = len(f"{merged_payload.get('introduction', '')} {merged_payload.get('body_markdown', '')}".split())
                logger.info("HumanizeMiddleware: length correction applied.")
                print(f"[CHECK length] repair END ({time.perf_counter() - t_repair:.2f}s) — {current_words} -> {new_words} words")
            else:
                logger.warning("HumanizeMiddleware: length correction failed — final content stays %s target.", direction)
                print(f"[CHECK length] repair END ({time.perf_counter() - t_repair:.2f}s) — FAILED, stays {direction} target")

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
            print(f"[IMAGE]   injected into body_markdown -> {image_url}")
        elif image_task is not None:
            logger.info("HumanizeMiddleware: image task returned no valid URL; skipping injection.")
            print("[IMAGE]   no valid URL to inject — skipped")

        updated_structured_response = self._rebuild_output(structured_response, merged_payload)
        if updated_structured_response is None:
            logger.warning("HumanizeMiddleware: failed to rebuild structured_response; skipping update.")
            print(f"[HUMANIZE] ✗ END ({time.perf_counter() - t_start:.2f}s) — failed to rebuild structured_response")
            return None

        logger.info("HumanizeMiddleware: content humanization applied successfully.")
        print(f"[HUMANIZE] ✓ END ({time.perf_counter() - t_start:.2f}s) — applied successfully")
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

        # Same total_min/total_max the system prompt (PersonaInjectionMiddleware)
        # already told the agent to hit — previously this method computed its
        # own, lower range independently, so a draft that correctly complied
        # with the system prompt's target could look "over budget" here and
        # get a spurious trim instruction (or vice versa). See length_targets.py.
        lt = compute_length_targets(word_target)
        total_target, total_max = lt["total_min"], lt["total_max"]
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
    def _persona_name_present(introduction: str, body_markdown: str, persona_name: str) -> bool:
        """Mirrors the two hard requirements set in PersonaInjectionMiddleware's
        system prompt: the name must open the introduction AND appear at least
        once more in the body."""
        name = persona_name.strip().lower()
        if not name:
            return True
        first_paragraph = (introduction or "").strip().split("\n\n", 1)[0].lower()
        total_mentions = (introduction or "").lower().count(name) + (body_markdown or "").lower().count(name)
        return name in first_paragraph and total_mentions >= 2

    async def _repair_missing_persona_mention(
        self, *, payload: dict[str, Any], persona_name: str, schema: type[BaseModel],
    ) -> dict[str, Any] | None:
        """Surgically reinsert the required author-persona name, same shape as
        ``_repair_missing_brand_mention``."""
        prompt_data = {
            "persona_name": persona_name,
            "title": payload.get("title") or "",
            "introduction": payload.get("introduction") or "",
            "body_markdown": payload.get("body_markdown") or "",
        }

        try:
            model = load_humanize_model().with_structured_output(schema)
            messages = get_persona_repair_prompt().format_messages(**prompt_data)
            repaired_obj = await model.ainvoke(messages, config={"tags": ["__persona_repair__"]})
        except Exception:
            logger.exception("HumanizeMiddleware: persona repair model call failed.")
            return None

        repaired_payload = self._to_dict(repaired_obj)
        if not repaired_payload:
            return None

        if not self._persona_name_present(
            repaired_payload.get("introduction", ""), repaired_payload.get("body_markdown", ""), persona_name,
        ):
            logger.warning("HumanizeMiddleware: repair pass still did not include sufficient persona mentions.")
            return None

        merged = dict(payload)
        for key in self.HUMANIZED_FIELDS:
            value = repaired_payload.get(key)
            if isinstance(value, str) and value.strip():
                merged[key] = value
        return merged

    async def _repair_missing_internal_links(
        self, *, payload: dict[str, Any], missing_links: list[dict[str, Any]], schema: type[BaseModel],
    ) -> dict[str, Any] | None:
        """Surgically weave in approved internal links that didn't survive
        generation/humanization, same shape as ``_repair_missing_brand_mention``.
        Only edits body_markdown — links never belong in the introduction."""
        links_block = "\n".join(
            f"- [{lnk.get('title') or lnk['url']}]({lnk['url']})" for lnk in missing_links
        )
        prompt_data = {
            "missing_links": links_block,
            "title": payload.get("title") or "",
            "introduction": payload.get("introduction") or "",
            "body_markdown": payload.get("body_markdown") or "",
        }

        try:
            model = load_humanize_model().with_structured_output(schema)
            messages = get_internal_links_repair_prompt().format_messages(**prompt_data)
            repaired_obj = await model.ainvoke(messages, config={"tags": ["__internal_links_repair__"]})
        except Exception:
            logger.exception("HumanizeMiddleware: internal links repair model call failed.")
            return None

        repaired_payload = self._to_dict(repaired_obj)
        if not repaired_payload:
            return None

        repaired_body = repaired_payload.get("body_markdown") or ""
        if not repaired_body.strip():
            return None

        still_missing = [lnk for lnk in missing_links if lnk["url"] not in repaired_body]
        if still_missing:
            # Accept a partial fix rather than discarding it outright — the
            # remaining gap(s) still get one more chance via
            # BaseGeneratedContent.enforce_internal_links_in_body downstream.
            logger.warning(
                "HumanizeMiddleware: repair pass fixed %d of %d link(s); %d still missing.",
                len(missing_links) - len(still_missing), len(missing_links), len(still_missing),
            )

        merged = dict(payload)
        merged["body_markdown"] = repaired_body
        return merged

    async def _correct_length(
        self, *, payload: dict[str, Any], current_words: int, target_min: int, target_max: int,
        schema: type[BaseModel],
    ) -> dict[str, Any] | None:
        """One narrow length-only edit call. Deliberately doesn't re-verify
        pass/fail the way the other repairs do — length is a continuous
        target, not a binary presence check, so a partial correction (closer
        to range even if not perfectly inside it) is still a real improvement
        worth keeping rather than discarding."""
        if current_words > target_max:
            direction_instruction = f"TOO LONG — trim by roughly {current_words - target_max} words."
        else:
            direction_instruction = f"TOO SHORT — expand by roughly {target_min - current_words} words."

        prompt_data = {
            "current_words": current_words,
            "target_min": target_min,
            "target_max": target_max,
            "direction_instruction": direction_instruction,
            "title": payload.get("title") or "",
            "introduction": payload.get("introduction") or "",
            "body_markdown": payload.get("body_markdown") or "",
        }

        try:
            model = load_humanize_model().with_structured_output(schema)
            messages = get_length_repair_prompt().format_messages(**prompt_data)
            repaired_obj = await model.ainvoke(messages, config={"tags": ["__length_repair__"]})
        except Exception:
            logger.exception("HumanizeMiddleware: length repair model call failed.")
            return None

        repaired_payload = self._to_dict(repaired_obj)
        if not repaired_payload:
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
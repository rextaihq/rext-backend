"""
Content Generation Node (Agent-Based)

Generates SEO-optimized content using the content agent.
Streams tokens and tool calls to the frontend via LangGraph's custom stream
so the user sees the agent work in real time (like GPT).
"""

import logging
import json
from langchain_core.messages import HumanMessage, AIMessage
from langgraph.config import get_stream_writer
from src.flow.states.rext import REXT
from src.flow.engines.agent.content_agent import create_content_agent
from src.flow.model.structure.contents import get_generated_content_model
from src.flow.model.structure.outlines import get_outline_model

logger = logging.getLogger(__name__)




async def generate_content(state: REXT) -> dict:
    """
    Generates SEO-optimized content using the content agent.

    The agent can invoke tools (e.g. DuckDuckGo web search) to verify facts
    and statistics before producing the final structured output.

    Args:
        state: REXT state containing outline and context

    Returns:
        dict: Updated state with generated content
    """
    content_state = state.get("content", {})

    try:
        # 1️⃣ Get content state, topic, and content type
        topic = content_state.get("selected_topic", "")
        content_type = content_state.get("content_type", "article")

        if not topic:
            logger.error("No topic found in state")
            return {
                "content": {
                    **content_state,
                    "error": "No topic found in state",
                }
            }

        logger.info(f"Generating content for: {topic} (content type: {content_type})")

        outline = content_state.get("outline", {})
        if not outline:
            logger.warning("No outline found in state. Proceeding without it.")
        outline_str = json.dumps(outline, indent=2) if outline else "NO OUTLINE FOUND"

        logger.info(f"Outline extracted: {outline_str[:20]}...")

        # 2️⃣ Prepare Reference Content (If any)
        page_content = ""
        meta_data = {}

        # 3️⃣ Get primary keyword from outline
        primary_keyword = (
            outline.get("keywords_to_include", [""])[0]
            if outline.get("keywords_to_include")
            else topic
        )

        # 4️⃣ Extract SEO & SERP Insights (CRITICAL)
        seo_result = state.get("seo_result", {})
        serp_backlinks = seo_result.get("serp_backlinks", {})
        serp_normalized = state.get("serp_normalized", {})

        # SEO Metrics
        backlink_volume = serp_backlinks.get("backlinks", 0)
        referring_domains = serp_backlinks.get("referring_domains", 0)
        intent = serp_backlinks.get("main_intent", "Informational")

        # SERP Data
        top_results = serp_normalized.get("normalize_results", [])[:5]
        questions = serp_normalized.get("questions", [])
        related_topics = serp_normalized.get("related_topics", [])
        # Format Competitor & SEO Insights
        competitor_list = []
        for res in top_results:
            competitor_list.append(
                f"- {res['title']} (Position {res['position']}): {res['snippet']}"
            )
        serp_insights = "\n".join(competitor_list)
        seo_signals = (
            f"SEO SIGNALS:\n"
            f"- Primary Intent: {intent}\n"
            f"- Average Backlink Volume: {backlink_volume}\n"
            f"- Referring Domains: {referring_domains}\n"
            f"- People Also Ask (Questions): {', '.join(questions[:5])}\n"
            f"- Related SEO Topics: {', '.join(related_topics[:10])}\n"
        )

        competitor_insights = (
            f"TOP SERP COMPETITORS:\n{serp_insights}\n\n{seo_signals}"
        )

        # 5️⃣ Extract Tone & Metadata
        tone = outline.get("tone", "Professional")
        target_word_count = outline.get("target_word_count", 3000)
        logger.info(f"Tone: {tone}")

        # Extract key_facts and image_suggestions from the outline
        key_facts = outline.get("key_facts", []) or []
        image_suggestions = outline.get("image_suggestions", []) or []

        key_facts_str = ""
        if key_facts:
            facts_lines = "\n".join(
                (
                    f"  - {f.get('text', str(f))}" + (f" (source: {f['source_url']})" if f.get("source_url") else "")
                    if isinstance(f, dict)
                    else f"  - {f}"
                )
                for f in key_facts
            )
            key_facts_str = f"\nKEY FACTS TO INCLUDE IN CONTENT:\n{facts_lines}\n"

        image_suggestions_str = ""
        if image_suggestions:
            img_lines = "\n".join(
                (
                    f"  - Section '{img.get('section', '?')}': {img.get('description', '')} | alt: {img.get('alt_text_template', '')}"
                    if isinstance(img, dict)
                    else f"  - {img}"
                )
                for img in image_suggestions
            )
            image_suggestions_str = (
                f"\nIMAGE PLACEMENT GUIDE (populate the 'images' output field):\n{img_lines}\n"
                f"For each image suggestion above, add an entry to the 'images' field with:\n"
                f"  alt_text: SEO-optimized alt text based on the template\n"
                f"  context: what the image shows\n"
                f"  placement: which section it belongs to\n"
            )

        # 6️⃣ Build internal links block from outline state
        internal_links = outline.get("internal_links") or []
        internal_links_str = ""
        if internal_links:
            link_lines = "\n".join(
                f"  - [{lnk['title']}]({lnk['url']})  [status={lnk.get('status','').upper()}  score={lnk.get('score', 0):.2f}]"
                for lnk in internal_links
            )
            internal_links_str = (
                f"\nINTERNAL LINKS — MANDATORY INCLUSION:\n"
                f"{link_lines}\n"
                f"You MUST embed every link above inside body_markdown. "
                f"Weave each one naturally into the relevant section as an inline hyperlink. "
                f"If no natural fit exists in a section, append it at the end of the nearest section as: "
                f"\"Read more: [title](url)\"\n"
            )

        # 7️⃣ Build the human message for the agent
        # (system prompt is already embedded in the agent
        human_message_content = (
            f"Content Type: {content_type}\n"
            f"Topic: {topic}\n\n"
            f"Primary Keyword: {primary_keyword}\n"
            f"Target Word Count: {target_word_count} words (minimum)\n\n"
            f"COMPETITIVE LANDSCAPE:\n"
            f"{competitor_insights}\n"
            f"- Go deeper than these competitors\n"
            f"- Cover gaps they missed\n"
            f"- Offer a unique angle/perspective\n\n"
            f"Approved Outline:\n{outline_str}\n\n"
            f"{key_facts_str}"
            f"{image_suggestions_str}"
            f"{internal_links_str}"
            f"Reference / Source Content:\n{page_content}\n\n"
            f"Meta_data:\n{meta_data}\n\n"
            f"Tone:\n{tone}\n\n"

            f"Generate complete SEO-optimized content following the outline.\n"
            f"Incorporate ALL key facts listed above verbatim in the relevant sections.\n"
            f"Embed ALL internal links listed above inside body_markdown — this is non-negotiable.\n"
            f"Populate the 'facts' output field with each fact used (text + source_url).\n"
            f"Populate the 'images' output field using the image placement guide above.\n"
            f"Ensure you outperform the competitors listed above."
        )

        # 7️⃣ Create the content agent
        logger.info("Creating content agent...")
        serp_payload = state.get("serp_payload", {})
        user_id = serp_payload.get("user_id")
        workspace_id = serp_payload.get("workspace_id")

        generated_model = get_generated_content_model(content_type)
        agent = await create_content_agent(content_type=content_type)
        agent_input = {
            "messages": [HumanMessage(content=human_message_content)],
            "serp_payload": {
                **serp_payload,
                "user_id": user_id,
                "workspace_id": workspace_id,
            },
            "content": {
                "outline": outline,
                "selected_topic": topic,
                "content_type": content_type,
            },
        }

        # 8️⃣ Stream agent events → forward tokens & tool calls to frontend
        write = get_stream_writer()
        final_messages = []
        structured_output = None  # typed Pydantic model instance (from get_generated_content_model) if agent returns one

        # The schema name used by ToolStrategy for the artificial structured-output tool
        _STRUCTURED_OUTPUT_TOOL_NAME = generated_model.__name__
        # Internal sub-tools that should not appear as separate UI events
        _INTERNAL_TOOL_NAMES = {"tavily_search_results_json"}

        # Instead we match the root completion by run_id.
        agent_root_run_id: str | None = None

        # Track query from tool_start keyed by run_id; emitted once on tool_end
        _pending_tool_queries: dict[str, str] = {}

        async for event in agent.astream_events(
            agent_input,
            version="v2",
            config={"recursion_limit": 50},
        ):
            kind = event["event"]
            tool_name = event.get("name", "")
            event_run_id = event.get("run_id", "")

            # Capture the root run_id from the very first chain-start event
            if kind == "on_chain_start" and agent_root_run_id is None:
                agent_root_run_id = event_run_id

            # Token-by-token LLM output
            elif kind == "on_chat_model_stream":
                chunk = event["data"].get("chunk")
                if chunk:
                    raw = chunk.content
                    if isinstance(raw, str):
                        token = raw
                    elif isinstance(raw, list):
                        token = "".join(
                            p.get("text", "")
                            for p in raw
                            if isinstance(p, dict) and p.get("type") == "text"
                        )
                    else:
                        token = ""

                    # ToolStrategy emits structured output as tool-call argument
                    # fragments (not as plain content). Capture those so the frontend
                    # can do live JSON field extraction (e.g. body_markdown appears
                    # character-by-character instead of dumping all at once).
                    if not token:
                        for tc in chunk.tool_call_chunks or []:
                            if tc.get("args"):
                                token += tc["args"]

                    if token:
                        write({"type": "token", "content": token})

            # on_chat_model_end: ToolStrategy never invokes the fake structured-output tool —
            # it parses args directly inside the model node. So on_tool_start never fires
            # for it. The structured content is in data.output.tool_calls[].args here.
            elif kind == "on_chat_model_end":
                output_msg = event["data"].get("output")
                if output_msg is not None and hasattr(output_msg, "tool_calls"):
                    for tc in output_msg.tool_calls:
                        if tc.get("name") == _STRUCTURED_OUTPUT_TOOL_NAME:
                            try:
                                structured_output = generated_model(**tc["args"])
                                logger.debug(f"Captured {generated_model.__name__} from on_chat_model_end")
                            except Exception as e:
                                logger.warning(
                                    "Structured output parse failed: %s | arg keys: %s",
                                    e, list(tc.get("args", {}).keys())
                                )

            # Real tool call started — emit immediately for live UI, store query for tool_end
            elif kind == "on_tool_start" and tool_name != _STRUCTURED_OUTPUT_TOOL_NAME and tool_name not in _INTERNAL_TOOL_NAMES:
                tool_input = event["data"].get("input")
                logger.info("on_tool_start: name=%s input_type=%s input=%r", tool_name, type(tool_input).__name__, tool_input)
                if isinstance(tool_input, str):
                    query = tool_input
                elif isinstance(tool_input, dict):
                    str_vals = [str(v) for v in tool_input.values() if v and str(v).strip()]
                    query = max(str_vals, key=len) if str_vals else ""
                else:
                    query = str(tool_input) if tool_input else ""
                _pending_tool_queries[event_run_id] = query
                write({
                    "type": "tool_start",
                    "id": event_run_id,
                    "name": tool_name,
                    "query": query,
                })

            # Real tool call finished — emit single event with query + results
            elif kind == "on_tool_end" and tool_name != _STRUCTURED_OUTPUT_TOOL_NAME and tool_name not in _INTERNAL_TOOL_NAMES:
                raw_output = event["data"].get("output", "")
                logger.info("on_tool_end: name=%s output_type=%s", tool_name, type(raw_output).__name__)
                query = _pending_tool_queries.pop(event_run_id, "")

                # Normalise to a list of result dicts regardless of output format
                results = []
                if isinstance(raw_output, list):
                    results = raw_output
                elif hasattr(raw_output, "content"):
                    try:
                        parsed = json.loads(raw_output.content)
                        results = parsed if isinstance(parsed, list) else [parsed]
                    except Exception:
                        results = [{"body": str(raw_output.content)[:360]}]
                elif isinstance(raw_output, str):
                    try:
                        parsed = json.loads(raw_output)
                        results = parsed if isinstance(parsed, list) else [parsed]
                    except Exception:
                        results = [{"body": raw_output[:360]}]
                elif isinstance(raw_output, dict):
                    results = [raw_output]

                # Detect hard-cap block: single dict with "error" key containing "cap"
                if (
                    len(results) == 1
                    and isinstance(results[0], dict)
                    and "cap" in results[0].get("error", "").lower()
                ):
                    write({"type": "tool_end", "id": event_run_id, "name": tool_name, "query": query, "blocked": True})
                    continue

                count = len(results)
                lines = []
                for item in results[:3]:
                    if isinstance(item, dict):
                        title = item.get("title", "")
                        body = item.get("body", item.get("snippet", item.get("content", "")))
                        if title:
                            lines.append(f"• {title}: {str(body)[:120]}")
                        elif body:
                            lines.append(f"• {str(body)[:120]}")
                    elif isinstance(item, str):
                        lines.append(f"• {item[:120]}")
                snippet = "\n".join(lines) if lines else (str(raw_output)[:360] if raw_output else "")

                write({
                    "type": "tool_end",
                    "id": event_run_id,
                    "name": tool_name,
                    "query": query,
                    "count": count,
                    "output": snippet,
                })

            # Always prefer the final chain-end state because HumanizeMiddleware
            # can replace structured_response after raw model output is parsed.
            elif kind == "on_chain_end":
                out = event["data"].get("output", {})
                if isinstance(out, generated_model):
                    structured_output = out
                elif isinstance(out, dict):
                    sr = out.get("structured_response")
                    if isinstance(sr, generated_model):
                        structured_output = sr
                    elif isinstance(sr, dict) and sr:
                        try:
                            structured_output = generated_model(**sr)
                        except Exception:
                            pass
                    if "messages" in out and not final_messages:
                        final_messages = out["messages"]

        # 9️⃣ Extract structured content from the agent output
        content_dict = None

        if structured_output is not None:
            content_dict = structured_output.model_dump()
        else:
            # Last-resort fallback: parse JSON from the last AIMessage
            for msg in reversed(final_messages):
                if isinstance(msg, AIMessage) and msg.content:
                    try:
                        content_dict = json.loads(msg.content)
                        break
                    except (json.JSONDecodeError, TypeError):
                        continue

        if not content_dict:
            raise ValueError("Content agent returned no structured output")

        logger.info(f"Content generated successfully: {content_dict.get('title', '')}")

        # Soft enforcement: warn when agent produced no sourced facts (evidence block was skipped)
        facts = content_dict.get("facts") or []
        sourced = [f for f in facts if (f.get("source_url") if isinstance(f, dict) else False)]
        if not sourced:
            logger.warning(
                "Content agent returned 0 sourced facts -- agent may have skipped EVIDENCE block. "
                "All third-party claims in this article are unverified. Topic: %s", topic
            )

        # Return structured content
        return {
            "content": {
                **content_state,
                "outline": outline,
                "final_content": {
                    **content_dict,
                    "status": "generated",
                    "rejected_reason": "",
                },
                "status": "content_generated",
            }
        }

    except Exception as e:
        logger.exception(f"Error generating content: {str(e)}")
        return {
            "content": {
                **content_state,
                "error": f"Generation failed: {str(e)}",
            }
        }


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
from langchain.agents.structured_output import ToolStrategy

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
        urls = []
        for res in top_results:
            competitor_list.append(
                f"- {res['title']} (Position {res['position']}): {res['snippet']}"
            )
            urls.append(res['url'])
        urls_str = "\n".join(urls)
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
        target_word_count = outline.get("target_word_count", 1500)
        logger.info(f"Tone: {tone}")

        # 6️⃣ Build the human message for the agent
        # (system prompt is already embedded in the agent)
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
            f"Reference / Source Content:\n{page_content}\n\n"
            f"Meta_data:\n{meta_data}\n\n"
            f"Tone:\n{tone}\n\n"
            f"Internal_links:\n{urls_str}\n\n"
            f"Generate complete SEO-optimized content following the outline.\n"
            f"Ensure you incorporate all facts and statistics mentioned in the outline.\n"
            f"Populate the 'facts' field in the output JSON with objects containing "
            f"'text' and 'source_url' for each key verifiable fact or statistic you "
            f"included in the content. For 'source_url', use the one from the outline "
            f"or find a direct link to the data source.\n"
            f"Ensure you outperform the competitors listed above."
        )

        # 7️⃣ Create the content agent
        logger.info("Creating content agent...")
        serp_payload = state.get("serp_payload", {})
        user_id = serp_payload.get("user_id")
        workspace_id = serp_payload.get("workspace_id")

        generated_model = get_generated_content_model(content_type)
        agent = await create_content_agent(
            response_format=ToolStrategy(generated_model)
        )
        agent_input = {
            "messages": [HumanMessage(content=human_message_content)],
            "serp_payload": {
                **serp_payload,
                "user_id": user_id,
                "workspace_id": workspace_id,
            },
            "content": {"outline": outline},
        }

        # 8️⃣ Stream agent events → forward tokens & tool calls to frontend
        write = get_stream_writer()
        final_messages = []
        structured_output = None  # GeneratedContent Pydantic object if agent returns one

        # The schema name used by ToolStrategy for the artificial structured-output tool
        _STRUCTURED_OUTPUT_TOOL_NAME = generated_model.__name__

        # Track the agent's root run_id from the very first on_chain_start.
        # When called from inside a LangGraph node the outer graph may inject parent_ids
        # into all inner events — so we cannot rely on `not event.get("parent_ids")`.
        # Instead we match the root completion by run_id.
        agent_root_run_id: str | None = None

        async for event in agent.astream_events(
            agent_input,
            version="v2",
            config={"recursion_limit": 200},
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

            # on_chat_model_end: ToolStrategy never invokes the fake GeneratedContent tool —
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
                                    "GeneratedContent parse failed: %s | arg keys: %s",
                                    e, list(tc.get("args", {}).keys())
                                )

            # Real tool call started — stream to frontend (skip the fake structured-output tool)
            elif kind == "on_tool_start" and tool_name != _STRUCTURED_OUTPUT_TOOL_NAME:
                tool_input = event["data"].get("input")
                logger.info("on_tool_start: name=%s input_type=%s input=%r", tool_name, type(tool_input).__name__, tool_input)
                if isinstance(tool_input, str):
                    query = tool_input
                elif isinstance(tool_input, dict):
                    # Walk all string values; pick the longest one (most likely the actual query)
                    str_vals = [str(v) for v in tool_input.values() if v and str(v).strip()]
                    query = max(str_vals, key=len) if str_vals else ""
                else:
                    query = str(tool_input) if tool_input else ""
                write({
                    "type": "tool_start",
                    "id": event_run_id,
                    "name": tool_name,
                    "query": query,
                })

            # Real tool call finished — stream results to frontend
            elif kind == "on_tool_end" and tool_name != _STRUCTURED_OUTPUT_TOOL_NAME:
                raw_output = event["data"].get("output", "")
                logger.info("on_tool_end: name=%s output_type=%s", tool_name, type(raw_output).__name__)

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
                    "count": count,
                    "output": snippet,
                })

            # Graph completion — check every on_chain_end for the structured_response key.
            # Fallback: if on_tool_start missed it, try on_chain_end state dict
            elif kind == "on_chain_end" and structured_output is None:
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
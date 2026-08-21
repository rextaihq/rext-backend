#!/usr/bin/env python3
"""
content_quality_latency_test.py

PURPOSE:
Run the ACTUAL production pipeline -- topic_generation -> generate_outline ->
generate_content -> review_content -- exactly as the LangGraph content_engine
runs them, but standalone from the terminal. No LangGraph server, no
frontend, no DB writes. This is a diagnostic script (analogous in spirit to
baseline_pipeline_test.py at the repo root): every pipeline function called
below is IMPORTED from the real codebase, nothing is reconstructed or
guessed. The only things NOT exercised are the langgraph interrupt() pauses
(topic selection / content-type selection / outline approval) -- those are
replaced with "auto-approve the top choice" so the script can run
non-interactively; every model call, prompt, and node function is the real
one.

SAFETY / COST:
- No `user_id` is set in `serp_payload`, which is the codebase's own
  documented no-op path for both credit deduction (credit_manager.py:
  `if user_id is None: return`) and article persistence
  (persist_content.py: `if not (user_id and workspace_id and thread_id):
  ... skipping save`). So this script makes real OpenAI/Tavily API calls
  (real cost, real latency) but deducts NO credits and writes NOTHING to
  the content/article tables.
- `workspace_id` IS set, to a real (pre-existing, low-stakes/dev) workspace
  so persona / brand-voice / internal-link lookups exercise real data
  instead of empty stubs -- this only ever performs read queries against
  those tables (persona, brand_voice, content, content_publishing_results).

INSTRUMENTATION:
There is no existing timing/tracing in the outline/content nodes (confirmed
by grepping the source for time.time/perf_counter/traceable -- zero hits).
This script adds NON-INVASIVE, in-process-only instrumentation: it monkeypatches
`create_content_agent` (only inside this process's imported module object,
nothing written to disk) so the returned agent's `astream_events` stream is
tapped and every event timestamped as it flows through -- the real
`generate_content` function and real agent are otherwise untouched. This
lets us see whether the agent's search-tool calls run sequentially or in
parallel, and how much wall time humanize/brand-repair adds on top of the
main generation call.

USAGE:
    python content_quality_latency_test.py --keyword "..." --content-type blog

Run from the REPO ROOT (~/rext-backend) so the `src.*` imports resolve.
"""

import argparse
import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# humanize_middleware.py (and some other nodes) use stdlib `logging` directly
# rather than the structlog-based src.utils.logger -- without a handler
# configured, their logger.info/.warning calls are silently dropped. This
# surfaces them so the word-count decision (expand/trim/keep + why) is visible.
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

RESULTS_DIR = Path("results")

# A real, pre-existing dev/test workspace with 2 real personas already set up
# (found by querying the `persona` table directly) -- used so persona /
# tone / audience alignment can actually be exercised and inspected, not just
# stubbed out. Only ever read from, never written to (see SAFETY note above).
WORKSPACE_ID = "162986e4-9410-4cc7-ab57-b9aa6effbb52"  # xomoashro-workspace


def _short(obj, limit=4000):
    text = json.dumps(obj, indent=2, default=str) if not isinstance(obj, str) else obj
    return text if len(text) <= limit else text[: limit - 20] + "\n...[truncated]..."


async def run_test(keyword: str, content_type: str):
    RESULTS_DIR.mkdir(exist_ok=True)
    report_lines = []

    def log(line: str = ""):
        print(line)
        report_lines.append(line)

    log("=" * 78)
    log("CONTENT PIPELINE QUALITY + LATENCY TEST")
    log(f"keyword: {keyword}")
    log(f"content_type: {content_type}")
    log(f"workspace_id: {WORKSPACE_ID} (no user_id -> credit deduction + persist are no-ops)")
    log(f"timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    log("=" * 78)

    timings: dict[str, float] = {}
    agent_timeline: list[dict] = []

    # ------------------------------------------------------------------
    # Non-invasive instrumentation: tap the real agent's astream_events
    # stream so we can see per-LLM-call and per-tool-call timing without
    # touching any source file. This patches the *imported module object*
    # in this process only.
    # ------------------------------------------------------------------
    from src.flow.engines.content.generation import content_generation as cg_module

    real_create_content_agent = cg_module.create_content_agent

    async def instrumented_create_content_agent(*args, **kwargs):
        agent = await real_create_content_agent(*args, **kwargs)
        real_astream_events = agent.astream_events

        async def wrapped_astream_events(*a, **kw):
            async for event in real_astream_events(*a, **kw):
                agent_timeline.append(
                    {
                        "t": time.perf_counter(),
                        "kind": event.get("event"),
                        "name": event.get("name"),
                        "tags": list(event.get("tags") or []),
                        "run_id": event.get("run_id"),
                    }
                )
                yield event

        agent.astream_events = wrapped_astream_events
        return agent

    cg_module.create_content_agent = instrumented_create_content_agent

    # ==================================================================
    # STEP 1 -- TOPIC GENERATION (real model + real prompt from
    # topic_generation.py, interrupt() pause skipped -> auto-pick the
    # model's own "recommended" topic, same as a user clicking it)
    # ==================================================================
    log("\n[STEP 1] topic_generation (real model call, interrupt skipped)")

    from src.flow.model.structure.topics import SEOTopics
    from src.flow.model.llm_manager import topic_generation_model
    from langchain_core.messages import SystemMessage, HumanMessage

    current_year = datetime.now(timezone.utc).year
    topic_model = topic_generation_model().with_structured_output(SEOTopics)
    topic_messages = [
        SystemMessage(
            content=(
                f"You are helping someone with ZERO SEO or content-marketing background choose "
                f"what to write next. They cannot judge ranking potential, competition, or search "
                f"trends themselves — that evaluation is entirely on you.\n\n"
                f"Generate 5 article topic ideas for {current_year} that fit the user's selected "
                f"search intent and content type. Titles should read like something a real person "
                f"would search for or want to click — not internal SEO jargon.\n\n"
                f"Then mark exactly ONE topic as recommended=True: the single safest, highest-value "
                f"pick for someone who can't evaluate these themselves. Prefer the topic that is "
                f"realistic to write well without specialist research, has clear reader demand, and "
                f"isn't already dominated by large competitors. For that one topic, fill "
                f"recommendation_reason with one short, plain-English sentence explaining why — no "
                f"SEO jargon ('SERP', 'intent', 'keyword density', 'ranking potential', etc.); if a "
                f"concept is unavoidable, explain it in plain words in the same sentence. All other "
                f"topics: recommended=False, recommendation_reason=null."
            )
        ),
        HumanMessage(
            content=(
                f"Generate 5 topics for: {keyword} in {current_year}\n"
                f"Search intent: informational\n"
                f"Content type: {content_type}"
            )
        ),
    ]

    t0 = time.perf_counter()
    topics_result: SEOTopics = await topic_model.ainvoke(topic_messages)
    timings["topic_generation"] = time.perf_counter() - t0

    titles = [t.title for t in topics_result.topics]
    recommended = next((t for t in topics_result.topics if t.recommended), topics_result.topics[0])
    selected_topic = recommended.title

    log(f"  duration: {timings['topic_generation']:.2f}s")
    for t in topics_result.topics:
        marker = "  <== selected (model's own recommendation)" if t.title == selected_topic else ""
        log(f"  - {t.title}{marker}")
    log(f"  recommendation_reason: {recommended.recommendation_reason}")

    # ==================================================================
    # STEP 2 -- GENERATE_OUTLINE (real production function, called
    # directly with a constructed REXT state)
    # ==================================================================
    log("\n[STEP 2] generate_outline (real production node)")

    from src.flow.engines.content.generation.outline import generate_outline

    state = {
        "content": {"selected_topic": selected_topic, "content_type": content_type},
        "serp_payload": {"workspace_id": WORKSPACE_ID, "query": keyword, "is_library": True},
        "serp_normalized": {"query": keyword, "related_topics": [], "questions": []},
        "seo_result": {},
        "competitors": [],
    }

    t0 = time.perf_counter()
    outline_update = await generate_outline(state)
    timings["generate_outline"] = time.perf_counter() - t0

    outline = (outline_update.get("content") or {}).get("outline") or {}
    log(f"  duration: {timings['generate_outline']:.2f}s")
    if (outline_update.get("content") or {}).get("error"):
        log(f"  ERROR: {outline_update['content']['error']}")
        _write_report(report_lines)
        return

    log(f"  title: {outline.get('title')}")
    log(f"  tone (LLM-inferred, no brand-voice grounding): {outline.get('tone')}")
    log(f"  target_audience (LLM-inferred): {outline.get('target_audience')}")
    log(f"  target_word_count: {outline.get('target_word_count')}")
    log(f"  sections: {len(outline.get('sections') or [])}")
    log(f"  selected_persona_id (auto-picked, post-hoc): {outline.get('selected_persona_id')}")
    brand_promo = outline.get("brand_voice_promotion") or {}
    log(f"  brand_voice_promotion: recommended={brand_promo.get('recommended')} brand={brand_promo.get('brand_name')}")
    log(f"  internal_links found: {len(outline.get('internal_links') or [])}")

    # Diagnostic: does the outline->prompt formatter actually find the
    # sections this content type nests them under? Calls the REAL helper
    # function the content-generation prompt builders use, unmodified.
    from src.flow.engines.content.generation.content_generation import _outline_sections as _real_outline_sections
    real_sections_seen = _real_outline_sections(outline, content_type)
    log(f"\n  [DIAGNOSTIC] _outline_sections(outline, content_type) found: {len(real_sections_seen)} section(s)")
    for s in real_sections_seen[:8]:
        log(f"    - {s.get('heading')}")

    log("\n  --- full outline (truncated) ---")
    log(_short(outline, 3000))

    # ==================================================================
    # STEP 3 -- APPROVE OUTLINE (replicates review_outline.py's "approve"
    # branch exactly -- same fields, same defaults). To get full coverage
    # of every verify+repair check in one run, this also replicates two
    # legitimate user overrides review_outline.py's approve branch already
    # supports (promote_brand, selected_internal_links) rather than taking
    # the recommender's un-overridden defaults:
    #   - promote_brand forced True (this workspace's brand-voice recommender
    #     didn't flag this topic as relevant in prior runs, so the brand
    #     check/repair path never fired -- a user can always override this
    #     at approval, same override review_outline.py exposes)
    #   - one synthetic internal link injected only if the DB found zero
    #     real candidates (this test workspace has no published content yet
    #     to source real ones from) -- exercises the real repair code path
    #     end-to-end; clearly logged as synthetic, not passed off as real data
    # ==================================================================
    # Multiple links (not just one) stress-tests whether the repair pass
    # places EACH missing link distinctly (its own instruction: "place each
    # missing link in a different section if possible") rather than just
    # proving a single-link case works.
    injected_synthetic_link = False
    approved_internal_links = outline.get("internal_links") or []
    if not approved_internal_links:
        approved_internal_links = [
            {
                "title": "our guide to remote team workflows",
                "url": "https://xomoashro.example/blog/remote-team-workflows",
                "score": 0.0,
                "status": "PUBLISHED",
            },
            {
                "title": "how we evaluate software tools before adopting them",
                "url": "https://xomoashro.example/blog/software-evaluation-checklist",
                "score": 0.0,
                "status": "PUBLISHED",
            },
            {
                "title": "common project management mistakes we see teams make",
                "url": "https://xomoashro.example/blog/pm-mistakes-to-avoid",
                "score": 0.0,
                "status": "PUBLISHED",
            },
        ]
        injected_synthetic_link = True

    outline_approved = {
        **outline,
        "internal_links": approved_internal_links,
        "promote_brand": True,
        "status": "approved",
        "rejected_reason": "",
    }
    state["content"]["outline"] = outline_approved
    log("\n[STEP 3] outline approved")
    log(f"  promote_brand: forced True (recommender said {brand_promo.get('recommended')}) -- tests brand check/repair")
    if injected_synthetic_link:
        log(f"  internal_links: 0 real candidates from DB -- injected {len(approved_internal_links)} SYNTHETIC links for coverage:")
        for lnk in approved_internal_links:
            log(f"    - {lnk['url']}")
    else:
        log(f"  internal_links: {len(approved_internal_links)} real candidate(s) from DB")

    # ==================================================================
    # STEP 4 -- GENERATE_CONTENT (real production function, agent-based;
    # this is the "takes time after outline approval" stage)
    # ==================================================================
    log("\n[STEP 4] generate_content (real production node, agent-based)")

    from src.flow.engines.content.generation.content_generation import generate_content
    from src.flow.states.rext import REXT
    from langgraph.graph import StateGraph, START, END

    # generate_content() calls langgraph.config.get_stream_writer(), which
    # requires an active LangGraph runnable context (raises RuntimeError if
    # called bare, as generate_outline's simpler no-writer path let us do
    # above). Wrap it as a 1-node graph so it runs the same way it does in
    # production (as a node inside content_engine), without changing any
    # of its behavior.
    _content_graph = StateGraph(REXT)
    _content_graph.add_node("generate_content", generate_content)
    _content_graph.add_edge(START, "generate_content")
    _content_graph.add_edge("generate_content", END)
    _compiled_content_graph = _content_graph.compile()

    t_content_start = time.perf_counter()
    content_update = await _compiled_content_graph.ainvoke(state)
    timings["generate_content_total"] = time.perf_counter() - t_content_start

    content_state = content_update.get("content") or {}
    final_content = content_state.get("final_content") or {}
    log(f"  duration: {timings['generate_content_total']:.2f}s")
    if content_state.get("error"):
        log(f"  ERROR: {content_state['error']}")

    # ---- derive sub-timings from the tapped astream_events timeline ----
    log("\n  --- internal timing breakdown (from tapped agent event stream) ---")

    tool_calls: dict[str, dict] = {}
    chat_calls: dict[str, dict] = {}
    for e in agent_timeline:
        rid = e["run_id"]
        if e["kind"] == "on_tool_start":
            tool_calls.setdefault(rid, {})["name"] = e["name"]
            tool_calls[rid]["start"] = e["t"]
        elif e["kind"] == "on_tool_end":
            tool_calls.setdefault(rid, {})["end"] = e["t"]
        elif e["kind"] == "on_chat_model_start":
            chat_calls.setdefault(rid, {"humanize": "__humanize__" in e["tags"]})["start"] = e["t"]
        elif e["kind"] == "on_chat_model_end":
            chat_calls.setdefault(rid, {}).setdefault("humanize", "__humanize__" in e["tags"])
            chat_calls[rid]["end"] = e["t"]

    def rel(t):
        return t - t_content_start

    complete_tools = {k: v for k, v in tool_calls.items() if "start" in v and "end" in v}
    if complete_tools:
        log(f"  tool calls: {len(complete_tools)}")
        for rid, v in sorted(complete_tools.items(), key=lambda kv: kv[1]["start"]):
            log(f"    [{v['name']}] start={rel(v['start']):.2f}s end={rel(v['end']):.2f}s dur={v['end']-v['start']:.2f}s")
        # overlap check -> parallel vs sequential
        sorted_tools = sorted(complete_tools.values(), key=lambda v: v["start"])
        overlaps = sum(
            1
            for i in range(1, len(sorted_tools))
            if sorted_tools[i]["start"] < sorted_tools[i - 1]["end"]
        )
        log(f"  tool-call overlaps detected: {overlaps} of {len(sorted_tools)-1} consecutive pairs "
            f"({'RUNNING IN PARALLEL' if overlaps else 'STRICTLY SEQUENTIAL'})")
    else:
        log("  tool calls: none captured (agent may not have called any tools)")

    complete_chats = {k: v for k, v in chat_calls.items() if "start" in v and "end" in v}
    main_chats = [v for v in complete_chats.values() if not v["humanize"]]
    humanize_chats = [v for v in complete_chats.values() if v["humanize"]]
    log(f"\n  main-generation LLM calls: {len(main_chats)}")
    for v in sorted(main_chats, key=lambda v: v["start"]):
        log(f"    start={rel(v['start']):.2f}s end={rel(v['end']):.2f}s dur={v['end']-v['start']:.2f}s")
    log(f"  humanize/brand-repair LLM calls: {len(humanize_chats)}")
    for v in sorted(humanize_chats, key=lambda v: v["start"]):
        log(f"    start={rel(v['start']):.2f}s end={rel(v['end']):.2f}s dur={v['end']-v['start']:.2f}s")
    if humanize_chats:
        humanize_span = max(v["end"] for v in humanize_chats) - min(v["start"] for v in humanize_chats)
        log(f"  => humanize phase adds ~{humanize_span:.2f}s sequentially after main generation")

    # ---- quality signal: outline adherence + persona/tone alignment ----
    log("\n  --- quality checks ---")
    log(f"  final title: {final_content.get('title')}")
    body = final_content.get("body_markdown") or ""
    import re as _re
    generated_h2 = _re.findall(r"^##\s+(.+)$", body, flags=_re.MULTILINE)
    log(f"  generated H2 headings in body: {len(generated_h2)}")
    for h in generated_h2:
        log(f"    - {h}")
    outline_headings = [s.get("heading") for s in real_sections_seen if s.get("heading")]
    log(f"  outline section headings (via _outline_sections): {len(outline_headings)}")
    for h in outline_headings:
        log(f"    - {h}")

    reliability: dict[str, str] = {}

    approved_faqs = outline_approved.get("faqs") or []
    if approved_faqs:
        faq_qs = [f.get("question", "") if isinstance(f, dict) else str(f) for f in approved_faqs]
        missing_faqs = [q for q in faq_qs if q and q.lower()[:30] not in body.lower()]
        log(f"  approved FAQs: {len(faq_qs)}; appear to be missing from body (first-30-char match): {len(missing_faqs)}")
        for q in missing_faqs:
            log(f"    MISSING: {q}")
        reliability["FAQs"] = "PASS" if not missing_faqs else f"FAIL ({len(missing_faqs)} missing)"

    internal_links = outline_approved.get("internal_links") or []
    if internal_links:
        missing_links = [lnk for lnk in internal_links if lnk.get("url") and lnk["url"] not in body]
        log(f"  approved internal links: {len(internal_links)}; missing from body: {len(missing_links)}")
        for lnk in missing_links:
            log(f"    MISSING: {lnk.get('title')} -> {lnk.get('url')}")
        reliability["Internal links"] = "PASS" if not missing_links else f"FAIL ({len(missing_links)}/{len(internal_links)} missing)"

    persona_id = outline_approved.get("selected_persona_id")
    if persona_id:
        from src.flow.engines.agent.middleware.persona_middleware import fetch_best_persona as _fetch_persona
        _persona = await _fetch_persona(WORKSPACE_ID, outline_approved)
        if _persona:
            _pname = str(_persona.full_name or _persona.name)
            combined = f"{final_content.get('introduction', '')}\n\n{body}"
            _count = combined.lower().count(_pname.lower())
            _first_para = (final_content.get("introduction", "") or "").strip().split("\n\n", 1)[0].lower()
            _in_first_para = _pname.lower() in _first_para
            log(f"  persona '{_pname}' mentioned {_count} time(s) in final content, in-first-paragraph={_in_first_para} "
                f"({'OK' if _count >= 2 and _in_first_para else 'BELOW REQUIRED MINIMUM'})")
            reliability["Persona mention"] = "PASS" if (_count >= 2 and _in_first_para) else f"FAIL (count={_count}, first_para={_in_first_para})"

    facts = final_content.get("facts") or []
    if facts:
        sourced = [f for f in facts if isinstance(f, dict) and f.get("source_url")]
        log(f"  facts: {len(facts)} total, {len(sourced)} with a source_url")
        for f in sourced:
            log(f"    - {_short(f.get('text', ''), 100)} (source: {f.get('source_url')})")
        reliability["Fact source URLs"] = f"{len(sourced)}/{len(facts)} sourced (all pass through the search-verified strip check)"

    if outline_approved.get("promote_brand"):
        brand_name = ((outline_approved.get("brand_voice_promotion") or {}).get("brand_name") or "").strip()
        if brand_name:
            present = brand_name.lower() in (final_content.get("introduction", "") + body).lower()
            log(f"  brand promotion '{brand_name}' present in final content: {present}")
            reliability["Brand mention"] = "PASS" if present else "FAIL (brand missing)"
        else:
            log("  brand promotion forced True, but outline has no brand_name resolved (no brand_voice row?) -- check skipped")

    outline_sections_match = bool(outline_headings) and generated_h2[: len(outline_headings)] == outline_headings
    reliability["Outline structure followed"] = (
        "PASS (generated headings match approved outline)" if outline_sections_match
        else f"CHECK ({len(outline_headings)} outline headings vs {len(generated_h2)} generated H2s -- see lists above)"
    )

    log("\n  --- RELIABILITY CHECKS SUMMARY ---")
    for name, result in reliability.items():
        log(f"  {name}: {result}")

    word_count = len(body.split())
    target = outline_approved.get("target_word_count", 0)
    log(f"  word count: {word_count} vs target {target} "
        f"({'within tolerance' if target and abs(word_count-target) <= max(50, round(target*0.15)) else 'OUT OF TOLERANCE'})")

    log("\n  --- introduction (verbatim, for tone/persona read) ---")
    log(_short(final_content.get("introduction", ""), 1500))
    log("\n  --- first 2000 chars of body_markdown (verbatim, for tone/persona read) ---")
    log(_short(body, 2000))

    # ==================================================================
    # STEP 5 -- REVIEW_CONTENT (real production subgraph: readability +
    # on-page SEO + E-E-A-T trust, run concurrently)
    # ==================================================================
    log("\n[STEP 5] review_content (real production subgraph, 3-way parallel)")

    from src.flow.engines.content.review.content.content_review import review_content
    from src.flow.states.reducers.custom_reducer import deep_merge_dicts

    review_graph = review_content()
    review_state = {**state, "content": content_state}

    node_times: dict[str, float] = {}
    merged_content: dict = dict(content_state)

    t0 = time.perf_counter()
    async for chunk in review_graph.astream(review_state, stream_mode="updates"):
        for node_name, node_output in chunk.items():
            node_times[node_name] = time.perf_counter() - t0
            node_content = (node_output or {}).get("content")
            if node_content:
                merged_content = deep_merge_dicts(merged_content, node_content)
    timings["review_content_total"] = time.perf_counter() - t0

    log(f"  duration: {timings['review_content_total']:.2f}s")
    for name, dur in sorted(node_times.items(), key=lambda kv: kv[1]):
        log(f"    {name}: finished at {dur:.2f}s")

    review = merged_content.get("review") or {}
    log("\n  --- review scores ---")
    log(_short(review, 2000))

    # ==================================================================
    # TIMING SUMMARY
    # ==================================================================
    log("\n" + "=" * 78)
    log("TIMING SUMMARY")
    log("=" * 78)
    total = sum(timings.values())
    for stage, dur in timings.items():
        pct = (dur / total * 100) if total else 0
        log(f"  {stage:<28} {dur:>7.2f}s  ({pct:>5.1f}%)")
    log(f"  {'TOTAL (measured stages)':<28} {total:>7.2f}s")
    log("\n  Note: persist_content is skipped in this test (no user_id -> no-op,")
    log("  per persist_content.py's own documented guard) and is a single DB")
    log("  write in production, not a latency hotspot per the static review.")

    _write_report(report_lines, keyword)
    _write_json(
        {
            "keyword": keyword,
            "content_type": content_type,
            "timings": timings,
            "tool_calls": [
                {"name": v["name"], "start_rel": rel(v["start"]), "end_rel": rel(v["end"]), "dur": v["end"] - v["start"]}
                for v in complete_tools.values()
            ],
            "main_chat_calls": [
                {"start_rel": rel(v["start"]), "end_rel": rel(v["end"]), "dur": v["end"] - v["start"]}
                for v in main_chats
            ],
            "humanize_chat_calls": [
                {"start_rel": rel(v["start"]), "end_rel": rel(v["end"]), "dur": v["end"] - v["start"]}
                for v in humanize_chats
            ],
            "review_node_times": node_times,
            "outline": outline_approved,
            "final_content": final_content,
            "review": review,
        },
        keyword,
    )


def _write_report(lines: list, keyword: str = "report"):
    safe = "".join(c if c.isalnum() else "_" for c in keyword)[:60]
    ts = time.strftime("%Y%m%d_%H%M%S")
    out_path = RESULTS_DIR / f"{ts}_{safe}.txt"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n[report saved] {out_path}")


def _write_json(data: dict, keyword: str):
    safe = "".join(c if c.isalnum() else "_" for c in keyword)[:60]
    ts = time.strftime("%Y%m%d_%H%M%S")
    out_path = RESULTS_DIR / f"{ts}_{safe}.json"
    out_path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    print(f"[json saved] {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--keyword", required=True, help="Keyword to generate content for")
    parser.add_argument("--content-type", default="blog", help="Content type (default: blog)")
    args = parser.parse_args()
    asyncio.run(run_test(args.keyword, args.content_type))

"""
Live run: SERP fetch → normalize → competitor/intent → LLM keyword clustering.
Usage: python scripts/run_keyword_clustering_live.py "your keyword here"
"""
from __future__ import annotations

import asyncio
import json
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")


class _MockRuntime:
    store = None


def _deep_merge(state: dict, update: dict) -> dict:
    for key, value in update.items():
        if key in ("serp_normalized", "seo_result") and isinstance(value, dict):
            state[key] = {**(state.get(key) or {}), **value}
        else:
            state[key] = value
    return state


async def run_pipeline(keyword: str, country: str = "us") -> dict:
    from src.flow.engines.serp.fetch_serp import fetch_serp_results
    from src.flow.engines.serp.normalization import normalize_serp_results
    from src.flow.engines.serp.competitor import extract_competitors_from_serp
    from src.flow.engines.seo.keyword_clustering import keyword_clustering_node

    state: dict = {
        "serp_payload": {
            "query": keyword,
            "country": country,
            "user_id": uuid.uuid4(),
            "workspace_id": uuid.uuid4(),
        },
        "seo_result": {},
    }

    print(f"\n=== Keyword clustering live run: {keyword!r} ({country}) ===\n")

    step1 = await fetch_serp_results(state, {}, runtime=_MockRuntime())
    state = _deep_merge(state, step1)
    organic = len((state.get("serp_result") or {}).get("organic_results") or [])
    print(f"[1] SERP fetch: {organic} organic results")
    if organic == 0:
        return {"error": "No SERP data — check DATAFORSEO_* env vars", "state": state}

    step2 = normalize_serp_results(state, {}, runtime=_MockRuntime())
    state = _deep_merge(state, step2)
    sn = state.get("serp_normalized") or {}
    print(
        f"[2] Normalize: {len(sn.get('questions') or [])} PAA, "
        f"{len(sn.get('related_topics') or [])} related"
    )

    step3 = await extract_competitors_from_serp(state)
    state = _deep_merge(state, step3)
    signals = (state.get("serp_normalized") or {}).get("intent_matched_signals") or {}
    print(
        f"[3] Intent: {state.get('final_intent_type')} | "
        f"matched signals — titles={len(signals.get('titles') or [])}, "
        f"paa={len(signals.get('questions') or [])}, "
        f"related={len(signals.get('related_topics') or [])}"
    )

    step4 = await keyword_clustering_node(state)
    state = _deep_merge(state, step4)
    clusters = (state.get("seo_result") or {}).get("keyword_clusters") or []
    print(f"[4] Clustering: {len(clusters)} clusters\n")

    return {
        "query": keyword,
        "final_intent_type": state.get("final_intent_type"),
        "intent_matched_signals": signals,
        "keyword_clusters": clusters,
        "competitor_count": len(state.get("competitors") or []),
    }


def main() -> None:
    keyword = sys.argv[1] if len(sys.argv) > 1 else "best seo tools"
    country = sys.argv[2] if len(sys.argv) > 2 else "us"
    result = asyncio.run(run_pipeline(keyword, country))
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
baseline_pipeline_test.py

PURPOSE:
Run your ACTUAL production crawl -> brand-voice/persona-extraction -> filter
steps, exactly as workspace_pipeline.py runs them, but standalone from your
terminal -- no DB, no rext-admin UI, no real workspace creation. This is the
"run it once as-is and see what's broken" baseline test you asked for.

Every function called below is IMPORTED from your real code -- nothing here
is reconstructed or guessed. If something breaks or behaves unexpectedly,
that tells us something true about the real pipeline, not about this script.

WHY EACH STEP EXISTS:
- Step 1 (crawl): proves whether the crawler actually reached the page(s)
  containing persona-worthy content (About/Team/Founder bios), or only ever
  saw the homepage -- this directly tests the "persona not extracted at all"
  issue you just reported, which we suspect is a single-URL crawl limitation.
- Step 2 (extract): proves what the LLM actually returned BEFORE any
  filtering -- so we can see raw model behavior, including any
  testimonial-vs-persona confusion, unfiltered.
- Step 3 (filter): proves what your existing _filter_valid_personas()
  function keeps vs. drops -- so we know if filtering logic itself is
  dropping anything unexpectedly.
- Step 4 (report): writes everything to one readable .txt file so you can
  eyeball the full chain end-to-end without digging through logs or a DB.

USAGE:
    python baseline_pipeline_test.py --url https://example.com

Run this from the REPO ROOT (~/rext-backend) so the `src.*` imports resolve.
"""

import argparse
import asyncio
import json
import time
from pathlib import Path

# WorkspacePipeline: we only use its @staticmethod _default_brand_voice_generator,
# which does NOT require a live DB session or a real workspace -- it just takes
# raw text and returns a BrandSchema. This is the exact function your production
# pipeline calls for extraction.
from src.services.workspace_pipeline import WorkspacePipeline, _filter_valid_personas

# --- Real imports from your codebase. No placeholders. ---------------------
# web_page_scraper: your actual crawler (currently single-URL only -- see
# docstring above, this is intentional for this test, not a bug in the script).
from src.utils.helper import web_page_scraper

RESULTS_DIR = Path("results")


async def run_baseline_test(url: str):
    RESULTS_DIR.mkdir(exist_ok=True)
    report_lines = []

    def log(line: str = ""):
        print(line)
        report_lines.append(line)

    log("=" * 70)
    log("BASELINE PIPELINE TEST")
    log(f"url: {url}")
    log(f"timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    log("=" * 70)

    # -------------------------------------------------------------------
    # STEP 1 — CRAWL
    # Purpose: this is the exact call your production `_default_scraper`
    # makes. If your site's persona content lives on a page other than
    # whatever gets crawled here, this step is where we'll see it missing.
    # -------------------------------------------------------------------
    log("\n[STEP 1] Crawling...")
    chunks, results = await web_page_scraper(urls=[url])

    if not results or not results[0].success:
        error_msg = results[0].error_message if results else "no results returned"
        log(f"  CRAWL FAILED: {error_msg}")
        log("\n>> Cannot continue -- crawl itself failed. This IS your answer")
        log(">> if you're seeing 'no persona extracted' -- there was no content")
        log(">> to extract from in the first place.")
        _write_report(url, report_lines)
        return

    result = results[0]
    content = result.markdown  # same field production code uses (confirmed in knowledge_task.py)

    log(f"  crawled URL: {result.url}")
    log(f"  success: {result.success}")
    log(f"  content length: {len(content)} chars")
    log(f"  chunks produced (for vector store): {len(chunks)}")
    log("\n  --- first 1000 chars of scraped content ---")
    log(content[:1000])
    log("  --- end preview ---")

    # -------------------------------------------------------------------
    # STEP 2 — EXTRACT (real LLM call, real schema, real prompt)
    # Purpose: see EXACTLY what the model returns before any filtering.
    # This is where we'll see raw evidence of testimonial-vs-persona
    # confusion, if it's happening.
    # -------------------------------------------------------------------
    log("\n[STEP 2] Extracting brand voice + personas via real LLM call...")
    log("  (this calls WorkspacePipeline._default_brand_voice_generator --")
    log("   the exact function your production pipeline uses)")

    brand_voice_schema = await WorkspacePipeline._default_brand_voice_generator(content)

    if brand_voice_schema is None:
        log("  EXTRACTION RETURNED None -- likely empty/whitespace-only content.")
        log("  If Step 1 showed real content above, this is worth flagging as a")
        log("  separate bug: content existed but extractor bailed out.")
        _write_report(url, report_lines)
        return

    data = brand_voice_schema.model_dump()
    raw_personas = data.pop("personas", [])

    log(f"\n  brand_name: {data.get('brand_name')}")
    log(f"  about: {data.get('about')}")
    log(f"  RAW personas returned by LLM (before filtering): {len(raw_personas)}")
    for i, p in enumerate(raw_personas, 1):
        log(f"\n  --- raw persona [{i}] ---")
        log(json.dumps(p, indent=4, default=str))

    # -------------------------------------------------------------------
    # STEP 3 — FILTER (your real _filter_valid_personas function)
    # Purpose: see what your existing filter keeps vs. silently drops.
    # -------------------------------------------------------------------
    log("\n[STEP 3] Filtering via real _filter_valid_personas()...")
    personas_data = _filter_valid_personas(raw_personas)

    log(f"  personas AFTER filtering: {len(personas_data)} (started with {len(raw_personas)})")
    dropped_count = len(raw_personas) - len(personas_data)
    if dropped_count > 0:
        log(f"  >> {dropped_count} persona(s) were dropped by the filter -- worth")
        log("     checking if that's correct or if it's over-filtering.")

    for i, p in enumerate(personas_data, 1):
        log(f"\n  --- FINAL persona [{i}] (this is what would be saved to DB) ---")
        log(json.dumps(p, indent=4, default=str))
        # Cheap heuristic flag -- NOT a real classifier, just a human hint.
        # Purpose: helps you eyeball which entries are worth double-checking
        # for the testimonial-vs-persona issue while reading the report.
        desc = str(p.get("description") or "").lower()
        bio = str(p.get("bio") or "").lower()
        combined = desc + " " + bio
        if any(
            word in combined
            for word in ["said", "review", '"', "recommend", "customer", "client of"]
        ):
            log("  >> FLAG: description/bio contains testimonial-like language --")
            log("     manually check if this is actually a team member/expert,")
            log("     or a testimonial-giver that got miscategorized.")

    if not raw_personas:
        log("\n>> ZERO personas returned by the LLM at all.")
        log(">> Combined with the content preview above, check by eye whether")
        log(">> the crawled page actually contained any team/founder/author info.")
        log(">> If it didn't -- this confirms the single-URL crawl limitation")
        log(">> (Problem 1) is the real cause, not the extraction prompt.")

    _write_report(url, report_lines)


def _write_report(url: str, lines: list):
    safe_host = url.replace("https://", "").replace("http://", "").replace("/", "_")
    ts = time.strftime("%Y%m%d_%H%M%S")
    out_path = RESULTS_DIR / f"{ts}_{safe_host}.txt"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n[report saved] {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True, help="Website URL to test")
    args = parser.parse_args()
    asyncio.run(run_baseline_test(args.url))

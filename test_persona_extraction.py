"""Interactive tester: run the real Crawl4AI scraper + persona-extraction LLM
call against a workspace name + URL you enter, and save both to one txt file.

Usage (interactive — prompts for workspace name and URL, repeatedly):
    python test_persona_extraction.py
    (press Enter on a blank workspace name to quit)

Usage (one-shot, non-interactive):
    python test_persona_extraction.py "Nextly" https://nextlyhq.com/

Output:
    persona_extraction_tests/<workspace_name>.txt
        - the scraped markdown (full, untruncated — exactly what Crawl4AI returned)
        - the content actually sent to the LLM (after the same head+tail
          sampling the real pipeline applies)
        - the LLM's full structured response (brand voice + personas)
        - the persona list both before and after the _filter_valid_personas()
          safety filter, so a failed test tells you whether the scrape, the
          LLM, or the filter is where it went wrong
"""

import asyncio
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from src.utils.helper import web_page_scraper
from src.services.workspace_pipeline import WorkspacePipeline, _filter_valid_personas

OUTPUT_DIR = Path(__file__).parent / "persona_extraction_tests"


def _safe_filename(name: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", name.strip()).strip("_")
    return slug or "workspace"


async def run_test(workspace_name: str, url: str) -> Path:
    OUTPUT_DIR.mkdir(exist_ok=True)
    out_path = OUTPUT_DIR / f"{_safe_filename(workspace_name)}.txt"

    lines: list[str] = []
    lines.append("=" * 90)
    lines.append(f"WORKSPACE: {workspace_name}")
    lines.append(f"URL: {url}")
    lines.append(f"RUN AT: {datetime.now(timezone.utc).isoformat()}")
    lines.append("=" * 90)

    print(f"[{workspace_name}] Scraping {url} ...")
    try:
        chunks, results = await web_page_scraper(urls=[url])
    except Exception as exc:  # noqa: BLE001 - report to file instead of crashing
        lines.append(f"\nSCRAPE RAISED AN EXCEPTION: {exc}\n")
        out_path.write_text("\n".join(lines), encoding="utf-8")
        print(f"[{workspace_name}] Scrape errored — see {out_path}")
        return out_path

    first = next((r for r in results if getattr(r, "success", False)), None)

    if first is None:
        lines.append("\nSCRAPE FAILED\n")
        for r in results:
            lines.append(
                f"- {getattr(r, 'url', '?')}: success={getattr(r, 'success', None)} "
                f"error={getattr(r, 'error_message', None)}"
            )
        out_path.write_text("\n".join(lines), encoding="utf-8")
        print(f"[{workspace_name}] Scrape failed — see {out_path}")
        return out_path

    markdown = first.markdown or ""
    lines.append(f"\nSCRAPED MARKDOWN LENGTH: {len(markdown)} chars")
    lines.append("-" * 90)
    lines.append("CRAWL4AI OUTPUT (full, untruncated)")
    lines.append("-" * 90)
    lines.append(markdown)

    # Same head+tail sampling the real onboarding pipeline applies before the
    # LLM call — see WorkspacePipeline._sample_content_for_extraction.
    pipeline = object.__new__(WorkspacePipeline)
    sampled_content = pipeline._sample_content_for_extraction(markdown)

    print(f"[{workspace_name}] Calling LLM for persona extraction ...")
    schema = await WorkspacePipeline._default_brand_voice_generator(sampled_content)

    lines.append("\n" + "-" * 90)
    lines.append(
        f"CONTENT SENT TO LLM: {len(sampled_content)} chars "
        f"(of {len(markdown)} scraped)"
    )
    lines.append("-" * 90)
    lines.append(sampled_content)

    lines.append("\n" + "=" * 90)
    lines.append("LLM PERSONA EXTRACTION RESPONSE")
    lines.append("=" * 90)

    if schema is None:
        lines.append("\nLLM returned None (empty content, or the call failed).")
    else:
        data = schema.model_dump()
        lines.append("\nFULL STRUCTURED RESPONSE:")
        lines.append(json.dumps(data, indent=2, ensure_ascii=False))

        raw_personas = data.get("personas") or []
        lines.append(f"\nPERSONAS — RAW FROM LLM: {len(raw_personas)}")
        for p in raw_personas:
            lines.append(f"  - name={p.get('name')!r}  source={p.get('source')!r}")

        filtered = _filter_valid_personas(raw_personas)
        lines.append(
            f"\nPERSONAS — AFTER _filter_valid_personas() "
            f"(what actually gets saved to the DB): {len(filtered)}"
        )
        for p in filtered:
            lines.append(f"  - name={p.get('name')!r}  source={p.get('source')!r}")

        if raw_personas and not filtered:
            lines.append(
                "\n>>> LLM found candidate(s) but the safety filter rejected all "
                "of them — check console/log output above for rejection reasons "
                "(e.g. testimonial-only, archetype keyword, single-word name)."
            )
        if not raw_personas:
            lines.append(
                "\n>>> LLM returned zero persona candidates — likely means no "
                "named individual appears in the 'CONTENT SENT TO LLM' section "
                "above, or the LLM judged them as not representing the brand "
                "(see extraction prompt RULE 1/3 in workspace_pipeline.py)."
            )

    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"[{workspace_name}] Done — wrote {out_path}")
    return out_path


async def main() -> None:
    if len(sys.argv) >= 3:
        # One-shot mode: python test_persona_extraction.py "Name" https://url
        url = sys.argv[2]
        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"
        await run_test(sys.argv[1], url)
        return

    print("Persona extraction tester — enter a workspace name and URL to test.")
    print("Leave workspace name blank to quit.\n")
    while True:
        workspace_name = input("Workspace name: ").strip()
        if not workspace_name:
            print("Bye.")
            break
        url = input("URL: ").strip()
        if not url:
            print("No URL given, skipping.\n")
            continue
        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"
        try:
            await run_test(workspace_name, url)
        except Exception as exc:  # noqa: BLE001 - keep the loop alive on a bad run
            print(f"[{workspace_name}] ERROR: {exc}")
        print()


if __name__ == "__main__":
    asyncio.run(main())

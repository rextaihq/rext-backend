"""Score persona extraction against tests/persona/benchmark.yaml.

    python tests/persona/run_benchmark.py            # every site
    python tests/persona/run_benchmark.py wpbeginner # one, by substring

Reports recall (of the people a human said are there), precision failures (names
that must never appear), and latency per site. Exits non-zero when a
must-not-appear name is found or a site falls below its floor, so it can gate a
change rather than merely describe one.
"""
import asyncio
import sys
import time
from pathlib import Path
from uuid import uuid4

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.services.workspace_pipeline import (  # noqa: E402
    WorkspacePipeline, _filter_valid_personas, _identity_key)

BENCHMARK = Path(__file__).with_name("benchmark.yaml")


async def _extract(url: str) -> tuple:
    started = time.time()
    pipeline = WorkspacePipeline(db=None, operation_id="benchmark",
                                 workspace_id=uuid4(), user_id=uuid4(), url=url)
    content, _, _ = await pipeline._fast_or_fallback_scrape()
    brand = await pipeline._default_brand_voice_generator(content)
    raw = [p.model_dump() if hasattr(p, "model_dump") else p
           for p in (brand.personas or [])]
    raw += getattr(pipeline, "_author_personas", []) or []
    people = _filter_valid_personas(raw, url)
    await pipeline._fetch_missing_author_archives(people)
    pipeline._attach_social_links(people)
    return people, time.time() - started


async def main() -> int:
    spec = yaml.safe_load(BENCHMARK.read_text())
    wanted = sys.argv[1:] 
    sites = [s for s in spec["sites"]
             if not wanted or any(w in s["url"] for w in wanted)]
    failures = 0

    for site in sites:
        url = site["url"]
        try:
            people, seconds = await _extract(url)
        except Exception as exc:  # noqa: BLE001 - a crash is a result too
            print(f"\n{url}\n  ERROR {type(exc).__name__}: {exc}")
            failures += 1
            continue

        found = {_identity_key(p.get("name") or "") for p in people}
        expected = site.get("expect_people") or []
        missing = [n for n in expected if _identity_key(n) not in found]
        leaked = [n for n in (site.get("expect_absent") or [])
                  if _identity_key(n) in found]
        photos = sum(1 for p in people
                     if (p.get("custom_metadata") or {}).get("avatar_source")
                     in ("page", "gravatar"))
        floor = site.get("min_people", 0)

        print(f"\n{url}")
        print(f"  {len(people)} personas in {seconds:.0f}s, {photos} with a real photo")
        if expected:
            print(f"  recall  {len(expected) - len(missing)}/{len(expected)}"
                  + (f"  MISSING: {', '.join(missing)}" if missing else ""))
        if leaked:
            print(f"  LEAKED  {', '.join(leaked)}")
            failures += 1
        if len(people) < floor:
            print(f"  BELOW FLOOR  {len(people)} < {floor}")
            failures += 1

    print(f"\n{len(sites)} site(s), {failures} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

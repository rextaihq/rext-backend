"""Manual test runner — kept separate from persona_discovery.py on purpose."""
import sys
import asyncio
import logging
from pathlib import Path

from persona_discovery import discover_personas, PersonaConfig


def _print_report(r: dict) -> None:
    print("\n" + "=" * 78)
    print(f"TARGET   {r['target']}")
    print(f"TIME     {r['duration_seconds']}s")
    print(f"URLS     {r['stats']['urls_found']}")
    print(f"FETCHED  {r['stats']['pages_fetched']} pages")
    print(f"PEOPLE   {r['stats']['people_before_gating']} raw -> "
          f"{r['stats']['personas_returned']} after evidence gating")
    if r["organizational_bylines"]:
        print(f"ORG      {[o['name'] for o in r['organizational_bylines']]}")
    print("=" * 78)
    for p in r["personas"]:
        print(f"\n  {p['name']}   conf={p['confidence']}")
        print(f"     type      : {p['person_type_label']}")
        print(f"     job title : {p['title_role'] or '-'}")
        print(f"     articles  : {p['article_count']}"
              f"   latest: {(p['latest_article_date'] or '-')[:10]}")
        print(f"     email     : {p['email'] or '-'}")
        print(f"     socials   : {p['socials'] or '-'}")
        print(f"     expertise : {p['expertise'] or '-'}")
        ws = p["writing_style"]
        if isinstance(ws, dict) and "error" not in ws:
            print(f"     tone      : {ws.get('tone')}")
            print(f"     vocabulary: {ws.get('vocabulary')}")
            print(f"     style     : {ws.get('sentence_style')}")
        else:
            print(f"     style     : (not analysed: "
                  f"{ws.get('error') if isinstance(ws, dict) else 'n/a'})")
    print()


def main() -> int:
    url = sys.argv[1] if len(sys.argv) > 1 else "https://example.com"
    verbose = "-v" in sys.argv or "--verbose" in sys.argv
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s %(message)s")

    cfg = PersonaConfig(out_dir=Path(__file__).parent / "results", enable_llm=True)
    result = asyncio.run(discover_personas(url, cfg))
    _print_report(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())

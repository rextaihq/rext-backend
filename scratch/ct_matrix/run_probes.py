"""Defect-injection pass: does the gate actually CATCH each failure mode?

The compliant-writer run (run_matrix.py) proves the rules are satisfiable. It
cannot prove they are enforced — a gate that passes everything passes a broken
article too. Each probe below takes the compliant payload for a content type,
breaks exactly one thing, and asserts the expected check fails.
"""

from __future__ import annotations

import argparse
import logging
import re
import sys

from src.flow.engines.content.generation.requirements_spec import (
    build_requirements_spec,
    resolve_outline_cta,
)
from src.flow.engines.content.generation.outline_structure import resolve_outline_structure
from src.flow.engines.content.generation.structured_body import (
    STRUCTURED_BLOCKS_KEY,
    build_structured_content_model,
    uses_structured_body,
)
from src.flow.engines.content.generation.validation import (
    merge_link_inventory,
    protected_links,
    run_checks,
)
from src.flow.model.structure.contents import get_generated_content_model
from src.flow.model.structure.outlines import CONTENT_TYPE_TO_MODEL

from .outline_fixtures import (
    BRAND,
    FOCUS_KEYPHRASE,
    INTERNAL_LINKS,
    SEARCHED_RESULTS,
    SELECTED_TITLE,
    build_outline,
    generation_meta,
)
from .synthetic_writer import write_content

logging.disable(logging.CRITICAL)

SKIP = {"pillar-content"}


# ── probes ──────────────────────────────────────────────────────────────────
# (name, area, mutate(payload) -> payload, expected check name)


def _drop_internal_link(p: dict) -> dict:
    url = INTERNAL_LINKS[0]["url"]
    p = dict(p)
    for field in ("introduction", "body_markdown"):
        p[field] = re.sub(r"\[([^\]]*)\]\(" + re.escape(url) + r"\)", r"\1", p.get(field) or "")
    return p


def _bolt_on_internal_link(p: dict) -> dict:
    p = _drop_internal_link(p)
    lnk = INTERNAL_LINKS[0]
    p["body_markdown"] += f"\n\n[{lnk['anchor_text']}]({lnk['url']})\n"
    return p


def _bolt_on_citation(p: dict) -> dict:
    url = SEARCHED_RESULTS[0]["url"]
    p = dict(p)
    for field in ("introduction", "body_markdown"):
        p[field] = re.sub(r"\[([^\]]*)\]\(" + re.escape(url) + r"\)", r"\1", p.get(field) or "")
    p["body_markdown"] += f"\n\n## Further reading\n\n[{url}]({url})\n"
    p["outbound_links"] = [{"url": url, "anchor_text": "source", "rel": "nofollow"}]
    return p


def _fabricate_citation(p: dict) -> dict:
    p = dict(p)
    p["facts"] = list(p.get("facts") or []) + [
        {"text": "Teams cut production time by 40%.", "source_url": "https://madeup-source.example/stats"}
    ]
    p["body_markdown"] += (
        "\n\nOne [widely cited study](https://madeup-source.example/stats) reports that teams "
        "cut production time by 40% after standardising their briefs."
    )
    return p


def _invent_price(p: dict) -> dict:
    p = dict(p)
    p["body_markdown"] += (
        f"\n\n{BRAND['brand_name']} costs $49 per month and is already used by more than "
        f"12,000 marketing teams worldwide."
    )
    return p


def _invent_experience(p: dict) -> dict:
    p = dict(p)
    p["body_markdown"] += (
        "\n\nWe tested all seven platforms across a full quarter and rebuilt three client "
        "content programmes on each one before reaching this verdict."
    )
    return p


def _superlative(p: dict) -> dict:
    p = dict(p)
    p["body_markdown"] += (
        f"\n\n{BRAND['brand_name']} is the best platform on the market and the clear winner "
        f"against every competitor in this category."
    )
    return p


def _placeholder_entities(p: dict) -> dict:
    p = dict(p)
    p["body_markdown"] += (
        "\n\nProduct A handles briefing well, while Product B focuses on publishing. "
        "Agency C sits between the two, and Tool 1 covers reporting only."
    )
    return p


def _remove_brand(p: dict) -> dict:
    p = dict(p)
    for field in ("introduction", "body_markdown"):
        text = p.get(field) or ""
        text = re.sub(
            r"\[" + re.escape(BRAND["brand_name"]) + r"\]\([^)]*\)",
            "One such platform",
            text,
        )
        p[field] = re.sub(re.escape(BRAND["brand_name"]), "that platform", text)
    return p


def _bury_brand(p: dict) -> dict:
    p = _remove_brand(p)
    p["body_markdown"] += (
        f"\n\n[{BRAND['brand_name']}]({BRAND['brand_url']}) turns a keyword into a researched "
        f"brief, a draft and a published post, which is what keeps a lean team off an agency "
        f"retainer."
    )
    return p


def _name_drop_brand(p: dict) -> dict:
    p = _remove_brand(p)
    body = p["body_markdown"]
    # An early, bare name-drop with no value attached.
    p["body_markdown"] = (
        f"Options include [{BRAND['brand_name']}]({BRAND['brand_url']}).\n\n" + body
    )
    return p


def _wrong_brand_url(p: dict) -> dict:
    p = dict(p)
    for field in ("introduction", "body_markdown"):
        p[field] = (p.get(field) or "").replace(
            f"]({BRAND['brand_url']})", "](https://some-other-site.example/tool)"
        )
    return p


def _drop_required_section(p: dict) -> dict:
    """Remove the first H2 section AND the structured-block provenance key.

    Dropping the key is what makes this a real test rather than a rigged one:
    `_structured_block_keys` is deliberately stripped downstream (humanization
    re-validates on headings), so this is exactly the shape the post-humanize
    payload has.
    """
    p = {k: v for k, v in p.items() if k != STRUCTURED_BLOCKS_KEY}
    body = p.get("body_markdown") or ""
    parts = re.split(r"(?m)^##(?!#)\s", body)
    if len(parts) > 2:
        p["body_markdown"] = parts[0] + "".join("## " + s for s in parts[2:])
    return p


def _drop_cta(p: dict) -> dict:
    p = dict(p)
    p.pop("cta", None)
    return p


PROBES = [
    ("internal link removed", "internal_links", _drop_internal_link, "internal_links_integration"),
    ("internal link bolted on", "internal_links", _bolt_on_internal_link, "internal_links_integration"),
    ("citation dumped at end", "external_links", _bolt_on_citation, "facts_and_external_links"),
    ("fabricated citation", "external_links", _fabricate_citation, "facts_and_external_links"),
    ("invented price/count", "facts", _invent_price, "unsupported_claims"),
    ("invented first-hand test", "facts", _invent_experience, "unsupported_claims"),
    ("absolute superlative", "facts", _superlative, "unsupported_claims"),
    ("placeholder entities", "noise", _placeholder_entities, "placeholder_product_names"),
    ("brand removed", "brand", _remove_brand, "brand_presence"),
    ("brand buried at end", "brand", _bury_brand, "brand_placement_policy"),
    ("brand bare name-drop", "brand", _name_drop_brand, "brand_integration_depth"),
    ("brand wrong URL", "brand", _wrong_brand_url, "brand_url_accuracy"),
    ("required section dropped", "structure", _drop_required_section, "required_sections"),
    ("cta dropped", "structure", _drop_cta, "cta_presence"),
]

# Probes that legitimately do not apply to a content type, with the reason.
def _not_applicable(probe: str, content_type: str, spec: dict) -> str:
    policy = spec.get("brand_placement_policy") or {}
    if probe in ("brand buried at end", "brand bare name-drop") and policy.get(
        "intensity"
    ) == "none":
        return "type has no PLM placement/depth requirement"
    if probe == "citation dumped at end" and (spec.get("evidence_placement") or {}).get(
        "citation_style"
    ) == "inline_or_references":
        return "type allows a labelled references section"
    if probe == "cta dropped" and not spec.get("cta_required"):
        return "outline declares no CTA"
    if probe == "required section dropped" and not spec.get("required_sections"):
        return "schema declares no mandatory section"
    return ""


def run_type(content_type: str) -> list[dict]:
    outline = build_outline(content_type)
    meta = generation_meta()
    blocks = resolve_outline_structure(outline, content_type)
    cta = resolve_outline_cta(outline)
    cta_text = cta["text"] if cta else None
    spec = build_requirements_spec(
        outline, content_type, FOCUS_KEYPHRASE, SELECTED_TITLE, generation_meta=meta
    )
    base_model = get_generated_content_model(content_type)
    derived = (
        build_structured_content_model(outline, content_type, base_model)
        if uses_structured_body(content_type)
        else None
    )
    structured_blocks = derived[1] if derived else blocks
    clean = write_content(structured_blocks, spec, content_type, cta_text)
    meta["link_inventory"] = merge_link_inventory(protected_links(clean, spec, SEARCHED_RESULTS))
    spec = build_requirements_spec(
        outline, content_type, FOCUS_KEYPHRASE, SELECTED_TITLE, generation_meta=meta
    )

    rows = []
    for name, area, mutate, expected in PROBES:
        reason = _not_applicable(name, content_type, spec)
        if reason:
            rows.append({"probe": name, "area": area, "result": "n/a", "reason": reason})
            continue
        broken = mutate({k: (list(v) if isinstance(v, list) else v) for k, v in clean.items()})
        failed, warnings = run_checks(broken, spec, SEARCHED_RESULTS)
        names_blocking = {c["name"] for c in failed}
        names_warn = {c["name"] for c in warnings}
        if expected in names_blocking:
            result = "caught"
        elif expected in names_warn:
            result = "warn-only"
        else:
            result = "MISSED"
        rows.append(
            {
                "probe": name,
                "area": area,
                "result": result,
                "reason": "" if result == "caught" else f"blocking={sorted(names_blocking)}",
            }
        )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", default="")
    args = parser.parse_args()
    types = [t for t in CONTENT_TYPE_TO_MODEL if t not in SKIP]
    if args.only:
        types = [t for t in types if t in args.only.split(",")]

    probe_names = [p[0] for p in PROBES]
    tally = {n: {"caught": 0, "warn-only": 0, "MISSED": 0, "n/a": 0} for n in probe_names}
    misses: list[str] = []

    for ct in types:
        try:
            rows = run_type(ct)
        except Exception as exc:  # noqa: BLE001
            print(f"{ct}: ERROR {type(exc).__name__}: {exc}")
            continue
        for row in rows:
            tally[row["probe"]][row["result"]] += 1
            if row["result"] in ("MISSED", "warn-only"):
                misses.append(f"{ct:18} {row['probe']:26} {row['result']:10} {row['reason']}")

    print(f"{'probe':28}{'area':16}{'caught':>8}{'warn':>7}{'MISSED':>8}{'n/a':>6}")
    print("-" * 73)
    for name, area, _, _ in PROBES:
        t = tally[name]
        print(f"{name:28}{area:16}{t['caught']:>8}{t['warn-only']:>7}{t['MISSED']:>8}{t['n/a']:>6}")

    if misses:
        print("\n=== not caught as a blocking failure ===")
        for m in misses:
            print("  " + m)
    return 0


if __name__ == "__main__":
    sys.exit(main())

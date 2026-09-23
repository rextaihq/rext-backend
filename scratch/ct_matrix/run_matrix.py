"""Drive all 34 content types through the REAL generation-side pipeline stages.

Stages exercised, all imported from production code, none reimplemented:

  resolve_outline_structure  -> the approved structure for this content type
  build_structured_content_model -> the schema the writer is constrained to
  brand_schema_context / brand_slot  -> where the approved brand goes
  assemble_structured_payload -> blocks collapsed into body_markdown
  build_requirements_spec + run_checks -> the deterministic validation gate

Usage:
    python -m scratch.ct_matrix.run_matrix            # compliant-writer pass
    python -m scratch.ct_matrix.run_matrix --probes   # defect-injection pass
"""

from __future__ import annotations

import argparse
import json
import logging
import sys

from src.flow.engines.content.generation.outline_structure import (
    resolve_expected_headings,
    resolve_outline_structure,
)
from src.flow.engines.content.generation.requirements_spec import (
    build_requirements_spec,
    resolve_outline_cta,
)
from src.flow.engines.content.generation.structured_body import (
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
from src.flow.model.structure.outlines.product_names import find_placeholder_names_in_text

from .outline_fixtures import (
    FOCUS_KEYPHRASE,
    SEARCHED_RESULTS,
    SELECTED_TITLE,
    build_outline,
    generation_meta,
)
from .synthetic_writer import write_content

logging.disable(logging.CRITICAL)

SKIP = {"pillar-content"}  # explicitly out of scope for this run

# Which validation check answers which review area.
AREAS = {
    "facts": ["unsupported_claims", "facts_and_external_links", "brand_factual_grounding"],
    "structure": [
        "required_sections",
        "hero_presence",
        "cta_presence",
        "subheading_length",
        "subheading_keyphrase",
        "word_count_band",
    ],
    "internal_links": ["internal_links_integration", "links_preserved"],
    "external_links": ["facts_and_external_links"],
    "brand": [
        "brand_presence",
        "brand_url_accuracy",
        "brand_placement",
        "brand_placement_policy",
        "brand_integration_depth",
        "brand_context_heuristic",
    ],
    "noise": ["placeholder_product_names"],
}


def run_one(content_type: str) -> dict:
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
    schema_fields = sorted(derived[0].model_fields) if derived else []

    payload = write_content(structured_blocks, spec, content_type, cta_text)

    # Same inventory the generation node records, so links_preserved is graded
    # exactly as it would be in a real run.
    meta["link_inventory"] = merge_link_inventory(
        protected_links(payload, spec, SEARCHED_RESULTS)
    )
    spec = build_requirements_spec(
        outline, content_type, FOCUS_KEYPHRASE, SELECTED_TITLE, generation_meta=meta
    )

    failed, warnings = run_checks(payload, spec, SEARCHED_RESULTS)
    combined = f"{payload.get('introduction') or ''}\n\n{payload.get('body_markdown') or ''}"

    return {
        "content_type": content_type,
        "blocks": [b.key for b in blocks],
        "structured_blocks": [b.key for b in structured_blocks],
        "expected_sections": resolve_expected_headings(blocks),
        "required_sections": spec.get("required_sections"),
        "schema_fields": schema_fields,
        "brand_policy": {
            k: v
            for k, v in (spec.get("brand_placement_policy") or {}).items()
            if k in ("intensity", "prefers_top", "placement")
        },
        "cta_required": spec.get("cta_required"),
        "failed": [{"name": c["name"], "detail": c["detail"]} for c in failed],
        "warnings": [{"name": c["name"], "detail": c["detail"]} for c in warnings],
        "placeholders_in_body": find_placeholder_names_in_text(combined),
        "placeholders_in_outline_render": find_placeholder_names_in_text(json.dumps(outline)),
        "word_count": len(combined.split()),
    }


def area_status(result: dict, area: str) -> str:
    names = set(AREAS[area])
    blocking = [c["name"] for c in result["failed"] if c["name"] in names]
    warned = [c["name"] for c in result["warnings"] if c["name"] in names]
    if area == "noise" and result["placeholders_in_body"]:
        return "FAIL"
    if blocking:
        return "FAIL"
    if warned:
        return "WARN"
    return "PASS"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--only", default="")
    args = parser.parse_args()

    types = [t for t in CONTENT_TYPE_TO_MODEL if t not in SKIP]
    if args.only:
        types = [t for t in types if t in args.only.split(",")]

    results = []
    for ct in types:
        try:
            results.append(run_one(ct))
        except Exception as exc:  # noqa: BLE001
            import traceback

            results.append(
                {
                    "content_type": ct,
                    "error": f"{type(exc).__name__}: {exc}",
                    "traceback": traceback.format_exc(),
                    "failed": [],
                    "warnings": [],
                    "placeholders_in_body": [],
                }
            )

    if args.json:
        print(json.dumps(results, indent=2, default=str))
        return 0

    header = f"{'content type':<18}" + "".join(f"{a:<16}" for a in AREAS)
    print(header)
    print("-" * len(header))
    for r in results:
        if r.get("error"):
            print(f"{r['content_type']:<18}ERROR {r['error'][:80]}")
            continue
        row = f"{r['content_type']:<18}"
        row += "".join(f"{area_status(r, a):<16}" for a in AREAS)
        print(row)

    print("\n=== Failures and warnings ===")
    for r in results:
        issues = [f"BLOCK {c['name']}: {c['detail']}" for c in r.get("failed", [])] + [
            f"warn  {c['name']}: {c['detail']}" for c in r.get("warnings", [])
        ]
        if r.get("error"):
            issues = [r["traceback"]]
        if r.get("placeholders_in_body"):
            issues.append(f"NOISE in body: {r['placeholders_in_body']}")
        if issues:
            print(f"\n[{r['content_type']}]  words={r.get('word_count')}")
            for issue in issues:
                print(f"  - {issue}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

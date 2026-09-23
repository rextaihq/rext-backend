"""A deterministic stand-in for the writer model.

It produces the payload a COMPLIANT writer would produce for a given approved
outline: every approved section written, the approved internal links woven into
the sentence they belong to, the key facts stated with their real sources, the
brand mentioned where the per-content-type policy says it belongs, and the
focus keyphrase used at the density the pipeline itself asks for.

The point is to hold everything except the pipeline constant. Anything the
validation gate flags against this payload is a property of the pipeline's own
rules — a rule that cannot be satisfied, or one content type's rule leaking
into another — not of a model having a bad day.
"""

from __future__ import annotations

from src.flow.engines.content.generation.keyword_density import (
    analyze_keyword_density,
    count_keyphrase_occurrences,
)
from src.flow.engines.content.generation.outline_structure import OutlineBlock
from src.flow.engines.content.generation.structured_body import assemble_structured_payload

from .outline_fixtures import (
    BRAND,
    FOCUS_KEYPHRASE,
    KEY_FACTS,
    INTERNAL_LINKS,
    SELECTED_TITLE,
)

_KW_HEADINGS = [
    "How seo content tools fit your workflow",
    "Choosing seo content tools for a small team",
    "What seo content tools actually automate",
    "Where seo content tools save the most time",
    "Comparing seo content tools on real work",
    "Rolling out seo content tools to editors",
    "Measuring results from seo content tools",
    "Common seo content tools mistakes to avoid",
    "Budgeting for seo content tools this year",
    "Auditing seo content tools after six months",
]

_PLAIN_HEADINGS = [
    "Why editorial review still matters",
    "Where most content workflows break down",
    "How a brief shapes the finished draft",
    "What to measure after publishing a page",
    "Planning a realistic publishing cadence",
    "Building an approval step editors trust",
    "Keeping research close to the draft",
    "Scaling output without losing your voice",
    "Training an in-house team on a workflow",
    "Avoiding thin pages that never rank well",
    "Refreshing articles that lost their traffic",
    "Connecting approved drafts to your CMS",
    "Reporting on organic growth every month",
    "Deciding what to publish next quarter",
    "Setting expectations with your leadership",
    "Running a pilot before you commit budget",
    "Handing over drafts without a rewrite",
    "Keeping a single source of truth for briefs",
    "Reviewing drafts against the original brief",
    "Closing the loop between data and writing",
]

_FILLER_SENTENCES = [
    "Most in-house teams start from a spreadsheet of queries and a shared document, "
    "which works until two writers and one editor are involved.",
    "The work that decides whether a page ranks happens before anyone writes a "
    "sentence, in the research and the brief.",
    "Editors consistently report that the slow part is not drafting but agreeing "
    "what a page is supposed to say.",
    "A workflow that nobody trusts gets bypassed, and the bypassed version is the "
    "one that quietly produces thin pages.",
    "Treat the brief as the contract between research and writing, and most "
    "arguments about a draft resolve themselves.",
    "Organic growth compounds slowly, so the programmes that win are the ones that "
    "survive a change of marketing lead.",
    "Publishing cadence matters less than consistency; two solid pages a month "
    "beats eight rushed ones followed by silence.",
    "Every additional review stage costs days, so each one has to earn its place in "
    "the process.",
]


def _heading_for(index: int, use_keyphrase: bool) -> str:
    pool = _KW_HEADINGS if use_keyphrase else _PLAIN_HEADINGS
    return pool[index % len(pool)]


def _fact_sentence(fact: dict) -> str:
    claim = fact["text"].rstrip(".")
    return (
        f"[{claim} across the sites studied]({fact['source_url']}). That is the number worth "
        f"holding on to when you argue for a content budget, because it reframes the work as "
        f"an acquisition channel rather than a branding exercise."
    )


def _link_sentence(link: dict) -> str:
    return (
        f"That planning step is the same one described in [{link['anchor_text']}]({link['url']}), "
        f"which walks through {link['context']} in the order a working team would actually "
        f"tackle it rather than as an abstract checklist."
    )


def _brand_sentence() -> str:
    return (
        f"[{BRAND['brand_name']}]({BRAND['brand_url']}) is one platform built around that "
        f"sequence: it turns a keyword into a researched brief, drafts the article from it, "
        f"and holds the draft at an editor approval step before it publishes to WordPress or "
        f"Shopify, which is what keeps a lean team from needing an agency retainer."
    )


def _paragraphs(n: int, offset: int) -> list[str]:
    return [_FILLER_SENTENCES[(offset + i) % len(_FILLER_SENTENCES)] for i in range(n)]


def build_blocks_markdown(
    blocks: list[OutlineBlock],
    brand_block_index: int,
    cta_text: str | None,
) -> dict[str, dict]:
    """One ContentBlock-shaped dict per approved section."""
    total = len(blocks)
    # Keyphrase-bearing headings: aim for the middle of the allowed band.
    kw_target = max(1, round(total * 0.5))
    written: dict[str, dict] = {}
    kw_used = 0
    plain_used = 0
    link_queue = list(INTERNAL_LINKS)
    fact_queue = list(KEY_FACTS)

    for i, block in enumerate(blocks):
        use_kw = kw_used < kw_target and i % 2 == 0
        if use_kw:
            heading = _heading_for(kw_used, True)
            kw_used += 1
        else:
            heading = _heading_for(plain_used, False)
            plain_used += 1

        body: list[str] = _paragraphs(3, i * 3)
        if link_queue and i in (0, min(2, total - 1)):
            body.insert(1, _link_sentence(link_queue.pop(0)))
        if fact_queue and i in (1, min(3, total - 1)):
            body.insert(1, _fact_sentence(fact_queue.pop(0)))
        if i == brand_block_index:
            body.insert(1, _brand_sentence())
        if cta_text and i == total - 1:
            body.append(f"Ready to see it on your own site? {cta_text}")

        written[block.key] = {"heading": heading, "markdown": "\n\n".join(body)}

    # Anything left over still has to land somewhere — a compliant writer would
    # not silently drop an approved link or a sourced fact.
    leftovers = [_link_sentence(link) for link in link_queue] + [
        _fact_sentence(fact) for fact in fact_queue
    ]
    if leftovers and blocks:
        key = blocks[min(1, len(blocks) - 1)].key
        written[key]["markdown"] += "\n\n" + "\n\n".join(leftovers)
    return written


def _introduction() -> str:
    return (
        f"The {FOCUS_KEYPHRASE} a team picks end up shaping how it works, not just what it "
        f"publishes. Choosing between them is less about feature lists and more about which "
        f"part of the process is currently breaking.\n\n"
        "This piece walks through the decisions in the order a team actually faces them: what "
        "to research, who approves a brief, how a draft reaches the CMS, and what to measure "
        "once a page is live.\n\n"
        "None of it assumes a large team or a big budget. The examples throughout come from "
        "in-house programmes run by one or two people alongside other work."
    )


def _pad_to_word_count(payload: dict, target: int, keyphrase: str, content_type: str) -> dict:
    """Grow the body to the approved length and land inside the density band.

    Uses the pipeline's own density analyzer rather than a guessed ratio, so the
    payload is graded against the same policy the writer prompt states.
    """
    intro = payload.get("introduction") or ""
    body = payload.get("body_markdown") or ""
    i = 0
    while len(f"{intro}\n\n{body}".split()) < target:
        body += "\n\n" + _FILLER_SENTENCES[i % len(_FILLER_SENTENCES)]
        i += 1
    payload["body_markdown"] = body

    # Now tune keyphrase occurrences into the measured band.
    for _ in range(80):
        report = analyze_keyword_density(
            text=f"{payload.get('introduction') or ''}\n\n{payload['body_markdown']}",
            keyphrase=keyphrase,
            content_type=content_type,
            extra_text="\n".join(
                str(payload.get(f) or "") for f in ("title", "meta_title", "meta_description")
            ),
        )
        if report["status"] == "ok":
            break
        if report["status"] in ("too_low", "below_min"):
            payload["body_markdown"] += (
                f"\n\nTeams that review their {keyphrase} once a quarter tend to notice a "
                f"gap long before it shows up in the traffic report."
            )
        else:
            break
    return payload


def write_content(
    blocks: list[OutlineBlock],
    spec: dict,
    content_type: str,
    cta_text: str | None,
) -> dict:
    """The payload a compliant writer would hand back, after structured assembly."""
    policy = spec.get("brand_placement_policy") or {}
    # body_only types are graded on the first mention landing inside the body
    # attention window, so a compliant writer puts it in an early body section.
    brand_index = 0 if policy.get("prefers_top") else min(1, max(0, len(blocks) - 1))

    content: dict = {
        "title": SELECTED_TITLE,
        "meta_title": SELECTED_TITLE,
        "meta_description": (
            f"Compare {FOCUS_KEYPHRASE} on the work they really do for a lean in-house "
            f"marketing team, then pick one and start your first brief this week."
        ),
        "slug": "seo-content-tools",
        "focus_keyphrase": FOCUS_KEYPHRASE,
        "introduction": _introduction(),
        "body_markdown": None,
        "facts": list(KEY_FACTS),
        "outbound_links": [],
        "internal_links": [
            {"url": lnk["url"], "anchor_text": lnk["anchor_text"], "rel": None}
            for lnk in INTERNAL_LINKS
        ],
        "images": [],
        "tags": ["seo", "content operations"],
        "category": "SEO",
    }
    if cta_text:
        content["cta"] = {"text": cta_text, "url": BRAND["brand_url"], "placement": "conclusion"}

    content.update(build_blocks_markdown(blocks, brand_index, cta_text))
    payload = assemble_structured_payload(content, blocks)
    payload = _pad_to_word_count(
        payload, spec.get("target_word_count") or 1400, FOCUS_KEYPHRASE, content_type
    )
    return payload


__all__ = ["write_content", "count_keyphrase_occurrences"]

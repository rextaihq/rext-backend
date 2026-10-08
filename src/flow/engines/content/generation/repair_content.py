"""Targeted quality-repair LangGraph node.

A single structured-output-only LLM call (no tools, no full agent
re-invocation) that fixes exactly the checks validate_content flagged.
Always loops back to validate_content (see router/content_quality.py's
validation_router) — bounded by MAX_REPAIR_ATTEMPTS (validation.py).
Soft-fails on any error: the attempt counter still increments so a
transient model failure can never create an infinite loop.

`run_targeted_repair` is the one repair implementation, shared by this node
(pre-humanize) and humanize_content.py's post-humanize brand-compliance
repair — previously humanize_content.py had its own separate, differently-
worded repair prompt/pathway that could drift out of sync with this one;
there is now a single place that knows how to call the repair model.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from src.flow.engines.content.generation.brand_placement_policy import (
    BrandPlacementPolicy,
    build_brand_structural_injection,
)
from src.flow.engines.content.generation.focus_keyword import resolve_focus_keyword
from src.flow.engines.content.generation.link_integrity import (
    LinkRecord,
    dedupe_records,
    reconcile_link_lists,
    restore_lost_links,
)
from src.flow.engines.content.generation.onpage_seo import (
    enforce_onpage_seo,
    merge_preserving_existing,
)
from src.flow.engines.content.generation.repair_salvage import salvage_repair
from src.flow.engines.content.generation.requirements_spec import (
    RequirementsSpec,
    build_requirements_spec,
)
from src.flow.engines.content.generation.subheading_seo import enforce_subheading_seo
from src.flow.model.llm_manager import load_content_model
from src.flow.model.runaway import ainvoke_watched
from src.flow.model.structure.contents import get_generated_content_model
from src.flow.prompts.human.repair import get_repair_prompt
from src.flow.states.rext import REXT

logger = logging.getLogger(__name__)

# Check names whose failure means the repair prompt should carry brand
# context (name/URL) and, where applicable, a concrete structural anchor for
# where the mention belongs — not just brand_presence/url/placement as
# before, which silently dropped that context on a brand_placement_policy or
# brand_integration_depth failure.
_BRAND_RELATED_CHECKS = (
    "brand_url_accuracy",
    "brand_presence",
    "brand_placement",
    "brand_placement_policy",
    "brand_prominence",
    "brand_integration_depth",
    # A flagged claim is often inside the brand mention itself ("Nextly is the
    # best CMS"); the repair must know the brand to soften the claim without
    # dropping the approved mention or its link.
    "unsupported_claims",
)

# Checks whose repair must be grounded in the evidence actually available: the
# retrieved sources to keep or re-cite a claim from, never a guessed value.
_EVIDENCE_RELATED_CHECKS = (
    "facts_and_external_links",
    "unsupported_claims",
)

# Checks whose failure means the repair prompt must carry the exact focus
# keyphrase. Telling a model "keyword density is too low" without giving it the
# literal phrase invites it to optimize for whatever phrase it infers from the
# draft — which is the original bug, reintroduced one layer down.
_KEYWORD_RELATED_CHECKS = (
    "keyword_presence",
    "keyword_density",
)

# Checks repaired by the headings-only rewrite (subheading_seo) rather than the
# full-article repair model. A heading problem does not justify handing the
# whole article to a model that returns every field — that risks the body,
# brand placement and citations to change a handful of heading lines.
SUBHEADING_CHECKS = (
    "subheading_keyphrase",
    "subheading_length",
)

# Checks owned by humanization rather than repair. Humanization already rewrites
# the whole article with an explicit expand/trim instruction measured against
# the same band, so a word-count failure never triggers a repair call on its own
# and is never handed to the repair model alongside other issues: repair is a
# minimal-edit pass, and "add 400 words" is the one instruction that cannot be
# satisfied minimally — attempting it was a leading reason a first repair broke
# density, links and placement and needed a second round.
HUMANIZATION_OWNED_CHECKS = ("word_count_band",)

# Checks whose repair needs the concrete link list (anchor, URL, original
# sentence) rather than a bare URL.
_LINK_RELATED_CHECKS = (
    "links_preserved",
    "internal_links_integration",
    "facts_and_external_links",
)


def checks_already_tried(repair_history: Optional[list[dict]]) -> set[str]:
    """The checks a repair has worked on, with its result kept, that still fail.

    Asking for the same thing again in the same words has not fixed one yet: on seven real
    runs every second attempt at such a check changed nothing (rext-control#818). A check
    counts only when the repair really had its turn: not when the attempt was thrown away,
    not when the model returned nothing, and not when the repair did fix it but the fix was
    lost with a block that broke something else (`lost_checks`).
    """
    tried: set[str] = set()
    for entry in repair_history or []:
        if not entry.get("accepted") or entry.get("no_result"):
            continue
        tried |= set(entry.get("unresolved_checks") or []) - set(entry.get("lost_checks") or [])
    return tried


def checks_worth_an_attempt(
    repairable: list[dict], repair_history: Optional[list[dict]]
) -> list[dict]:
    """The failed checks another repair attempt is run for.

    Not those already tried (above), and not the headings' own (`SUBHEADING_CHECKS`): the
    headings-only pass runs inside any attempt and again after the rewrite, which rewords
    headings anyway, so an attempt for them alone is half a minute for nothing.
    """
    tried = checks_already_tried(repair_history)
    return [
        c
        for c in repairable
        if c.get("name") not in tried and c.get("name") not in SUBHEADING_CHECKS
    ]


def without_facts_removed_with_a_claim(before: dict, after: dict) -> dict:
    """`after` without the facts whose words a repair took out of the prose.

    Asked to fix an unsupported claim, a repair removes or softens the sentence that made
    it. When that sentence carried a cited figure, its entry in `facts` stayed behind, the
    facts check read it as "never woven into the prose", and the fix was thrown away for it:
    3 of 3 replays of one real article (rext-control#818). A fact goes with its sentence: one
    that was in the prose before the repair and is not after it is no longer a fact of the
    article. Presence is judged as the facts check judges it, so exactly the entries it would
    report are the ones dropped.
    """
    facts = after.get("facts")
    if not isinstance(facts, list) or not facts:
        return after
    # Imported here: validation imports this module at load time.
    from src.flow.engines.content.generation.validation import (
        _combined_text,
        _word_overlap_ratio,
    )

    def stated(text: str, prose: str) -> bool:
        return text in prose or _word_overlap_ratio(text, prose) >= 0.2

    was, now = _combined_text(before), _combined_text(after)
    kept = []
    for fact in facts:
        text = (fact.get("text") or "").strip() if isinstance(fact, dict) else ""
        if text and stated(text, was) and not stated(text, now):
            continue
        kept.append(fact)
    return after if len(kept) == len(facts) else {**after, "facts": kept}


# How far a repair may move the article's length. Repair fixes named issues; a
# rewrite that shrinks the body is how unrelated checks (density, links, word
# count) regressed and forced a second attempt.
_REPAIR_LENGTH_TOLERANCE = 0.05


async def enforce_subheadings_for_spec(
    final_content: dict,
    spec: RequirementsSpec,
    *,
    stage: str,
) -> dict:
    """``enforce_subheading_seo`` with its inputs resolved from the requirements spec.

    One call shape for every node (generation, repair, final validation), so
    the keyphrase, synonyms, brand guard and outline-section guard cannot differ
    between stages.
    """
    brand_context = spec.get("brand_context") or {}
    return await enforce_subheading_seo(
        final_content,
        focus_keyphrase=spec.get("target_keyword") or "",
        content_type=spec.get("content_type") or "",
        synonyms=spec.get("keyphrase_synonyms") or [],
        brand_name=brand_context.get("brand_name") or "",
        expected_sections=spec.get("expected_sections") or [],
        stage=stage,
    )


def _build_issues_block(failed_checks: list[dict]) -> str:
    if not failed_checks:
        return "(none)"
    return "\n".join(
        f"{i}. [{c.get('name')}] {c.get('detail')}" for i, c in enumerate(failed_checks, 1)
    )


def _build_sources_block(failed_checks: list[dict], searched_results: list[dict]) -> str:
    """Real search-tool results to draw a genuine replacement citation from.

    Without this, telling the model "this citation is fabricated, fix it"
    just produces a second fabrication — it needs real material to pick from.
    """
    needs_sources = any(c.get("name") in _EVIDENCE_RELATED_CHECKS for c in failed_checks)
    if not needs_sources or not searched_results:
        return ""
    lines = [
        "AVAILABLE VERIFIED SOURCES — only use one of these to replace an unverifiable citation:"
    ]
    # Sources a failed check names come first. Previously this was simply the
    # first six results, so the source a "not woven in" issue was about was often
    # not in the list at all and the repair had nothing to anchor the link on.
    details = " ".join(str(c.get("detail") or "") for c in failed_checks)
    flagged = [r for r in searched_results if r.get("url") and r["url"] in details]
    others = [r for r in searched_results if r not in flagged]
    for r in (flagged + others)[: max(6, len(flagged))]:
        lines.append(
            f"- URL: {r.get('url')}\n  TITLE: {r.get('title')}\n  EXCERPT: {(r.get('snippet') or '')[:400]}"
        )
    return "\n".join(lines)


def _build_brand_block(
    failed_checks: list[dict],
    brand_context: Optional[dict],
    content_type: str = "",
    brand_policy: Optional[BrandPlacementPolicy] = None,
) -> str:
    brand_related = any(c.get("name") in _BRAND_RELATED_CHECKS for c in failed_checks)
    if not brand_related or not brand_context:
        return ""
    brand_name = brand_context.get("brand_name") or ""
    url_line = (
        f"Approved brand URL (use exactly this): {brand_context.get('brand_url')}"
        if brand_context.get("brand_url")
        else "No approved brand URL — mention as plain text only, do not invent one."
    )
    # Only a placement-policy failure needs the concrete WHERE anchor — a
    # wrong-URL or bare-name-drop failure is a same-spot edit, not a move.
    structural = ""
    if content_type and any(c.get("name") == "brand_placement_policy" for c in failed_checks):
        structural = build_brand_structural_injection(content_type, brand_name, brand_policy)
    # When claims are being corrected, the approved brand facts are the only
    # thing a brand claim may be restated with — keep the promotion, swap an
    # unsupported specific for one of these rather than for a new guess.
    approved_facts = ""
    if any(c.get("name") == "unsupported_claims" for c in failed_checks):
        about = " ".join(
            t.strip()
            for t in (brand_context.get("about") or "", brand_context.get("selling_position") or "")
            if t and t.strip()
        )
        if about:
            approved_facts = (
                f"\nApproved brand facts (the only claims {brand_name} may carry): {about}"
            )
    return f"BRAND CONTEXT — Brand: {brand_name}. {url_line}{structural}{approved_facts}"


def _build_exclusion_block(
    failed_checks: list[dict], excluded_brand: Optional[dict], final_content: dict
) -> str:
    """What the repair needs to take an excluded brand out: its name, and the call to action's
    text, which the article fields below don't show (rext-control#760). The call to action's
    link and any link to the brand's site are removed in code, not here."""
    if not excluded_brand or not any(c.get("name") == "brand_absent" for c in failed_checks):
        return ""
    name = excluded_brand.get("brand_name") or ""
    cta = final_content.get("cta") if isinstance(final_content.get("cta"), dict) else {}
    cta_text = (cta.get("text") or "").strip()
    cta_line = (
        f' The call to action reads "{cta_text}". If it names {name}, return `cta.text` reworded '
        "without it, and use that same wording where the article states the call to action."
        if cta_text
        else ""
    )
    return (
        f"BRAND EXCLUSION — the user chose NO mention of {name}. Rewrite every sentence, heading "
        f"or list entry that names it so it says the same without the name: name another real "
        f"product where a list needs one, or none. Do not add a link to its site.{cta_line}"
    )


def _build_keyword_block(failed_checks: list[dict], focus_keyword: str) -> str:
    """Exact-phrase instruction for a keyword presence/density repair.

    The check `detail` already states the measured count and the required band
    (see keyword_density._build_detail), so this block does not restate the
    numbers — it supplies the one thing the detail cannot: that the phrase is
    fixed, is the user's own, and must be reproduced verbatim rather than
    improved upon.
    """
    if not focus_keyword:
        return ""
    if not any(c.get("name") in _KEYWORD_RELATED_CHECKS for c in failed_checks):
        return ""
    return (
        f'FOCUS KEYPHRASE — the focus keyphrase for this article is exactly: "{focus_keyword}".\n'
        "- It is the user's own search query. Do NOT substitute a synonym, reorder its words, "
        "pluralize it, or swap in a phrase you consider better.\n"
        "- Adjust its usage to the count stated in the issue above by rewriting existing "
        "sentences so the exact phrase fits naturally — do not append a keyword list, a summary "
        "paragraph, or repeat it in consecutive sentences.\n"
        "- Good places to add it: the first sentence of the introduction, a section opening "
        "sentence, an H2/H3 where it reads naturally. To reduce it: replace surplus occurrences "
        "with pronouns or natural variants, keeping the meaning identical.\n"
        "- Keep the article's length inside its existing target band while doing this."
    )


def _build_links_block(failed_checks: list[dict], protected: list[LinkRecord]) -> str:
    """The links this repair must keep, and (for a link failure) how to put one back.

    Stated as an explicit list on every repair that has protected links: a
    general "don't remove links" rule is exactly what a full-article structured
    rewrite kept breaking, and a dropped link was then a new failure for the next
    round to fix.
    """
    if not protected:
        return ""
    lines = [
        "LINKS THAT MUST SURVIVE — every one of these is a verified or approved link. Each must "
        "appear in your output as a markdown link with this exact URL, in the same section and "
        "the same (or the rewritten) sentence. Reword an anchor only if you rewrite its sentence:"
    ]
    lines.extend(f"- [{r.get('anchor_text') or r.get('url')}]({r.get('url')})" for r in protected)
    if any(c.get("name") in _LINK_RELATED_CHECKS for c in failed_checks):
        lines.append(
            "To restore or embed a link named in an issue: find the sentence given as its original "
            "sentence (or the sentence in that section that now makes the same point) and turn the "
            "matching words into [anchor](url). If no sentence makes that point any more, add one "
            "short, specific clause to the most relevant existing sentence in that section. Never "
            "add a bare link line, a 'Read more' line, or a list of links."
        )
    return "\n".join(lines)


def _word_count(final_content: dict) -> int:
    return len(
        f"{final_content.get('introduction') or ''} {final_content.get('body_markdown') or ''}".split()
    )


def _build_length_block(final_content: dict) -> str:
    words = _word_count(final_content)
    if not words:
        return ""
    low = round(words * (1 - _REPAIR_LENGTH_TOLERANCE))
    high = round(words * (1 + _REPAIR_LENGTH_TOLERANCE))
    return (
        f"LENGTH — the article is currently {words} words. Return {low}-{high} words. Length is "
        "handled by a later stage: do not summarize, shorten, drop or merge any section, "
        "paragraph, list or table while fixing the issues. Return every section in full."
    )


def _build_previous_attempt_block(previous_attempt: Optional[dict]) -> str:
    """Why the previous repair did not settle it — so a retry is not a repeat."""
    if not previous_attempt:
        return ""
    parts = []
    if previous_attempt.get("regressed_checks"):
        parts.append(
            "it broke checks that were already passing ("
            + ", ".join(previous_attempt["regressed_checks"])
            + ") and was discarded — fix the issues WITHOUT changing what those checks measure"
        )
    if previous_attempt.get("unresolved_checks"):
        parts.append(
            "it did not resolve: "
            + ", ".join(previous_attempt["unresolved_checks"])
            + " — re-read those issues and apply every item they list, not just the first"
        )
    if not parts:
        return ""
    return "PREVIOUS REPAIR ATTEMPT FAILED — " + "; ".join(parts) + "."


async def run_targeted_repair(
    *,
    final_content: dict,
    content_type: str,
    failed_checks: list[dict],
    brand_context: Optional[dict] = None,
    searched_results: Optional[list[dict]] = None,
    focus_keyword: str = "",
    selected_title: str = "",
    article_stage: str = "pre-humanization (raw draft — tone not yet finalized)",
    protected: Optional[list[LinkRecord]] = None,
    previous_attempt: Optional[dict] = None,
    brand_policy: Optional[BrandPlacementPolicy] = None,
    excluded_brand: Optional[dict] = None,
) -> dict | None:
    """Core repair LLM call: fix exactly the listed issues, minimally.

    Returns the updated final_content dict, or None on failure (no schema for
    this content type, or the model call/re-validation raised) — soft-fail,
    the caller decides what to do when this returns None (repair_content
    keeps the pre-repair content; humanize_content's post-check logs and
    ships the unrepaired-but-otherwise-valid content).
    """
    schema = get_generated_content_model(content_type)
    if schema is None:
        logger.warning(
            "run_targeted_repair: no schema for content_type=%r; cannot repair.", content_type
        )
        return None

    failed_checks = [c for c in failed_checks if c.get("name") not in HUMANIZATION_OWNED_CHECKS]
    if not failed_checks:
        logger.info("run_targeted_repair: only humanization-owned checks listed; no repair call.")
        return None
    protected = dedupe_records(protected or [])

    preservation_block = "\n\n".join(
        filter(
            None,
            [
                _build_previous_attempt_block(previous_attempt),
                _build_links_block(failed_checks, protected),
                _build_length_block(final_content),
            ],
        )
    )
    sources_block = "\n\n".join(
        filter(
            None,
            [
                _build_sources_block(failed_checks, searched_results or []),
                _build_brand_block(failed_checks, brand_context, content_type, brand_policy),
                _build_exclusion_block(failed_checks, excluded_brand, final_content),
                _build_keyword_block(failed_checks, focus_keyword),
            ],
        )
    )
    locked_title = (selected_title or final_content.get("title") or "").strip()
    prompt_data = {
        "article_stage": article_stage,
        "issues_block": _build_issues_block(failed_checks),
        "sources_block": f"\n{sources_block}\n" if sources_block else "",
        "preservation_block": f"\n{preservation_block}\n" if preservation_block else "",
        "title": locked_title,
        "meta_description": final_content.get("meta_description") or "(missing)",
        "introduction": final_content.get("introduction") or "",
        "body_markdown": final_content.get("body_markdown") or "",
    }

    try:
        model = load_content_model().with_structured_output(schema)
        messages = get_repair_prompt().format_messages(**prompt_data)
        repaired_obj = await ainvoke_watched(model, messages, stage="repair")
        repaired_payload = (
            repaired_obj.model_dump() if hasattr(repaired_obj, "model_dump") else dict(repaired_obj)
        )
        # Merge onto the original rather than trusting every unrelated field
        # was echoed back verbatim, then re-validate through the Pydantic
        # model so enforce_internal_links_in_body re-applies. model_dump()
        # only covers schema fields, so bookkeeping keys generate_content
        # added outside the schema (status, rejected_reason) are layered back
        # on top afterward.
        #
        # merge_preserving_existing, not a plain dict merge: the repair model
        # returns the FULL schema, so every optional field it chose not to
        # rewrite comes back as None. A plain merge therefore deleted a good
        # meta_description, slug or category that generation had produced —
        # which is one of the two ways an article reached the user with no meta
        # description at all.
        merged = merge_preserving_existing(final_content, repaired_payload)
        # Put back any protected link the rewrite dropped, in place, and match the
        # link lists to the prose — both BEFORE model_validate, whose internal-link
        # fallback would otherwise append a dropped link as a bare trailing line
        # (a bolted-on failure that alone forced a second repair round).
        merged, restored, still_missing = restore_lost_links(merged, protected)
        if restored or still_missing:
            logger.info(
                "run_targeted_repair: links restored in place=%s not restorable=%s",
                [r.get("url") for r in restored],
                [r.get("url") for r in still_missing],
            )
        merged = reconcile_link_lists(final_content, merged)
        revalidated = schema.model_validate(merged)
        merged = merge_preserving_existing(merged, revalidated.model_dump())
        # The user-selected title is read-only. A repair prompt that is fixing
        # a keyword or section issue has no business rewording it, but it does
        # emit the field, so the lock is re-applied here rather than trusted.
        return enforce_onpage_seo(
            merged,
            selected_title=locked_title,
            focus_keyphrase=focus_keyword,
            stage="targeted_repair",
        )
    except Exception:
        logger.exception("run_targeted_repair: repair attempt failed (model error).")
        return None


async def repair_content(state: REXT) -> dict:
    content_state = state.get("content") or {}
    final_content = content_state.get("final_content") or {}
    outline = content_state.get("outline") or {}
    content_type = content_state.get("content_type", "")
    review = content_state.get("review") or {}
    searched_results = (content_state.get("generation_meta") or {}).get("searched_results") or []

    validation = review.get("validation") or {}
    failed_checks = validation.get("failed_checks") or []
    attempt_number = review.get("repair_attempts", 0) + 1
    # deep_merge_dicts replaces lists wholesale rather than merging them, so
    # this must read the existing history and return the FULL appended list —
    # never a single-entry list, or prior attempts silently vanish.
    repair_history = list(review.get("repair_history") or [])

    # Humanization owns word count; it is never a repair target (see
    # HUMANIZATION_OWNED_CHECKS). validate_content does not route here for a
    # word-count-only failure, and this filter keeps it out of a mixed one.
    repair_targets = [c for c in failed_checks if c.get("name") not in HUMANIZATION_OWNED_CHECKS]
    targeted_checks = [c.get("name") for c in repair_targets]
    updated_final_content = final_content
    generation_meta = content_state.get("generation_meta") or {}
    history_entry: dict = {}

    if not repair_targets:
        logger.info("repair_content: no repairable failed checks; passing through unchanged.")
    else:
        # Imported here: validation imports this module at load time.
        from src.flow.engines.content.generation.validation import (
            apply_brand_exclusion,
            apply_density_report,
            merge_link_inventory,
            protected_links,
            run_checks,
        )

        spec = build_requirements_spec(
            outline,
            content_type,
            resolve_focus_keyword(state),
            content_state.get("selected_topic") or "",
            generation_meta=generation_meta,
        )
        protected = merge_link_inventory(
            spec.get("link_inventory"), protected_links(final_content, spec, searched_results)
        )
        # What the model is asked for: not the headings' own checks (their pass follows),
        # and not what an earlier attempt already worked on and left failing.
        article_checks = checks_worth_an_attempt(repair_targets, repair_history)
        asked = {c.get("name") for c in article_checks}
        targeted_checks = [
            name for name in targeted_checks if name in asked or name in SUBHEADING_CHECKS
        ]
        # The note about the attempt before names only what is asked for again.
        previous_attempt = None
        if repair_history:
            previous_attempt = {
                **repair_history[-1],
                "unresolved_checks": [
                    name
                    for name in repair_history[-1].get("unresolved_checks") or []
                    if name in asked
                ],
            }
        candidate = final_content
        no_result = False
        if article_checks:
            repaired = await run_targeted_repair(
                final_content=final_content,
                content_type=content_type,
                failed_checks=article_checks,
                brand_context=spec.get("brand_context"),
                searched_results=searched_results,
                focus_keyword=spec.get("target_keyword") or "",
                selected_title=spec.get("selected_title") or "",
                article_stage="pre-humanization (raw draft — tone not yet finalized)",
                protected=protected,
                previous_attempt=previous_attempt,
                brand_policy=spec.get("brand_placement_policy"),
                excluded_brand=spec.get("excluded_brand"),
            )
            if repaired is not None:
                # The repair returns every field: the brand choice's cleanup applies to it too.
                candidate = apply_brand_exclusion(repaired, spec, stage="repair_content")
            else:
                no_result = True
                logger.warning(
                    "repair_content: attempt %d model call failed — keeping pre-repair content; "
                    "attempt counter still increments to bound the loop.",
                    attempt_number,
                )

        # Headings last: they were either flagged directly, or the article
        # repair above may have reworded them. A no-op (no model call) when the
        # headings already comply.
        candidate = await enforce_subheadings_for_spec(candidate, spec, stage="repair_content")

        # Verify before accepting. A repair that fixes the named issue while
        # breaking a check that was passing is the loop this node used to create:
        # the next validation failed on the new breakage, a second repair ran, and
        # the article could end up worse than before either. Such a repair is not
        # accepted as it stands, but it is not thrown away whole either: what of it
        # fixes an issue and breaks nothing is kept (repair_salvage), and only when
        # no such part exists does the pre-repair content stand. The next attempt is told exactly what
        # the repair broke. Humanization-owned checks are excluded from "regressed":
        # length is corrected after this loop.
        failed_before = {c.get("name") for c in failed_checks}

        def settled(content: dict) -> dict:
            """The content as it would be kept: a fact goes with the claim a repair removed."""
            if "unsupported_claims" not in asked:
                return content
            return without_facts_removed_with_a_claim(final_content, content)

        def failing(content: dict) -> set[str]:
            blocking, _ = run_checks(
                apply_density_report(settled(content), spec), spec, searched_results
            )
            return {c["name"] for c in blocking}

        failed_after = failing(candidate)
        regressed = sorted(failed_after - failed_before - set(HUMANIZATION_OWNED_CHECKS))
        fixed_by_the_repair = [name for name in targeted_checks if name not in failed_after]
        salvaged = None
        if regressed:
            kept, how = salvage_repair(
                final_content,
                candidate,
                failing,
                failed_before,
                ignore=HUMANIZATION_OWNED_CHECKS,
            )
            if kept is not None:
                candidate, salvaged = kept, how
                failed_after = failing(candidate)
        candidate = settled(candidate)
        unresolved = [name for name in targeted_checks if name in failed_after]
        resolved = [name for name in targeted_checks if name not in failed_after]
        accepted = not regressed or salvaged is not None
        history_entry = {
            "accepted": accepted,
            "resolved_checks": resolved,
            "unresolved_checks": unresolved,
            "regressed_checks": regressed,
        }
        if salvaged is not None:
            # Kept in part: how, and which fixes went with the blocks that broke something
            # (those have not had their turn; see checks_already_tried).
            history_entry["salvaged"] = salvaged
            history_entry["lost_checks"] = [n for n in fixed_by_the_repair if n in failed_after]
        if no_result:
            history_entry["no_result"] = True
        if accepted:
            updated_final_content = candidate
            generation_meta = {
                **generation_meta,
                "link_inventory": merge_link_inventory(
                    protected, protected_links(candidate, spec, searched_results)
                ),
            }
            logger.info(
                "repair_content: attempt %d accepted — resolved=%s unresolved=%s kept_in_part=%s "
                "broke=%s",
                attempt_number,
                resolved,
                unresolved,
                salvaged,
                regressed,
            )
        else:
            logger.warning(
                "repair_content: attempt %d discarded — it broke previously passing checks %s "
                "(resolved=%s unresolved=%s).",
                attempt_number,
                regressed,
                resolved,
                unresolved,
            )

    repair_history.append(
        {
            "attempt": attempt_number,
            "targeted_checks": targeted_checks,
            "at": datetime.now(timezone.utc).isoformat(),
            **history_entry,
        }
    )

    return {
        "content": {
            **content_state,
            "final_content": updated_final_content,
            "generation_meta": generation_meta,
            "review": {
                **review,
                "repair_attempts": attempt_number,
                "repair_history": repair_history,
            },
        }
    }

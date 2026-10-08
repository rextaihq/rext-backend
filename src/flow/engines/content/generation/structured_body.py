"""Derive a structured body model for an article from its APPROVED OUTLINE.

The outline is the single source of truth for structure. Its per-content-type
Pydantic model already declares which blocks exist and which are mandatory (a
non-Optional field), and `resolve_outline_structure` already reconciles that
schema against the values the user actually approved. This module turns that
same block list into a Pydantic model for the *article*, so structure is
enforced by constrained decoding at generation time instead of being requested
in prose and pattern-matched afterwards.

Deriving rather than hand-writing is the point. Thirty-four hand-maintained
content models mirroring thirty-four outline models is exactly the duplication
that drifts: add a field to an outline schema and the content schema silently
falls behind. Here a new outline field flows through with no second edit, and
the two definitions cannot disagree because there is only one.

What this module does NOT touch, by design:
  * `body_markdown` remains the representation everything downstream reads —
    persistence, the WordPress publisher, EEAT/on-page/readability scoring, the
    API schemas, and every existing validator. It becomes derived rather than
    generated; its consumers see no change.
  * Facts, internal/outbound links, images, CTA, schema markup and SEO metadata
    stay on `BaseGeneratedContent` as they are today. Research results (Tavily)
    stay in `generation_meta`, out of the output schema entirely.
  * Brand placement, validation and repair keep using the existing policy and
    check functions. Structure being reliable makes those checks easier to
    satisfy; it does not replace them.

Nothing here is wired into generation yet — this is the additive groundwork.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Callable, List, Optional

from pydantic import BaseModel, Field, create_model

from src.flow.engines.content.generation.brand_slot import SLOT_LINE_PREFIX
from src.flow.engines.content.generation.link_integrity import extract_links, restore_lost_links
from src.flow.engines.content.generation.outline_structure import (
    OutlineBlock,
    expand_section_containers,
    faq_section_heading,
    is_cta_key,
    is_faq_section,
    render_section_plan,
    resolve_outline_structure,
)
from src.flow.engines.content.generation.seo_title_rules import display_keyphrase
from src.flow.engines.content.generation.subheading_seo import (
    heading_length_issue,
    subheading_report,
)
from src.flow.engines.content.generation.title_articles import reads_as_another_language
from src.flow.engines.content.generation.word_count_utils import TYPED_SECTION_WORDS_KEY
from src.flow.model.structure.content import Link
from src.flow.model.structure.contents.base import (
    EMPTY_SCHEMA_CONTEXT,
    ContentBlock,
    SchemaContext,
    blocks_to_body_markdown,
)

logger = logging.getLogger(__name__)

# Key recording the block keys a structured generation actually produced.
# Underscore-prefixed so Pydantic's extra="ignore" drops it at the first
# model_validate downstream — it describes how this payload was produced, not
# part of the content contract, and it must not reach the DB or the API.
STRUCTURED_BLOCKS_KEY = "_structured_block_keys"

# Key carrying links the model wrote only into its own `body_markdown` that could
# not be re-anchored in the assembled sections. Same underscore convention: the
# generation node pops it into the link inventory, it never reaches persistence.
UNPLACED_LINKS_KEY = "_unplaced_body_links"

# The structured model's own description for `body_markdown`. The base model's
# description demands every link be written there, which is the instruction that
# made the writer put links in a field this module then replaces.
_STRUCTURED_BODY_MARKDOWN_DESCRIPTION = (
    "Leave this null. The article body is assembled automatically from the section "
    "fields, and anything written here is discarded. Write every paragraph, inline "
    "link [anchor](url) and citation inside the section `markdown` fields (or the "
    "`introduction`), in the sentence it supports."
)
_STRUCTURED_INTERNAL_LINKS_DESCRIPTION = (
    "MANDATORY: populate this with every internal link provided in the prompt's "
    "INTERNAL LINKS block. Every URL in this list MUST also be embedded as an inline "
    "hyperlink [anchor](url) inside the `markdown` of the section it is most relevant "
    "to. Do not omit any link from the prompt."
)

# Cache keyed on the block signature, not just the content type: two articles of
# the same type can resolve to different block sets, because
# resolve_outline_structure skips blocks the approved outline left empty and
# appends any user-added ones. Rebuilding an identical model per article would
# also defeat Pydantic's own schema caching.
_MODEL_CACHE: dict[tuple, type[BaseModel]] = {}


def _model_key(content_type: str, blocks: list[OutlineBlock]) -> tuple:
    return (content_type, tuple((b.key, b.required) for b in blocks))


def _is_per_article(blocks: list[OutlineBlock]) -> bool:
    """A model with expanded sections describes this article's own plan, so it is not cached."""
    return any(b.parent for b in blocks)


def _section_description(block: OutlineBlock) -> str:
    """A planned section's field: its place, its approved heading and its plan."""
    shape = (
        f"an H{block.level} subsection of the section before it"
        if block.level > 2
        else "its own H2 section"
    )
    lines = [
        f"Planned section {block.position} of {block.of}: {block.heading!r}, written as "
        f"{shape}, in this position.",
        "REQUIRED — write it in full; never merge it into another section or leave it out."
        if block.required
        else "Optional — write it when the approved outline gives it content, otherwise leave null.",
        # A heading the user reworded in the outline step is theirs: it's used word for
        # word, and assembly writes it whatever the model returns (G70,
        # revnix/rext-control#586). The others may still be tuned for the keyphrase.
        f"Use the heading {block.heading!r} as `heading`, word for word: the user wrote it."
        if _heading_edited(block)
        else f"Use the approved heading {block.heading!r} as `heading`; change its wording "
        "only to read naturally, never its meaning.",
    ]
    if isinstance(block.data, dict) and is_faq_section(block.data):
        lines.append(
            "This is the article's FAQ section: write the approved FAQs here, as questions "
            "and answers. There is no other FAQ section."
        )
    plan = render_section_plan(block.data)
    if plan:
        lines.append("Its approved plan:\n" + plan)
    return "\n".join(lines)


def _heading_edited(block: OutlineBlock) -> bool:
    return isinstance(block.data, dict) and block.data.get("heading_edited") is True


def _without_separate_faqs(
    blocks: list[OutlineBlock], outline: dict, content_type: str
) -> list[OutlineBlock]:
    """The blocks less the outline's FAQ list when a planned section holds the FAQs.

    That section is where they're written (G71, revnix/rext-control#587): the list as
    a required block of its own made the writer write them twice.
    """
    if not faq_section_heading(outline, content_type):
        return blocks
    kept = [b for b in blocks if b.key not in ("faqs", "faq")]
    if len(kept) != len(blocks):
        logger.info(
            "structured body: content_type=%s writes the FAQs in their planned section",
            content_type,
        )
    return kept


def _writer_blocks(outline: dict, content_type: str) -> list[OutlineBlock]:
    """The blocks the article's body is assembled from, in order: what
    build_structured_content_model keeps (a block a typed field of the content model owns,
    such as a how-to guide's `steps`, is written through that field), each planned section a
    block of its own, less the call to action, which is a line or two and no section."""
    from src.flow.model.structure.contents import get_generated_content_model

    base_model = get_generated_content_model(content_type)
    reserved = set(base_model.model_fields) if base_model is not None else set()
    resolved = [
        block
        for block in resolve_outline_structure(outline or {}, content_type)
        if block.key not in reserved
    ]
    blocks = _without_separate_faqs(
        expand_section_containers(resolved), outline or {}, content_type
    )
    return [block for block in blocks if not is_cta_key(block.key)]


def planned_section_count(outline: dict, content_type: str) -> int:
    """How many H2 sections the writer is asked for (planned subsections, H3 and H4, are part
    of their section). 0 when the outline resolves to none."""
    return sum(1 for block in _writer_blocks(outline, content_type) if block.level == 2)


def _section_list(outline: dict) -> list[dict]:
    """The outline's own list of sections, as the brand slot reads it (brand_slot.py):
    `structure.sections`, or a flat `sections`."""
    container = outline.get("structure")
    sections = container.get("sections") if isinstance(container, dict) else None
    if not isinstance(sections, list):
        sections = outline.get("sections")
    return [s for s in sections if isinstance(s, dict)] if isinstance(sections, list) else []


def _holds_brand_slot(value: Any) -> bool:
    """Whether a brand slot was reserved here: a line the review step wrote for the writer
    ("Work in the approved mention of …"), at any depth."""
    if isinstance(value, str):
        return value.startswith(SLOT_LINE_PREFIX)
    if isinstance(value, dict):
        return any(_holds_brand_slot(item) for item in value.values())
    if isinstance(value, list):
        return any(_holds_brand_slot(item) for item in value)
    return False


def early_body_sections(outline: dict, content_type: str, fraction: float) -> list[str]:
    """What "an early body section" means for this outline, by name: the sections inside the
    first ``fraction`` of the article by their place in the plan.

    A writer told "inside the first 30% of the article" cannot measure it, and put the one
    mention a section too late (31% on a ten-section guide, rext-control#760).

    It never says anything the brand slot does not (brand_slot.py reserves the section the
    mention belongs in, and brand_schema_context tells the writer that field):

    * a slot reserved in the outline's section list is the one section named;
    * with none reserved, the window is counted as the slot counts it, over the same list:
      the first ``max(1, int(sections x fraction))`` entries, H3s included;
    * a slot reserved anywhere else (a typed list of a fixed-shape type) says where already,
      and nothing is named here;
    * an outline with no section list (a how-to's blocks) is counted over the blocks the body
      is built from, the opening and the FAQ left out.
    """
    outline = outline or {}
    sections = _section_list(outline)
    if sections:
        reserved = [section for section in sections if _holds_brand_slot(section)]
        named = reserved[:1] or sections[: max(1, int(len(sections) * fraction))]
        return [str(s.get("heading") or "").strip() for s in named if s.get("heading")]
    if _holds_brand_slot(outline):
        return []
    parts = [
        block
        for block in _writer_blocks(outline, content_type)
        if block.key not in ("hero", "faq", "faqs")
        and not (isinstance(block.data, dict) and is_faq_section(block.data))
    ]
    return [block.heading for block in parts[: max(1, int(len(parts) * fraction))]]


def _field_description(block: OutlineBlock) -> str:
    if block.parent:
        return _section_description(block)
    requirement = (
        "REQUIRED — this content type declares this section mandatory; it must be written."
        if block.required
        else "Optional — write it when the approved outline gives it content, otherwise leave null."
    )
    return (
        f"The '{block.heading}' section of the article. {requirement} "
        f"Cover what the approved outline specifies for this block, and give it a "
        f"reader-facing heading rather than the field name."
    )


def build_structured_body_model(
    outline: dict,
    content_type: str,
    blocks: Optional[list[OutlineBlock]] = None,
) -> Optional[type[BaseModel]]:
    """A Pydantic model whose fields are this article's approved sections.

    Required outline blocks become required `ContentBlock` fields; optional ones
    become `Optional[ContentBlock] = None`. Field order follows the outline's
    schema declaration order, which is the same order the generation prompt and
    `blocks_to_body_markdown` use — so the plan the model is given, the object it
    returns and the assembled article can never disagree about ordering.

    Returns None when the outline resolves to no structural blocks (an empty or
    unrecognised outline), so callers can fall back to today's prose generation
    rather than fail. Structure being underivable is a reason to degrade, not to
    break a production run.
    """
    resolved = blocks if blocks is not None else resolve_outline_structure(outline, content_type)
    resolved = _without_separate_faqs(expand_section_containers(resolved), outline, content_type)
    if not resolved:
        logger.info(
            "build_structured_body_model: no structural blocks for content_type=%s; "
            "caller should fall back to unstructured generation.",
            content_type,
        )
        return None

    key = _model_key(content_type, resolved)
    cached = _MODEL_CACHE.get(key)
    if cached is not None:
        return cached

    fields: dict[str, tuple] = {}
    for block in resolved:
        description = _field_description(block)
        if block.required:
            fields[block.key] = (ContentBlock, Field(description=description))
        else:
            fields[block.key] = (
                Optional[ContentBlock],
                Field(default=None, description=description),
            )

    model_name = "".join(part.title() for part in content_type.split("-")) + "StructuredBody"
    model = create_model(model_name, **fields)
    if not _is_per_article(resolved):
        _MODEL_CACHE[key] = model

    logger.info(
        "build_structured_body_model: content_type=%s blocks=%s required=%s",
        content_type,
        [b.key for b in resolved],
        [b.key for b in resolved if b.required],
    )
    return model


def structured_body_to_markdown(
    structured_body: BaseModel,
    blocks: list[OutlineBlock],
) -> str:
    """Assemble a filled structured body into `body_markdown`, in block order.

    Order comes from `blocks` rather than the model's own field order so that a
    single source — the resolved outline — governs both what is asked for and how
    it is laid out.
    """
    ordered = [(block.key, getattr(structured_body, block.key, None)) for block in blocks]
    return blocks_to_body_markdown(ordered, levels={b.key: b.level for b in blocks})


def describe_expected_blocks(blocks: list[OutlineBlock]) -> str:
    """Human-readable required/optional summary, for prompts and logs."""
    return ", ".join(f"{b.key}{'' if b.required else ' (optional)'}" for b in blocks)


# Structured generation is on for every content type. The escape hatch is an
# EXCLUSION list rather than an allow-list, so a type opts out explicitly and a
# newly added content type is structured by default rather than silently
# reverting to prose.
#
# Nothing is excluded today. The candidate if generation proves unreliable is
# `comparison`, which resolves to the most blocks of any type in a single
# structured response — watch its retry rate first. Excluding a type here
# restores exactly today's prose generation for it, with no other change.
STRUCTURED_BODY_EXCLUDED_TYPES: frozenset[str] = frozenset()


def uses_structured_body(content_type: str) -> bool:
    from src.flow.model.structure.outlines import normalize_content_type

    return normalize_content_type(content_type) not in STRUCTURED_BODY_EXCLUDED_TYPES


def build_structured_content_model(
    outline: dict,
    content_type: str,
    base_model: type[BaseModel],
    blocks: Optional[list[OutlineBlock]] = None,
    context: Optional[SchemaContext] = None,
) -> Optional[tuple[type[BaseModel], list[OutlineBlock]]]:
    """`<Type>GeneratedContent` extended with one field per approved section.

    The base model is kept whole rather than replaced: every existing field —
    facts, internal/outbound links, images, CTA, schema markup, SEO metadata —
    stays exactly as it is, because none of them are part of the structure
    problem. Only the article's prose gains typed shape.

    `body_markdown` is left declared but is assembled from the blocks after
    generation (see `assemble_structured_payload`), so the model is not asked to
    produce the same prose twice.

    `context` carries run-specific guidance to fold into the schema — resolved
    from the approved outline when not supplied. It is what puts the approved
    brand's placement rules on the field that has to satisfy them, instead of
    leaving them to a prompt paragraph several thousand tokens away. An empty
    context changes nothing about the produced model.

    Returns (model, blocks), or None when structure can't be derived — the caller
    then generates exactly as it does today.
    """
    resolved = blocks if blocks is not None else resolve_outline_structure(outline, content_type)
    if not resolved:
        return None

    # A block key that matches an existing base field would REPLACE that field's
    # type. `cta` and `images` collide on all 34 content types: the base model
    # declares them as a typed CTABlock and a list of ImageAltText, and turning
    # either into a prose ContentBlock would break check_cta_presence, the
    # placeholder-image stripper and the WordPress featured-image lookup. Those
    # already have dedicated typed fields carrying them, so they must never
    # become prose blocks — drop them from the structured set and let the base
    # model keep ownership.
    reserved = set(base_model.model_fields)
    collisions = [b.key for b in resolved if b.key in reserved]
    if collisions:
        resolved = [b for b in resolved if b.key not in reserved]
        logger.info(
            "build_structured_content_model: content_type=%s blocks already owned by typed "
            "base fields, left to the base model: %s",
            content_type,
            collisions,
        )
    if not resolved:
        logger.info(
            "build_structured_content_model: content_type=%s has no blocks left after "
            "collision filtering; using unstructured generation.",
            content_type,
        )
        return None

    # Each planned section of a container (blog's `structure.sections`) gets a
    # field of its own, so the writer can't fold sections together
    # (rext-control#329). After the collision filter: a container a typed field
    # owns (how-to-guide's `steps`) stays with that field.
    resolved = _without_separate_faqs(expand_section_containers(resolved), outline, content_type)

    # Resolved here rather than demanded from the caller, because everything it
    # needs is already in `outline` — so the call site is unchanged and no stage
    # can forget to pass it.
    if context is None:
        from src.flow.engines.content.generation.brand_schema_context import (
            resolve_brand_schema_context,
        )

        try:
            context = resolve_brand_schema_context(outline, content_type, resolved)
        except Exception:
            # Same philosophy as the rest of this module: guidance that cannot be
            # resolved degrades to none, it does not take a production run down.
            logger.exception(
                "build_structured_content_model: could not resolve schema context for "
                "content_type=%s; building without it.",
                content_type,
            )
            context = EMPTY_SCHEMA_CONTEXT

    # The signature MUST be part of the key. Without it, two articles of the same
    # content type with the same block set share a cache entry — so a
    # brand-disabled run could be handed the model built for a brand-approved one
    # and inherit its injected rules, which is precisely the leak this guidance
    # exists to prevent. An empty context contributes `()`, leaving the key
    # identical to what it was before contexts existed.
    key = (
        ("content", base_model.__name__)
        + _model_key(content_type, resolved)[1:]
        + context.signature
    )
    cached = None if _is_per_article(resolved) else _MODEL_CACHE.get(key)
    if cached is not None:
        return cached, resolved

    fields: dict[str, tuple] = {}
    for block in resolved:
        description = context.describe_field(block.key, _field_description(block))
        if block.required:
            fields[block.key] = (ContentBlock, Field(description=description))
        else:
            fields[block.key] = (
                Optional[ContentBlock],
                Field(default=None, description=description),
            )

    # Re-describe the two base fields that point the writer at `body_markdown`.
    # Same types and defaults, so every validator and downstream consumer is
    # unchanged; only where the model is told to write links changes.
    if "body_markdown" in base_model.model_fields:
        fields["body_markdown"] = (
            Optional[str],
            Field(default=None, description=_STRUCTURED_BODY_MARKDOWN_DESCRIPTION),
        )
    if "internal_links" in base_model.model_fields:
        fields["internal_links"] = (
            List[Link],
            Field(default_factory=list, description=_STRUCTURED_INTERNAL_LINKS_DESCRIPTION),
        )

    model_name = base_model.__name__ + "Structured"
    # Passed only when there is something to say, so a run with no guidance
    # produces exactly the model it produced before.
    extra: dict = {}
    if context and hasattr(base_model, "schema_doc"):
        extra["__doc__"] = base_model.schema_doc(context)
    try:
        model = create_model(model_name, __base__=base_model, **extra, **fields)
    except Exception:
        # A block key colliding with an existing base field (or any other schema
        # conflict) must not take generation down — fall back to prose.
        logger.exception(
            "build_structured_content_model: could not extend %s for content_type=%s; "
            "falling back to unstructured generation.",
            base_model.__name__,
            content_type,
        )
        return None

    if not _is_per_article(resolved):
        _MODEL_CACHE[key] = model
    logger.info(
        "build_structured_content_model: %s -> %s blocks=%s schema_context=%s directive_fields=%s",
        base_model.__name__,
        model_name,
        describe_expected_blocks(resolved),
        context.signature or "none",
        sorted(context.field_directives or {}),
    )
    return model, resolved


# ── Sections a typed field writes (G98, revnix/rext-control#812) ─────────────
#
# A block whose key is also a typed field of the content model is left to that
# field (the collision filter in `build_structured_content_model`), which is
# right for `cta` and `images`. Three of those fields are sections of the
# article, though, and nothing ever put them in the body: a how-to guide's
# steps, an in-depth review's verdict and a tutorial's prerequisites were
# written and never shown. They are rendered here, once, at assembly, where the
# block's place in the approved order is known. The typed field stays in the
# payload as it is.

# A number the writer put before a step's title ("Step 2: Mix", "2. Mix", "2) Mix"): the list
# numbers the steps itself. Not a number the title starts with ("10-minute bake").
_STEP_NUMBER = re.compile(r"^(?:step\s*\d+(?:\s*[.:)–—-]\s*|\s+)|\d{1,2}[.)]\s+)", re.IGNORECASE)
_WHOLLY_EMPHASIZED = re.compile(r"(\*{1,3})(.+?)\1")
# Underscores at a word's edge would read as emphasis ("__init__"); inside a word they don't.
_EDGE_UNDERSCORES = re.compile(r"(?<![A-Za-z0-9])_+|_+(?![A-Za-z0-9])")


def _step_title(title: Any) -> str:
    """A step's title as the list sets it in bold: without asterisks of emphasis around the
    whole of it and without the writer's own numbering. An asterisk or an underscore that is
    part of it is the writer's ("SELECT *", "__init__") and is shown as one."""
    title = " ".join(str(title or "").split())
    emphasized = _WHOLLY_EMPHASIZED.fullmatch(title)
    if emphasized:
        title = emphasized.group(2).strip()
    title = _STEP_NUMBER.sub("", title).strip().replace("*", "\\*")
    return _EDGE_UNDERSCORES.sub(lambda run: "\\_" * len(run.group()), title)


# A step's text that is more than a sentence: a blank line, a code fence or a list inside it.
_HAS_BLOCKS = re.compile(r"\n[ \t]*\n|```|~~~|\n[ \t]*(?:[-*+]|\d+[.)])[ \t]")


def _step_text(description: Any, indent: int) -> str:
    """A step's instructions on the step's line. Text of several blocks (a paragraph break, a
    code block, a list) keeps its lines, each indented as an item of a numbered list needs, so
    a fence stays a fence; a sentence the writer merely wrapped is one line."""
    text = str(description or "").strip()
    if not _HAS_BLOCKS.search(text):
        return " ".join(text.split())
    first, *rest = text.splitlines()
    pad = " " * indent
    return "\n".join(
        [" ".join(first.split())]
        + [f"{pad}{line.rstrip()}" if line.strip() else "" for line in rest]
    )


def _numbered_steps(steps: Any) -> str:
    """A how-to guide's typed steps as one numbered list: "1. **Title.** What to do."

    A list and not a heading per step: every H2 and H3 counts toward the share of
    subheadings that carry the keyphrase, which is a blocking check.
    """
    lines: list[str] = []
    for step in steps if isinstance(steps, list) else []:
        if hasattr(step, "model_dump"):
            step = step.model_dump()
        if not isinstance(step, dict):
            continue
        title = _step_title(step.get("title"))
        number = f"{len(lines) + 1}. "
        text = _step_text(step.get("description"), indent=len(number))
        if not title and not text:
            continue
        if title and title[-1] not in ".!?:":
            title += "."
        lead = f"**{title}** " if title else ""
        lines.append(f"{number}{lead}{text}".rstrip())
    return "\n".join(lines)


def _paragraphs(text: Any) -> str:
    return text.strip() if isinstance(text, str) else ""


def _bullets(items: Any) -> str:
    entries = [" ".join(str(item).split()) for item in (items if isinstance(items, list) else [])]
    return "\n".join(f"- {entry}" for entry in entries if entry)


# A keyphrase that is a question of its own ("what is compound interest") can't be a part of
# another sentence; "how to ..." can, in the two headings that take a verb.
_QUESTION_OPENINGS = (
    "how", "what", "why", "when", "where", "which", "who", "is", "are", "can", "does", "do",
    "should", "will",
)  # fmt: skip


def _is_a_question(keyphrase: str) -> bool:
    return (keyphrase or "").strip().lower().split(" ", 1)[0] in _QUESTION_OPENINGS


def _how_to(keyphrase: str) -> Optional[str]:
    """What follows "how to" in the keyphrase, in the keyphrase's Title Case, or None."""
    shown = display_keyphrase(keyphrase)
    return shown[7:].strip() or None if shown.lower().startswith("how to ") else None


# The headings carry the keyphrase as a part of what they say, never set before a colon: that
# is the "Keyphrase: ..." form the heading rules call bolted on (subheading_seo._is_bolted_on).
def _steps_heading(keyphrase: str, markdown: str) -> Optional[str]:
    steps = len(re.findall(r"(?m)^\d+\. ", markdown))
    if _is_a_question(keyphrase) and not _how_to(keyphrase):
        return None
    count = f"{steps} Steps" if steps > 1 else "One Step"
    return f"{display_keyphrase(keyphrase)} in {count}"


def _verdict_heading(keyphrase: str, markdown: str) -> Optional[str]:
    return None if _is_a_question(keyphrase) else f"The Verdict on {display_keyphrase(keyphrase)}"


def _prerequisites_heading(keyphrase: str, markdown: str) -> Optional[str]:
    doing = _how_to(keyphrase)
    if doing:
        return f"What You Need to {doing}"
    if _is_a_question(keyphrase):
        return None
    return f"What You Need for {display_keyphrase(keyphrase)}"


# Content type -> the block a typed field owns -> how its value is written, the section's
# heading with the keyphrase in it, and its heading without. The plain ones fit the H2 length
# rule; one with the keyphrase is used only when it does too.
_TYPED_SECTIONS: dict[
    str, dict[str, tuple[Callable[[Any], str], Callable[[str, str], Optional[str]], str]]
] = {
    "how-to-guide": {"steps": (_numbered_steps, _steps_heading, "Follow These Steps in Order")},
    "in-depth-review": {"verdict": (_paragraphs, _verdict_heading, "The Verdict in a Few Words")},
    "tutorial": {
        "prerequisites": (_bullets, _prerequisites_heading, "What You Need Before You Start")
    },
}


def typed_section_blocks(outline: dict, content_type: str) -> list[OutlineBlock]:
    """The approved outline's blocks that a typed field of the content model writes and
    `assemble_structured_payload` renders, in the approved order. None for most types."""
    from src.flow.model.structure.outlines import normalize_content_type

    keys = _TYPED_SECTIONS.get(normalize_content_type(content_type))
    if not keys:
        return []
    try:
        resolved = resolve_outline_structure(outline, content_type)
    except Exception:
        logger.exception("typed_section_blocks: no structure for content_type=%s", content_type)
        return []
    return [block for block in resolved if block.key in keys and not block.parent]


def _typed_heading(
    with_keyphrase: Optional[str],
    plain: str,
    keyphrase: str,
    title: str,
    body: str,
    content_type: str,
) -> Optional[str]:
    """The section's H2: the candidate that fits the heading length rule and leaves the share
    of subheadings carrying the keyphrase nearest its range, the keyphrase one first.

    None for a title that is surely in another language: these headings are English words,
    and the section then follows the one before it without a heading of its own.
    """
    if reads_as_another_language(title):
        return None
    candidates = ([with_keyphrase] if with_keyphrase else []) + [plain]

    def cost(candidate: str) -> tuple[bool, int]:
        share = subheading_report(f"{body}\n\n## {candidate}\n", keyphrase, content_type)[
            "keyphrase"
        ]
        off = 0
        if share["status"] in ("too_low", "too_high"):
            off = max(share["min"] - share["matching"], share["matching"] - share["max"])
        return heading_length_issue(2, candidate, content_type) is not None, off

    return min(candidates, key=cost)


def _with_typed_sections(
    ordered: list[tuple[str, Optional[ContentBlock]]],
    blocks: list[OutlineBlock],
    typed: list[OutlineBlock],
    content_dict: dict,
    body: str,
    keyphrase: str,
    content_type: str,
) -> tuple[list[tuple[str, Optional[ContentBlock]]], list[str]]:
    """`ordered` with each typed section put where its block stands in the approved order, and
    the keys of the ones that had something to show."""
    from src.flow.model.structure.outlines import normalize_content_type

    writers = _TYPED_SECTIONS.get(normalize_content_type(content_type)) or {}
    order_of = {block.key: block.order for block in blocks}
    placed = list(ordered)
    shown: list[str] = []
    for block in typed:
        if block.key not in writers:
            continue
        write, with_keyphrase, plain = writers[block.key]
        markdown = write(content_dict.get(block.key))
        if not markdown:
            continue
        heading = _typed_heading(
            with_keyphrase(keyphrase, markdown) if (keyphrase or "").strip() else None,
            plain,
            keyphrase,
            str(content_dict.get("title") or ""),
            body,
            content_type,
        )
        at = next(
            (i for i, (key, _) in enumerate(placed) if order_of.get(key, -1) > block.order),
            len(placed),
        )
        placed.insert(at, (block.key, ContentBlock(heading=heading, markdown=markdown)))
        order_of[block.key] = block.order
        shown.append(block.key)
    return placed, shown


def assemble_structured_payload(
    content_dict: dict,
    blocks: list[OutlineBlock],
    typed: Optional[list[OutlineBlock]] = None,
    keyphrase: str = "",
    content_type: str = "",
) -> dict:
    """Collapse generated blocks into `body_markdown` and drop the block fields.

    After this, the payload has exactly the shape every downstream stage already
    expects — validation, repair, humanization, EEAT/on-page/readability scoring,
    persistence and the WordPress publisher all keep reading `body_markdown` and
    never learn that generation was structured. That is what makes the change
    backward-compatible.

    If the blocks produced nothing usable, any `body_markdown` the model happened
    to write is left in place rather than being replaced with an empty string.

    `typed` (see `typed_section_blocks`) are the sections a typed field wrote
    instead of a block: each is rendered into the body where its block stands in
    the approved order. Only beside written blocks, so a payload assembled once
    already (its block fields are gone) is never given them a second time.
    """
    ordered = []
    for block in blocks:
        raw = content_dict.get(block.key)
        written = None
        if isinstance(raw, dict):
            try:
                written = ContentBlock(**raw)
            except Exception:
                logger.warning(
                    "assemble_structured_payload: block %r malformed; skipping.", block.key
                )
        elif isinstance(raw, ContentBlock):
            written = raw
        if written is not None and block.parent and _heading_edited(block):
            # A heading the user reworded is written as they wrote it, never the
            # model's rewording of it (G70, revnix/rext-control#586).
            written = written.model_copy(update={"heading": block.heading})
        ordered.append((block.key, written))

    assembled = blocks_to_body_markdown(ordered, levels={b.key: b.level for b in blocks})
    payload = {k: v for k, v in content_dict.items() if k not in {b.key for b in blocks}}
    # Links the model wrote into its own `body_markdown` rather than into the
    # section blocks. The prompt and the base schema both told the writer that
    # every link belongs "inside body_markdown", and that string is replaced
    # below — so every such link was deterministically discarded for all 34
    # content types, even though it was visible while the output streamed.
    model_body = content_dict.get("body_markdown")
    model_body_links = (
        extract_links(model_body, "body_markdown") if isinstance(model_body, str) else []
    )

    # A block counts as written only with prose in it: an empty one renders as
    # nothing, so it is as missing as an absent one.
    written = [k for k, b in ordered if b is not None and (b.markdown or "").strip()]
    typed_words = 0
    if typed and written:
        try:
            placed, typed_shown = _with_typed_sections(
                ordered, blocks, typed, content_dict, assembled, keyphrase, content_type
            )
        except Exception:
            # As everywhere in this module: what can't be rendered degrades to the body
            # without it, it does not take a run down.
            logger.exception(
                "assemble_structured_payload: typed sections not rendered for content_type=%s",
                content_type,
            )
            typed_shown = []
        if typed_shown:
            ordered = placed
            without = len(assembled.split())
            assembled = blocks_to_body_markdown(ordered, levels={b.key: b.level for b in blocks})
            written = written + typed_shown
            # What the sections add to the body, as the length check counts words: its
            # maximum grows by exactly this (word_count_utils.typed_section_allowance).
            typed_words = len(assembled.split()) - without
    missing_required = [b.key for b in blocks if b.required and b.key not in written]
    if missing_required:
        # Should be unreachable — these are required fields under constrained
        # decoding — but log rather than assume, so a provider that degrades to
        # best-effort output is visible instead of silent.
        logger.warning(
            "assemble_structured_payload: required block(s) absent after generation: %s",
            missing_required,
        )

    if assembled.strip():
        payload["body_markdown"] = assembled
        # Carry those links over onto the same anchor text in the assembled
        # sections — the writer usually produced the same prose in both places.
        # A link with no matching anchor is returned for the caller to record
        # (with its anchor and sentence), so validation can name it and repair
        # can place it; it is never appended as a bare line.
        restored_payload, restored, unplaced = restore_lost_links(
            payload, model_body_links, fields=("introduction", "body_markdown")
        )
        payload = restored_payload
        if model_body_links:
            logger.info(
                "assemble_structured_payload: links written outside the section blocks "
                "carried over=%s unplaced=%s",
                [r.get("url") for r in restored],
                [r.get("url") for r in unplaced],
            )
        if unplaced:
            payload[UNPLACED_LINKS_KEY] = unplaced
    else:
        logger.warning(
            "assemble_structured_payload: blocks produced no markdown; keeping model output."
        )

    # Record which sections were actually written, so validation can verify
    # section presence directly instead of pattern-matching headings.
    #
    # This matters because the two disagree by design: `expected_sections` holds
    # SCHEMA labels ("Problem", "Objection Handling"), while a structured block's
    # heading is deliberately reader-facing ("Buying Without Clarity") — emitting
    # the field name as a heading is the very defect ContentBlock.heading exists
    # to prevent. Left alone, check_required_sections would report every
    # structured article as missing its required sections.
    #
    # Underscore-prefixed and therefore dropped by Pydantic's extra="ignore" on
    # the first model_validate downstream, which is correct: after humanization
    # rewrites body_markdown freely, block provenance no longer holds and the
    # heading-based check should apply again.
    payload[STRUCTURED_BLOCKS_KEY] = written
    if typed_words > 0:
        payload[TYPED_SECTION_WORDS_KEY] = typed_words

    logger.info(
        "assemble_structured_payload: blocks_written=%s/%s body_chars=%s",
        len(written),
        len(blocks),
        len(assembled),
    )
    return payload

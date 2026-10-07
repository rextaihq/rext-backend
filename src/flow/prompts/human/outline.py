import re

from langchain_core.prompts import ChatPromptTemplate

from src.flow.model.structure.outlines import normalize_content_type
from src.flow.prompts.system.outline import OUTLINE_GENERATION_PROMPT

# H3 subsections, per content type (rext-control#603). Only blog and pillar-content outlines carry
# heading levels; every other type has a fixed shape (steps, rankings, products, categories) whose
# items each become a heading of their own in the article. Without an explicit rule the model
# returned H2s only for 7 of 8 outlines, a pillar guide and a regeneration asking for H3s included.
_EXPECTED, _BY_SHAPE, _NONE = "expected", "by_shape", "none"
_SUBSECTION_POLICY = {"pillar-content": _EXPECTED, "blog": _BY_SHAPE}
_STEP_TYPES = frozenset({"how-to-guide", "tutorial"})

# Feedback that asks for subsections, in the words reviewers use: "H3s", "subsections",
# "sub-headings", "nested headings".
_ASKS_FOR_SUBSECTIONS = re.compile(
    r"\bh3s?\b|\bsub[- ]?(?:sections?|headings?|heads?)\b|\bnested\s+headings?\b", re.IGNORECASE
)

_PARTS = "steps, stages, types, options, tools, or pros and cons"
_PLACEMENT = (
    "An H3 comes directly after its H2 or after a sibling H3, never first and never on its own."
)


def _kebab(value: str | None) -> str:
    """A content type as written, lower-kebab-case, without the aliases ("listicle" stays)."""
    return re.sub(r"[\s_-]+", "-", str(value or "").strip().lower()).strip("-")


def asks_for_subsections(feedback: str | None) -> bool:
    """Whether the reviewer's rejection reason asks for H3 subsections."""
    return bool(feedback) and bool(_ASKS_FOR_SUBSECTIONS.search(str(feedback)))


def outline_subsection_rule(
    content_type: str | None,
    raw_content_type: str | None = None,
    feedback: str | None = None,
) -> str:
    """The outline prompt's rule for H3 subsections, for this content type.

    Expected for pillar content; for a blog it follows the article's shape (expected for a
    long guide, optional for a short post, none for a list article); none for the types
    whose schema fixes the structure. Feedback asking for subsections makes them required
    where the schema can hold them.
    """
    kind = normalize_content_type(content_type) or "blog"
    raw = _kebab(raw_content_type)
    policy = _NONE if raw == "listicle" else _SUBSECTION_POLICY.get(kind, _NONE)
    asked = asks_for_subsections(feedback)

    if policy == _EXPECTED:
        lines = [
            "H3 SUBSECTIONS: EXPECTED for this content type.",
            f"- Wherever an H2 covers two or more distinct parts ({_PARTS}), give each part its "
            "own H3 under that H2.",
            "- A pillar guide's main sections nearly always have parts: plan H3s under at least "
            "half of the H2s.",
            f"- {_PLACEMENT}",
        ]
    elif policy == _BY_SHAPE:
        lines = [
            "H3 SUBSECTIONS: decide by the article's shape.",
            "- A long blog or guide (a complete or ultimate guide, or a plan past about 1,200 "
            f"words): EXPECTED. Wherever an H2 covers two or more distinct parts ({_PARTS}), give "
            "each part its own H3 under that H2.",
            "- A short blog (about 1,200 words or fewer): OPTIONAL. Use H3s only where an H2 "
            "really splits into parts; H2s alone are fine.",
            '- A list article ("Top 5 ...", "7 ways to ...", "best X for Y"): NONE. Each list '
            "item is its own H2.",
            "- The sections list holds the H2s and their H3s together: 4-8 H2s, plus H3s, at "
            "most 16 entries in all.",
            "- An H2 that has H3s keeps a short budget of its own (about 80-120 words, its "
            "introduction) and its H3s carry the rest, so the plan's total stays the length "
            "this article needs.",
            f"- {_PLACEMENT}",
        ]
    elif raw == "listicle":
        lines = [
            "H3 SUBSECTIONS: NONE. This is a list article: each list item is its own H2, with "
            "no H3s under it."
        ]
    else:
        lines = [
            "H3 SUBSECTIONS: NONE for this content type. Its schema fixes the structure: each "
            "step, item or block you fill becomes a heading of its own in the article, so do not "
            "nest headings inside them."
        ]
        if kind in _STEP_TYPES:
            lines.append(
                "- Plan 3-10 steps. A one-step guide is not a guide: split the work into the "
                "steps a reader actually takes, in order."
            )

    if asked:
        if policy == _NONE:
            lines.append(
                "- The reviewer's feedback asks for subsections. This content type can't nest "
                "headings, but each step, item or block already gets a heading of its own in the "
                "article: honour the request by giving every item its own entry with distinct, "
                "fuller key points, and add the items the feedback names."
            )
        else:
            lines.append(
                "- The reviewer's feedback asks for subsections, so this pass MUST contain H3s: "
                "add them under every H2 that covers distinct parts (at least two H2s with H3s), "
                "and keep the H2s the feedback did not criticize."
            )
    return "\n".join(lines)


def get_outline_prompt() -> ChatPromptTemplate:
    return ChatPromptTemplate.from_messages(
        [
            ("system", OUTLINE_GENERATION_PROMPT),
            (
                "human",
                """
Generate a HIGH-QUALITY, SEO-OPTIMIZED CONTENT OUTLINE for a **{content_type}**.

### ITERATION FEEDBACK — HIGHEST PRIORITY, READ AND APPLY FIRST

Previous Rejection Reason: {rejected_reason}

If the reason above is anything other than "None", it is a direct instruction from the human reviewer and OVERRIDES any conflicting rule elsewhere in this prompt. Rewrite the outline to concretely address it — do not just reword the same structure. Everything else below (SERP data, keyword clusters, strict requirements) still applies, but only insofar as it does not conflict with this feedback.

Previous Outline (reference only — shows what was rejected; do not treat as a template, reuse only the parts the feedback above did not criticize):
{previous_outline}

### INPUT DATA

Content Type: {content_type}
Primary Topic / Query:
{topic}

SERP Insights:
- Related Topics: {related_topics}
- People Also Ask Questions:
{questions}

- Competitor Coverage Summary:
{competitors_context}

- Known Real Entities (this workspace's brand and its actual competitors):
{known_entities}

- Intent Distribution:
{intent_distribution}

SEO Keyword Clusters (Semantic Groups):
{keyword_clusters}

Cluster to Content Structure Map (H1/H2/H3):
{cluster_heading_map}

### STRICT REQUIREMENTS (DO NOT IGNORE)

1. Output MUST be valid JSON matching the `Outline` Pydantic schema.
2. Use 4–8 main sections.
3. Use exactly one H1: the selected topic/title.
4. All main sections MUST be H2 and should follow the provided cluster-to-heading map when available.
4b. Subsections, for this content type:
{subsection_rule}
   Where the cluster map lists sub-topics under a section, they are the first candidates for its H3s.
5. Each section must:
   - Map to a clear search intent (Use the provided **Keyword Clusters** to guide these intents)
   - Include 2–4 key points (Ensure the 'Supporting Keywords' from the cluster are covered here)
5b. **Semantic Synthesis**: Each unique Keyword Cluster should ideally inform a main H2 or H3 heading. If clusters overlap semantically, merge them into a single authoritative section to avoid redundancy.
6. Include:
   - At least 1 featured snippet–targeted section
   - A dedicated FAQ section using the People Also Ask questions above. The FAQ
     block is the ONLY place questions belong — do not also list questions under
     individual sections.
7. Primary keyword must be reflected in:
   - Title
   - First section
   - At least one other section
8. Do NOT repeat competitor structure verbatim.
9. Add unique angles, frameworks, or insights.
10a. REAL NAMES ONLY — applies to every product, tool, company or agency this outline names (comparison, best-tools, alternatives, product-roundup and buying-guide outlines especially). Name only real, specific, publicly recognisable products — prefer the entities listed under "Known Real Entities" above, then any real product named in the topic or SERP data. NEVER invent a generic stand-in such as "Agency A", "Agency B", "Tool 1", "Product A", "Competitor X", "Your Brand" or "Acme Corp": a placeholder name makes the whole page worthless and it will be rejected. If you cannot name enough real products to fill every slot, compare FEWER products instead of inventing one. Every reference elsewhere in the outline (comparison table columns, pricing entries, use-case winners, the verdict, recommendations) must spell a product's name exactly as you spelled it in the products list.
10. Plan WHERE evidence is needed — name the claims that will require a statistic or citation in each section's key points. Do NOT state the statistic itself and do NOT provide source URLs: you have no search tool at this stage, so any figure or URL you write here would be fabricated. The writing stage has live search and is responsible for finding and citing the real numbers. The same applies to time-sensitive product facts for every product you name: in price/pricing fields describe the pricing MODEL without figures (e.g. "Free tier; paid plans per seat") unless the figure is in the brand info above, and do not assert specific plans, feature availability, integrations, versions or competitor limitations as fact — phrase them as what the writer should verify (e.g. "compare native localization support"). Recommend by fit ("best for agencies needing X"), not as an absolute winner.
11. Donot Change the title of the article title should be same as the input title.

Return ONLY the JSON. No explanations.
""",
            ),
        ]
    )

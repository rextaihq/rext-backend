import re

from langchain_core.prompts import ChatPromptTemplate

from src.flow.model.structure.outlines import CONTENT_TYPE_TO_MODEL, normalize_content_type
from src.flow.prompts.system.outline import OUTLINE_GENERATION_PROMPT

# H3 subsections, per content type (rext-control#603). Only blog and pillar-content outlines carry
# heading levels; every other type has a fixed shape (steps, rankings, products, categories) whose
# items each become a heading of their own in the article. Without an explicit rule the model
# returned H2s only for 7 of 8 outlines, a pillar guide and a regeneration asking for H3s included.
_EXPECTED, _BY_SHAPE, _NONE = "expected", "by_shape", "none"
_SUBSECTION_POLICY = {"pillar-content": _EXPECTED, "blog": _BY_SHAPE}
_STEP_TYPES = frozenset({"how-to-guide", "tutorial"})

# Subsections, in the words reviewers use: "H3s", "subsections", "sub-headings", "nested headings".
_SUBSECTION_WORDS = re.compile(
    r"\bh3s?\b|\bsub[- ]?(?:sections?|headings?|heads?)\b|\bnested\s+headings?\b", re.IGNORECASE
)
# A request for fewer: a cue up to three words before the term ("remove the H3s", "no
# subsections", "don't use sub-headings", "too many H3s"), or a whole verdict just after it ("H3s
# aren't needed", "the subsections are unnecessary", "the H3s need to be removed"); "the H3s
# aren't detailed enough" asks for better ones, not fewer.
_FEWER_BEFORE = re.compile(
    r"\b(?:no|without|remove|removing|drop|dropping|delete|deleting|fewer|less|flatten|avoid|"
    r"skip|stop|get\s+rid\s+of|too\s+many|(?:do|does)\s*n[o']?t\s+(?:\w+\s+)?"
    r"(?:use|add|want|need|include))(?:\s+[\w'-]+){0,3}\s*$",
    re.IGNORECASE,
)
_FEWER_AFTER = re.compile(
    r"^\W*(?:\w+\W+){0,2}?(?:(?:aren'?t|isn'?t|are\s+not|is\s+not)\s+(?:needed|necessary|"
    r"wanted|required|useful|helpful)|(?:are|is)\s+(?:unnecessary|unneeded|redundant|overkill|"
    r"pointless|too\s+many)|not\s+needed|(?:should|can|must)\s+go|"
    r"(?:(?:needs?|has|have)\s+to|should|must|can)\s+be\s+(?:removed|dropped|deleted|cut|"
    r"taken\s+out|flattened))\b",
    re.IGNORECASE,
)
# A doubt up to five words before the term and a "needed" just after it: "I don't think that any
# of the H3s are needed" asks for fewer, though "are needed" alone asks for more (review round 3 of
# #890). "Helpful enough" judges quality, not the count, so it isn't a verdict.
_DOUBT_BEFORE = re.compile(
    r"\b(?:(?:do|does)\s*n[o']?t\s+(?:think|believe|feel)|doubt|not\s+sure)(?:\s+[\w'-]+){0,5}\s*$",
    re.IGNORECASE,
)
_NEEDED_AFTER = re.compile(
    r"^\W*(?:are|is)\s+(?:really\s+)?(?:needed|necessary|required|useful|helpful|wanted)\b"
    r"(?!\s+enough)",
    re.IGNORECASE,
)
# A request for more: a cue up to four words before the term ("add H3s", "it needs
# subsections", "split them into sub-headings", "each tool as its own H3"), or just after it
# ("nested headings, please", "the H3s are missing"). A mention with neither, such as "rename
# the H3 \"Cost\"", asks nothing of the structure.
_MORE_BEFORE = re.compile(
    r"\b(?:add|adding|more|use|using|include|including|needs?|want|split|break|create|nest|"
    r"missing|lacks?|lacking|give|as\s+(?:its|their)\s+own)(?:\s+[\w'-]+){0,4}\s*$",
    re.IGNORECASE,
)
_MORE_AFTER = re.compile(
    r"^\W*(?:please|would\s+help|(?:are|is)\s+missing|(?:are\s+|is\s+)?(?:needed|required))\b",
    re.IGNORECASE,
)
# A removal that is negated right after the term keeps them: "the H3s do not need to be removed",
# "the subsections shouldn't go" (review of #922).
_KEPT_AFTER = re.compile(
    r"^\W*(?:do(?:es)?|should|must|need|can)\s*(?:n[o']?t|not)\s+(?:(?:need|have)\s+to\s+)?"
    r"(?:be\s+(?:removed|dropped|deleted|cut|taken\s+out|flattened)|go)\b",
    re.IGNORECASE,
)
# A passive request to add them ("H3s should be added", "subsections must be included"), and its
# negation, which asks for fewer.
_ADDED_AFTER = re.compile(
    r"^\W*(?:should|must|could|can|(?:needs?|has|have)\s+to)\s+(n[o']?t\s+|not\s+)?be\s+"
    r"(?:added|included|used|introduced)\b",
    re.IGNORECASE,
)
# A terse request that only says where they go: "H3s under each list item", "Subsections for
# pricing and features". It counts when the mention opens the sentence, so "the H3 under the intro
# is too long" still asks nothing (review round 2 of #922).
_PLACED_AFTER = re.compile(r"^\s+(?:under|beneath|below|for|in|within|per|on)\s+\w+", re.IGNORECASE)

_PARTS = "steps, stages, types, options, tools, or pros and cons"
_PLACEMENT = (
    "An H3 comes directly after its H2 or after a sibling H3, never first and never on its own."
)


def _kebab(value: str | None) -> str:
    """A content type as written, lower-kebab-case, without the aliases ("listicle" stays)."""
    return re.sub(r"[\s_-]+", "-", str(value or "").strip().lower()).strip("-")


# The same terms named in the plural: the subsections as a whole ("remove the H3s", "no
# subsections"). "The H3 under the introduction" names one of them and leaves the rest.
_SUBSECTIONS_AS_A_WHOLE = re.compile(
    r"\bh3s\b|\bsub[- ]?(?:sections|headings|heads)\b|\bnested\s+headings\b", re.IGNORECASE
)


def wants_no_subsections(feedback: str | None) -> bool:
    """Whether feedback that asks for fewer H3 subsections is about them as a whole.

    True for "remove the H3s" or "no subsections, please"; false for "remove the H3 under the
    introduction", which leaves every other one, and for feedback that asks for none fewer."""
    return subsection_request(feedback) == "fewer" and bool(
        _SUBSECTIONS_AS_A_WHOLE.search(feedback or "")
    )


def subsection_request(feedback: str | None) -> str | None:
    """What the reviewer's rejection reason asks of H3 subsections: "more", "fewer" or None.

    Each mention is read in its sentence, and counts only with a cue either way. Any request
    for more wins, so "drop the H3 under the intro, add H3s to the tools" is "more", and the
    model reads which ones from the feedback itself.
    """
    asks = set()
    for sentence in re.split(r"[.!?;\n]+", str(feedback or "")):
        for match in _SUBSECTION_WORDS.finditer(sentence):
            before, after = sentence[: match.start()], sentence[match.end() :]
            doubt = _DOUBT_BEFORE.search(before)
            if (doubt and _FEWER_AFTER.search(after)) or _KEPT_AFTER.search(after):
                # "I don't think the H3s should be removed", "the H3s do not need to be
                # removed": leave them as they are.
                continue
            doubted = doubt and _NEEDED_AFTER.search(after)
            placed = not before.strip() and _PLACED_AFTER.search(after)
            added = _ADDED_AFTER.search(after)
            not_added = bool(added and added.group(1))
            if doubted or not_added or _FEWER_BEFORE.search(before) or _FEWER_AFTER.search(after):
                asks.add("fewer")
            elif _MORE_BEFORE.search(before) or _MORE_AFTER.search(after) or placed or added:
                asks.add("more")
    return "more" if "more" in asks else "fewer" if asks else None


def outline_subsection_rule(
    content_type: str | None,
    raw_content_type: str | None = None,
    feedback: str | None = None,
) -> str:
    """The outline prompt's rule for H3 subsections, for this content type.

    Expected for pillar content; for a blog it follows the article's shape (expected for a
    long guide, optional for a short post, none for a list article); none for the types
    whose schema fixes the structure. Feedback asking for subsections makes them required
    where the schema can hold them (a listicle's too); feedback asking for fewer is followed.
    """
    kind = normalize_content_type(content_type) or "blog"
    # A type the outline models don't know is written on the blog schema (get_outline_model),
    # so it gets the blog's rule.
    kind = kind if kind in CONTENT_TYPE_TO_MODEL else "blog"
    raw = _kebab(raw_content_type)
    # Whether the schema can hold H3s, apart from whether this article should have them: a
    # listicle runs on the blog schema, so feedback asking for H3s there can still be met.
    holds_h3s = kind in _SUBSECTION_POLICY
    policy = _NONE if raw == "listicle" else _SUBSECTION_POLICY.get(kind, _NONE)
    asked = subsection_request(feedback)

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
            "H3 SUBSECTIONS: NONE by default. This is a list article: each list item is its own "
            "H2, with no H3s under it."
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

    if asked == "fewer" and policy != _NONE:
        lines.append(
            "- The reviewer's feedback asks for fewer or no subsections: follow it, whatever this "
            "content type's default. Keep H3s only where the feedback leaves them."
        )
    elif asked == "more":
        if not holds_h3s:
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
    if holds_h3s and (policy != _NONE or asked == "more"):
        lines.append(
            "- Where the cluster map lists sub-topics under a section, they are the first "
            "candidates for its H3s."
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

Focus Keyword (what the reader typed into the search engine):
{focus_keyword}

SERP Insights:
- Related Topics: {related_topics}
- People Also Ask Questions:
{questions}

- Competitor Coverage Summary:
{competitors_context}

- Known Real Entities (this workspace's brand and its actual competitors):
{known_entities}

- The Workspace's Customers and Offer (who this site serves, and what it offers):
{reader_and_offer}

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
5. Each section must:
   - Map to a clear search intent (Use the provided **Keyword Clusters** to guide these intents)
   - Include 2–4 key points, never fewer than 2 (Ensure the 'Supporting Keywords' from the cluster are covered here)
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
12. WRITE FOR THE PERSON SEARCHING THIS KEYWORD, AS THIS SITE'S CUSTOMER: the reader is whoever types the Focus Keyword above. "The Workspace's Customers and Offer" above says who the site serves. Where those customers and this searcher overlap, choose and word the sections for that overlap — the questions they actually have, at their level of expertise, with examples from their world — not for a generic reader. `target_audience` names the searcher this article serves, in the keyword's own terms (for "crm for a startup": startup founders), narrowed toward the site's customers where the two overlap. Never copy the site's customer list into `target_audience` when the keyword is aimed at someone else.
13. LET THE INTENT SHAPE THE STRUCTURE (use the dominant intent above): Informational → what it is, how it works, the steps or methods, pitfalls, examples. Commercial → how to choose (criteria), the options compared, pricing models, which fits which use case, a verdict. Transactional → the offer, proof, the objections answered, the next step. Navigational → where to go and how, step by step.
14. WHERE THE OFFER FITS: when "WHAT THE BRAND OFFERS" above relates to the topic, plan ONE section where a solution of that kind genuinely helps this reader, described by what it does. Do NOT name the brand there and do not make it a pitch: whether and how the brand is mentioned is decided later, at the outline review.
15. Write every H2 and H3 heading in the title's capitalization style: when the title capitalizes only its first word and proper nouns (sentence case), so does every heading; when it capitalizes each major word (Title Case), every heading does too. Never mix the two in one outline.

Return ONLY the JSON, written compactly: no indentation, no line breaks and no spaces between its parts. No explanations.
""",
            ),
        ]
    )

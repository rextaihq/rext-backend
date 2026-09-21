from langchain_core.prompts import ChatPromptTemplate

from src.flow.prompts.system.outline import OUTLINE_GENERATION_PROMPT


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
2. Use 4–8 sections total.
3. Use exactly one H1: the selected topic/title.
4. All main sections MUST be H2 and should follow the provided cluster-to-heading map when available.
4b. H3 sections only when logically required under their parent H2; use them for supporting long-tail keywords or questions, not as standalone main sections.
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

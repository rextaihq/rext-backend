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

- Intent Distribution:
{intent_distribution}

Iteration Feedback:
- Previous Rejection Reason: {rejected_reason}
- Previous Outline (if any):
{previous_outline}

### STRICT REQUIREMENTS (DO NOT IGNORE)

1. Output MUST be valid JSON matching the `Outline` Pydantic schema.
2. Use 4–8 sections total.
3. All main sections MUST be H2.
4. H3 sections only when logically required.
5. Each section must:
   - Map to a clear search intent
   - Include 2–4 key points
   - Answer real user questions
6. Include:
   - At least 1 featured snippet–targeted section
   - A dedicated FAQ section using PAA questions
7. Primary keyword must be reflected in:
   - Title
   - First section
   - At least one other section
8. Do NOT repeat competitor structure verbatim.
9. Add unique angles, frameworks, or insights.

Return ONLY the JSON. No explanations.
""",
            ),
        ]
    )
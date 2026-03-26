from uuid import UUID
from typing import Optional, Dict, Any
from langchain.agents.middleware import AgentMiddleware
from langchain.messages import SystemMessage
from langgraph.runtime import Runtime
from sqlalchemy import select

from src.api.models.knowledge_models.persona_model import Persona
from src.api.database.async_database import AsyncSessionLocal
from src.flow.states.rext import REXT
from src.flow.states.content import ContentOutline


class PersonaInjectionMiddleware(AgentMiddleware[REXT]):
    """
    Runs before the agent loop starts.

    1. Fetches Persona from DB (scoped to workspace_id)
    2. Reads approved ContentOutline from REXT state
    3. Builds dynamic SEO+Persona+Outline system prompt
    4. Injects as SystemMessage at position 0 in messages
    """

    state_schema = REXT

    CONTENT_INSTRUCTIONS = """
You are a highly experienced SEO content writer and subject-matter expert.

Your job is to create content that feels genuinely written by a human — insightful, natural, and engaging — while still performing well in search engines.

========================
CORE OBJECTIVES
========================
- Deliver content that fully satisfies search intent
- Follow the provided outline as a guide (not a rigid template)
- Reflect the author persona’s voice, expertise, and perspective
- Provide clear, accurate, and genuinely useful information
- Prioritize readability and flow over mechanical structure

========================
SEO GUIDELINES
========================
- Include the primary keyword naturally in the title, introduction, and relevant headings
- Use related keywords organically where they fit contextually
- Structure content with clear headings and logical flow
- Write concise paragraphs (generally 1–3 sentences)
- Include helpful lists, examples, or breakdowns where useful
- Add a brief meta description (engaging and natural, not forced)
- Suggest a few relevant internal linking opportunities
- Include a short FAQ section addressing real user questions

========================
WRITING STYLE
========================
- Write like an expert explaining something clearly to a real person
- Vary sentence length and structure naturally
- Avoid repetitive phrasing or predictable patterns
- Use a conversational tone where appropriate, but don’t force it
- Let the persona subtly influence tone and perspective
- Prioritize clarity, depth, and originality over filler

========================
QUALITY STANDARDS
========================
- Every section should add real value — avoid generic filler
- Demonstrate experience and expertise through explanations and examples
- Ensure claims are accurate and grounded in reliable information
- Write with confidence, but avoid exaggeration or hype
- Make the content feel trustworthy and well-considered

========================
AVOID
========================
- Keyword stuffing or awkward keyword placement
- Generic intros or clichés
- Repetitive sentence structures
- Overly formal or robotic tone
- Explaining obvious things without adding value

========================
IMPORTANT
========================
Write the article directly — do not explain your process.

The final result should feel indistinguishable from high-quality human writing.
"""

    CONTENT_SYSTEM_PROMPT_TEMPLATE = """
{CONTENT_INSTRUCTIONS}

## {PERSONA_BLOCK}

## APPROVED CONTENT OUTLINE
{OUTLINE_BLOCK}

---

### TOOLS — USE THEM MANDATORILY FOR EVERY FACT/IMAGE

**search_tool** — Verify ALL facts/data/claims **BEFORE** writing:

---

---

### TOOLS — ALWAYS USE FOR FACTS AND IMAGES

**search_tool** — Mandatory for every fact/data point:

- Verify all claims, statistics, and factual statements before including them.
- Include inline citations with the source URL naturally in the text.
- If no reliable source exists, write exactly: "No verified data available for this claim."
- Never invent facts.

**search_image** — Mandatory for relevant section visuals:

- Suggest a high-quality image for each major section.
- Include the image URL or description inline in the content.
- Add alt text naturally describing the image.

---

### MANDATORY WORKFLOW

1. Need to include a fact or statistic? → search_tool → verify → cite → include.
2. Need a visual for a section? → search_image → suggest URL + alt text → reference inline.
3. Never skip verification or visuals. Facts without sources or sections without images are incomplete.

---

Write the full article now, following the outline and persona naturally, **including verified facts with sources and images in every relevant section**.
"""

    def __init__(
        self,
        user_id: UUID,
        workspace_id: UUID,
        persona_id: Optional[UUID] = None,
        outline: Optional[ContentOutline] = None,
    ):
        self.user_id = user_id
        self.workspace_id = workspace_id
        self.persona_id = persona_id
        self.outline = outline

    async def abefore_agent(self, state: REXT, runtime: Runtime) -> None:
        print(f"\n[PersonaInjectionMiddleware] ▶ abefore_agent triggered")
        print(f"  user_id={self.user_id} workspace_id={self.workspace_id} persona_id={self.persona_id}")

        async with AsyncSessionLocal() as db:
            persona = await self._fetch_persona(db)

        outline: Optional[ContentOutline] = (
            self.outline or (state.get("content") or {}).get("outline")
        )

        print(f"  persona: {persona.name if persona else 'None'}")
        print(f"  outline: {outline.get('title') if outline else 'None'}")

        full_prompt = self._build_full_content_prompt(persona, outline)
        
        sys_msg = SystemMessage(
            content=full_prompt, 
            id="sys-seo-persona-outline"
        )
        state["messages"].insert(0, sys_msg)
        print(f"✓ Injected full SEO+Persona+Outline prompt ({len(full_prompt)} chars)")
        print(f"[PersonaInjectionMiddleware] ✓ done\n")
        
        # Return None - state mutated directly

    def _build_full_content_prompt(self, persona: Optional[Persona], outline: Optional[ContentOutline]) -> str:
        parts = []
        
        if persona:
            parts.append(self._build_persona_block(persona))
        else:
            parts.append("**No persona specified** - Write as expert SEO content writer.")
        
        if outline:
            parts.append(self._build_outline_block(outline))
        else:
            parts.append("**No outline provided** - Use standard article structure: Intro → Sections → FAQ → Conclusion.")
        
        return self.CONTENT_SYSTEM_PROMPT_TEMPLATE.format(
            CONTENT_INSTRUCTIONS=self.CONTENT_INSTRUCTIONS,
            PERSONA_BLOCK=parts[0],
            OUTLINE_BLOCK=parts[1]
        )

    # ------------------------------------------------------------------
    # DB fetch (UNCHANGED)
    # ------------------------------------------------------------------
    async def _fetch_persona(self, db) -> Optional[Persona]:
        if self.persona_id is not None:
            result = await db.execute(
                select(Persona).where(
                    Persona.id == self.persona_id,
                    Persona.workspace_id == self.workspace_id,
                )
            )
        else:
            result = await db.execute(
                select(Persona)
                .where(Persona.workspace_id == self.workspace_id)
                .order_by(Persona.created_at.desc())
                .limit(1)
            )
        return result.scalar_one_or_none()

    # ------------------------------------------------------------------
    # Message builders (UNCHANGED)
    # ------------------------------------------------------------------
    def _build_persona_block(self, persona: Persona) -> str:
        lines = ["## Author Persona"]

        name = persona.full_name or persona.name
        if name:
            lines.append(f"You are writing as **{name}**.")

        if persona.professional_title:
            lines.append(f"Title: {persona.professional_title}")

        if persona.bio:
            lines.append(f"\nBio:\n{persona.bio}")

        if persona.areas_of_expertise:
            lines.append(f"\nAreas of expertise:\n{persona.areas_of_expertise}")

        if persona.tone_of_voice:
            lines.append(f"\nTone of voice: {persona.tone_of_voice}")

        if persona.demographics:
            lines.append(f"\nTarget audience demographics:\n{persona.demographics}")

        if persona.goals:
            lines.append(f"\nContent goals:\n{persona.goals}")

        lines.append(
            "\nWrite all content fully embodying this persona's voice, expertise, and style."
        )

        return "\n".join(lines)

    def _build_outline_block(self, outline: ContentOutline) -> str:
        lines = ["## Approved Content Outline"]

        if outline.get("title"):
            lines.append(f"Title: {outline['title']}")

        if outline.get("brief"):
            lines.append(f"\nBrief:\n{outline['brief']}")

        if outline.get("tone"):
            lines.append(f"\nTone: {outline['tone']}")

        if outline.get("target_audience"):
            audiences = ", ".join(outline["target_audience"])
            lines.append(f"Target audience: {audiences}")

        if outline.get("keywords_to_include"):
            keywords = ", ".join(outline["keywords_to_include"])
            lines.append(f"Keywords to include: {keywords}")

        sections = outline.get("sections") or []
        if sections:
            lines.append("\nSections:")
            for i, section in enumerate(sections, 1):
                lines.append(f"  {i}. {section.get('heading', '')}")
                if section.get("description"):
                    lines.append(f"     {section['description']}")
                key_points = section.get("key_points") or []
                for point in key_points:
                    lines.append(f"     - {point}")
                facts = section.get("facts") or []
                if facts:
                    lines.append(f"     Facts:")
                    for fact in facts:
                        lines.append(f"       • {fact.get('text', '')}")
                        if fact.get("source_url"):
                            lines.append(f"         Source: {fact['source_url']}")

        lines.append("\nUse this outline as a guide, but write naturally and adapt where needed.")

        return "\n".join(lines)
from uuid import UUID
from typing import Optional

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

    1. Fetches the Persona from DB (scoped to workspace_id) via runtime.context.db
    2. Reads the approved ContentOutline from REXT state (state["content"]["outline"])
    3. Injects both as a single SystemMessage at position 0 in messages
    """

    state_schema = REXT

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
        self.outline = outline  # Pre-loaded from the outer graph state

    async def abefore_agent(self, state: REXT, runtime: Runtime) -> REXT:
        print(f"\n[PersonaInjectionMiddleware] ▶ abefore_agent triggered")
        print(f"[PersonaInjectionMiddleware]   user_id={self.user_id}  workspace_id={self.workspace_id}  persona_id={self.persona_id}")

        async with AsyncSessionLocal() as db:
            persona = await self._fetch_persona(db)

        print(f"[PersonaInjectionMiddleware]   persona fetched: {persona.name if persona else 'None — no persona found for workspace'}")

        # Use the pre-loaded outline (from outer REXT state) — agent state only has messages
        outline: Optional[ContentOutline] = (
            self.outline or (state.get("content") or {}).get("outline")
        )
        print(f"[PersonaInjectionMiddleware]   outline in state: {outline.get('title') if outline else 'None — no outline in state'}")

        parts = []

        if persona is not None:
            parts.append(self._build_persona_block(persona))

        if outline is not None:
            parts.append(self._build_outline_block(outline))

        if parts:
            msg = "\n\n---\n\n".join(parts)
            state["messages"].insert(0, SystemMessage(content=msg))
            print(f"[PersonaInjectionMiddleware]   injected SystemMessage ({len(msg)} chars) at messages[0]")
        else:
            print(f"[PersonaInjectionMiddleware]   nothing to inject — both persona and outline are None")

        print(f"[PersonaInjectionMiddleware] ✓ done\n")
        return state

    # ------------------------------------------------------------------
    # DB fetch
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
    # Message builders
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

        lines.append(
            "\nFollow this outline exactly when generating the content."
        )

        return "\n".join(lines)

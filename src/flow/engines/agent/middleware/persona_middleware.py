from uuid import UUID
from typing import Optional

from langchain.agents.middleware import BaseMiddleware, AgentState
from langchain.messages import SystemMessage
from langgraph.runtime import Runtime
from sqlalchemy import select

from src.api.models.knowledge_models.persona_model import Persona
from src.flow.engines.agent.context import RextContext


class PersonaInjectionMiddleware(BaseMiddleware):
    """
    Fetches a Persona from DB (scoped to workspace_id) and injects it
    as a SystemMessage before the agent loop starts.

    DB session is pulled from runtime.context (RextContext) — not stored
    on the middleware itself.

    If persona_id is provided, that specific persona is fetched.
    If not, the most recently created persona for the workspace is used.
    """

    def __init__(
        self,
        user_id: UUID,
        workspace_id: UUID,
        persona_id: Optional[UUID] = None,
    ):
        self.user_id = user_id
        self.workspace_id = workspace_id
        self.persona_id = persona_id

    async def abefore_agent(self, state: AgentState, runtime: Runtime[RextContext]) -> AgentState:
        db = runtime.context.db
        persona = await self._fetch_persona(db)
        if persona is None:
            return state

        system_message = self._build_system_message(persona)
        state["messages"].insert(0, SystemMessage(content=system_message))
        return state

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

    def _build_system_message(self, persona: Persona) -> str:
        lines = ["## Author Persona\n"]

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

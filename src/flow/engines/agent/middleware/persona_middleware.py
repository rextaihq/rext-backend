import logging
from uuid import UUID
from typing import Optional, Any

from langchain.agents.middleware import AgentMiddleware, AgentState  # type: ignore
from langchain.messages import SystemMessage  # type: ignore
from langgraph.runtime import Runtime  # type: ignore
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession  # type: ignore

from src.api.models.knowledge_models.persona_model import Persona  # type: ignore
from src.flow.engines.agent.context import RextContext  # type: ignore

logger = logging.getLogger(__name__)


class PersonaInjectionMiddleware(AgentMiddleware):
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

    async def abefore_agent(self, state: AgentState, runtime: Runtime[RextContext]) -> dict[str, Any] | None:
        logger.info(
            "[PersonaMiddleware] abefore_agent called | user_id=%s workspace_id=%s persona_id=%s",
            self.user_id, self.workspace_id, self.persona_id
        )
        db = runtime.context.db
        persona = await self._fetch_persona(db)  # type: ignore
        if persona is None:
            logger.warning(
                "[PersonaMiddleware] No persona found for workspace_id=%s — skipping injection",
                self.workspace_id
            )
            return None

        logger.info(
            "[PersonaMiddleware] Injecting persona: id=%s name=%s",
            persona.id, persona.name
        )
        system_message = self._build_system_message(persona)
        state["messages"].insert(0, SystemMessage(content=system_message))
        logger.debug("[PersonaMiddleware] SystemMessage injected:\n%s", system_message[:300])
        return None

    async def _fetch_persona(self, db: AsyncSession) -> Optional[Persona]:
        if self.workspace_id is None:
            logger.error("[PersonaMiddleware] workspace_id is None — cannot query DB")
            return None
        if self.persona_id is not None:
            logger.debug("[PersonaMiddleware] Fetching specific persona id=%s", self.persona_id)
            result = await db.execute(
                select(Persona).where(
                    Persona.id == self.persona_id,
                    Persona.workspace_id == self.workspace_id,
                )
            )
        else:
            logger.debug(
                "[PersonaMiddleware] Fetching latest persona for workspace_id=%s", self.workspace_id
            )
            result = await db.execute(
                select(Persona)
                .where(Persona.workspace_id == self.workspace_id)
                .order_by(Persona.created_at.desc())
                .limit(1)
            )
        persona = result.scalar_one_or_none()
        logger.debug("[PersonaMiddleware] DB result: %s", persona)
        return persona

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

"""
Brand Voice Service - Business Logic for Workspace Brand Voice Management

This service encapsulates all business logic related to workspace brand voice
configuration, including creation, update, and retrieval.

Responsibilities:
- Brand voice upsert (create or update)
- Brand voice retrieval
- Workspace membership validation

Does NOT:
- Handle HTTP requests/responses (that's routes)
- Commit transactions (that's decorators/routes)
- Validate workspace existence (assumes valid UUID)
"""

import asyncio
import re
from typing import Any, Dict, Optional, Union
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.cache.decorators import invalidate_cache_key
from src.api.middleware.exceptions import RextAuthenticationException, RextValidationException
from src.api.models.knowledge_models.knowledge_model import BrandVoice
from src.api.models.workspace_models.workspace_member import WorkspaceMembers
from src.api.models.workspace_models.workspace_model import WorkspaceModel
from src.api.schema.knowledge_schema import BrandSchema, BrandVoiceUpdateSchema
from src.utils.logger import logger

# asyncio only holds a *weak* reference to tasks created via ensure_future/create_task.
# Without a strong reference kept somewhere, the embedding task can be garbage-collected
# mid-flight (e.g. before the OpenAI embedding call + DB write finish). Same pattern as
# workspace_service.py's _background_tasks.
_background_tasks: set = set()
_COMPETITOR_DOMAIN_LABEL_RE = re.compile(r"[a-z0-9]+")
_COMPETITOR_SITE_TIMEOUT_SECONDS = 10.0
_COMPETITOR_SITE_MAX_REDIRECTS = 5


class BrandVoiceService:
    """Service for workspace brand voice management"""

    def __init__(self, db: AsyncSession):
        """
        Initialize BrandVoiceService.

        Args:
            db: Async database session
        """
        self.db = db

    @staticmethod
    def _competitor_domain(name: str) -> str:
        """Derive a .com hostname from a validated company name."""
        label = "".join(_COMPETITOR_DOMAIN_LABEL_RE.findall(name.casefold()))
        return f"{label}.com"

    @staticmethod
    async def _competitor_site_is_available(name: str) -> bool:
        """A manually entered competitor must have a live https://<name>.com site.

        Redirects are followed (nike.com -> www.nike.com is normal), and every
        hop is checked against private and internal addresses first. The site
        counts as existing only when the final page answers HTTP 200.
        """
        import httpx

        from src.utils.fast_scraper import REQUEST_HEADERS
        from src.utils.url_validator import SSRFValidationError, validate_url_for_ssrf

        url = f"https://{BrandVoiceService._competitor_domain(name)}"
        try:
            async with httpx.AsyncClient(
                headers=REQUEST_HEADERS,
                follow_redirects=False,
                timeout=_COMPETITOR_SITE_TIMEOUT_SECONDS,
                trust_env=False,
            ) as client:
                for _ in range(_COMPETITOR_SITE_MAX_REDIRECTS + 1):
                    await asyncio.to_thread(validate_url_for_ssrf, url)
                    async with client.stream("GET", url) as response:
                        if not response.is_redirect:
                            return response.status_code == 200
                        url = str(response.url.join(response.headers["location"]))
        except (httpx.HTTPError, SSRFValidationError, KeyError, ValueError):
            return False
        return False

    async def validate_competitor_site(self, competitor: str) -> None:
        """Validate one competitor for the add-chip action without persisting it."""
        await self._validate_competitor_sites([competitor])

    async def _validate_competitor_sites(self, competitors: list[str]) -> None:
        """Check every competitor's site at once and report all that failed."""
        results = await asyncio.gather(
            *(self._competitor_site_is_available(name) for name in competitors)
        )
        missing = [name for name, ok in zip(competitors, results) if not ok]
        if missing:
            messages = [
                f'The website for "{name}" doesn\'t exist. Please enter a real competitor name.'
                for name in missing
            ]
            raise RextValidationException(
                message=messages[0], field_errors={"competitors": messages}
            )

    async def get_brand_voice(self, workspace_id: UUID, user_id: UUID) -> Optional[BrandVoice]:
        """
        Get brand voice for a workspace.

        Args:
            workspace_id: Workspace UUID
            user_id: User UUID (for membership check)

        Returns:
            BrandVoice object or None if not configured

        Raises:
            RextAuthenticationException: If user not workspace member
        """
        # Verify workspace membership
        await self._verify_workspace_membership(workspace_id, user_id)

        from sqlalchemy.orm import joinedload

        # Get brand voice with workspace and personas loaded
        result = await self.db.execute(
            select(BrandVoice)
            .options(joinedload(BrandVoice.workspace).joinedload(WorkspaceModel.personas))
            .where(BrandVoice.workspace_id == workspace_id)
        )
        brand_voice = result.unique().scalar_one_or_none()

        return brand_voice

    async def upsert_brand_voice(
        self, workspace_id: UUID, user_id: UUID, brand_data: Union[BrandSchema, Dict[str, Any]]
    ) -> BrandVoice:
        """
        Create or update brand voice for workspace.

        Business Rules:
        - User must be workspace member
        - Creates new if doesn't exist
        - Updates existing if exists
        - Supports data provided as BrandSchema or mapping

        Args:
            workspace_id: Workspace UUID
            user_id: User UUID (for membership check)
            brand_data: Structured brand voice payload

        Returns:
            BrandVoice object (created or updated)

        Raises:
            RextAuthenticationException: If user not workspace member
        """
        # Verify workspace membership
        await self._verify_workspace_membership(workspace_id, user_id)

        # Check if brand voice exists
        result = await self.db.execute(
            select(BrandVoice).where(BrandVoice.workspace_id == workspace_id)
        )
        brand_voice = result.scalar_one_or_none()

        # Competitors a user adds by hand must have a live website. Ones already
        # saved (including AI-extracted ones) are not re-checked, so editing any
        # other field never fails on an old competitor. AI-extracted
        # BrandSchema data stays lenient so a crawl never fails here.
        if isinstance(brand_data, BrandVoiceUpdateSchema):
            saved = {c.casefold() for c in ((brand_voice.competitors if brand_voice else None) or [])}
            added = [c for c in brand_data.competitors if c.casefold() not in saved]
            await self._validate_competitor_sites(added)

        payload = self._normalize_brand_data(brand_data)

        if brand_voice:
            for field, value in payload.items():
                setattr(brand_voice, field, value)

            action = "updated"
        else:
            # Create new brand voice entry
            brand_voice = BrandVoice(workspace_id=workspace_id, **payload)
            self.db.add(brand_voice)
            action = "created"

        await self.db.flush()

        # Personas are not columns on brand_voice, so they are applied
        # separately — and before the reload below, so the response shows the
        # set the caller just chose rather than the one it replaced.
        await self._apply_persona_selection(workspace_id, self._personas_from(brand_data))

        # Eagerly load workspace and personas for serialization
        from sqlalchemy.orm import joinedload

        result = await self.db.execute(
            select(BrandVoice)
            .options(joinedload(BrandVoice.workspace).joinedload(WorkspaceModel.personas))
            .where(BrandVoice.id == brand_voice.id)
        )
        brand_voice = result.unique().scalar_one()

        logger.info(
            f"Brand voice {action} for workspace {workspace_id}",
            extra={"workspace_id": str(workspace_id), "action": action},
        )

        # Invalidate workspace:brand_voice cache
        cache_key = f"workspace:brand_voice:{workspace_id}"
        await invalidate_cache_key(cache_key)

        # Fire-and-forget brand voice embedding update — reference retained in
        # _background_tasks so it isn't garbage-collected before it completes.
        from src.services.brand_voice_embedding_service import BrandVoiceEmbeddingService

        workspace_name = brand_voice.workspace.name if brand_voice.workspace else None
        embed_task = asyncio.ensure_future(
            BrandVoiceEmbeddingService().upsert_brand_voice_embedding(
                workspace_id=workspace_id,
                brand_data=payload,
                workspace_name=workspace_name,
            )
        )
        _background_tasks.add(embed_task)

        def _on_embed_done(task: "asyncio.Task") -> None:
            _background_tasks.discard(task)
            exc = task.exception() if not task.cancelled() else None
            if exc is not None:
                logger.warning(
                    f"[BrandVoiceEmbed] Background embedding task failed for workspace {workspace_id}: {exc}"
                )

        embed_task.add_done_callback(_on_embed_done)

        return brand_voice

    # ========================================================================
    # Private Helper Methods
    # ========================================================================

    async def _verify_workspace_membership(
        self, workspace_id: UUID, user_id: UUID
    ) -> WorkspaceMembers:
        """
        Verify user is workspace member.

        Args:
            workspace_id: Workspace UUID
            user_id: User UUID

        Returns:
            WorkspaceMembers object

        Raises:
            RextAuthenticationException: If user not member
        """
        result = await self.db.execute(
            select(WorkspaceMembers).where(
                WorkspaceMembers.workspace_id == workspace_id, WorkspaceMembers.user_id == user_id
            )
        )
        membership = result.scalar_one_or_none()

        if not membership:
            raise RextAuthenticationException(
                message="You are not a member of this workspace",
                context={"workspace_id": str(workspace_id)},
            )

        return membership

    # --------------------------------------------------------------------
    # Internal helpers
    # --------------------------------------------------------------------

    @staticmethod
    def _personas_from(brand_data: Union[BrandSchema, Dict[str, Any]]) -> Any:
        """The personas the caller sent, from either payload shape."""
        if isinstance(brand_data, BrandSchema):
            return brand_data.personas
        if isinstance(brand_data, dict):
            return brand_data.get("personas")
        return getattr(brand_data, "personas", None)

    @staticmethod
    def _persona_identities(personas: Any) -> set[str]:
        """Normalised names of the personas a caller selected."""
        identities: set[str] = set()
        for persona in personas or []:
            if isinstance(persona, dict):
                values = (persona.get("name"), persona.get("full_name"))
            else:
                values = (getattr(persona, "name", None), getattr(persona, "full_name", None))
            for value in values:
                if isinstance(value, str) and value.strip():
                    identities.add(value.strip().lower())
        return identities

    async def _apply_persona_selection(self, workspace_id: UUID, personas: Any) -> None:
        """Make the selected personas the workspace's persona set.

        Extraction saves every author it can prove the site publishes, which is
        the right default while nobody has said otherwise. The review step is
        where someone says otherwise: choosing five of fourteen means the other
        nine were declined, and leaving them in the workspace shows the user a
        persona list they already rejected.

        An EMPTY selection means "no preference", never "remove everyone" — the
        brand-voice settings form saves text without sending personas at all,
        and that must leave the workspace's authors untouched.

        Two things are never removed: personas someone created by hand
        (custom_metadata is NULL — they were never part of this selection), and
        anything at all when the selection matches no existing persona, which
        means the payload is not describing this workspace's personas and is no
        basis for deleting them.
        """
        selected = self._persona_identities(personas)
        if not selected:
            return

        from src.api.models.knowledge_models.persona_model import Persona

        result = await self.db.execute(select(Persona).where(Persona.workspace_id == workspace_id))
        existing = list(result.scalars().all())

        def is_selected(persona: Persona) -> bool:
            for value in (persona.name, persona.full_name):
                if isinstance(value, str) and value.strip().lower() in selected:
                    return True
            return False

        kept = [persona for persona in existing if is_selected(persona)]
        if not kept:
            logger.warning(
                "Persona selection matched none of the %d persona(s) in workspace %s; "
                "leaving them all in place",
                len(existing),
                workspace_id,
            )
            return

        removed = []
        for persona in existing:
            if is_selected(persona):
                continue
            if persona.custom_metadata is None:
                # Created by hand, not by extraction — not this selection's to drop.
                continue
            removed.append(persona.name)
            await self.db.delete(persona)

        if removed:
            await self.db.flush()
            logger.info(
                "Persona selection for workspace %s kept %d and removed %d: %s",
                workspace_id,
                len(kept),
                len(removed),
                ", ".join(str(name) for name in removed),
            )

    def _normalize_brand_data(
        self, brand_data: Union[BrandSchema, Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Convert brand voice payload into model-compatible structure.

        This method ensures all fields are correctly extracted from either a
        BrandSchema instance or a dictionary.
        """
        if isinstance(brand_data, BrandSchema):
            data = brand_data.model_dump()
        else:
            data = dict(brand_data)

        return {
            "brand_name": data.get("brand_name"),
            "about": data.get("about"),
            "customer_profile": data.get("customer_profile"),
            "selling_position": data.get("selling_position"),
            "target_audience": data.get("target_audience"),
            "brand_voice": data.get("brand_voice"),
            "competitors": data.get("competitors"),
            # content_strategy is mapped to content_pillar for backward compatibility
            "content_pillar": data.get("content_pillar") or data.get("content_strategy"),
        }

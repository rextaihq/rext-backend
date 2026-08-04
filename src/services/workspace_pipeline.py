from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional, Sequence, Tuple
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete, select

from src.api.models.knowledge_models.knowledge_model import Brand, BrandVoice
from src.api.schema.knowledge_schema import BrandSchema
from src.flow.model.llm_manager import load_model
from src.services.sse_service import (
    emit_pipeline_complete,
    emit_step_failure,
    emit_step_start,
    emit_step_success,
)
from src.api.models.knowledge_models.persona_model import AuthorPersona
from src.api.models.knowledge_models.audience_model import Audience
from src.api.models.knowledge_models.extraction_evidence_model import ExtractionEvidence

from src.utils.helper import web_page_scraper
from src.utils.logger import logger
from src.utils.vector_store import add_to_vector_store

ScrapeCallable = Callable[[str], Awaitable[Tuple[List[Any], List[Any]]]]
VectorUploaderCallable = Callable[[Sequence[Any], str], Awaitable[bool]]
BrandVoiceGeneratorCallable = Callable[[str], Awaitable[Optional[BrandSchema]]]


@dataclass
class _ScrapeResult:
    """Container for scraped data reused across pipeline steps."""

    chunks: List[Any]
    content: str
    metadata: Dict[str, Any]


_ARCHETYPE_KEYWORDS = {
    "owner", "manager", "user", "customer", "client", "buyer", "blogger",
    "professional", "entrepreneur", "startup", "business", "store", "shop",
    "target", "audience", "segment", "persona", "marketer", "executive",
    "director", "officer", "employee", "worker", "freelancer", "consultant",
}


def _filter_valid_personas(personas: list[dict]) -> list[dict]:
    """Return only personas that appear to be real named individuals.

    Rejects entries whose name is a role/archetype (e.g. "Online Store Owner")
    rather than an actual human name (e.g. "John Smith").
    """
    valid = []
    rejected = []
    for p in personas:
        name: str = (p.get("name") or "").strip()
        if not name:
            rejected.append({"name": "(empty)", "reason": "missing name"})
            continue
        source: str = (p.get("source") or "").strip().lower()
        if source == "testimonial":
            rejected.append({"name": name, "reason": "testimonial-only source"})
            continue
        words = name.lower().split()
        if any(w in _ARCHETYPE_KEYWORDS for w in words):
            rejected.append({"name": name, "reason": "archetype keyword"})
            continue
        title_prefixes = {"dr.", "dr", "mr.", "mr", "ms.", "ms", "mrs.", "prof.", "prof"}
        has_title = words[0] in title_prefixes
        if len(words) < 2 and not has_title:
            rejected.append({"name": name, "reason": "single word / no title"})
            continue
        valid.append(p)

    if rejected:
        logger.info(
            "Filtered out invalid personas",
            extra={"rejected": rejected, "valid_count": len(valid)},
        )
    if not valid:
        logger.info("No valid personas found — no real named individuals identified on site")

    return valid


_URL_LIKE_RE = re.compile(r"^(https?://|www\.)|(\.[a-z]{2,63}(/.*)?$)", re.IGNORECASE)

_NON_COMPETITOR_KEYWORDS = {
    "trusted by", "as seen in", "as featured in", "our clients", "our partners",
    "our customers", "integrates with", "works with", "powered by", "built with",
    "backed by", "sponsors", "sponsored by",
}


def _filter_valid_competitors(
    competitors: list[str],
    brand_name: Optional[str],
) -> list[str]:
    """Return only entries that look like real, distinct competitor brand names.

    The extraction prompt asks the LLM to infer competitors when none are
    directly mentioned, which is prone to two failure modes: echoing the
    scraped site's own brand name back as a "competitor", and picking up
    partner/client/integration logos (or their raw domains/URLs) from
    "trusted by" or "as seen in" sections instead of actual competitors.
    """
    normalized_brand = (brand_name or "").strip().lower()
    seen: set[str] = set()
    valid: list[str] = []
    rejected: list[dict[str, str]] = []

    for raw in competitors:
        name = (raw or "").strip()
        if not name:
            continue

        lowered = name.lower()

        if normalized_brand and lowered == normalized_brand:
            rejected.append({"name": name, "reason": "matches brand's own name"})
            continue

        if _URL_LIKE_RE.search(name):
            rejected.append({"name": name, "reason": "URL/domain, not a brand name"})
            continue

        if any(keyword in lowered for keyword in _NON_COMPETITOR_KEYWORDS):
            rejected.append({"name": name, "reason": "partner/client mention, not a competitor"})
            continue

        if lowered in seen:
            continue
        seen.add(lowered)
        valid.append(name)

    if rejected:
        logger.info(
            "Filtered out invalid competitors",
            extra={"rejected": rejected, "valid_count": len(valid)},
        )

    return valid


class WorkspacePipeline:
    """Background pipeline responsible for workspace onboarding tasks."""

    # Head + tail budget for the brand-voice/persona extraction prompt.
    # Landing pages routinely put the founder/team "Built by ..." credit in
    # the footer — the very end of the scraped markdown — while marketing
    # copy (hero, features, testimonials) fills the middle. A flat head-only
    # slice reliably drops that credit on any page longer than the budget.
    # Confirmed on nextlyhq.com: "Built by Mobeen Abdullah at Revnix" sits at
    # char ~10,800 of a 10,816-char page — the old flat 5,000-char head slice
    # discarded it entirely, so the LLM never saw the one real person on the
    # page and correctly (per its own rules) returned an empty persona list.
    # Sampling both ends keeps the prompt bounded while guaranteeing the
    # footer is never lost.
    _HEAD_CHARS = 8_000
    _TAIL_CHARS = 4_000

    def __init__(
        self,
        *,
        db: AsyncSession,
        operation_id: str,
        workspace_id: UUID,
        user_id: UUID,
        url: str,
        scraper: Optional[ScrapeCallable] = None,
        vector_uploader: Optional[VectorUploaderCallable] = None,
        brand_voice_generator: Optional[BrandVoiceGeneratorCallable] = None,
    ) -> None:
        self.db = db
        self.operation_id = operation_id
        self.workspace_id = workspace_id
        self.url = url
        self.user_id = user_id
        self._scraper = scraper or self._default_scraper
        self._vector_uploader = vector_uploader or self._default_vector_uploader
        self._brand_voice_generator = (
            brand_voice_generator or self._default_brand_voice_generator
        )
        self.scope = "workspace"

    async def run(self) -> None:
        """Execute the workspace pipeline and stream progress via SSE."""
        logger.info(
            "Workspace pipeline started",
            extra={"workspace_id": str(self.workspace_id), "operation_id": self.operation_id},
        )
        brand_voice_schema: Optional[BrandSchema] = None

        try:
            scrape_result = await self._scrape_website()
            await self._create_vector_embeddings(scrape_result.chunks)
            brand_voice_schema = await self._extract_brand_voice(scrape_result.content)
            await self._persist_brand_voice(brand_voice_schema)
            await self._embed_brand_voice(brand_voice_schema)

            payload: Dict[str, Any] = {"workspace_id": str(self.workspace_id)}
            if brand_voice_schema:
                payload["brand_voice"] = brand_voice_schema.model_dump()

            await emit_pipeline_complete(
                operation_id=self.operation_id,
                scope=self.scope,
                message="Workspace creation pipeline completed successfully",
                payload=payload,
                user_id=self.user_id,
            )
            logger.info(
                "Workspace pipeline completed",
                extra={"workspace_id": str(self.workspace_id), "operation_id": self.operation_id},
            )

        except Exception as exc:  # noqa: BLE001 - propagate for caller logging
            logger.error(
                "Workspace pipeline failed",
                extra={
                    "workspace_id": str(self.workspace_id),
                    "operation_id": self.operation_id,
                    "error": str(exc),
                },
            )
            await emit_step_failure(
                operation_id=self.operation_id,
                scope=self.scope,
                step="pipeline",
                message="Workspace creation pipeline failed",
                error=str(exc),
                user_id=self.user_id,
            )
            raise

    async def _scrape_website(self) -> _ScrapeResult:
        """Scrape the target URL and emit relevant SSE events."""
        logger.info(
            "Starting to scrape URL",
            extra={
                "workspace_id": str(self.workspace_id),
                "operation_id": self.operation_id,
                "url": self.url,
            },
        )
        
        await emit_step_start(
            operation_id=self.operation_id,
            scope=self.scope,
            step="scrape",
            message=f"Scraping website: {self.url}",
            progress=10,
            user_id=self.user_id,
        )

        try:
            chunks, results = await self._scraper(self.url)
        except Exception as exc:  # noqa: BLE001 - surface to pipeline
            await emit_step_failure(
                operation_id=self.operation_id,
                scope=self.scope,
                step="scrape",
                message=f"Failed to scrape website: {exc}",
                error=str(exc),
                user_id=self.user_id,
            )
            raise

        first_success = next(
            (result for result in results or [] if getattr(result, "success", False)),
            None,
        )
        content = getattr(first_success, "markdown", "") if first_success else ""
        metadata = {
            "url": getattr(first_success, "url", self.url),
            "title": (getattr(first_success, "metadata", {}) or {}).get("title"),
            "word_count": len(content.split()),
            "char_count": len(content),
        }

        await emit_step_success(
            operation_id=self.operation_id,
            scope=self.scope,
            step="scrape",
            message="Website scraped successfully",
            payload=metadata,
            progress=30,
            user_id=self.user_id,
        )

        return _ScrapeResult(
            chunks=list(chunks or []),
            content=content,
            metadata=metadata,
        )

    async def _create_vector_embeddings(self, chunks: Sequence[Any]) -> None:
        """Create vector embeddings for scraped chunks."""
        if not chunks:
            logger.info(
                "Skipping vector store insertion - no chunks available",
                extra={"workspace_id": str(self.workspace_id), "operation_id": self.operation_id},
            )
            return

        # ============================================================================
        # VECTOR STORE DISABLED (COMMENTED OUT)
        # To re-enable: uncomment the code block below
        # ============================================================================
        
        logger.info(
            "Vector store disabled, skipping chunks",
            extra={
                "workspace_id": str(self.workspace_id),
                "operation_id": self.operation_id,
                "chunk_count": len(chunks),
            },
        )
        
        # Original code commented out below:
        # await emit_step_start(
        #     operation_id=self.operation_id,
        #     scope=self.scope,
        #     step="vector_store",
        #     message="Generating vector embeddings",
        #     progress=40,
        # )

        # try:
        #     success = await self._vector_uploader(chunks, str(self.workspace_id))
        # except Exception as exc:  # noqa: BLE001 - propagate
        #     await emit_step_failure(
        #         operation_id=self.operation_id,
        #         scope=self.scope,
        #         step="vector_store",
        #         message=f"Failed to create embeddings: {exc}",
        #         error=str(exc),
        #     )
        #     raise

        # if not success:
        #     error_message = "Vector store reported failure"
        #     await emit_step_failure(
        #         operation_id=self.operation_id,
        #         scope=self.scope,
        #         step="vector_store",
        #         message=error_message,
        #         error=error_message,
        #     )
        #     raise RuntimeError(error_message)

        # payload = {"chunks": len(chunks)}
        # await emit_step_success(
        #     operation_id=self.operation_id,
        #     scope=self.scope,
        #     step="vector_store",
        #     message="Vector embeddings created",
        #     payload=payload,
        #     progress=60,
        # )

    async def _extract_brand_voice(
        self,
        content: str,
    ) -> Optional[BrandSchema]:
        """Generate brand voice insights from scraped content."""
        await emit_step_start(
            operation_id=self.operation_id,
            scope=self.scope,
            step="brand_voice",
            message="Analyzing brand voice",
            progress=70,
            user_id=self.user_id,
        )

        if not content.strip():
            await emit_step_success(
                operation_id=self.operation_id,
                scope=self.scope,
                step="brand_voice",
                message="No content available for brand voice extraction",
                payload=None,
                progress=90,
                user_id=self.user_id,
            )
            return None

        trimmed_content = self._sample_content_for_extraction(content)

        logger.info(
            "Scraped content prepared for brand voice extraction",
            extra={
                "workspace_id": str(self.workspace_id),
                "operation_id": self.operation_id,
                "original_length": len(content),
                "trimmed_length": len(trimmed_content),
            },
        )
        logger.debug(
            "Scraped content for LLM analysis",
            extra={
                "workspace_id": str(self.workspace_id),
                "operation_id": self.operation_id,
                "content_preview": trimmed_content[:500],
                "content_length": len(trimmed_content),
            },
        )


        try:
            brand_voice_schema = await self._brand_voice_generator(trimmed_content)
        except Exception as exc:  # noqa: BLE001 - surface to pipeline
            await emit_step_failure(
                operation_id=self.operation_id,
                scope=self.scope,
                step="brand_voice",
                message=f"Failed to extract brand voice: {exc}",
                error=str(exc),
                user_id=self.user_id,
            )
            raise

        if brand_voice_schema is None:
            await emit_step_success(
                operation_id=self.operation_id,
                scope=self.scope,
                step="brand_voice",
                message="Brand voice extraction returned no data",
                payload=None,
                progress=90,
                user_id=self.user_id,
            )
            return None

        await emit_step_success(
            operation_id=self.operation_id,
            scope=self.scope,
            step="brand_voice",
            message="Brand voice extracted successfully",
            payload=brand_voice_schema.model_dump(),
            progress=90,
            user_id=self.user_id,
        )
        return brand_voice_schema

    def _sample_content_for_extraction(self, content: str) -> str:
        """Sample the scraped page for the brand-voice/persona extraction prompt.

        Takes the head (hero/intro/features — brand voice signal) AND the
        tail (footer — where founder/"Built by"/author credits usually live)
        instead of a single flat head-slice, so long landing pages don't
        silently drop the one line that names a real person. See
        ``_HEAD_CHARS``/``_TAIL_CHARS`` for why this exists.
        """
        total_budget = self._HEAD_CHARS + self._TAIL_CHARS
        if len(content) <= total_budget:
            return content
        head = content[: self._HEAD_CHARS]
        tail = content[-self._TAIL_CHARS:]
        return f"{head}\n\n...[middle of page omitted]...\n\n{tail}"

    async def _persist_brand_voice(
        self,
        brand_voice_schema: Optional[BrandSchema],
    ) -> Optional[Brand]:
        """Persist brand identity + voice, and extract personas/audience/evidence."""
        if brand_voice_schema is None:
            return None

        data = brand_voice_schema.model_dump()

        # Extract nested payloads before processing brand identity/voice
        raw_personas = data.pop("personas", [])
        personas_data = _filter_valid_personas(raw_personas)
        audience_segments = data.pop("audience_segments", []) or []
        evidence_items = data.pop("evidence", []) or []

        data["competitors"] = _filter_valid_competitors(
            data.get("competitors") or [], data.get("brand_name")
        )

        try:
            result = await self.db.execute(
                select(Brand).where(Brand.workspace_id == self.workspace_id)
            )
            existing = result.scalar_one_or_none() if result else None

            if existing:
                # Preserve a manually-entered brand name if this extraction pass
                # couldn't find one on the site — don't let a refresh null it out.
                existing.brand_name = data.get("brand_name") or existing.brand_name
                existing.about = data.get("about")
                existing.website_type = data.get("website_type")
                existing.website_type_confidence = data.get("website_type_confidence")
                existing.customer_profile = data.get("customer_profile")
                existing.selling_position = data.get("selling_position")
                existing.target_audience_summary = data.get("target_audience") or []
                existing.competitors = data.get("competitors") or []
                existing.content_pillar = data.get("content_pillar") or []
                brand_record = existing
            else:
                brand_record = Brand(
                    workspace_id=self.workspace_id,
                    brand_name=data.get("brand_name"),
                    about=data.get("about"),
                    website_type=data.get("website_type"),
                    website_type_confidence=data.get("website_type_confidence"),
                    customer_profile=data.get("customer_profile"),
                    selling_position=data.get("selling_position"),
                    target_audience_summary=data.get("target_audience") or [],
                    competitors=data.get("competitors") or [],
                    content_pillar=data.get("content_pillar") or [],
                )
                self.db.add(brand_record)

            await self.db.flush()

            result = await self.db.execute(
                select(BrandVoice).where(BrandVoice.brand_id == brand_record.id)
            )
            existing_voice = result.scalar_one_or_none()
            voice_kwargs = dict(
                tone_attributes=data.get("tone_attributes") or [],
                formality_level=data.get("formality_level"),
                point_of_view=data.get("point_of_view"),
                preferred_terms=[t if isinstance(t, dict) else t for t in (data.get("preferred_terms") or [])],
                banned_terms=data.get("banned_terms") or [],
                cta_style=data.get("cta_style"),
            )
            if existing_voice:
                for field_name, value in voice_kwargs.items():
                    setattr(existing_voice, field_name, value)
            else:
                self.db.add(BrandVoice(brand_id=brand_record.id, **voice_kwargs))

            await self.db.flush()

            # Persist personas, audience segments, and evidence separately
            await self._persist_personas(personas_data)
            await self._persist_audience_segments(audience_segments)
            await self._persist_evidence(brand_record.id, evidence_items, data)

            await self.db.flush()
            return brand_record

        except Exception as exc:  # noqa: BLE001 - rollback and propagate
            await self.db.rollback()
            logger.error(
                "Failed to persist brand voice and personas",
                extra={
                    "workspace_id": str(self.workspace_id),
                    "operation_id": self.operation_id,
                    "error": str(exc),
                },
            )
            raise

    async def _persist_audience_segments(self, audience_segments: list[dict]) -> None:
        """Save extracted audience segments. Best-effort — see AudienceExtract docstring."""
        if not audience_segments:
            return

        for segment in audience_segments:
            demographics = segment.get("demographics")
            audience = Audience(
                workspace_id=self.workspace_id,
                name=segment.get("name") or "Audience Segment",
                description=segment.get("description"),
                demographics=demographics if isinstance(demographics, dict) else None,
                pain_points=segment.get("pain_points") or [],
                goals=segment.get("goals") or [],
                behaviors=segment.get("behaviors") or [],
            )
            self.db.add(audience)

        await self.db.flush()
        logger.info(
            "Persisted audience segments",
            extra={
                "workspace_id": str(self.workspace_id),
                "operation_id": self.operation_id,
                "segment_count": len(audience_segments),
            },
        )

    async def _persist_evidence(
        self,
        brand_id: UUID,
        evidence_items: list[dict],
        brand_data: dict,
    ) -> None:
        """Persist per-field confidence/source/citation for the brand extraction.

        Brand-identity vs. brand-voice fields route to the correct FK based
        on which schema they belong to (see knowledge_schema.BrandSchema).
        """
        if not evidence_items:
            return

        voice_field_names = {
            "tone_attributes", "formality_level", "point_of_view",
            "preferred_terms", "banned_terms", "cta_style",
        }
        result = await self.db.execute(
            select(BrandVoice).where(BrandVoice.brand_id == brand_id)
        )
        brand_voice_row = result.scalar_one_or_none()

        for item in evidence_items:
            field_name = item.get("field_name")
            if not field_name:
                continue
            is_voice_field = field_name in voice_field_names
            self.db.add(
                ExtractionEvidence(
                    workspace_id=self.workspace_id,
                    brand_id=None if is_voice_field else brand_id,
                    brand_voice_id=(brand_voice_row.id if (is_voice_field and brand_voice_row) else None),
                    field_name=field_name,
                    extracted_value=str(brand_data.get(field_name, ""))[:2000],
                    confidence=item.get("confidence"),
                    supporting_excerpt=item.get("excerpt"),
                    extraction_method="llm_structured_output",
                )
            )

        await self.db.flush()
        logger.info(
            "Persisted extraction evidence",
            extra={
                "workspace_id": str(self.workspace_id),
                "operation_id": self.operation_id,
                "evidence_count": len(evidence_items),
            },
        )

    async def _embed_brand_voice(self, brand_voice_schema: Optional[BrandSchema]) -> None:
        """Store brand voice embedding in the vector store (non-fatal)."""
        if not brand_voice_schema:
            return
        try:
            from src.services.brand_voice_embedding_service import BrandVoiceEmbeddingService
            from src.api.models.workspace_models.workspace_model import WorkspaceModel

            result = await self.db.execute(
                select(WorkspaceModel).where(WorkspaceModel.id == self.workspace_id)
            )
            workspace = result.scalar_one_or_none()
            workspace_name = workspace.name if workspace else None

            svc = BrandVoiceEmbeddingService()
            await svc.upsert_brand_voice_embedding(
                workspace_id=self.workspace_id,
                brand_data=brand_voice_schema.model_dump(),
                workspace_name=workspace_name,
            )
        except Exception as exc:
            logger.warning(
                "[BrandVoiceEmbed] Embedding failed (non-fatal)",
                extra={"workspace_id": str(self.workspace_id), "error": str(exc)},
            )

    async def _persist_personas(self, personas_data: list[dict]) -> None:
        """Save extracted personas to persona table.

        Always clears out personas from the previous workspace URL, even when
        the new extraction found none — otherwise a refresh to a persona-less
        site would leave stale personas from the old site in place.
        """
        if not personas_data:
            logger.info(
                "No personas extracted; clearing existing personas for workspace",
                extra={"workspace_id": str(self.workspace_id), "operation_id": self.operation_id}
            )
        else:
            logger.info(
                "Extracted personas ready for persistence",
                extra={
                    "workspace_id": str(self.workspace_id),
                    "operation_id": self.operation_id,
                    "persona_count": len(personas_data),
                    "persona_names": [p.get("name", "Unnamed") for p in personas_data],
                },
            )
            logger.debug(
                "Extracted persona details",
                extra={
                    "workspace_id": str(self.workspace_id),
                    "operation_id": self.operation_id,
                    "personas": [
                        {
                            "name": p.get("name"),
                            "description": p.get("description"),
                            "professional_title": p.get("professional_title"),
                            "has_bio": bool(p.get("bio")),
                            "has_linkedin": bool(p.get("linkedin_url")),
                        }
                        for p in personas_data
                    ],
                },
            )

        # Use a savepoint to make the delete-then-insert atomic.
        # If insertion fails, the savepoint rollback also undoes the deletion,
        # preserving the original personas.
        def _normalize_text(value: Any) -> Optional[str]:
            if value is None:
                return None
            if isinstance(value, (list, tuple, set)):
                return ", ".join(str(item).strip() for item in value if item is not None)
            if isinstance(value, dict):
                return json.dumps(value, ensure_ascii=False)
            return str(value)

        async with self.db.begin_nested():
            # Delete existing personas (and their evidence, via FK cascade)
            # for this workspace
            await self.db.execute(
                delete(AuthorPersona).where(AuthorPersona.workspace_id == self.workspace_id)
            )

            # Insert new author personas with all E-E-A-T identity fields
            for persona_data in personas_data:
                linkedin_url = _normalize_text(persona_data.get("linkedin_url"))
                persona = AuthorPersona(
                    workspace_id=self.workspace_id,
                    name=_normalize_text(persona_data.get("name")) or "",
                    description=_normalize_text(persona_data.get("description")),
                    full_name=_normalize_text(persona_data.get("full_name")),
                    professional_title=_normalize_text(persona_data.get("professional_title")),
                    areas_of_expertise=persona_data.get("areas_of_expertise"),
                    experience_type=_normalize_text(persona_data.get("experience_type")),
                    years_of_experience=persona_data.get("years_of_experience"),
                    credentials=persona_data.get("credentials") or [],
                    employer=_normalize_text(persona_data.get("employer")),
                    writing_voice=_normalize_text(persona_data.get("writing_voice")),
                    bio=_normalize_text(persona_data.get("bio")),
                    social_profiles=(
                        [{"platform": "linkedin", "url": linkedin_url}] if linkedin_url else []
                    ),
                    avatar_url=_normalize_text(persona_data.get("avatar_url")),
                )
                self.db.add(persona)
                await self.db.flush()

                # Capture the 'source' signal (founder/team_member/author/expert)
                # that was previously computed then silently discarded before
                # persistence — now recorded as extraction evidence.
                source = persona_data.get("source")
                if source:
                    self.db.add(
                        ExtractionEvidence(
                            workspace_id=self.workspace_id,
                            author_persona_id=persona.id,
                            field_name="source",
                            extracted_value=str(source),
                            confidence=None,
                            extraction_method="llm_structured_output",
                        )
                    )

            # Flush within the savepoint to detect constraint violations
            await self.db.flush()

        logger.info(
            "Persisted personas",
            extra={
                "workspace_id": str(self.workspace_id),
                "operation_id": self.operation_id,
                "persona_count": len(personas_data),
            },
        )

    @staticmethod
    async def _default_scraper(url: str) -> Tuple[List[Any], List[Any]]:
        return await web_page_scraper(urls=[url])

    @staticmethod
    async def _default_vector_uploader(
        chunks: Sequence[Any],
        workspace_id: str,
    ) -> bool:
        return await asyncio.to_thread(
            add_to_vector_store,
            blog_context=list(chunks),
            workspace_id=workspace_id,
        )

    @staticmethod
    async def _default_brand_voice_generator(content: str) -> Optional[BrandSchema]:
        if not content.strip():
            return None

        async def _invoke_model() -> BrandSchema:
            from langchain_core.messages import SystemMessage, HumanMessage
            
            model = load_model()
            structured = model.with_structured_output(BrandSchema)
            
            system_prompt = """You are an expert at analyzing website content and extracting brand information and real people.

IMPORTANT INSTRUCTIONS FOR BRAND INFORMATION:
- Extract 'brand_name': The actual brand/company/product name as it appears on the site (e.g. in the logo, title tag, "About Us", or copyright line) — NOT a generic description, NOT the URL/domain, and NOT anything you infer from context. If the real brand name genuinely cannot be found in the content, leave this null — never guess or fabricate one.
- Extract 'about': A brief summary of what the brand/business does (1-2 sentences).
- Extract 'website_type': Classify the site's business model as one of: saas, ecommerce, agency, personal_blog, news_media, documentation, knowledge_base, educational, government, healthcare, finance, legal, non_profit, community, business_services, other. Base this only on what the content actually shows.
- Extract 'website_type_confidence': Your confidence in that classification, 0.0-1.0.
- Extract 'customer_profile': Who their ideal customers are and their characteristics.
- Extract 'selling_position': Their unique value proposition (what makes them different).
- Extract 'target_audience': Specific segments or demographics they target (short labels).
- Extract 'tone_attributes': The characteristics of their communication style (e.g., Authoritative, Friendly, Professional, etc.).
- Extract 'formality_level' (one of: very_casual, casual, neutral, formal, very_formal), 'point_of_view' (one of: first_singular, first_plural, second, third), 'preferred_terms' (exact vocabulary the brand consistently uses, only if clearly evidenced — e.g. always says "track" never "monitor"), 'banned_terms' (words/phrases the brand visibly avoids, only if evidenced), and 'cta_style' (how the brand phrases calls-to-action, only if evidenced) — leave any of these null/empty rather than guessing if the site doesn't give clear signal.
- Extract 'competitors': Only OTHER businesses that offer the SAME specific service/product, at the SAME specialization level, to the SAME target customer as this brand — i.e. a customer would realistically choose between this brand and the competitor for the exact same purchase decision. Accuracy matters far more than hitting any particular count — zero correct competitors is a better answer than one wrong-niche guess.
  - STEP 1 — Identify the brand's SPECIFIC niche and business model from what it actually says about its services/offerings and target customers (not just a broad topic/industry). "Custom enterprise WordPress development agency serving publishers and SaaS companies" is a specific niche; "WordPress" alone is just a broad topic. "Direct-to-consumer sustainable sneaker brand" is a specific niche; "footwear" alone is just a broad topic.
  - STEP 2 — A valid competitor must match that SAME specific niche , business model Audience and Real customer — being in the same broad topic/industry/ecosystem is NOT enough, and being generically "well-known" in that broad topic is NOT a reason to include something. A correct but less-famous same-niche peer always beats a famous but wrong-niche name. Worked examples, one per common business model — use whichever matches this site, and reason the same way for any other model you encounter:
    a) Content/blog/review site that writes ABOUT a topic (e.g. WordPress tips, tutorials, plugin roundups): competitors are OTHER content/blog sites covering the same topic — NOT the hosting companies, plugins, tools, or freelance marketplaces it writes about, links to, reviews, or recommends.
    b) Service AGENCY/consultancy (e.g. a custom WordPress development agency serving enterprise clients): competitors are OTHER agencies offering the same specific service at the same tier (e.g. rtCamp, 10up, Human Made, WebDevStudios, DevriX, XWP, Multidots, IT Monks, Syde for enterprise WordPress dev) — NOT generic hosting providers (e.g. WP Engine, Kinsta), freelance talent marketplaces (e.g. Toptal, Upwork), or media/education sites (e.g. SitePoint, WPBeginner) that merely share the same broad topic.
    c) SaaS product (e.g. a CRM tool): competitors are OTHER SaaS products solving the same problem for the same buyer (e.g. Salesforce, HubSpot, Pipedrive for a SaaS CRM) — NOT the tools it integrates with, its hosting/infra provider, or its own customers' logos.
    d) E-commerce/DTC brand (e.g. a sustainable clothing brand): competitors are OTHER brands selling similar products to the same shopper (e.g. Patagonia, Everlane) — NOT payment processors, shipping partners, or marketplaces it merely sells through.
  - A company being named on the page (as a tool recommendation, hosting sponsor, affiliate link, citation, or example) does NOT make it a competitor — those are references, not rivals.
  - Prefer direct evidence: an explicit comparison page, "vs" content, or "alternatives to us" callout naming a rival.
  - If no direct evidence exists, you may infer up to 3-5 competitors, but ONLY the ones you are genuinely confident match the SAME specific niche per Step 2 — it is fine to return 1, 2, or 0 inferred competitors instead of forcing the count to 3-5. Before finalizing each inferred name, silently double-check it against your own 'about'/'selling_position' answer: does this competitor sell the exact same specific thing, to the exact same specific customer, that you just described? If you cannot honestly say yes, drop it. If the content is generic, placeholder, template/demo text, or too ambiguous to confidently pin down the specific niche, return an EMPTY list rather than guessing a famous but wrong-niche name.
  - Output the competitor's proper brand/company name only (e.g., "HubSpot") — NEVER a URL or domain (e.g., NOT "hubspot.com" or "www.hubspot.com").
  - NEVER include the brand's own name as one of its competitors.
  - Do NOT confuse competitors with: technology/integration partners ("works with X"), payment/hosting providers, tools/plugins/services reviewed or recommended in the content, clients or customers, or logos shown in "trusted by" / "as seen in" / "as featured in" sections — none of these are competitors, even when named prominently.
- Extract 'content_pillar': The main themes or categories they create content about.

STRICT RULES FOR PERSONAS — READ CAREFULLY:

RULE 1 — REAL PEOPLE ONLY, AND ONLY IF THEY SPEAK FOR THE BRAND:
The personas list MUST contain ONLY real, named human individuals explicitly mentioned by name on the website who represent or speak ON BEHALF OF the brand/business itself.
Valid sources: founders, co-founders, authors, blog writers, team members, executives, named experts employed by or affiliated with the brand.

RULE 2 — NAME REQUIREMENT:
A valid persona MUST have a real human name consisting of at least a first and last name (e.g., "John Smith", "Dr. Sarah Mitchell", "Mobheen Abdullah").
Single words, job titles, roles, or descriptions are NOT valid names.

RULE 3 — STRICTLY FORBIDDEN PERSONAS (these are NEVER valid — DO NOT add them to the personas list at all):
Do NOT create a persona entry for any of the following. Simply OMIT them from the list entirely — they belong conceptually in 'target_audience' or 'customer_profile', NOT personas:
  - Named individuals who ONLY appear as customer testimonial/review/case-study contributors (e.g., a quote attributed to "Jane Doe, Ohio" praising the product). These are customers, not brand representatives. Even though they have a real name, do NOT add them to the personas list under any circumstances — not even with a different source label.
  - Customer archetypes (e.g., "Online Store Owner", "Busy Blogger", "Small Business Owner")
  - Target audience segments (e.g., "Marketing Manager", "Entrepreneur", "Startup Founder")
  - Fictional or representative users (e.g., "The Modern Professional", "Tech-Savvy User")
  - Generic roles without a real name attached

RULE 4 — EMPTY LIST WHEN NO REAL PEOPLE FOUND:
If the website content does NOT explicitly mention any real named individuals who are founders, team members, authors, or otherwise represent the brand, you MUST return an EMPTY list: personas = []
Do NOT invent, fabricate, or infer personas. Do NOT use testimonial/review authors as a substitute. Do NOT populate this field with guesses.
Returning an empty list IS the correct answer when no real brand-affiliated people are named on the site — even if named customers/testimonial contributors are present.

For each valid PERSONA extracted, provide:
- name: The person's actual name exactly as it appears on the site (e.g., "Mobheen Abdullah").
- source: One of 'founder', 'team_member', 'author', 'expert', or 'testimonial'. Per RULE 3, if the ONLY place a person's name appears is as the attribution on a customer testimonial/review/case-study quote, do NOT add them to the personas list at all — leave them out entirely rather than including them with source='testimonial'. The 'testimonial' value exists only as a safety label for the rare edge case where you are unsure; it is never the preferred outcome — omission is.
- full_name: Their complete professional name if available.
- professional_title: Their stated job title (e.g., "Founder & CEO").
- areas_of_expertise: What they specialize in based on their stated role and content.
- writing_voice: Their personal writing or communication style if discernible.
- experience_type: 'formal_expertise' if they have a stated license/degree/certification, 'everyday_experience' if they speak from lived experience without credentials, 'both' if both are evidenced, otherwise leave null.
- years_of_experience, credentials, employer: only if explicitly stated — leave null/empty rather than guessing.
- bio: A brief professional background based ONLY on what the site explicitly states about them.

OPTIONAL — 'audience_segments': Only add an entry here if the site gives genuinely distinct buyer/reader segment detail beyond what 'customer_profile'/'target_audience' already capture (e.g. two clearly different named customer types with different pain points). Leave this empty in the common case — do not force a segment into existence.

OPTIONAL — 'evidence': For the most important fields above (brand_name, about, selling_position, competitors, tone_attributes, and any persona's source), include one evidence entry with the field_name, a short verbatim excerpt from the content that supports it, and a confidence score (0-1). Skip fields you inferred without a direct textual excerpt — do not fabricate an excerpt.
"""

            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=f"Analyze the following website content and extract brand information and any real named individuals:\n\n{content}")
            ]
            
            return await structured.ainvoke(messages)

        return await _invoke_model()


async def run_workspace_pipeline(
    *,
    db: AsyncSession,
    operation_id: str,
    workspace_id: UUID,
    user_id: UUID,
    url: str,
    scraper: Optional[ScrapeCallable] = None,
    vector_uploader: Optional[VectorUploaderCallable] = None,
    brand_voice_generator: Optional[BrandVoiceGeneratorCallable] = None,
) -> None:
    """
    Entrypoint for triggering the workspace pipeline, typically from background tasks.

    Args:
        db: Async SQLAlchemy session
        operation_id: Identifier correlating SSE stream subscribers
        workspace_id: Workspace being processed
        url: Primary website URL provided during creation
        scraper: Optional override used for testing
        vector_uploader: Optional override used for testing
        brand_voice_generator: Optional override used for testing
    """
    pipeline = WorkspacePipeline(
        db=db,
        operation_id=operation_id,
        workspace_id=workspace_id,
        user_id=user_id,
        url=url,
        scraper=scraper,
        vector_uploader=vector_uploader,
        brand_voice_generator=brand_voice_generator,
    )
    await pipeline.run()

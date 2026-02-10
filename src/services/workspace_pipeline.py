from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional, Sequence, Tuple
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete, select

from src.api.models.knowledge_models.knowledge_model import BrandVoice
from src.api.schema.knowledge_schema import BrandSchema
from src.flow.model.llm_manager import load_model
from src.services.sse_service import (
    emit_pipeline_complete,
    emit_step_failure,
    emit_step_start,
    emit_step_success,
)
from src.api.models.knowledge_models.persona_model import Persona

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


class WorkspacePipeline:
    """Background pipeline responsible for workspace onboarding tasks."""

    _MAX_BRAND_VOICE_CHARS = 5_000

    def __init__(
        self,
        *,
        db: AsyncSession,
        operation_id: str,
        workspace_id: UUID,
        url: str,
        scraper: Optional[ScrapeCallable] = None,
        vector_uploader: Optional[VectorUploaderCallable] = None,
        brand_voice_generator: Optional[BrandVoiceGeneratorCallable] = None,
    ) -> None:
        self.db = db
        self.operation_id = operation_id
        self.workspace_id = workspace_id
        self.url = url
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

            payload: Dict[str, Any] = {"workspace_id": str(self.workspace_id)}
            if brand_voice_schema:
                payload["brand_voice"] = brand_voice_schema.model_dump()

            await emit_pipeline_complete(
                operation_id=self.operation_id,
                scope=self.scope,
                message="Workspace creation pipeline completed successfully",
                payload=payload,
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
            )
            raise

    async def _scrape_website(self) -> _ScrapeResult:
        """Scrape the target URL and emit relevant SSE events."""
        logger.info(
            f"🌐 Starting to scrape URL: {self.url}",
            extra={"workspace_id": str(self.workspace_id), "operation_id": self.operation_id},
        )
        
        await emit_step_start(
            operation_id=self.operation_id,
            scope=self.scope,
            step="scrape",
            message=f"Scraping website: {self.url}",
            progress=10,
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
            f"⚠️ VECTOR STORE DISABLED - Skipping {len(chunks)} chunks",
            extra={"workspace_id": str(self.workspace_id), "operation_id": self.operation_id},
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
        )

        if not content.strip():
            await emit_step_success(
                operation_id=self.operation_id,
                scope=self.scope,
                step="brand_voice",
                message="No content available for brand voice extraction",
                payload=None,
                progress=90,
            )
            return None

        trimmed_content = content[: self._MAX_BRAND_VOICE_CHARS]
        
        # Log scraped content for debugging
        logger.info(
            "=" * 80,
            extra={"workspace_id": str(self.workspace_id), "operation_id": self.operation_id}
        )
        logger.info(
            "📄 SCRAPED CONTENT (for LLM analysis)",
            extra={"workspace_id": str(self.workspace_id), "operation_id": self.operation_id}
        )
        logger.info(
            "=" * 80,
            extra={"workspace_id": str(self.workspace_id), "operation_id": self.operation_id}
        )
        logger.info(
            f"Content length: {len(trimmed_content)} characters (trimmed from {len(content)})",
            extra={"workspace_id": str(self.workspace_id), "operation_id": self.operation_id}
        )
        logger.info(
            "-" * 80,
            extra={"workspace_id": str(self.workspace_id), "operation_id": self.operation_id}
        )
        logger.info(
            trimmed_content,
            extra={"workspace_id": str(self.workspace_id), "operation_id": self.operation_id}
        )
        logger.info(
            "=" * 80,
            extra={"workspace_id": str(self.workspace_id), "operation_id": self.operation_id}
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
            )
            return None

        await emit_step_success(
            operation_id=self.operation_id,
            scope=self.scope,
            step="brand_voice",
            message="Brand voice extracted successfully",
            payload=brand_voice_schema.model_dump(),
            progress=90,
        )
        return brand_voice_schema

    async def _persist_brand_voice(
        self,
        brand_voice_schema: Optional[BrandSchema],
    ) -> Optional[BrandVoice]:
        """Persist brand voice data and extract personas to separate table."""
        if brand_voice_schema is None:
            return None

        data = brand_voice_schema.model_dump()
        
        # Extract personas before processing brand voice
        personas_data = data.pop("personas", [])
        
        try:
            result = await self.db.execute(
                select(BrandVoice).where(BrandVoice.workspace_id == self.workspace_id)
            )
            existing = result.scalar_one_or_none() if result else None

            if existing:
                existing.about = data.get("about")
                existing.customer_profile = data.get("customer_profile")
                existing.selling_position = data.get("selling_position")
                existing.target_audience = data.get("target_audience") or []
                existing.brand_voice = data.get("brand_voice") or []
                existing.competitors = data.get("competitors") or []
                existing.content_strategy = data.get("content_strategy") or []
                brand_voice_record = existing
            else:
                brand_voice_record = BrandVoice(
                    workspace_id=self.workspace_id,
                    about=data.get("about"),
                    customer_profile=data.get("customer_profile"),
                    selling_position=data.get("selling_position"),
                    target_audience=data.get("target_audience") or [],
                    brand_voice=data.get("brand_voice") or [],
                    competitors=data.get("competitors") or [],
                    content_strategy=data.get("content_pillar") or [],
                )
                self.db.add(brand_voice_record)

            await self.db.flush()
            
            # Persist personas separately
            await self._persist_personas(personas_data)
            
            await self.db.commit()
            return brand_voice_record

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

    async def _persist_personas(self, personas_data: list[dict]) -> None:
        """Save extracted personas to persona table."""
        if not personas_data:
            logger.info(
                "No personas to persist",
                extra={"workspace_id": str(self.workspace_id), "operation_id": self.operation_id}
            )
            return
        
        # Log extracted personas for review
        logger.info(
            "=" * 80,
            extra={"workspace_id": str(self.workspace_id), "operation_id": self.operation_id}
        )
        logger.info(
            f"📊 EXTRACTED PERSONAS ({len(personas_data)} total)",
            extra={"workspace_id": str(self.workspace_id), "operation_id": self.operation_id}
        )
        logger.info(
            "=" * 80,
            extra={"workspace_id": str(self.workspace_id), "operation_id": self.operation_id}
        )
        
        for idx, persona_data in enumerate(personas_data, 1):
            logger.info(
                f"\n👤 PERSONA #{idx}: {persona_data.get('name', 'Unnamed')}",
                extra={"workspace_id": str(self.workspace_id), "operation_id": self.operation_id}
            )
            logger.info(
                f"  📝 Description: {persona_data.get('description', 'N/A')}",
                extra={"workspace_id": str(self.workspace_id), "operation_id": self.operation_id}
            )
            
            # E-E-A-T Professional Fields
            if persona_data.get('full_name'):
                logger.info(
                    f"  👔 Full Name: {persona_data.get('full_name')}",
                    extra={"workspace_id": str(self.workspace_id), "operation_id": self.operation_id}
                )
            if persona_data.get('professional_title'):
                logger.info(
                    f"  💼 Title: {persona_data.get('professional_title')}",
                    extra={"workspace_id": str(self.workspace_id), "operation_id": self.operation_id}
                )
            if persona_data.get('areas_of_expertise'):
                logger.info(
                    f"  🎓 Expertise: {persona_data.get('areas_of_expertise')}",
                    extra={"workspace_id": str(self.workspace_id), "operation_id": self.operation_id}
                )
            if persona_data.get('tone_of_voice'):
                logger.info(
                    f"  🗣️  Tone: {persona_data.get('tone_of_voice')}",
                    extra={"workspace_id": str(self.workspace_id), "operation_id": self.operation_id}
                )
            if persona_data.get('bio'):
                logger.info(
                    f"  📖 Bio: {persona_data.get('bio')[:100]}...",
                    extra={"workspace_id": str(self.workspace_id), "operation_id": self.operation_id}
                )
            if persona_data.get('linkedin_url'):
                logger.info(
                    f"  🔗 LinkedIn: {persona_data.get('linkedin_url')}",
                    extra={"workspace_id": str(self.workspace_id), "operation_id": self.operation_id}
                )
            
            # User Persona Fields (if any)
            if persona_data.get('demographics'):
                logger.info(
                    f"  👥 Demographics: {persona_data.get('demographics')}",
                    extra={"workspace_id": str(self.workspace_id), "operation_id": self.operation_id}
                )
            if persona_data.get('pain_points'):
                logger.info(
                    f"  ⚠️  Pain Points: {persona_data.get('pain_points')}",
                    extra={"workspace_id": str(self.workspace_id), "operation_id": self.operation_id}
                )
            if persona_data.get('goals'):
                logger.info(
                    f"  🎯 Goals: {persona_data.get('goals')}",
                    extra={"workspace_id": str(self.workspace_id), "operation_id": self.operation_id}
                )
            if persona_data.get('behaviors'):
                logger.info(
                    f"  🔄 Behaviors: {persona_data.get('behaviors')}",
                    extra={"workspace_id": str(self.workspace_id), "operation_id": self.operation_id}
                )
            
            logger.info(
                "-" * 80,
                extra={"workspace_id": str(self.workspace_id), "operation_id": self.operation_id}
            )
        

        # Use a savepoint to make the delete-then-insert atomic.
        # If insertion fails, the savepoint rollback also undoes the deletion,
        # preserving the original personas.
        async with self.db.begin_nested():
            # Delete existing personas for this workspace
            await self.db.execute(
                delete(Persona).where(Persona.workspace_id == self.workspace_id)
            )

            # Insert new personas with ALL fields
            for persona_data in personas_data:
                persona = Persona(
                    workspace_id=self.workspace_id,
                    # Basic fields
                    name=persona_data.get("name"),
                    description=persona_data.get("description"),
                    # E-E-A-T Professional fields
                    full_name=persona_data.get("full_name"),
                    professional_title=persona_data.get("professional_title"),
                    areas_of_expertise=persona_data.get("areas_of_expertise"),
                    tone_of_voice=persona_data.get("tone_of_voice"),
                    bio=persona_data.get("bio"),
                    linkedin_url=persona_data.get("linkedin_url"),
                    # User persona fields
                    demographics=persona_data.get("demographics"),
                    pain_points=persona_data.get("pain_points"),
                    goals=persona_data.get("goals"),
                    behaviors=persona_data.get("behaviors"),
                )
                self.db.add(persona)

            # Flush within the savepoint to detect constraint violations
            await self.db.flush()

        logger.info(
            f"Persisted {len(personas_data)} persona(s)",
            extra={"workspace_id": str(self.workspace_id), "operation_id": self.operation_id}
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
            
            system_prompt = """You are an expert at analyzing website content and extracting brand information and personas.

IMPORTANT INSTRUCTIONS FOR PERSONAS:
- Extract AUTHOR/EXPERT personas (real people who create content, run the business, or are mentioned as experts)
- DO NOT extract customer/user personas or target audience segments
- Look for:
  * Blog authors and their names
  * Company founders or leadership team members
  * Experts, consultants, or professionals mentioned on the site
  * Team members with "About" or "Team" pages
  * People with professional credentials or expertise
  
EXAMPLES OF CORRECT PERSONAS:
✓ "Dr. Sarah Mitchell" - Board-Certified Dermatologist
✓ "Mobheen Abdullah" - Founder & CEO
✓ "John Smith" - Senior Software Engineer & Tech Blogger

EXAMPLES OF INCORRECT PERSONAS (DO NOT EXTRACT):
✗ "Eco-Conscious Shopper" - this is a customer, not an author
✗ "Tech-Savvy Professional" - this is a target audience, not a real person
✗ "Busy Executive" - this is a user persona, not an expert/author

For personas, fill in:
- name: The person's actual name (e.g., "Mobheen Abdullah")
- full_name: Their complete professional name
- professional_title: Their job title or credentials
- areas_of_expertise: What they specialize in
- tone_of_voice: How they communicate
- bio: Their professional background
- linkedin_url: If available on the website

If no real people/authors are found on the website, return an empty personas list.

Now analyze the following website content and extract brand information:"""
            
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=content)
            ]
            
            return await structured.ainvoke(messages)

        return await _invoke_model()


async def run_workspace_pipeline(
    *,
    db: AsyncSession,
    operation_id: str,
    workspace_id: UUID,
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
        url=url,
        scraper=scraper,
        vector_uploader=vector_uploader,
        brand_voice_generator=brand_voice_generator,
    )
    await pipeline.run()

from src.flow.model.llm_manager import load_model
from src.utils.logger import logger
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from src.api.database.async_database import get_async_db as get_db
from src.utils.helper import web_page_scraper
from src.utils.vector_store import add_to_vector_store
from src.api.models.knowledge_models.knowledge_model import Website, BrandVoice
from src.api.models.knowledge_models.persona_model import Persona
from pydantic import HttpUrl
from src.api.schema.knowledge_schema import BrandSchema


async def _persist_personas_with_savepoint(
    db: AsyncSession,
    workspace_id,
    personas_data,
):
    """
    TASK-096 compliant persona replacement.

    Uses SAVEPOINT so that:
    - If any persona insert fails → deletion is rolled back
    - Original personas remain intact
    """

    if not personas_data:
        return

    async with db.begin_nested():
        # Delete existing personas
        await db.execute(
            delete(Persona).where(Persona.workspace_id == workspace_id)
        )

        # Insert new personas
        for persona_data in personas_data:
            persona = Persona(
                workspace_id=workspace_id,
                name=persona_data.name,
                description=persona_data.description,
                # E-E-A-T professional fields
                full_name=persona_data.full_name,
                professional_title=persona_data.professional_title,
                areas_of_expertise=persona_data.areas_of_expertise,
                tone_of_voice=persona_data.tone_of_voice,
                bio=persona_data.bio,
                linkedin_url=persona_data.linkedin_url,
                # User persona fields
                demographics=persona_data.demographics,
                pain_points=persona_data.pain_points,
                goals=persona_data.goals,
                behaviors=persona_data.behaviors,
            )
            db.add(persona)

        # Force DB validation inside SAVEPOINT
        await db.flush()

    logger.info(f"Persisted {len(personas_data)} persona(s) atomically")


async def scrape_web_content(url: HttpUrl, website_id: str):
    """
    Refactored knowledge task fulfilling TASK-096:

    ✔ Single atomic transaction
    ✔ Persona replacement protected by SAVEPOINT
    ✔ Proper AsyncSession usage
    ✔ No partial commits
    """

    logger.info(f"Scraping web content from {url}...")

    async for db in get_db():  # Proper async session handling
        try:
            # -----------------------------
            # Load website
            # -----------------------------
            website: Website | None = await db.get(Website, website_id)

            if not website:
                logger.error(f"Website with id {website_id} not found")
                return {"status": 404, "message": "Website not found"}

            # -----------------------------
            # Crawl webpage
            # -----------------------------
            chunks, results = await web_page_scraper(url)
            result = results[0]

            if not result.success:
                logger.error(f"Scraping failed for {result.url}: {result.error_message}")
                website.status = "error"
                await db.commit()
                return {
                    "status": 400,
                    "message": f"Scraping failed: {result.error_message}",
                }

            content = result.markdown

            # -----------------------------
            # Vector store (external side-effect)
            # -----------------------------
            logger.info(f"Adding chunks for {result.url} to vector store")
            add_to_vector_store(
                blog_context=chunks,
                workspace_id=str(website.workspace_id),
                knowledge_id=str(website_id),
                knowledge_type="web",
            )

            # -----------------------------
            # Extract brand voice via LLM
            # -----------------------------
            logger.info("Extracting brand voice from content...")
            model = load_model()
            structured_model = model.with_structured_output(BrandSchema)
            brand_data = await structured_model.ainvoke(content)

            # -----------------------------
            # BEGIN SINGLE ATOMIC TRANSACTION
            # -----------------------------
            async with db.begin():
                # Update website stats
                website.char_count = str(len(content))
                website.word_count = str(len(content.split()))
                website.status = "completed"

                # Insert brand voice
                brand_voice = BrandVoice(
                    workspace_id=website.workspace_id,
                    about=brand_data.about,
                    customer_profile=brand_data.customer_profile,
                    selling_position=brand_data.selling_position,
                    target_audience=brand_data.target_audience,
                    brand_voice=brand_data.brand_voice,
                    competitors=brand_data.competitors,
                    content_strategy=brand_data.content_strategy,
                )
                db.add(brand_voice)

                # Flush so FK/ID ready before personas
                await db.flush()

                # TASK-096 persona persistence
                await _persist_personas_with_savepoint(
                    db=db,
                    workspace_id=website.workspace_id,
                    personas_data=brand_data.personas,
                )

            # -----------------------------
            # Fetch personas for response
            # -----------------------------
            result_personas = await db.execute(
                select(Persona).where(Persona.workspace_id == website.workspace_id)
            )
            all_personas = result_personas.scalars().all()

            logger.info(f"Scraping + persistence completed for {result.url}")

            return {
                "status": 200,
                "message": f"Scraping completed successfully for {result.url}.",
                "brand_voice": brand_voice.to_dict() if brand_voice else None,
                "personas": [p.to_dict() for p in all_personas] if all_personas else [],
            }

        except Exception as e:  # noqa: BLE001
            logger.exception(f"Error during scraping: {str(e)}")

            # Best-effort failure status update
            try:
                website.status = "error"  # type: ignore
                await db.commit()
            except Exception:
                await db.rollback()

            return {"status": 500, "message": "Internal server error"}
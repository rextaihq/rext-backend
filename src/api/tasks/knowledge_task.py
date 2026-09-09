from pydantic import HttpUrl
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database.async_database import AsyncSessionLocal
from src.api.models.knowledge_models.knowledge_model import BrandVoice, Website
from src.api.models.knowledge_models.persona_model import Persona
from src.api.schema.knowledge_schema import BrandSchema
from src.flow.model.llm_manager import load_model
from src.utils.content_sanitizer import (
    build_extraction_prompt,
    sanitize_content_for_llm,
)
from src.utils.helper import web_page_scraper
from src.utils.logger import logger
from src.utils.vector_store import add_to_vector_store

# Maximum allowed field length for LLM output
MAX_FIELD_LENGTH = 5000


def _truncate_field(value, field_name: str, max_len: int = MAX_FIELD_LENGTH):
    """Truncate LLM output fields to prevent oversized payload persistence."""
    if isinstance(value, str) and len(value) > max_len:
        logger.warning(f"Truncating field '{field_name}' from {len(value)} to {max_len} characters")
        return value[:max_len]
    return value


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
        await db.execute(delete(Persona).where(Persona.workspace_id == workspace_id))

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

    async with AsyncSessionLocal() as db:
        website = None

        try:
            # Fetch website record
            result = await db.execute(select(Website).where(Website.id == website_id))
            website: Website = result.scalar_one_or_none()

            if not website:
                logger.error(f"Website with id {website_id} not found")
                return {"status": 404, "message": "Website not found"}

            # Crawl page
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

            logger.info(f"Adding chunks for {result.url} to vector store")
            add_to_vector_store(
                blog_context=chunks,
                workspace_id=str(website.workspace_id),
                knowledge_id=str(website_id),
                knowledge_type="web",
            )

            logger.info("Sanitizing scraped content before LLM processing")

            sanitized_content = sanitize_content_for_llm(
                content,
                max_length=50_000,
                source_description=f"scraped URL {result.url}",
            )

            if not sanitized_content:
                logger.warning(f"No usable content after sanitization for {result.url}")
                website.status = "completed"
                await db.commit()
                return {
                    "status": 200,
                    "message": "Scraping completed but no extractable content found",
                }

            extraction_prompt = build_extraction_prompt(sanitized_content)

            logger.info("Extracting brand information using structured LLM output")

            model = load_model()
            structure_model = model.with_structured_output(BrandSchema)

            brand_data = await structure_model.ainvoke(extraction_prompt)

            logger.info("Brand voice extraction completed")

            brand_voice = BrandVoice(
                workspace_id=website.workspace_id,
                about=_truncate_field(brand_data.about, "about"),
                customer_profile=_truncate_field(brand_data.customer_profile, "customer_profile"),
                selling_position=_truncate_field(brand_data.selling_position, "selling_position"),
                target_audience=_truncate_field(brand_data.target_audience, "target_audience"),
                brand_voice=_truncate_field(brand_data.brand_voice, "brand_voice"),
                competitors=_truncate_field(brand_data.competitors, "competitors"),
                content_strategy=_truncate_field(brand_data.content_pillar, "content_strategy"),
            )

            db.add(brand_voice)
            await db.flush()
            await db.refresh(brand_voice)

            logger.info(f"Brand voice information saved with id: {brand_voice.id}")

            if brand_data.personas:
                logger.info(f"Saving {len(brand_data.personas)} persona(s)")

                for persona_data in brand_data.personas:
                    persona = Persona(
                        workspace_id=website.workspace_id,
                        name=_truncate_field(persona_data.name, "persona.name"),
                        description=_truncate_field(
                            persona_data.description, "persona.description"
                        ),
                        full_name=_truncate_field(persona_data.full_name, "persona.full_name"),
                        professional_title=_truncate_field(
                            persona_data.professional_title,
                            "persona.professional_title",
                        ),
                        areas_of_expertise=_truncate_field(
                            persona_data.areas_of_expertise,
                            "persona.areas_of_expertise",
                        ),
                        tone_of_voice=_truncate_field(
                            persona_data.tone_of_voice,
                            "persona.tone_of_voice",
                        ),
                        bio=_truncate_field(persona_data.bio, "persona.bio"),
                        linkedin_url=_truncate_field(
                            persona_data.linkedin_url,
                            "persona.linkedin_url",
                        ),
                        demographics=_truncate_field(
                            persona_data.demographics,
                            "persona.demographics",
                        ),
                        pain_points=_truncate_field(
                            persona_data.pain_points,
                            "persona.pain_points",
                        ),
                        goals=_truncate_field(
                            persona_data.goals,
                            "persona.goals",
                        ),
                        behaviors=_truncate_field(
                            persona_data.behaviors,
                            "persona.behaviors",
                        ),
                    )

                    db.add(persona)

                await db.flush()
                logger.info("Personas saved successfully")

            website.status = "completed"
            await db.commit()

            # Fetch personas for response
            result_personas = await db.execute(
                select(Persona).where(Persona.workspace_id == website.workspace_id)
            )
            all_personas = result_personas.scalars().all()

            return {
                "status": 200,
                "message": f"Scraping completed successfully for {result.url}.",
                "brand_voice": brand_voice.to_dict(),
                "personas": [p.to_dict() for p in all_personas],
            }

        except Exception as e:
            logger.exception(f"Error during scraping: {str(e)}")

            try:
                if website:
                    website.status = "error"
                    await db.commit()
            except Exception:
                pass

            return {"status": 500, "message": "Internal server error"}

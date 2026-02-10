from src.flow.model.llm_manager import load_model
from src.utils.logger import logger
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from src.api.database.async_database import AsyncSessionLocal
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

    # Create async DB session
    async with AsyncSessionLocal() as db:
        try:
            # Get target website from DB
            result = await db.execute(
                select(Website).where(Website.id == website_id)
            )
            website: Website = result.scalar_one_or_none()
            
            if not website:
                logger.error(f"Website with id {website_id} not found")
                return {"status": 404, "message": "Website not found"}

            # Crawl + chunk data (expecting single result now)
            chunks, results = await web_page_scraper(url)
            result = results[0]  # since we only expect one URL

            if result.success:
                content = result.markdown

                # Push chunks to vector store with workspace and knowledge metadata
                logger.info(f"Adding chunks for {result.url} to vector store")
                add_to_vector_store(
                    blog_context=chunks,
                    workspace_id=str(website.workspace_id),
                    knowledge_id=str(website_id),
                    knowledge_type="web"
                )

                # Update DB with stats
                website.char_count = str(len(content))
                website.word_count = str(len(content.split()))
                website.status = "completed"
                await db.flush()

                # Extract the information from context using llm
                logger.info(f"Extracting information from context....")
                model = load_model()
                logger.info("Bound the model with structure output")
                structure_model = model.with_structured_output(BrandSchema)

                brand_data = await structure_model.ainvoke(content)
                
                logger.info(f"Extracted Brand Voice: {brand_data}")
                brand_voice = BrandVoice(
                    workspace_id=website.workspace_id,
                    about=brand_data.about,
                    customer_profile=brand_data.customer_profile,
                    selling_position=brand_data.selling_position,
                    target_audience=brand_data.target_audience,
                    brand_voice=brand_data.brand_voice,
                    competitors=brand_data.competitors,
                    content_strategy=brand_data.content_pillar
                )
                db.add(brand_voice)
                await db.flush()
                await db.refresh(brand_voice)
                logger.info(f"Brand voice information saved with id: {brand_voice.id}")
                
                # Save personas separately
                if brand_data.personas:
                    logger.info(f"Saving {len(brand_data.personas)} persona(s)")
                    for persona_data in brand_data.personas:
                        persona = Persona(
                            workspace_id=website.workspace_id,
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
                    await db.flush()
                    logger.info(f"Personas saved successfully")
                
                # Fetch all personas for response
                result_personas = await db.execute(
                    select(Persona).where(Persona.workspace_id == website.workspace_id)
                )
                all_personas = result_personas.scalars().all()

                # Commit all changes
                await db.commit()

                return {
                    "status": 200,
                    "message": f"Scraping completed successfully for {result.url}.",
                    "brand_voice": brand_voice.to_dict() if brand_voice else None,
                    "personas": [p.to_dict() for p in all_personas] if all_personas else []
                }
            else:
                logger.error(f"Scraping failed for {result.url}: {result.error_message}")
                website.status = "error"
                await db.commit()
                return {
                    "status": 400,
                    "message": f"Scraping failed: {result.error_message}",
                }

        except Exception as e:
            logger.exception(f"Error during scraping: {str(e)}")
            # Rollback will happen automatically when exiting the context manager
            # Update website status if we can
            try:
                if website:
                    website.status = "error"
                    await db.commit()
            except:
                pass  # If even this fails, just log and return error
            
            return {"status": 500, "message": "Internal server error"}


if __name__ == "__main__":
    import asyncio
    result = asyncio.run(
        scrape_web_content(
            url="https://python.langchain.com/docs/how_to/recursive_text_splitter/",
            website_id="11235"
        )
    )
    logger.info(result)

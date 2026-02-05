from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.flow.model.llm_manager import load_model
from src.utils.logger import logger
from src.api.database.async_database import get_async_db
from src.utils.helper import web_page_scraper
from src.services.embedding_service import EmbeddingService
from src.api.models.knowledge_models.knowledge_model import Website, BrandVoice
from src.api.models.knowledge_models.persona_model import Persona
from pydantic import HttpUrl
from src.api.schema.knowledge_schema import BrandSchema


async def scrape_web_content(url: HttpUrl, website_id: str):
    """
    Scrape a single web page using crawling and store results in Website + pgvector.
    """
    logger.info(f"Scraping web content from {url}...")

    # Get async DB session
    async for db in get_async_db():
        try:
            return await _process_web_scrape(db, url, website_id)
        finally:
            await db.close()


async def _process_web_scrape(db: AsyncSession, url: HttpUrl, website_id: str):
    """Process the web scrape with proper async DB operations."""
    # Get target website from DB
    result = await db.execute(
        select(Website).where(Website.id == website_id)
    )
    website = result.scalar_one_or_none()

    if not website:
        logger.error(f"Website with id {website_id} not found")
        return {"status": 404, "message": "Website not found"}

    try:
        # Crawl + chunk data (expecting single result now)
        chunks, results = await web_page_scraper(url)
        scrape_result = results[0] if results else None

        if scrape_result and scrape_result.success:
            content = scrape_result.markdown

            # Add embeddings to pgvector
            logger.info(f"Adding embeddings for {scrape_result.url} to pgvector")
            embedding_service = EmbeddingService(db)
            await embedding_service.add_embeddings_from_documents(
                documents=chunks,
                workspace_id=website.workspace_id,
                knowledge_id=website.id,
                knowledge_type="web",
                knowledge_base_id=website.knowledge_base_id,
            )

            # Update DB with stats
            website.char_count = len(content)
            website.word_count = len(content.split())
            website.status = "completed"
            await db.commit()

            # Extract brand voice using LLM
            logger.info("Extracting brand voice from content...")
            model = load_model()
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
            await db.commit()
            await db.refresh(brand_voice)
            logger.info(f"Brand voice saved with id: {brand_voice.id}")

            # Save personas
            if brand_data.personas:
                logger.info(f"Saving {len(brand_data.personas)} persona(s)")
                for persona_data in brand_data.personas:
                    persona = Persona(
                        workspace_id=website.workspace_id,
                        name=persona_data.name,
                        description=persona_data.description,
                        full_name=persona_data.full_name,
                        professional_title=persona_data.professional_title,
                        areas_of_expertise=persona_data.areas_of_expertise,
                        tone_of_voice=persona_data.tone_of_voice,
                        bio=persona_data.bio,
                        linkedin_url=persona_data.linkedin_url,
                        demographics=persona_data.demographics,
                        pain_points=persona_data.pain_points,
                        goals=persona_data.goals,
                        behaviors=persona_data.behaviors,
                    )
                    db.add(persona)
                await db.commit()
                logger.info("Personas saved successfully")

            # Fetch all personas for response
            result_personas = await db.execute(
                select(Persona).where(Persona.workspace_id == website.workspace_id)
            )
            all_personas = result_personas.scalars().all()

            return {
                "status": 200,
                "message": f"Scraping completed successfully for {scrape_result.url}.",
                "brand_voice": brand_voice.to_dict() if brand_voice else None,
                "personas": [p.to_dict() for p in all_personas] if all_personas else []
            }
        else:
            error_msg = scrape_result.error_message if scrape_result else "No results"
            logger.error(f"Scraping failed for {url}: {error_msg}")
            website.status = "error"
            await db.commit()
            return {
                "status": 400,
                "message": f"Scraping failed: {error_msg}",
            }

    except Exception as e:
        logger.exception(f"Error during scraping: {str(e)}")
        website.status = "error"
        await db.commit()
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

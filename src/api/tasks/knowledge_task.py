from src.model.model import load_model
from src.utils.logger import logger
from sqlalchemy.orm import Session
from src.api.database.database import get_db
from src.utils.helper import web_page_scraper
from src.nodes.vectorStore.buildVectorStore import build_vector_store
from src.api.models.knowledge_model import Website,BrandVoice
from pydantic import HttpUrl
from src.api.schema.knowledge_schema import BrandSchema


async def scrape_web_content(url: HttpUrl, website_id: str):
    """
    Scrape a single web page using crawling and store results in Website + vector store.
    """
    logger.info(f"Scraping web content from {url}...")

    # DB session
    db_gen = get_db()
    db: Session = next(db_gen)

    # Get target website from DB
    website: Website = db.query(Website).filter(Website.id == website_id).first()
    if not website:
        logger.error(f"Website with id {website_id} not found")
        return {"status": 404, "message": "Website not found"}

    try:
        # Crawl + chunk data (expecting single result now)
        chunks, results = await web_page_scraper(url)  # pass as list to keep crawler happy
        result = results[0]  # since we only expect one URL

        if result.success:
            content = result.markdown

            # Push chunks to vector store
            logger.info(f"Adding chunks for {result.url} to vector store")
            build_vector_store(blog_context=chunks)

            # Update DB with stats
            website.char_count = str(len(content))
            website.word_count = str(len(content.split()))
            website.status = "completed"
            db.commit()

            # extract the information from context using llm
            logger.info(f"Extracting information form context....")
            model = load_model()
            logger.info("Bound the model with structure output")
            structure_model = model.with_structured_output(BrandSchema)

            brand_data = structure_model.invoke(content)
            
            logger.info(f"Extracted Brand Voice: {brand_data}")
            brand_voice = BrandVoice(
                knowledge_id=website.knowledge_id,
                about=brand_data.about,
                customer_profile=brand_data.customer_profile,
                selling_position=brand_data.selling_position,
                target_audience=brand_data.target_audience,
                brand_voice=brand_data.brand_voice,
                competitors=brand_data.competitors,
                content_strategy=brand_data.content_pillar
            )
            db.add(brand_voice)
            db.commit()
            db.refresh(brand_voice)
            logger.info(f"Brand voice information saved with id: {brand_voice.id}")
            return {
                "status": 200,
                "message": f"Scraping completed successfully for {result.url}.",
            }
        else:
            logger.error(f"Scraping failed for {result.url}: {result.error_message}")
            website.status = "error"
            db.commit()
            return {
                "status": 400,
                "message": f"Scraping failed: {result.error_message}",
            }

    except Exception as e:
        logger.exception(f"Error during scraping: {str(e)}")
        website.status = "error"
        db.commit()
        return {"status": 500, "message": "Internal server error"}

import asyncio

if __name__ == "__main__":
    result = asyncio.run(
        scrape_web_content(
            url="https://python.langchain.com/docs/how_to/recursive_text_splitter/",
            website_id="11235"
        )
    )
    print(result)

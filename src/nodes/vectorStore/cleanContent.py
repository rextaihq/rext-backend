from src.states.State import AgentState
from src.utils.helper import clean_blog_content_with_urls
# from src.utils.helper import splitting_text
from src.utils.splitter import split_data

from src.api.lib.logger import auto_logger

logger = auto_logger()

async def clean_context(state:AgentState):
    # Retrieve state
    logger.info("Text Cleaning Node Start....")
    selected_articles = state.get("selected_articles", [])

    reference_urls = []
    context = []

    for i in range(len(selected_articles)):

        logger.info(f"📝 Processing: {selected_articles[i]['title']}")

        # ✅ Extract context for blog generation
        raw_reference_content = selected_articles[i]["Raw Blog Content"]

        clean_text,urls = clean_blog_content_with_urls(raw_reference_content)

        # Split the text into chunks
        chunks_text = split_data(clean_text)
        reference_urls.extend(urls)  # flatten
        context.extend(chunks_text)

    logger.info("Text Cleaning Node End....")
    logger.info(f"Total context: {len(context)}")
    return {
        'context':context,
        "reference_url":reference_urls
    }
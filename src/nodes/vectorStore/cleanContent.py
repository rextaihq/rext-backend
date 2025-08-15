from src.states.State import AgentState
from src.utils.helper import clean_blog_content_with_urls
from src.utils.helper import Splitting

async def clean_context(state:AgentState):
    # Retrieve state
    print("Text Cleaning Node Start....")
    selected_articles = state.get("selected_articles", [])

    reference_urls = []
    blog_context = []

    for i in range(len(selected_articles)):

        print(f"📝 Processing: {selected_articles[i]['title']}")

        # ✅ Extract context for blog generation
        raw_reference_content = selected_articles[i]["Raw Blog Content"]

        clean_text,urls = clean_blog_content_with_urls(raw_reference_content)

        # Split the text into chunks
        chunks_text = Splitting(clean_text)
        reference_urls.extend(urls)  # flatten
        blog_context.extend(chunks_text)

    print("Text Cleaning Node End....")
    return {
        'blog_content':blog_context,
        "reference_url":reference_urls
    }
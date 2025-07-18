from src.states.State import AgentState
from src.model.model import StructuredModel
from src.prompts.prompt import create_relevance_score_prompt

def score_relevance(state: AgentState) -> dict:
    """
    Evaluate how relevant each article topic is to the WordPress ecosystem.

    Loops through all articles and assigns a score using an LLM.

    Returns:
        dict:
            - article_rating (List[List[int]]): Nested list of scores (1–10) for each article.
            - article_weight (List[List[int]]): Nested list of fixed weight = 2 for each article.
    """
    try:
        print("Scoring relevance to WordPress...")

        ratings = []
        weights = []

        for article in state.get("combine_articles", []):
            title = article.get("title", "")
            description = article.get("summary", "")
            blog_data = article.get("scraped_markdown", "")

            if not title and not blog_data:
                continue  # Skip empty articles

            prompt_template = create_relevance_score_prompt()

            prompt = prompt_template.format_messages(
                topic=title,
                description=description,
                raw_blog=blog_data
            )

            # Call the LLM
            model_with_parser = StructuredModel()
            response = model_with_parser.invoke(prompt)

            ratings.append(response.rating)
            weights.append(response.weight)

        return {
            'relevance_rating': ratings,
            'relevance_weight': weights
        }

    except Exception as e:
        print("Relevance scoring failed:", e)
        state["error"] = str(e)
        return str(e)

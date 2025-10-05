from src.states.State import AgentState
from src.model.model import structure_model
from src.prompts.prompt import create_relevance_score_prompt

from src.api.lib.logger import auto_logger

logger = auto_logger()

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
        logger.info("Scoring relevance to WordPress...")

        ratings = []
        weights = []

        for article in state.get("filter_articles", []):
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
            model_with_parser = structure_model()
            response = model_with_parser.invoke(prompt)

            ratings.append(response.rating)
            weights.append(response.weight)

        return {
            "evaluations":{
            'relevance_rating': ratings,
            'relevance_weight': weights
        }
        }

    except Exception as e:
        logger.info("Relevance scoring failed:", e)
        return {"error": [{"Relevance scoring failed": str(e)}]}

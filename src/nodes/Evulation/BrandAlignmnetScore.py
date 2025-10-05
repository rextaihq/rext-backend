from src.states.State import AgentState
from src.model.model import structure_model
from src.prompts.prompt import create_brand_alignment_score_prompt

from src.api.lib.logger import auto_logger

logger = auto_logger()

def score_brand_alignment(state: AgentState) -> dict:
    """
    Evaluate how well each topic aligns with your brand’s goals and content style.

    Loops through all articles and evaluates alignment using an LLM.

    Returns:
        dict:
            - article_rating (List[List[int]]): Nested list of ratings (1–10).
            - article_weight (List[List[int]]): Nested list of fixed weights (1).
    """
    try:
        logger.info("Scoring brand alignment...")

        ratings = []
        weights = []

        for article in state.get("filter_articles", []):
            title = article.get("title", "")
            description = article.get("summary", "")
            blog_data = article.get("scraped_markdown", "")

            if not title and not blog_data:
                continue  

            prompt_template = create_brand_alignment_score_prompt()
            prompt = prompt_template.format_messages(
                topic=title,
                description=description,
                raw_blog=blog_data
            )

            # Model call
            model_with_parser = structure_model()
            response = model_with_parser.invoke(prompt)

            ratings.append(response.rating)
            weights.append(response.weight)

        return {
            "evaluations":{
            'brand_rating': ratings,
            'brand_weight': weights
        }
        }

    except Exception as e:
        logger.info("Brand alignment scoring failed:", e)
        return {"error": [{"Brand alignment scoring failed": str(e)}]}
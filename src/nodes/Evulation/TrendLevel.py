from src.states.State import AgentState
from src.model.model import StructuredModel
from src.prompts.prompt import create_trend_level_prompt

def score_trend_level(state: AgentState) -> dict:
    """
    Assess how popular or trending each topic is currently in the WordPress or tech community.

    Loops through all articles and assigns a score using an LLM.

    Returns:
        dict:
            - article_rating (List[List[int]]): Nested list of ratings (1–10).
            - article_weight (List[List[int]]): Nested list of fixed weight = 2.
    """
    try:
        print("Scoring trend level...")

        ratings = []
        weights = []

        for article in state.get("filter_articles", []):
            title = article.get("title", "")
            description = article.get("summary", "")
            blog_data = article.get("scraped_markdown", "")

            if not title and not blog_data:
                continue  # Skip empty entries

            prompt_template = create_trend_level_prompt()

            prompt = prompt_template.format_messages(
                topic=title,
                description=description,
                raw_blog=blog_data
            )

            # Pass the prompt to LLM
            model_with_parser = StructuredModel()
            response = model_with_parser.invoke(prompt)

            ratings.append(response.rating)
            weights.append(response.weight)

        return {
            "evaluations":{
            'trend_rating': ratings,
            'trend_weight': weights
        }
        }

    except Exception as e:
        print("Trend level scoring failed:", e)
        return {"error": [{"Trend level scoring failed": str(e)}]}

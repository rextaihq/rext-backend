from src.states.State import AgentState
from src.model.model import StructuredModel
from src.prompts.prompt import create_controversy_score_prompt

def score_controversy(state: AgentState) -> dict:
    """
    Evaluate whether each topic is currently controversial or debated within the WordPress ecosystem.

    Loops through all articles and scores each using an LLM.

    Returns:
        dict:
            - article_rating (List[List[int]]): Nested list of controversy scores (1–10).
            - article_weight (List[List[int]]): Nested list with fixed weight = 1.
    """
    try:
        print("Scoring controversy...")

        ratings = []
        weights = []

        for article in state.get("combine_articles", []):
            title = article.get("title", "")
            description = article.get("summary", "")
            blog_data = article.get("scraped_markdown", "")

            if not title and not blog_data:
                continue  # Skip empty entries


            prompt_template = create_controversy_score_prompt()


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
            'controversy_rating': ratings,
            'controversy_weight': weights
        }

    except Exception as e:
        print("Controversy scoring failed:", e)
        state["error"] = str(e)
        return str(e)

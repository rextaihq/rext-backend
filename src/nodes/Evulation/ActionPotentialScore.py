from src.states.State import AgentState
from src.model.model import StructuredModel
from src.prompts.prompt import create_actionable_potential_score_prompt

def score_actionable_potential(state: AgentState) -> dict:
    """
    Evaluate whether each topic can lead to actionable content like tutorials or guides.

    Loops through all articles and scores each using an LLM.

    Returns:
        dict:
            - article_rating (List[List[int]]): A nested list of ratings.
            - article_weight (List[List[int]]): A nested list of weights.
    """
    try:
        print("Scoring actionable content potential...")

        ratings = []
        weights = []

        for article in state.get("combine_articles", []):
            title = article.get("title", "")
            description = article.get("summary", "")
            blog_data = article.get("scraped_markdown", "")

            if not title and not blog_data:
                continue  

            # Define prompt
            prompt_template =  create_actionable_potential_score_prompt()


            prompt = prompt_template.format_messages(
                topic=title,
                description=description,
                raw_blog=blog_data
            )

            # Call the model
            model_with_parser = StructuredModel()
            response = model_with_parser.invoke(prompt)

            ratings.append(response.rating)
            weights.append(response.weight)

        return {
            'actionable_rating': ratings,
            'actionable_weight': weights
        }

    except Exception as e:
        print("Actionable content scoring failed:", e)
        state["error"] = str(e)
        return str(e)

from src.states.State import AgentState
from src.model.model import structure_model
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

        for article in state.get("filter_articles", []):
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
            model_with_parser = structure_model()
            response = model_with_parser.invoke(prompt)

            ratings.append(response.rating)
            weights.append(response.weight)

        return {
            "evaluations":{
            'actionable_rating': ratings,
            'actionable_weight': weights
        }
        }

    except Exception as e:
        print("Actionable content scoring failed:", e)
        return {"error": [{"Actionable content scoring failed": str(e)}]}

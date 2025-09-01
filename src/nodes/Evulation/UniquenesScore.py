from src.states.State import AgentState
from src.model.model import structure_model
from src.prompts.prompt import create_uniqueness_score_prompt

def score_uniqueness(state: AgentState) -> dict:
    """
    Measure how unique or uncommon each topic is compared to typical WordPress content.

    This function loops through all articles in the `combine_articles` list and scores each
    using an LLM. It appends the result to the state's `article_rating` and `article_weight`.

    Returns:
        dict:
            - article_rating (List[List[int]]): Nested list of ratings (per article).
            - article_weight (List[List[int]]): Nested list of fixed weight = 1 (per article).
    """
    try:
        print("Scoring uniqueness...")

        ratings = []
        weights = []

        for article in state.get("filter_articles", []):
            title = article.get("title", "")
            description = article.get("summary", "")
            blog_data = article.get("scraped_markdown", "")

            if not title and not blog_data:
                continue  # Skip empty articles

            prompt_template = create_uniqueness_score_prompt()


            prompt = prompt_template.format_messages(
                topic=title,
                description=description,
                raw_blog=blog_data
            )

            # Call LLM model with parser
            model_with_parser = structure_model()

            response = model_with_parser.invoke(prompt)

            ratings.append(response.rating)  
            weights.append(response.weight)

        return {
            "evaluations":{
            'uniqueness_rating': ratings,
            'uniqueness_weight': weights
        }
            }

    except Exception as e:
        print("Uniqueness scoring failed:", e)
        return {"error": [{"Uniqueness scoring failed": str(e)}]}

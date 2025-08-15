from src.states.State import AgentState
from src.model.model import StructuredModel
from src.prompts.prompt import create_reader_interest_score_prompt

def score_reader_interest(state: AgentState) -> dict:
    """
    Estimate how interesting each topic might be to the average WordPress reader.

    Loops through all articles and evaluates using an LLM.

    Returns:
        dict:
            - article_rating (List[List[int]]): Nested list of ratings (1–10).
            - article_weight (List[List[int]]): Nested list of fixed weights (1).
    """
    try:
        print("Scoring reader interest...")

        ratings = []
        weights = []

        for article in state.get("filter_articles", []):
            title = article.get("title", "")
            description = article.get("summary", "")
            blog_data = article.get("scraped_markdown", "")

            if not title and not blog_data:
                continue  # skip invalid articles

            # Define the prompt
            prompt_template = create_reader_interest_score_prompt()

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
            "evaluations":{
            'reader_rating': ratings,
            'reader_weight': weights
        }
        }


    except Exception as e:
        print("Reader interest scoring failed:", e)
        return {"error": [{"Reader interest scoring failed": str(e)}]}

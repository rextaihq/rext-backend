from src.states.State import AgentState
from src.model.model import StructuredModel
from src.prompts.prompt import score_seo_potential_prompt

def score_seo_potential(state: AgentState) -> dict:
    """
    Evaluate the SEO potential of each topic based on keyword relevance and searchability.

    Loops through all articles and scores each using an LLM.

    Returns:
        dict:
            - article_rating (List[List[int]]): A nested list of ratings.
            - article_weight (List[List[int]]): A nested list of weights.
    """
    try:
        print("Scoring SEO potential...")

        ratings = []
        weights = []

        for article in state.get("filter_articles", []):
            title = article.get('title', '')
            description = article.get('summary', '')
            blog_data = article.get('scraped_markdown', '')

            if not title and not blog_data:
                continue  

            prompt_template = score_seo_potential_prompt()
            
            prompt = prompt_template.format_messages(
                topic=title,
                description=description,
                raw_blog=blog_data
            )

            # Pass the prompt to model
            model_with_parser = StructuredModel()
            response = model_with_parser.invoke(prompt)

            ratings.append(response.rating)
            weights.append(response.weight)

        return {
            "evaluations":{
            'seo_rating': ratings,
            'seo_weight': weights
        }
        }

    except Exception as e:
        print("SEO scoring failed:", e)
        return {"error": [{"SEO scoring failed": str(e)}]}

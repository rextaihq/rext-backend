from langgraph.types import interrupt
from src.states.State import AgentState
import pandas as pd

from src.api.lib.logger import auto_logger

logger = auto_logger()

def topic_selection(state: AgentState) ->AgentState:
        logger.info("Human In Loop...")
        # Extract combined article data
        articles = state.get('filter_articles', [])
        if not articles:
            raise ValueError("No articles found in state['combine_articles'].")

        # Convert to DataFrame
        df = pd.DataFrame(articles)

        # Show top 10 articles by total_score
        df_sorted = df.sort_values(by='total_score', ascending=False).reset_index(drop=True)
        top_df = df_sorted.head(10)

        # Display title + total_score to the user
        message = "Select up to 3 articles to keep :\n\n"
        for i, row in top_df.iterrows():
            message += f"{i}. {row['title']} \n"

        message += "\nEnter your selection as comma-separated indexes (e.g., 0,2,5):"

        # Interrupt and wait for user input
        response = interrupt({
            "name":"TopicSelection",
            "value":message
        })
        # Assume response contains: "Title 1, Title 2, Title 3"
        selected_titles = [t.strip() for t in response.split(',')]

        # Filter the DataFrame based on these titles
        selected_articles = df_sorted[df_sorted["title"].isin(selected_titles)]

        return {
            "selected_articles": selected_articles.to_dict(orient="records")
        }
from src.states.State import AgentState
import pandas as pd
import numpy as np

# Adding Evulation Results
def re_ranking(state: AgentState) -> AgentState:
    """
    Combine the original article data with all evaluation scores.

    Returns:
        dict: Updated state with `evaluated_articles` (DataFrame serialized as a list of dicts).
    """
    try:
        # Extract combined article data
        combine_data = state.get("combine_articles", [])
        if not combine_data:
            raise ValueError("No articles found in state['combine_articles'].")

        num_articles = len(combine_data)

        # get all the rating and weight, ensuring consistent shape
        relevance_rating = np.array(state.get("relevance_rating", [0] * num_articles))
        trend_rating = np.array(state.get("trend_rating", [0] * num_articles))
        controversy_rating = np.array(state.get("controversy_rating", [0] * num_articles))
        uniqueness_rating = np.array(state.get("uniqueness_rating", [0] * num_articles))
        reader_rating = np.array(state.get("reader_rating", [0] * num_articles))
        brand_rating = np.array(state.get("brand_rating", [0] * num_articles))
        actionable_rating = np.array(state.get("actionable_rating", [0] * num_articles))
        seo_rating = np.array(state.get("seo_rating", [0] * num_articles))


        # get all the weights, ensuring consistent shape and default to 1 if not present
        relevance_weight = np.array(state.get("relevance_weight", [1] * num_articles))
        trend_weight = np.array(state.get("trend_weight", [1] * num_articles))
        controversy_weight = np.array(state.get("controversy_weight", [1] * num_articles))
        uniqueness_weight = np.array(state.get("uniqueness_weight", [1] * num_articles))
        reader_weight = np.array(state.get("reader_weight", [1] * num_articles))
        brand_weight = np.array(state.get("brand_weight", [1] * num_articles))
        actionable_weight = np.array(state.get("actionable_weight", [1] * num_articles))
        seo_weight = np.array(state.get("seo_weight", [1] * num_articles))

        # now calculte the sum index wise
        total_rating = (relevance_rating +
                        trend_rating +
                        controversy_rating +
                        uniqueness_rating +
                        reader_rating +
                        brand_rating +
                        actionable_rating +
                        seo_rating)

        total_weight = (relevance_weight +
                        trend_weight +
                        controversy_weight +
                        uniqueness_weight +
                        reader_weight +
                        brand_weight +
                        actionable_weight +
                        seo_weight)

        state['total_rating'] = total_rating.tolist()
        state['total_weight'] = total_weight.tolist()
        
        # add the totalrating and weigh back into articles
        article = state['combine_articles']
        for i in range(len(article)):
            article[i]['rating'] = state['total_rating'][i]
            article[i]['weight'] = state['total_weight'][i]

            # add a total score
            article[i]['total_score'] = state['total_rating'][i] * state['total_weight'][i]

        # Sort in-place using pandas
        df = pd.DataFrame(combine_data)
        
        df_sorted = df.sort_values(by='total_score', ascending=False)
        df.to_csv('full_blog.csv', index=False)
        # Update state['combine_articles'] with sorted data
        state['combine_articles'] = df_sorted.to_dict(orient='records')

        return state


    except Exception as e:
        state["error"] = str(e)
        return state
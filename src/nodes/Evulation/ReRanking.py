from src.states.State import AgentState
import pandas as pd
import numpy as np

from src.api.lib.logger import auto_logger

logger = auto_logger()

# Adding Evulation Results
def re_ranking(state: AgentState) -> AgentState:
    """
    Combine the original article data with all evaluation scores.

    Returns:
        dict: Updated state with `evaluated_articles` (DataFrame serialized as a list of dicts).
    """
    try:
        filter_data = state.get("filter_articles", [])
        evulaion_data = state.get("evaluations", {})

        if not filter_data:
            raise ValueError("No articles found in state['filter_articles'].")

        num_articles = len(filter_data)

        logger.info("getting Rating and weights")

        # Get lists of ratings and weights, providing defaults if a category is missing
        relevance_rating = np.array(evulaion_data.get("relevance_rating", [0] * num_articles))
        trend_rating = np.array(evulaion_data.get("trend_rating", [0] * num_articles))
        controversy_rating = np.array(evulaion_data.get("controversy_rating", [0] * num_articles))
        uniqueness_rating = np.array(evulaion_data.get("uniqueness_rating", [0] * num_articles))
        reader_rating = np.array(evulaion_data.get("reader_rating", [0] * num_articles))
        brand_rating = np.array(evulaion_data.get("brand_rating", [0] * num_articles))
        actionable_rating = np.array(evulaion_data.get("actionable_rating", [0] * num_articles))
        seo_rating = np.array(evulaion_data.get("seo_rating", [0] * num_articles))

        relevance_weight = np.array(evulaion_data.get("relevance_weight", [1] * num_articles))
        trend_weight = np.array(evulaion_data.get("trend_weight", [1] * num_articles))
        controversy_weight = np.array(evulaion_data.get("controversy_weight", [1] * num_articles))
        uniqueness_weight = np.array(evulaion_data.get("uniqueness_weight", [1] * num_articles))
        reader_weight = np.array(evulaion_data.get("reader_weight", [1] * num_articles))
        brand_weight = np.array(evulaion_data.get("brand_weight", [1] * num_articles))
        actionable_weight = np.array(evulaion_data.get("actionable_weight", [1] * num_articles))
        seo_weight = np.array(evulaion_data.get("seo_weight", [1] * num_articles))

        logger.info("Calculating Totals")
        # Ensure all arrays have the same length before summing
        min_len = min(len(relevance_rating), len(trend_rating), len(controversy_rating), len(uniqueness_rating),
                      len(reader_rating), len(brand_rating), len(actionable_rating), len(seo_rating),
                      len(relevance_weight), len(trend_weight), len(controversy_weight), len(uniqueness_weight),
                      len(reader_weight), len(brand_weight), len(actionable_weight), len(seo_weight))

        # Trim arrays to the minimum length
        relevance_rating = relevance_rating[:min_len]
        trend_rating = trend_rating[:min_len]
        controversy_rating = controversy_rating[:min_len]
        uniqueness_rating = uniqueness_rating[:min_len]
        reader_rating = reader_rating[:min_len]
        brand_rating = brand_rating[:min_len]
        actionable_rating = actionable_rating[:min_len]
        seo_rating = seo_rating[:min_len]

        relevance_weight = relevance_weight[:min_len]
        trend_weight = trend_weight[:min_len]
        controversy_weight = controversy_weight[:min_len]
        uniqueness_weight = uniqueness_weight[:min_len]
        reader_weight = reader_weight[:min_len]
        brand_weight = brand_weight[:min_len]
        actionable_weight = actionable_weight[:min_len]
        seo_weight = seo_weight[:min_len]


        # Totals
        total_rating = (
            relevance_rating + trend_rating + controversy_rating + uniqueness_rating +
            reader_rating + brand_rating + actionable_rating + seo_rating
        )
        total_weight = (
            relevance_weight + trend_weight + controversy_weight + uniqueness_weight +
            reader_weight + brand_weight + actionable_weight + seo_weight
        )

        logger.info("Total Ratting: ",total_rating)
        logger.info("Total Weight: ",total_weight)


        # Attach scores to each article
        # Ensure we only process up to min_len articles
        for i in range(min_len):
            logger.info("Adding Score: ",i)
            filter_data[i]['rating'] = int(total_rating[i])
            filter_data[i]['weight'] = int(total_weight[i])
            filter_data[i]['total_score'] = int(total_rating[i] * total_weight[i])

        # Remove articles that did not get fully scored
        filtered_scored_articles = filter_data[:min_len]


        # Sort by total_score
        df = pd.DataFrame(filtered_scored_articles)
        df_sorted = df.sort_values(by='total_score', ascending=False)
        
        df.to_csv('full_blog.csv', index=False)
        
        return {
            "filter_articles": df_sorted.to_dict(orient='records')
        }

    except Exception as e:
        return {"error": [{"AddEvulationResult failed": str(e)}]}
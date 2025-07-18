from src.states.State import AgentState

# Combine both articles
def merge_articles(state:AgentState)->AgentState:
    """
    MergeArticles

    Combines the articles from both
    the GNewsArticles and WordpressArticles
    functions into a single list.

    Returns:
        List[dict]: A list of combined articles.

    Example:
        combined_articles = CombineArticles(latest_articles, wordpress_articles)
        for article in combined_articles:
            print(article['title'], article['link'])

    """
    print("Combining articles...")
    combined_articles = state['articles'] + state['wordpress_articles']
    state['combine_articles'] = combined_articles
    print(f"Combined {len(combined_articles)} articles.")

    return state
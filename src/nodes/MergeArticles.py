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

    articles = state.get('articles', [])
    wordpress_articles = state.get('wordpress_articles', [])

    combined_articles = articles + wordpress_articles
    state['combine_articles'] = combined_articles

    print(f"Combined {len(combined_articles)} articles.")

    return {
        'combine_articles': combined_articles
    }
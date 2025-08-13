from src.states.State import AgentState
from sentence_transformers import util
from src.model.model import load_embedder
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

    print("Combining articles...")

    articles = state['articles']
    wordpress_articles = state['wordpress_articles']
    combined_articles = articles + wordpress_articles

    print(f"Total articles before filtering: {len(combined_articles)}")

    config = state.get('config', {})
    keywords = config.keyword
    similarity_threshold = 0.3

    if not combined_articles:
        state['combine_articles'] = []
        print("No articles to combine.")
        return state

    # Embed keywords and combined article titles + summaries
    keyword_embeddings = load_embedder().encode(keywords, convert_to_tensor=True)
    article_texts = [f"{a.get('title', '')} {a.get('summary', '')}" for a in combined_articles]

    print(article_texts)
    article_embeddings = load_embedder().encode(article_texts, convert_to_tensor=True)

    similarities = util.cos_sim(article_embeddings, keyword_embeddings)

    filtered_articles = []
    for idx, article in enumerate(combined_articles):
        max_sim, max_idx = similarities[idx].max(dim=0)
        max_sim = max_sim.item()
        matched_keyword = keywords[max_idx]

        if max_sim >= similarity_threshold:
            article['matched_keyword'] = matched_keyword
            article['similarity'] = max_sim
            filtered_articles.append(article)

    print(f"Articles after filtering: {len(filtered_articles)}")
    
    return {
        "combine_articles":filtered_articles
    }

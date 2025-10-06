from src.states.State import AgentState
from src.model.model import title_refine_model

from src.api.lib.logger import auto_logger

logger = auto_logger()
# query refine node
def title_rewriter(state:AgentState):
    """
    Query refine
    """
    try:
        logger.info("Query Refiner....")
        selected_articles = state['selected_articles']

        for article in selected_articles:
            title = article['title']
            logger.info("Title: ",title)

            prompt = f"""You are a helpful assistant your task is to refine the title but refine the title in this way donot loss the context of original title maintain the context of original title.
            Original title: {title}
            """
            refine_title = title_refine_model().invoke(prompt)

            logger.info("Query Refiner: ",refine_title)

            article["refine_title"] = refine_title if isinstance(refine_title, str) else str(refine_title)

        return state
    except Exception as e:
        logger.info(str(e))
        return [{
            "error":str(e)
        }]
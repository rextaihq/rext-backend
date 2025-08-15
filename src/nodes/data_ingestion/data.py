from src.nodes.data_ingestion.GNewsArticles import gnews_articles
from src.nodes.data_ingestion.WordpressArticles import wordpress_articles
from src.nodes.data_ingestion.FilterArticles import filter_articles
from src.nodes.Scrapper.Scraper import scrape_full_content
from langchain_core.runnables import RunnableLambda
from langgraph.types import CachePolicy
from src.states.State import AgentState
from langgraph.graph import StateGraph,START, END
from src.states.State import URLCONFIF

def get_data() -> RunnableLambda[AgentState, AgentState]:

    data_gathering = StateGraph(AgentState)

    # ========================= Data Gathering Nodes
    data_gathering.add_node(
        "GetLocal Articles",
        RunnableLambda(gnews_articles).with_config({
            "run_name": "Fetch Local Articles",
            "metadata": {"stage": "data_collection", "source": "local"}
        })
    )

    data_gathering.add_node(
        "GetWordpress Articles",
        RunnableLambda(wordpress_articles).with_config({
            "run_name": "Fetch WordPress Articles",
            "metadata": {"stage": "data_collection", "source": "wordpress"}
        })
    )

    data_gathering.add_node(
        "FilterArticles",
        RunnableLambda(filter_articles).with_config({
            "run_name": "Combine Articles",
            "metadata": {"stage": "preprocessing"}
        })
    )

    data_gathering.add_node(
        "ScrapeFullContent",
        RunnableLambda(scrape_full_content).with_config({
            "run_name": "Scrape Full Content",
            "metadata": {"stage": "preprocessing"}
        })
    )

    # Define the edges
    data_gathering.add_edge(START, "GetWordpress Articles")
    data_gathering.add_edge(START, "GetLocal Articles")
    data_gathering.add_edge("GetLocal Articles", "FilterArticles")
    data_gathering.add_edge("GetWordpress Articles", "FilterArticles")
    data_gathering.add_edge("FilterArticles", "ScrapeFullContent")
    data_gathering.add_edge("ScrapeFullContent",END)

    # compile the flow
    return data_gathering.compile()

if __name__ == "__main__":
    import uuid
    import asyncio

    config = {
        "configurable": {"thread_id": str(uuid.uuid1())},
    }
    my_config_instance = URLCONFIF(
        category="technology",
        language="en",
        country="us",
        WP_URL={
            "WPTavern": "https://wptavern.com/feed"
        },
        keyword = ['AI',"WordPress","DL","Machine Learning"],
        similarity_threshold=0.4
    )

    
    data_graph = get_data()
    # run the graph
    async def getting_data():
        result = await data_graph.ainvoke(
            input={"config":my_config_instance},
            config=config
        )
        return result

    data_result = asyncio.run(getting_data())
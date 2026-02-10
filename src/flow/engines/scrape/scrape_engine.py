from src.flow.states.rext import REXT
from langgraph.graph import StateGraph,START,END


def create_scrape_engine()-> StateGraph:
    from src.flow.engines.scrape.scrape_content import scrape_serp_content
    from src.flow.engines.scrape.store_content import store_scraped_content
    scrape_graph = StateGraph(REXT)

    #  add node
    scrape_graph.add_node("scrape_content",scrape_serp_content)
    scrape_graph.add_node("store_content", store_scraped_content)
    

    # add edges
    scrape_graph.add_edge(START,"scrape_content")
    # scrape_graph.add_edge("filter_relevant_content",END)
    scrape_graph.add_edge("scrape_content", "store_content")
    scrape_graph.add_edge("store_content",END)


    # compile the graph
    app = scrape_graph.compile()
    return app
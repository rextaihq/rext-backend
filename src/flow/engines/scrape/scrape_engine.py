from src.flow.states.wrext import WREXT
from langgraph.graph import StateGraph,START,END


def create_scrape_engine()-> StateGraph:
    from src.flow.engines.scrape.scrape_content import scrape_serp_content
    scrape_graph = StateGraph(WREXT)

    #  add node
    scrape_graph.add_node("scrape_content",scrape_serp_content)
    

    # add edges
    scrape_graph.add_edge(START,"scrape_content")
    # scrape_graph.add_edge("filter_relevant_content",END)
    scrape_graph.add_edge("scrape_content",END)


    # compile the graph
    app = scrape_graph.compile()
    return app
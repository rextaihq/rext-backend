
from src.nodes.vectorStore.buildVectorStore import build_vector_store
from src.nodes.vectorStore.cleanContent import clean_context
from src.states.State import AgentState
from langgraph.graph import StateGraph,START, END


def vector_store_building():
        
    vectore_graph  = StateGraph(AgentState)


    # add_node
    vectore_graph.add_node("CleanContext",clean_context)
    vectore_graph.add_node("build_vector_store",build_vector_store)

    # create edges
    vectore_graph.add_edge(START,"CleanContext")
    vectore_graph.add_edge("CleanContext","build_vector_store")
    vectore_graph.add_edge("build_vector_store",END)

    # compile
    return vectore_graph.compile()
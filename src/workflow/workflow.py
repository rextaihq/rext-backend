from src.nodes.Scrapper.GetRelevant import get_relevant_articles
from src.subgraphs.getSubgraph import get_subgraph
from src.nodes.data_ingestion.data import get_data
from src.states.State import AgentState
from langgraph.graph import StateGraph,START, END
from langchain_core.runnables import RunnableLambda
from src.nodes.Evulation.Evulate import re_ranked_data
from src.nodes.vectorStore.vectorGraph import vector_store_building
from src.nodes.generation.blogFlow import blog_generator


def CreateWorkflow()-> RunnableLambda[AgentState, AgentState]:
        """
        Main workflow function that orchestrates the entire scraping process.

        Returns:
            AgentState: The final state of the agent after all processing.
        """
    # try:
        # define the workflow
        workflow = StateGraph(AgentState)

        # --- Add Data Gathering Nodes ---
        workflow.add_node("Get Data",get_data())
        workflow.add_node("Evulation",re_ranked_data())
        workflow.add_node("WebSearch",get_subgraph())
        workflow.add_node("GetRelevant",get_relevant_articles)
        workflow.add_node("Building Vectore Store",vector_store_building())
        workflow.add_node("BlogGenertion",blog_generator)


        # ------- Connect the nodes
        workflow.add_edge(START,"Get Data")
        workflow.add_edge("Get Data",'Evulation')
        workflow.add_edge("Evulation",'WebSearch')
        workflow.add_edge("WebSearch",'GetRelevant')

        workflow.add_edge("GetRelevant",'Building Vectore Store')

        workflow.add_edge("Building Vectore Store",'BlogGenertion')
        
        return workflow
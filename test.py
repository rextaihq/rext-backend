from src.nodes.data_ingestion.FilterArticles import filter_articles
from src.nodes.data_ingestion.GNewsArticles import gnews_articles
from src.nodes.data_ingestion.WordpressArticles import wordpress_articles
from src.nodes.data_ingestion.data import get_data
from src.states.State import AgentState
from langgraph.graph import StateGraph,START, END
from langchain_core.runnables import RunnableLambda


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


        # ------- Connect the nodes
        workflow.add_edge(START,"Get Data")
        
        return workflow
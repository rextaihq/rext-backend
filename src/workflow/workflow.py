import asyncio
from src.nodes.data.GNewsArticles import gnews_articles
from src.nodes.data.WordpressArticles import wordpress_articles
from src.nodes.MergeArticles import merge_articles
from src.nodes.Scrapper.Scraper import scrape_full_content

from src.nodes.Evulation.RelevanceScore import score_relevance
from src.nodes.Evulation.TrendLevel import score_trend_level
from src.nodes.Evulation.ActionPotentialScore import score_actionable_potential
from src.nodes.Evulation.BrandAlignmnetScore import score_brand_alignment
from src.nodes.Evulation.ControversyScore import score_controversy
from src.nodes.Evulation.ReaderIntrestScore import score_reader_interest
from src.nodes.Evulation.UniquenesScore import score_uniqueness
from src.nodes.Evulation.SeoScore import score_seo_potential
from src.nodes.Evulation.ReRanking import re_ranking
from src.nodes.Interrupt.interrupt import TopicSelection
from src.nodes.Scrapper.GetRelevant import get_relevant_articles
from src.nodes.generation.outline_generation import outline_generator
from src.nodes.generation.blogGeneraion import blog_generation

from src.states.State import AgentState
from langgraph.graph import StateGraph,START, END
from langchain_core.runnables import RunnableLambda
from src.model.model import LoadModel, StructuredModel
from src.utils.helper import CreateCheckpointer
from langgraph.checkpoint.memory import MemorySaver

checkpointer = CreateCheckpointer()

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
        workflow.add_node("GNewsArticles",RunnableLambda(gnews_articles))
        workflow.add_node("WordpressArticles",RunnableLambda(wordpress_articles))
        workflow.add_node("MergeArticles",RunnableLambda(merge_articles))
        workflow.add_node("Scraper",RunnableLambda(scrape_full_content))
        workflow.add_node("RelevanceScore",RunnableLambda(score_relevance))
        workflow.add_node("TrendLevel",RunnableLambda(score_trend_level))
        workflow.add_node("ControversyScore",RunnableLambda(score_controversy))
        workflow.add_node("BrandAlignmentScore",RunnableLambda(score_brand_alignment))
        workflow.add_node("ReaderInterestScore",RunnableLambda(score_reader_interest))
        workflow.add_node("ActionPotentialScore",RunnableLambda(score_actionable_potential))
        workflow.add_node("UniquenessScore",RunnableLambda(score_uniqueness))
        workflow.add_node("SeoScore",RunnableLambda(score_seo_potential))
        workflow.add_node("ReRanking",RunnableLambda(re_ranking))
        workflow.add_node("TopicSelection",RunnableLambda(TopicSelection))
        workflow.add_node("GetRelevantArticles",RunnableLambda(get_relevant_articles))
        # generate outline
        workflow.add_node("OutineGeneration",RunnableLambda(outline_generator))
        # add human approval node
        workflow.add_node("BlogGeneration",RunnableLambda(blog_generation))
                



        # ------- Connect the nodes
        workflow.add_edge(START, "GNewsArticles")
        workflow.add_edge(START, "WordpressArticles")

        workflow.add_edge("GNewsArticles", "MergeArticles")
        workflow.add_edge("WordpressArticles", "MergeArticles")
        workflow.add_edge("MergeArticles", "Scraper")


        # --- Connect the evaluation node
        workflow.add_edge("Scraper", "RelevanceScore")
        workflow.add_edge("Scraper", "TrendLevel")
        workflow.add_edge("Scraper", "ControversyScore")
        workflow.add_edge("Scraper", "BrandAlignmentScore")
        workflow.add_edge("Scraper", "ReaderInterestScore")
        workflow.add_edge("Scraper", "ActionPotentialScore")
        workflow.add_edge("Scraper", "UniquenessScore")
        workflow.add_edge("Scraper", "SeoScore")    

        # --- Connect the re-ranking node
        workflow.add_edge("RelevanceScore", "ReRanking")
        workflow.add_edge("TrendLevel", "ReRanking")
        workflow.add_edge("ControversyScore", "ReRanking")
        workflow.add_edge("BrandAlignmentScore", "ReRanking")
        workflow.add_edge("ReaderInterestScore", "ReRanking")
        workflow.add_edge("ActionPotentialScore", "ReRanking")
        workflow.add_edge("UniquenessScore", "ReRanking")
        workflow.add_edge("SeoScore", "ReRanking")

        # Human in loop
        workflow.add_edge("ReRanking", "TopicSelection")
        workflow.add_edge("TopicSelection", "GetRelevantArticles")

        # draw b/w outline genration
        workflow.add_edge("GetRelevantArticles",'OutineGeneration')

        # Add conditional edge for looping
        workflow.add_conditional_edges(
            "OutineGeneration",
            lambda state: "continue" if state.get("current_approval_index", 0) < len(state.get("selected_articles", [])) else "done",
            {
                "continue": "OutineGeneration",
                "done": "BlogGeneration"
            }
        )

        # Compile the workflow into a runnable
        # checkpointer = CreateCheckpointer()
        runnable = workflow.compile(checkpointer=checkpointer)
        return runnable
    # except Exception as e:
    #     print(f"An error occurred while creating the workflow: {e}")
    #     return AgentState(error=str(e))
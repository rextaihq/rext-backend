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
from src.nodes.Interrupt.topicSelection import TopicSelection
from src.nodes.Interrupt.blogApproval import blog_approval
from src.nodes.Interrupt.outlineApproval import outline_approval
from src.nodes.Scrapper.GetRelevant import get_relevant_articles
from src.nodes.generation.outline_generation import outline_generator
from src.nodes.generation.blogGeneraion import blog_generation
from src.nodes.draft.draft_blog import draft_blog
from src.states.State import AgentState
from langgraph.graph import StateGraph,START, END
from langchain_core.runnables import RunnableLambda
# from src.utils.checkpoiner import checkpointer
from langgraph.checkpoint.memory import MemorySaver


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
        workflow.add_node("OutlineApproval",RunnableLambda(outline_approval))

        # add human approval node
        workflow.add_node("BlogGeneration",RunnableLambda(blog_generation))
        workflow.add_node("BlogApproval",RunnableLambda(blog_approval))

        # add draft blog node
        workflow.add_node("DraftBlog",RunnableLambda(draft_blog))



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

        # draw b/w outline generation
        workflow.add_edge("GetRelevantArticles",'OutineGeneration')
        workflow.add_edge("OutineGeneration", "OutlineApproval")

        # Add conditional edge for looping
        workflow.add_conditional_edges(
            "OutlineApproval",
            lambda state: "continue" if state.get("current_approval_index", 0) < len(state.get("selected_articles", [])) else "done",
            {
                "continue": "OutineGeneration",
                "done": 'BlogGeneration'
            }
        )

        # Add a conditional edge b/etween blog generation and draft blog
        workflow.add_edge("BlogGeneration",'BlogApproval')
        workflow.add_conditional_edges(
            "BlogApproval",
            lambda state: "continue" if state.get("current_blog_index", 0) < len(state.get("selected_articles", [])) else "done",
            {
                "continue": "BlogGeneration",
                "done": "DraftBlog"
            }
        )
        return workflow
        
        # if(checkpointer is not None):
        #     print("Checkpointer Setup Successfully")
        #     return workflow.compile(checkpointer=checkpointer)
        # else:
        #     print("Checkpointer is None, run without checkpointing")
        #     return workflow.compile()

from src.nodes.Evulation.ActionPotentialScore import score_actionable_potential
from src.nodes.Evulation.BrandAlignmnetScore import score_brand_alignment
from src.nodes.Evulation.ControversyScore import score_controversy
from src.nodes.Evulation.ReaderIntrestScore import score_reader_interest
from src.nodes.Evulation.RelevanceScore import score_relevance
from src.nodes.Evulation.ReRanking import re_ranking
from src.nodes.Evulation.SeoScore import score_seo_potential
from src.nodes.Evulation.TrendLevel import score_trend_level
from src.nodes.Evulation.UniquenesScore import score_uniqueness
from src.nodes.Interrupt.topicSelection import topic_selection
from langchain_core.runnables import RunnableLambda
from langgraph.graph import StateGraph,START, END
from src.states.State import AgentState



def re_ranked_data()-> RunnableLambda[AgentState, AgentState]:
    evulation = StateGraph(AgentState)
    # add nodes
    # Evaluation Nodes
    evulation.add_node("Relevance to WordPress", RunnableLambda(score_relevance).with_config({
        "run_name": "Relevance Scoring",
        "metadata": {"evaluation": "relevance"}
    }))

    evulation.add_node("Trend Level", RunnableLambda(score_trend_level).with_config({
        "run_name": "Trend Level Scoring",
        "metadata": {"evaluation": "trend_level"}
    }))

    evulation.add_node("Controversy", RunnableLambda(score_controversy).with_config({
        "run_name": "Controversy Scoring",
        "metadata": {"evaluation": "controversy"}
    }))

    evulation.add_node("Uniqueness", RunnableLambda(score_uniqueness).with_config({
        "run_name": "Uniqueness Scoring",
        "metadata": {"evaluation": "uniqueness"}
    }))

    evulation.add_node("Reader Interest", RunnableLambda(score_reader_interest).with_config({
        "run_name": "Reader Interest Scoring",
        "metadata": {"evaluation": "interest"}
    }))

    evulation.add_node("Brand Alignment", RunnableLambda(score_brand_alignment).with_config({
        "run_name": "Brand Alignment Scoring",
        "metadata": {"evaluation": "brand_alignment"}
    }))

    evulation.add_node("Actionable Potential", RunnableLambda(score_actionable_potential).with_config({
        "run_name": "Actionability Scoring",
        "metadata": {"evaluation": "actionability"}
    }))


    # Evaluation Result Aggregation
    evulation.add_node("Evulation Result", RunnableLambda(re_ranking).with_config({
        "run_name": "Add Evaluation Result",
        "metadata": {"stage": "evaluation_result"}
    }))

    evulation.add_node("SEO Potential", RunnableLambda(score_seo_potential).with_config({
    "run_name": "SEO Potential Scoring",
    "metadata": {"evaluation": "seo"}
    }))

    evulation.add_node("Topic Selection", RunnableLambda(topic_selection).with_config({
        "run_name": "Article Selection",
    }))


    # Define the edges
    # All scoring nodes run in parallel from the start of the evaluation graph
    evulation.add_edge(START, "Relevance to WordPress")
    evulation.add_edge(START, "Trend Level")
    evulation.add_edge(START, "Controversy")
    evulation.add_edge(START, "Uniqueness")
    evulation.add_edge(START, "Reader Interest")
    evulation.add_edge(START, "Brand Alignment")
    evulation.add_edge(START, "Actionable Potential")
    evulation.add_edge(START, "SEO Potential")

    # All scoring nodes transition to the Evulation Result node
    evulation.add_edge("Relevance to WordPress","Evulation Result")
    evulation.add_edge("Trend Level","Evulation Result")
    evulation.add_edge("Controversy","Evulation Result")
    evulation.add_edge("Uniqueness","Evulation Result")
    evulation.add_edge("Reader Interest","Evulation Result")
    evulation.add_edge("Brand Alignment","Evulation Result")
    evulation.add_edge("Actionable Potential","Evulation Result")
    evulation.add_edge("SEO Potential","Evulation Result")
    evulation.add_edge("Evulation Result","Topic Selection")




    # The Evulation Result node is the finish point of the evaluation graph
    evulation.set_finish_point("Topic Selection")
    return evulation.compile()
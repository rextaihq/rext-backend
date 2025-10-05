from langgraph.graph import StateGraph,START
# from langchain_core.runnables import RunnableLambda
from src.nodes.generation.titleRewriter import title_rewriter
from src.nodes.generation.getRelevnt import get_relevnt_doc
from src.nodes.generation.queryDecomposition import query_decomposition
from src.nodes.generation.queryExpansion import query_expansion
from src.nodes.generation.docReordering import reordering_doc
from src.nodes.generation.blogGeneraion import blog_generation
from src.nodes.Interrupt.blogApproval import blog_approval
from src.nodes.generation.parallarizm import continue_retrieval,continue_generation
from src.states.State import AgentState

from src.api.lib.logger import auto_logger

logger = auto_logger()


def blog_generator():
    builder = StateGraph(AgentState)

    builder.add_node("titleRewriter", title_rewriter)
    builder.add_node("GetRelevantDoc", get_relevnt_doc)
    builder.add_node("QueryExpansion", query_expansion)
    builder.add_node("QueryDecomposition", query_decomposition)
    builder.add_node("ReOrderingDocument", reordering_doc)
    builder.add_node("BlogGeneration", blog_generation)
    builder.add_node("BlogApproval", blog_approval)
    # builder.add_node("DraftBlog", DraftBlog,defer=True)

    # Edges
    builder.add_edge(START, "titleRewriter")
    builder.add_conditional_edges("titleRewriter", continue_retrieval, ["GetRelevantDoc", "QueryExpansion", "QueryDecomposition"])
    builder.add_edge("GetRelevantDoc", "ReOrderingDocument")
    builder.add_edge("QueryExpansion", "ReOrderingDocument")
    builder.add_edge("QueryDecomposition", "ReOrderingDocument")
    builder.add_conditional_edges("ReOrderingDocument", continue_generation, ['BlogGeneration'])


    # builder.add_edge("BlogApproval", "DraftBlog")
    # builder.add_edge("DraftBlog", END)
    # Compile
    return  builder.compile()

if __name__ == "__main__":
    # Dummy state to test workflow
    data = {
        "selected_articles": [
            {"title": "Rahul Bansal: Achieving Success in Enterprise WordPress"},
        ]
    }

    # # Build workflow
    # workflow = blog_generator()
    #
    # # Run the workflow with dummy input
    # result = workflow.invoke(data)
    #
    # print("\n=== Final State ===")
    # print(result)
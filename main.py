from src.workflow.workflow import CreateWorkflow
from src.states.State import URLCONFIF
import os
os.environ["TOKENIZERS_PARALLELISM"] = "false"

my_config_instance = URLCONFIF(
    category="technology",
    language="en",
    country="us",
    WP_URL={
        "WPTavern": "https://wptavern.com/feed",
        "UserFeed2": "https://wordpress.org/news/feed"
    }
)

workflow = CreateWorkflow()
graph = workflow.compile()


# import asyncio

# async def run_workflow():
#     await graph.ainvoke({
#         "config": my_config_instance.model_dump()  # use `model_dump()` instead of `dict()` (Pydantic v2)
#     })

# if __name__ == "__main__":
#     asyncio.run(run_workflow())
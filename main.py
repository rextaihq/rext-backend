import asyncio
import os
# from src.flow.flow import create_workflow
from src.flow.engines.wrext import create_wrext_engine

# workflow = create_workflow()
# graph = workflow.compile()

graph = create_wrext_engine()

result = asyncio.run(graph.ainvoke(
    {
        "serp_payload": {
            "query": "seo tools for beginners",
            "country": "us"
        }
    }
))

print(result)
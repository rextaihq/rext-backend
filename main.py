import asyncio
import os
from src.flow.engines.rext import create_rext_engine
graph = create_rext_engine()

result = asyncio.run(graph.ainvoke(
    {
        "serp_payload": {
            "query": "email marketing best practices",
            "country": "us",
            "user_id":"user-1234",
            "workspace_id":"workspace-1234"
        }
    }
))

# print(result["seo_result"]["keyword_difficulty"])

print(result["content"])

# import asyncio
# from langgraph.types import Command
# from langgraph.checkpoint.memory import MemorySaver

# # Ensure your engine is compiled with a checkpointer
# checkpointer = MemorySaver()
# graph = create_rext_engine()

# async def process_stream(stream):
#     async for path, mode, data in stream: # Fixed Unpacking
#         if mode == "debug":
#             if data.get("type") == "node":
#                 # path[0] if path else "root"
#                 print(f"[DEBUG] Node: {data.get('node')} (Path: {path})")

#         elif mode == "updates":
#             if "__interrupt__" in data:
#                 return {"type": "interrupt", "data": data["__interrupt__"][0]}
            
#             for node_name, node_data in data.items():
#                 print(f"--- {node_name} finished ---")

#         elif mode == "messages":
#             message_chunk, metadata = data
#             if metadata.get("langgraph_node") == "content_engine":
#                 print(message_chunk.content, end="", flush=True)

# async def main():
#     # Ensure this doesn't pass 'checkpointer' if the function doesn't support it
#     # graph = create_rext_engine() 
    
#     config = {"configurable": {"thread_id": "session_123"}}
#     input_data = {"serp_payload": {"query": "wordpress maintenance", "country": "us"}}

#     stream = graph.astream(
#         input_data, 
#         config=config, 
#         stream_mode=["updates", "messages", "debug"],
#         subgraphs=True
#     )
    
#     result = await process_stream(stream)
#     # ... handle resume logic ...

# if __name__ == "__main__":
#     asyncio.run(main())
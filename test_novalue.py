# src/flow/model/llm_manager.py (updated for Groq)

from langchain_groq import ChatGroq


def load_model():
    return ChatGroq(
        model="openai/gpt-oss-120b",  # Fastest option, or "mixtral-8x7b-32768"
        temperature=0.1,  # Low for factual research
        api_key="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",
    )


from langchain_community.tools import DuckDuckGoSearchRun
from langchain_core.messages import AIMessage, HumanMessage

# Your search tool (unchanged)
search = DuckDuckGoSearchRun()

# Load Groq model and bind tools (unchanged interface)
model = load_model()  # Now ChatGroq under the hood
model_with_tools = model.bind_tools([search])

# Your full research + generation flow (unchanged)
prompt = """Write a comprehensive, SEO-optimized blog post on "AI Automation for Business".

MANDATORY PROCESS:
1. Research key topics: benefits, stats, case studies, 2024 trends
2. For EVERY statistic/claim, use search tool to verify (e.g., "AI automation ROI statistics 2024")
3. Cite sources inline
4. Structure: H1 title, meta excerpt, H2 sections, bullets, FAQ, CTA
5. Keywords: AI automation for business, business AI automation benefits, etc.

Start researching now."""

messages = [HumanMessage(content=prompt)]
response = model_with_tools.invoke(messages)

print("Model response with tool calls:")
print(response)

# Tool execution loop (unchanged - handles multiple calls)
if response.tool_calls:
    tool_messages = []
    for tool_call in response.tool_calls:
        if tool_call["name"] == "duckduckgo_search":
            result = search.invoke(tool_call["args"]["query"])
            tool_messages.append(AIMessage(content=result, tool_call_id=tool_call["id"]))

    final_messages = messages + [response] + tool_messages
    blog_post = model_with_tools.invoke(final_messages)
    print("\nFinal blog post:")
    print(blog_post)

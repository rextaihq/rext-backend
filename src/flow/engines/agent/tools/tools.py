from langchain_core.messages import HumanMessage
from langchain_community.tools import DuckDuckGoSearchResults
from langchain_ollama import ChatOllama


llm = ChatOllama(model="gpt-oss:120b-cloud", temperature=0)

from langchain.agents import create_agent  # v1 API
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage



def get_tools():
    search = DuckDuckGoSearchResults(output_format="list")

    return [search]
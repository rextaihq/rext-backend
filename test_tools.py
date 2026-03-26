from langchain_core.messages import HumanMessage
from langchain_community.tools import DuckDuckGoSearchResults
import json

search = DuckDuckGoSearchResults(output_format="list")
print(json.dumps(search.run("LLM Rich"), indent=2))
import json

from langchain_community.tools import DuckDuckGoSearchResults

search = DuckDuckGoSearchResults(output_format="list")
print(json.dumps(search.run("LLM Rich"), indent=2))

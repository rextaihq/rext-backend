import pprint

from langchain_community.utilities import SearxSearchWrapper


search = SearxSearchWrapper(searx_host="http://127.0.0.1:8888/search")
results = search.results(
    "Large Language Model prompt",
    num_results=5,
    categories="science",
    time_range="year",
)
pprint.pp(results)

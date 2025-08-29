from src.states.State import URLCONFIF
from src.workflow.workflow import CreateWorkflow
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
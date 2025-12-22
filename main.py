# from src.flow.flow import create_workflow
from src.flow.engines.serp.serp_flow import get_serp_flow

# workflow = create_workflow()
# graph = workflow.compile()

graph = get_serp_flow()

from fastapi import APIRouter, HTTPException
from src.workflow.workflow import CreateWorkflow
from src.api.schema.schema import TopicSelectionSchema,WorkflowConfigSchema
from langgraph.types import Command
from src.utils.checkpoiner import init_checkpointer
import yaml
import uuid

router = APIRouter(
    prefix="/workflow",
    tags=["workflow"]
)

# ✅ Instantiate the LangGraph workflow once at startup
CONFIG_PATH = "config/config.yaml"

@router.get("/status")
def get_workflow_status():
    # ✅ Could be expanded to track graph health or queue status
    return {"status": "running"}


# se the workflow configuration
@router.post("/configure")
def configure_workflow(config_data: WorkflowConfigSchema):
    """
    Configure the workflow with user-defined parameters.
    Saves the configuration as a YAML file.
    """
    config = {
        "GNews": {
            "url": "https://gnews.io/api/v4/top-headlines",
            "category": config_data.category or "technology",
            "country": config_data.country or "pk",
            "language": config_data.language or "en"
        },
        "rss_sources": {}
    }

    if config_data.rss_sources:
        for feed in config_data.rss_sources:
            config["rss_sources"][feed.title] = str(feed.url)

    with open(CONFIG_PATH, 'w') as f:
        yaml.dump(config, f)

    return {
        "message": "✅ Workflow configured and saved successfully.",
        "config": config
    }


@router.post("/execute")
async def execute_workflow():
    try:
        checkpointer = await init_checkpointer()  # Ensure checkpointer is initialized
        if checkpointer is None:
            raise HTTPException(status_code=500, detail="Checkpointer initialization failed")
        
        print("Checkpointer initialized successfully")
        workflow  = CreateWorkflow()


        graph = workflow.compile(checkpointer=checkpointer)
        # ✅ Generate a unique thread ID for this execution
        thread_id = str(uuid.uuid4())  # uuid4 is more standard for random IDs

        config = {"configurable": {"thread_id": thread_id}}
        print("Running Workflow with thread ID:", thread_id)
        # ✅ Run the graph with empty initial state
        results = await graph.ainvoke({}, config)

        print("Run successfully;WW")
        # ✅ Check for interrupt result
        interrupt = results.get('__interrupt__')
        if interrupt and interrupt[0].value:
            return {
                "results": interrupt[0].value,
                "thread_id": thread_id
            }

        return {
            "results": results,
            "thread_id": thread_id
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Workflow failed: {str(e)}")



@router.post("/resume/{thread_id}")
async def resume_workflow(thread_id: str,topic_selection: TopicSelectionSchema):
    try:
        # used the  thread id for resume the  execution

        user_input = ",".join(topic_selection.topic) 

        config = {"configurable": {"thread_id": thread_id}}
        print("Resuming Workflow with thread ID:", thread_id, "and user input:", user_input)

        checkpointer = await init_checkpointer()  # Ensure checkpointer is initialized
        if checkpointer is None:
            raise HTTPException(status_code=500, detail="Checkpointer initialization failed")

        workflow  = CreateWorkflow()


        graph = workflow.compile(checkpointer=checkpointer)


        results = await graph.ainvoke(
            input=Command(resume=user_input),
            config=config
        )

        interrupt = results.get('__interrupt__')
        if interrupt and interrupt[0].value:
            return {
                "results": interrupt[0].value,
                "thread_id": thread_id
            }


        return {
            "results": results,
            "thread_id": thread_id
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
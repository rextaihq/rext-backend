from fastapi import APIRouter, HTTPException, Depends
from src.workflow.workflow import CreateWorkflow
from src.api.schema.configSchema import TopicSelectionSchema,WorkflowConfigSchema
from src.api.schema.workflowSchema import WorkflowSchema
from src.api.database.database import get_db
from sqlalchemy.orm import Session
from src.api.models.models import Workflow
from langgraph.types import Command
from fastapi import BackgroundTasks
from src.utils.checkpoiner import init_checkpointer
from src.api.backgroundTasks.workflowTask import execute_workflow_task
import yaml
import uuid

router = APIRouter(
    prefix="/workflow",
    tags=["workflow"]
)

# ✅ Instantiate the LangGraph workflow once at startup
CONFIG_PATH = "config/config.yaml"


@router.get("/status/{thread_id}")
def get_workflow_status(thread_id: str, db: Session = Depends(get_db)):
    # ✅ Could be expanded to track graph health or queue status
    try:
        workflow = db.query(Workflow).filter_by(thread_id=thread_id).first()
        if not workflow:
            raise HTTPException(status_code=404, detail="Workflow not found.")
        
        return {
            "id": workflow.id,
            "name": workflow.name,
            "description": workflow.description,
            "thread_id": workflow.thread_id,
            "status": workflow.status,
            "is_active": workflow.is_active
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching workflow status: {str(e)}")


# set the workflow configuration
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
async def execute_workflow(data: WorkflowSchema, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    try:
        checkpointer = await init_checkpointer()  # Ensure checkpointer is initialized
        if checkpointer is None:
            raise HTTPException(status_code=500, detail="Checkpointer initialization failed")
        
        # check if the workflow already exists
        existing_workflow = db.query(Workflow).filter_by(thread_id=data.thread_id).first()
        if existing_workflow:
            raise HTTPException(status_code=400, detail="Workflow with this thread_id already exists.")
        
        # create a new workflow entry in the database
        new_workflow = Workflow(
            thread_id=data.thread_id,
            name=data.name,
            description=data.description,
            is_active=data.is_active,
            status=data.status
        )

        db.add(new_workflow)
        db.commit()
        db.refresh(new_workflow)

        print("Checkpointer initialized successfully")
        workflow  = CreateWorkflow()

        graph = workflow.compile(checkpointer=checkpointer)
        thread_id = str(uuid.uuid4())  # Generate a unique thread ID

        background_tasks.add_task(execute_workflow_task, graph, thread_id)

        return {
            "status": new_workflow.status,
            "thread_id": new_workflow.thread_id,
            "message": "Workflow execution started in the background."
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
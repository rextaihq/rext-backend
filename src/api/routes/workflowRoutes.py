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
@router.get("/test")
def test_route():
    return {"message": "Workflow API is working!"}

@router.get("/get_all")
def get_all_workflows(db: Session = Depends(get_db)):
    """
    Endpoint to retrieve all workflows.
    """
    try:
        workflows = db.query(Workflow).all()
        return {"workflows": [workflow.__dict__ for workflow in workflows]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching workflows: {str(e)}")
    
    

@router.get("/status/{workflow_id}")
def get_workflow_status(workflow_id: str, db: Session = Depends(get_db)):
    # ✅ Could be expanded to track graph health or queue status
    try:

        workflow = db.query(Workflow).filter_by(id=workflow_id).first()
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



@router.post("/create")
async def execute_workflow(data: WorkflowSchema, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    try:
        checkpointer = await init_checkpointer()  # Ensure checkpointer is initialized
        if checkpointer is None:
            raise HTTPException(status_code=500, detail="Checkpointer initialization failed")
        
        # check if the workflow already exists
        existing_workflow = db.query(Workflow).filter_by(name=data.name).first()
        if existing_workflow:
            raise HTTPException(status_code=400, detail="Workflow with this name already exists.")

        print("Checkpointer initialized successfully")
        workflow  = CreateWorkflow()

        graph = workflow.compile(checkpointer=checkpointer)
        thread_id = str(uuid.uuid4())  # Generate a unique thread ID

        background_tasks.add_task(execute_workflow_task, graph, thread_id)

        # create a new workflow entry in the database
        new_workflow = Workflow(
            id=uuid.uuid4(),
            name=data.name,
            description=data.description,
            thread_id=thread_id,
            is_active=data.is_active,
            status=data.status
        )

        db.add(new_workflow)
        db.commit()
        db.refresh(new_workflow)


        return {
            "id": new_workflow.id,
            "name": new_workflow.name,
            "description": new_workflow.description,
            "is_active": new_workflow.is_active,
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
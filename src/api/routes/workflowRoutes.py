from fastapi import APIRouter, HTTPException
from src.workflow.workflow import CreateWorkflow
from src.api.schema.schema import TopicSelectionSchema
from langgraph.types import Command
import uuid

router = APIRouter(
    prefix="/workflow",
    tags=["workflow"]
)

# ✅ Instantiate the LangGraph workflow once at startup

@router.get("/status")
def get_workflow_status():
    # ✅ Could be expanded to track graph health or queue status
    return {"status": "running"}

@router.post("/execute")
async def execute_workflow():
    try:
        graph = CreateWorkflow()
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

        graph = CreateWorkflow()
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
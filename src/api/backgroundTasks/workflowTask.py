from fastapi import HTTPException
from src.api.database.database import get_db
from sqlalchemy.orm import Session

async def execute_workflow_task(graph ,thread_id=None):
    """
    Execute the workflow with the given checkpointer and workflow.
    """
    try:
        config = {"configurable": {"thread_id": thread_id}}
        print("Running Workflow with thread ID:", thread_id)
        # ✅ Run the graph with empty initial state
        results = await graph.ainvoke({}, config)

        print("Run successfully")
        # ✅ Check for interrupt result
        interrupt = results.get('__interrupt__')
        if interrupt and interrupt[0].value['name']== 'TopicSelection':
            # Handle TopicSelection interrupt
            return {
                "Topics": interrupt[0].value['value'],
                "thread_id": thread_id
            }

        # Handle other interrupts
        if interrupt and interrupt[0].value['name'] == 'OutlineApproval':
            # Handle OutlineApproval interrupt
            return {
                "Outline": interrupt[0].value['value'],
                "thread_id": thread_id
            }
        
        if interrupt and interrupt[0].value['name'] == 'BlogApproval':
            # Handle BlogApproval interrupt
            return {
                "Blog": interrupt[0].value['value'],
                "thread_id": thread_id
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Workflow execution failed: {str(e)}")
from src.flow.states.content_state import ContentState
from src.api.models.workspace_models.workspace_model import WorkspaceModel
from src.api.database.database import get_db
from src.flow.utils.progress_helper import update_node_progress
from langsmith import traceable, trace

@traceable(
    run_type="retriever",
    name="Fetch Workspace from Database",
    metadata={
        "description": "Retrieves workspace details by author_id from the SQLAlchemy database.",
        "inputs": ["workspace id"],
        "outputs": ["workspace detail"],
        "dependencies": ["SQLAlchemy", "WorkspaceModel"],
        "category": "database_retrieval"
    },
    tags=["Database", "Fetch User", "SQLAlchemy"],
    project_name="WREXT"
)
def fetch_workspace(state: ContentState):
    print("Fetching Workspace.....")
    payload = state.get("request_payload", {})

    # Update progress (15%)
    content_id = payload.get("content_id")
    if content_id:
        update_node_progress(content_id, "fetching_workspace")

    user_id = payload.get("author_id") or payload.get("user_id")
    workspace_id = payload.get("workspace_id")

    print("workspace id: ",workspace_id)
    print("User idL ",user_id)
    print("Paylaod: ",payload)
    if not user_id or not workspace_id:
        print("⚠️ Missing user_id or workspace_id in payload")
        return {
            "error": [{"node": "fetch_workspace", "message": "Missing user_id or workspace_id in payload"}]
        }

    db = next(get_db())
    try:
        # Query workspace - user can be owner OR member
        # Simple approach: just verify workspace exists
        # Access control is already handled by API layer before workflow starts
        workspace = (
            db.query(WorkspaceModel)
            .filter(WorkspaceModel.id == workspace_id)
            .first()
        )

        if not workspace:
            print(f"⚠️ Workspace {workspace_id} not found")
            return {
                "error": [{"node": "fetch_workspace", "message": f"Workspace {workspace_id} not found"}]
            }

        return {
            "workspace": {
                "id": str(workspace.id),
                "user_id": str(workspace.user_id),
                "name": workspace.name,
                "slug": workspace.slug,
                "url": workspace.url,
                "timezone": workspace.timezone,
                "created_at": workspace.created_at,
                "updated_at": workspace.updated_at
            }
        }

    except Exception as e:
        return {
            "error": [{"node": "fetch_workspace", "message": f"Unexpected error occurred: {str(e)}"}]
        }

    finally:
        db.close()
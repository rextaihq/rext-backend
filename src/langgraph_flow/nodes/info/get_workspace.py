from src.langgraph_flow.states.content_state import ContentState
from src.api.models.workspace_models.workspace_model import WorkspaceModel
from src.api.database.database import get_db
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
    user_id = payload.get("author_id") or payload.get("user_id")
    workspace_id = payload.get("workspace_id")

    print("workspace id: ",workspace_id)
    print("User idL ",user_id)
    
    if not user_id or not workspace_id:
        print("⚠️ Missing user_id or workspace_id in payload")
        return {
            "node": "fetch workspace",
            "error": f"workfpace not found",
            "workspace": None
        }

    db = next(get_db())
    try:
        workspace = (
            db.query(WorkspaceModel)
            .filter(
                WorkspaceModel.id == workspace_id,
                WorkspaceModel.user_id == user_id
            )
            .first()
        )

        if not workspace:
            print("⚠️ Workspace not found for this user")
            return {
            "node": "fetch workspace",
            "error": f"workfpace not found",
            "workspace": None
        }

        return {
            "workspace": {
                "id": str(workspace.id),
                "user_id": str(workspace.user_id),
                "name": workspace.name,
                "slug": workspace.slug,
                "description": workspace.description,
                "url": workspace.url,
                "created_at": workspace.created_at,
                "updated_at": workspace.updated_at
            }
        }

    except Exception as e:
        return {
            "node": "fetch_workspace",
            "error": f"Unexpected error occurred: {str(e)}",
            "workspace": None
        }

    finally:
        db.close()
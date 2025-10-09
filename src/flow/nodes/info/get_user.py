from src.flow.states.content_state import ContentState
from src.api.models.user_models.users import Users
from src.api.database.database import get_db
from langsmith import traceable, trace

@traceable(
    run_type="retriever",
    name="Fetch Topic from Database",
    metadata={
        "description": "Retrieves user details by author_id from the SQLAlchemy database.",
        "inputs": ["useer_id"],
        "outputs": ["user detail"],
        "dependencies": ["SQLAlchemy", "TopicsModel"],
        "category": "database_retrieval"
    },
    tags=["Database", "Fetch User", "SQLAlchemy"],
    project_name="WREXT"
)
def fetch_user(state: ContentState):
    print("Fetching User.....")
    payload = state.get("request_payload", {})
    # print("Payload: ",payload)
    user_id = payload.get("author_id")

    print("User id: ",user_id)
    if not user_id:
        print("⚠️ Missing author_id")
        return {
            "node": "fetch user",
            "error": f"User id {user_id} None",
            "workspace": None
        }

    db = next(get_db())
    try:
        user = db.query(Users).filter(Users.id == user_id).first()
        if not user:
            print("⚠️ User not found")
            return {
            "node": "fetch_user",
            "error": f"user {user_id} not found",
            "user": None
        }

        return {
            "user": {
                "id": str(user.id),
                "email": user.email,
                "username": user.username,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "display_name": user.display_name,
                "language": user.language,
                "timezone": user.timezone,
                "avatar_url": user.avatar_url,
                "status": user.status,
                "email_verified": user.email_verified,
                "created_at": user.created_at,
                "updated_at": user.updated_at
            }
        }

    except Exception as e:
        return {
            "node": "fetch_user",
            "error": f"Unexpected error occurred: {str(e)}",
            "user": None
        }
    
    finally:
        db.close()
from src.flow.states.content_state import ContentState
from src.api.models.topic_models.topic_models import TopicsModel
from src.api.database.database import get_db
from langsmith import traceable, trace

@traceable(
    run_type="retriever",
    name="Fetch Topic from Database",
    metadata={
        "description": "Retrieves topic details by topicId from the SQLAlchemy database.",
        "inputs": ["topicId"],
        "outputs": ["topics"],
        "dependencies": ["SQLAlchemy", "TopicsModel"],
        "category": "database_retrieval"
    },
    tags=["Database", "TopicFetch", "SQLAlchemy"],
    project_name="WREXT"
)
def fetch_topic(state: ContentState):
    print("Fetching Topic.....")
    request_payload = state.get("request_payload", {})

    topic_id = request_payload.get("topicId")
    workspace_id = request_payload.get("workspace_id")

    print("topic id: ",topic_id)
    print("Payload: ",request_payload)
    print("workspace id: ",workspace_id)
    if not topic_id or not workspace_id:
        print("⚠️ Missing topic_id or workspace_id in payload")
        return {"topics": None, "error": "Missing topic_id or workspace_id"}


    db = next(get_db())
    try:
        topic = (
            db.query(TopicsModel)
            .filter(
                TopicsModel.id == topic_id,
                TopicsModel.workspace_id == workspace_id
            )
            .first()
        )

        if not topic:
            return {
                "node": "fetch_topic",
                "error": f"No topic found with id={topic_id}",
                "topics": None
            }

        return {
            "topics": [
                {
                    "id": str(topic.id),
                    "workspace_id": str(topic.workspace_id),
                    "title": topic.title,
                    "angle": topic.angle,
                    "description": topic.description,
                    "channel_fit": topic.channel_fit,
                    "audience_fit": topic.audience_fit,
                    "why_it_works": topic.why_it_works,
                    "scores": topic.scores,
                    "tags": topic.tags,
                    "suggested_defaults": topic.suggested_defaults,
                    "goal_alignment": topic.goal_alignment,
                    "content_guidance": topic.content_guidance,
                    "audience_insights": topic.audience_insights,
                    "internal_research_config": topic.internal_research_config,
                    "approved": topic.approved,
                    "approved_at": topic.approved_at,
                    "user_settings": topic.user_settings,
                    "created_at": topic.created_at,
                    "updated_at": topic.updated_at
                }
            ]
        }

    except Exception as e:
        return {
            "node": "fetch_topic",
            "error": f"Unexpected error occurred: {str(e)}",
            "topics": None
        }

    finally:
        db.close()

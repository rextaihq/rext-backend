from fastapi import APIRouter,Depends,HTTPException
from src.api.schema.topic_schema import TopicGenerationInput,DeleteTopics
from langchain_core.messages import SystemMessage
from src.model.model import topic_generation_model
from src.prompts.topic_generation_prompts import topic_generation_prompt
from src.api.security.auth import get_api_key,API_KEY
from sqlalchemy.orm import Session
from src.api.models.topic_models import Topics
from src.api.database.database import get_db
from src.states.schemas import SaveTopicRequestList
from src.services.topic_enrichment_service import TopicEnrichmentService
import uuid

router = APIRouter(
    prefix="/topic",
    tags=["topic generation"]
)


@router.get("/")
def get_status():
    return {"status": "Topic Generation Route is working!"}


@router.post("/generate-topic")
def generate_topic(data:TopicGenerationInput, api_key: str = Depends(get_api_key)):
    if api_key != API_KEY:
        return {"error": "Unauthorized"}
    # Dummy response matching GeneratedTopic interface
    print("Sending Response..")
    # load the model
    model = topic_generation_model()

    # format the human message
    human_messages = topic_generation_prompt().format_messages(**data.model_dump())
    # this is usually a list with one HumanMessage, but we keep it flexible

    # define system message separately
    system_message = SystemMessage(
        content=(
            "You are a helpful content strategist. "
            "Your task is to propose topic ideas. "
            "Each topic must be useful for the specific audience, "
            "fit the content goals, and suit the selected channels."
        )
    )

    # combine them into one list
    messages = [system_message] + human_messages

    # call the model
    basic_topics = model.invoke(messages).topics
    print("Basic Response Received..")
    print(basic_topics)

    # Create lightweight enrichment for frontend display (just add suggested defaults)
    enrichment_service = TopicEnrichmentService()
    display_topics = []

    for basic_topic in basic_topics:
        # Convert basic topic to dict
        basic_topic_dict = basic_topic.model_dump() if hasattr(basic_topic, 'model_dump') else basic_topic

        # Add ID and suggested defaults for frontend display
        basic_topic_dict["id"] = f"topic_{str(uuid.uuid4())[:8]}"
        basic_topic_dict["suggested_defaults"] = enrichment_service._create_suggested_defaults(
            basic_topic_dict,
            data.model_dump()
        ).model_dump()

        display_topics.append(basic_topic_dict)

    print(f"Prepared {len(display_topics)} topics for display")

    return {
        "status": "success",
        "topics": display_topics,
    }


@router.post("/save-topic")
def save_topic(data: SaveTopicRequestList, api_key: str = Depends(get_api_key), db: Session = Depends(get_db)):
    if api_key != API_KEY:
        return {"error": "Unauthorized"}

    print("Enriching and Saving Topics to DB..")
    enrichment_service = TopicEnrichmentService()
    saved = []

    for save_topic_data in data.topics:
        # Convert SaveTopicRequest to dict for enrichment
        basic_topic_dict = {
            "title": save_topic_data.title,
            "angle": save_topic_data.angle,
            "description": save_topic_data.description,
            "channel_fit": save_topic_data.channel_fit,
            "audience_fit": save_topic_data.audience_fit,
            "why_it_works": save_topic_data.why_it_works,
            "tags": save_topic_data.tags,
            "scores": save_topic_data.scores  # This is now a BasicTopicScore object
        }

        # Use input params if provided, otherwise use defaults
        input_params = save_topic_data.input_params or {}

        # Enrich the topic with full structured data
        enriched_topic = enrichment_service.enrich_topic(basic_topic_dict, input_params)

        # Use the provided ID from frontend
        enriched_topic.id = save_topic_data.id

        # Create database record with fully enriched data
        db_topic = Topics(
            id=enriched_topic.id,
            title=enriched_topic.title,
            angle=enriched_topic.angle,
            description=enriched_topic.description,
            channel_fit=enriched_topic.channel_fit,
            audience_fit=enriched_topic.audience_fit,
            why_it_works=enriched_topic.why_it_works,
            scores=enriched_topic.scores.model_dump(),
            tags=enriched_topic.tags,
            suggested_defaults=enriched_topic.suggested_defaults.model_dump(),
            goal_alignment=enriched_topic.goal_alignment.model_dump(),
            content_guidance=enriched_topic.content_guidance.model_dump(),
            audience_insights=enriched_topic.audience_insights.model_dump(),
            internal_research_config=enriched_topic.internal_research_config.model_dump(),
            user_settings=enriched_topic.user_settings.model_dump()
        )
        db.add(db_topic)
        saved.append(db_topic)

    db.commit()
    print(f"Enriched and saved {len(saved)} topics")
    return {
        "status": "success",
        "message": f"{len(saved)} topics saved successfully."
    }


@router.get("/get-topics")
def get_topics(api_key: str = Depends(get_api_key),db: Session = Depends(get_db)):
    if api_key != API_KEY:
        return {"error": "Unauthorized"}

    print("Fetching Topics from DB..")
    topics = db.query(Topics).all()
    print("Topics Fetched..")
    return {
        "topics":topics
    }


@router.delete("/delete-topic", description="Delete multiple topics by IDs")
def delete_topics(
    topic_ids: DeleteTopics,
    api_key: str = Depends(get_api_key),
    db: Session = Depends(get_db)
):
    if api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")

    print(f"Attempting to delete topics with IDs {topic_ids}..")

    # Fetch topics
    topic_ids = topic_ids.topic_ids
    topics = db.query(Topics).filter(Topics.id.in_(topic_ids)).all()
    if not topics:
        raise HTTPException(status_code=404, detail="No topics found for given IDs")

    # Delete all fetched topics
    for topic in topics:
        db.delete(topic)
    db.commit()

    print("Topics deleted successfully.")
    return {
        "status": "success",
        "message": f"Deleted {len(topics)} topics successfully.",
        "ids": topic_ids
    }
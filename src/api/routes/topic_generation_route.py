from fastapi import APIRouter,Depends,Query,HTTPException
from src.api.schema.topic_schema import TopicGeneration,DeleteTopics
from langchain_core.messages import SystemMessage,HumanMessage
from src.model.model import topic_generation_model
from src.prompts.topic_generation_prompts import topic_generation_prompt
from src.api.security.auth import get_api_key,api_key_header,API_KEY
from sqlalchemy.orm import Session
from src.api.models.topic_models import Topics
from src.api.database.database import get_db
from src.states.schemas import TopicGenerationList
from typing import List

router = APIRouter(
    prefix="/topic",
    tags=["topic generation"]
)


@router.get("/")
def get_status():
    return {"status": "Topic Generation Route is working!"}


@router.post("/generate-topic")
def generate_topic(data:TopicGeneration, api_key: str = Depends(get_api_key),db: Session = Depends(get_db)):
    if api_key != API_KEY:
        return {"error": "Unauthorized"}
    # Dummy response matching GeneratedTopic interface
    print("Sending Dummy Response..")
    # load the model
    model = topic_generation_model()

    # format the human message
    human_messages = topic_generation_prompt().format_messages(**data.dict())
    # this is usually a list with one HumanMessage, but we keep it flexible

    # define system message separately
    system_message = SystemMessage(
        content=(
            "You are a helpful content strategist. "
            "Your task is to propose topic ideas. "
            "Each idea must be useful for the specific audience, "
            "fit the content goals, and suit the selected channels."
        )
    )

    # combine them into one list
    messages = [system_message] + human_messages

    # call the model
    response = model.invoke(messages).topics
    print("Response Received..")
    print(response)

    return {
        "status": "success",
        "topics": response,
    }


@router.post("/save-topic")
def save_topic(data: TopicGenerationList, api_key: str = Depends(get_api_key), db: Session = Depends(get_db)):
    if api_key != API_KEY:
        return {"error": "Unauthorized"}
    
    print("Saving Topic to DB..")
    saved = []

    for topic in data.topics: 
        db_topic = Topics(
            title=topic.title,
            angle=topic.angle,
            channel_fit=topic.channel_fit,
            audience_fit=topic.audience_fit,
            why_it_works=topic.why_it_works,
            scores=topic.scores.dict() if hasattr(topic.scores, "dict") else topic.scores,
            tags=topic.tags
        )
        db.add(db_topic)
        saved.append(db_topic)

    db.commit()
    print("Topic Saved..")
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
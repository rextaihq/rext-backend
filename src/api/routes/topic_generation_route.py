from fastapi import APIRouter,Depends
from src.api.schema.topic_schema import TopicGeneration
from langchain_core.messages import SystemMessage,HumanMessage
from src.model.model import topic_generation_model
from src.prompts.topic_generation_prompts import topic_generation_prompt
from src.api.security.auth import get_api_key,api_key_header,API_KEY

router = APIRouter(
    prefix="/topic",
    tags=["topic generation"]
)


@router.get("/")
def get_status():
    return {"status": "Topic Generation Route is working!"}


@router.post("/generate-topic")
def generate_topic(data:TopicGeneration, api_key: str = Depends(get_api_key)):
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
        "topics": response
    }
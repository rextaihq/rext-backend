from fastapi import APIRouter, Depends, HTTPException, Request
from src.api.schema.topic_schema import TopicGenerationInput, DeleteTopics
from langchain_core.messages import SystemMessage
from src.model.model import topic_generation_model
from src.prompts.topic_generation_prompts import topic_generation_prompt
from src.api.security.auth import get_api_key, API_KEY
from sqlalchemy.orm import Session
from src.api.models.topic_models import Topics
from src.api.database.database import get_db
from src.states.schemas import SaveTopicRequestList
from src.services.topic_enrichment_service import TopicEnrichmentService
from src.utils.response_utils import success, error, unauthorized, not_found, no_content
from src.api.schemas.response_schemas import ErrorCode, ErrorSeverity
from src.api.middleware.exceptions import (
    TopicGenerationException,
    ResourceNotFoundException,
    WrextAuthenticationException,
    WrextExternalServiceException
)
import uuid

router = APIRouter(
    prefix="/topic",
    tags=["topic generation"]
)


@router.get("/")
def get_status(request: Request):
    return success(
        data={"status": "operational", "service": "topic_generation"},
        request=request,
        message="Topic Generation Route is working!"
    )


@router.post("/generate-topic")
def generate_topic(
    data: TopicGenerationInput,
    request: Request,
    api_key: str = Depends(get_api_key)
):
    if api_key != API_KEY:
        raise WrextAuthenticationException(
            message="Invalid API key provided",
            context={"api_key_provided": bool(api_key)}
        )
    try:
        print("Starting topic generation...")

        # Load the model
        model = topic_generation_model()
        if not model:
            raise TopicGenerationException(
                message="Failed to load topic generation model",
                generation_params=data.model_dump()
            )

        # Format the human message
        human_messages = topic_generation_prompt().format_messages(**data.model_dump())

        # Define system message separately
        system_message = SystemMessage(
            content=(
                "You are a helpful content strategist. "
                "Your task is to propose topic ideas. "
                "Each topic must be useful for the specific audience, "
                "fit the content goals, and suit the selected channels."
            )
        )

        # Combine messages
        messages = [system_message] + human_messages

        # Call the model
        try:
            response = model.invoke(messages)
            basic_topics = response.topics
            print(f"Generated {len(basic_topics)} basic topics")
        except Exception as model_err:
            print(f"Model invocation failed: {model_err}")
            raise TopicGenerationException(
                message="Failed to generate topics using AI model",
                generation_params=data.model_dump(),
                context={"model_error": str(model_err)}
            )

        # Create lightweight enrichment for frontend display
        enrichment_service = TopicEnrichmentService()
        display_topics = []

        try:
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
        except Exception as enrichment_err:
            print(f"Topic enrichment failed: {enrichment_err}")
            raise TopicGenerationException(
                message="Failed to enrich generated topics",
                generation_params=data.model_dump(),
                context={"enrichment_error": str(enrichment_err)}
            )

        return success(
            data={
                "topics": display_topics,
                "total_generated": len(display_topics),
                "generation_params": {
                    "industry": data.industry,
                    "num_topics": getattr(data, 'num_topics', len(display_topics))
                }
            },
            request=request,
            message=f"Successfully generated {len(display_topics)} topics"
        )

    except (TopicGenerationException, WrextAuthenticationException):
        # Re-raise custom exceptions to be handled by middleware
        raise
    except Exception as e:
        print(f"Unexpected error during topic generation: {e}")
        return error(
            message="Topic generation failed due to server error",
            code=ErrorCode.TOPIC_GENERATION_FAILED,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            context={"error_details": str(e), "generation_params": data.model_dump()},
            request=request
        )


@router.post("/save-topic")
def save_topic(
    data: SaveTopicRequestList,
    request: Request,
    api_key: str = Depends(get_api_key),
    db: Session = Depends(get_db)
):
    if api_key != API_KEY:
        raise WrextAuthenticationException(
            message="Invalid API key provided",
            context={"api_key_provided": bool(api_key)}
        )

    try:
        print(f"Enriching and saving {len(data.topics)} topics to DB...")
        enrichment_service = TopicEnrichmentService()
        saved = []

        for save_topic_data in data.topics:
            try:
                # Convert SaveTopicRequest to dict for enrichment
                basic_topic_dict = {
                    "title": save_topic_data.title,
                    "angle": save_topic_data.angle,
                    "description": save_topic_data.description,
                    "channel_fit": save_topic_data.channel_fit,
                    "audience_fit": save_topic_data.audience_fit,
                    "why_it_works": save_topic_data.why_it_works,
                    "tags": save_topic_data.tags,
                    "scores": save_topic_data.scores
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

            except Exception as topic_err:
                print(f"Failed to process topic {save_topic_data.id}: {topic_err}")
                # Continue with other topics rather than failing entirely
                continue

        if not saved:
            return error(
                message="No topics could be saved successfully",
                code=ErrorCode.VALIDATION_FAILED,
                status_code=422,
                severity=ErrorSeverity.MEDIUM,
                request=request
            )

        db.commit()
        print(f"Enriched and saved {len(saved)} topics")

        return success(
            data={
                "saved_count": len(saved),
                "saved_topic_ids": [topic.id for topic in saved],
                "total_requested": len(data.topics)
            },
            request=request,
            message=f"{len(saved)} topics saved successfully"
        )

    except Exception as e:
        print(f"Error saving topics: {e}")
        db.rollback()
        return error(
            message="Failed to save topics due to server error",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            context={"error_details": str(e), "topics_count": len(data.topics)},
            request=request
        )


@router.get("/get-topics")
def get_topics(
    request: Request,
    api_key: str = Depends(get_api_key),
    db: Session = Depends(get_db)
):
    if api_key != API_KEY:
        raise WrextAuthenticationException(
            message="Invalid API key provided",
            context={"api_key_provided": bool(api_key)}
        )

    try:
        print("Fetching topics from DB...")
        topics = db.query(Topics).all()
        print(f"Fetched {len(topics)} topics")

        # Convert topics to dict format for consistent response
        topics_data = [
            {
                "id": topic.id,
                "title": topic.title,
                "angle": topic.angle,
                "description": topic.description,
                "channel_fit": topic.channel_fit,
                "audience_fit": topic.audience_fit,
                "why_it_works": topic.why_it_works,
                "scores": topic.scores,
                "tags": topic.tags,
                "created_at": topic.created_at.isoformat() if hasattr(topic, 'created_at') else None
            }
            for topic in topics
        ]

        return success(
            data={
                "topics": topics_data,
                "total_count": len(topics_data)
            },
            request=request,
            message=f"Retrieved {len(topics_data)} topics successfully"
        )

    except Exception as e:
        print(f"Error fetching topics: {e}")
        return error(
            message="Failed to retrieve topics",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            context={"error_details": str(e)},
            request=request
        )


@router.delete("/delete-topic", description="Delete multiple topics by IDs")
def delete_topics(
    topic_ids: DeleteTopics,
    request: Request,
    api_key: str = Depends(get_api_key),
    db: Session = Depends(get_db)
):
    if api_key != API_KEY:
        raise WrextAuthenticationException(
            message="Invalid API key provided",
            context={"api_key_provided": bool(api_key)}
        )

    try:
        topic_id_list = topic_ids.topic_ids
        print(f"Attempting to delete {len(topic_id_list)} topics...")

        # Fetch topics
        topics = db.query(Topics).filter(Topics.id.in_(topic_id_list)).all()

        if not topics:
            raise ResourceNotFoundException(
                message="No topics found for the provided IDs",
                resource_type="topics",
                context={"requested_ids": topic_id_list}
            )

        # Check if all requested topics were found
        found_ids = [topic.id for topic in topics]
        missing_ids = [tid for tid in topic_id_list if tid not in found_ids]

        # Delete all found topics
        deleted_count = 0
        for topic in topics:
            db.delete(topic)
            deleted_count += 1

        db.commit()
        print(f"Successfully deleted {deleted_count} topics")

        response_data = {
            "deleted_count": deleted_count,
            "deleted_ids": found_ids,
            "requested_count": len(topic_id_list)
        }

        # Include missing IDs if any
        if missing_ids:
            response_data["missing_ids"] = missing_ids

        return success(
            data=response_data,
            request=request,
            message=f"Successfully deleted {deleted_count} topics"
        )

    except (ResourceNotFoundException, WrextAuthenticationException):
        raise
    except Exception as e:
        print(f"Error deleting topics: {e}")
        db.rollback()
        return error(
            message="Failed to delete topics",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            context={"error_details": str(e), "topic_ids": topic_ids.topic_ids},
            request=request
        )
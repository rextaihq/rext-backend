from fastapi import APIRouter, Depends, HTTPException, Request
from src.api.schema.topic_schema import TopicGenerationInput, DeleteTopics, UpdateTopicRequest
from langchain_core.messages import SystemMessage
from src.model.model import topic_generation_model
from src.prompts.topic_generation_prompts import topic_generation_prompt
from src.api.security.auth import get_api_key, API_KEY
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select
from src.api.models.topic_models.topic_models import TopicsModel as Topics
from src.api.database.async_database import get_async_db
from src.states.schemas import SaveTopicRequestList
from src.services.topic_enrichment_service import TopicEnrichmentService
from src.utils.response_utils import success, error, unauthorized, not_found, no_content
from src.utils.workspace_utils import get_workspace_id_from_identifier
from src.api.schema.response_schemas import ErrorCode, ErrorSeverity
from src.api.middleware.exceptions import (
    TopicGenerationException,
    ResourceNotFoundException,
    WrextAuthenticationException
)
import uuid

from src.api.lib.logger import auto_logger

logger = auto_logger()

router = APIRouter(
    prefix="/topic",
    tags=["topic generation"]
)


@router.get("/")
async def get_status(request: Request):
    return success(
        data={"status": "operational", "service": "topic_generation"},
        request=request,
        message="Topic Generation Route is working!"
    )


@router.post("/generate-topic")
async def generate_topic(
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
        logger.info("Starting topic generation...")

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
            logger.info(f"Generated {len(basic_topics)} basic topics")
        except Exception as model_err:
            logger.info(f"Model invocation failed: {model_err}")
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
                basic_topic_dict["id"] = str(uuid.uuid4())
                basic_topic_dict["suggested_defaults"] = enrichment_service._create_suggested_defaults(
                    basic_topic_dict,
                    data.model_dump()
                ).model_dump()

                display_topics.append(basic_topic_dict)

            logger.info(f"Prepared {len(display_topics)} topics for display")
        except Exception as enrichment_err:
            logger.info(f"Topic enrichment failed: {enrichment_err}")
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
        logger.info(f"Unexpected error during topic generation: {e}")
        return error(
            message="Topic generation failed due to server error",
            code=ErrorCode.TOPIC_GENERATION_FAILED,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            context={"error_details": str(e), "generation_params": data.model_dump()},
            request=request
        )


@router.post("/save-topic")
async def save_topic(
    data: SaveTopicRequestList,
    request: Request,
    api_key: str = Depends(get_api_key),
    db: AsyncSession = Depends(get_async_db)
):
    if api_key != API_KEY:
        raise WrextAuthenticationException(
            message="Invalid API key provided",
            context={"api_key_provided": bool(api_key)}
        )

    try:
        logger.info(f"Enriching and saving {len(data.topics)} topics to DB...")
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

                # Use the provided ID from frontend, ensuring it's a proper UUID
                topic_uuid = uuid.UUID(save_topic_data.id) if isinstance(save_topic_data.id, str) else save_topic_data.id
                enriched_topic.id = topic_uuid

                # Resolve workspace ID from either UUID or slug
                actual_workspace_id = await get_workspace_id_from_identifier(db, save_topic_data.workspace_id)
                if not actual_workspace_id:
                    raise ResourceNotFoundException(
                        message=f"Workspace '{save_topic_data.workspace_id}' not found",
                        resource_type="workspace",
                        context={"workspace_identifier": save_topic_data.workspace_id}
                    )

                # Create database record with fully enriched data
                db_topic = Topics(
                    id=topic_uuid,
                    workspace_id=actual_workspace_id,
                    title=enriched_topic.title,
                    angle=enriched_topic.angle,
                    description=enriched_topic.description,
                    channel_fit=enriched_topic.channel_fit,
                    audience_fit=enriched_topic.audience_fit,
                    why_it_works=enriched_topic.why_it_works,
                    scores=enriched_topic.scores.model_dump(),
                    tags=enriched_topic.tags,
                    approved=False,  # Explicitly set to false - topics require manual approval
                    approved_at=None,  # Will be set when topic is approved
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
                logger.info(f"Failed to process topic {save_topic_data.id}: {topic_err}")
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

        await db.commit()
        logger.info(f"Enriched and saved {len(saved)} topics")

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
        logger.info(f"Error saving topics: {e}")
        await db.rollback()
        return error(
            message="Failed to save topics due to server error",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            context={"error_details": str(e), "topics_count": len(data.topics)},
            request=request
        )


@router.get("/get-topic/{topic_id}")
async def get_topic(
    topic_id: str,
    request: Request,
    workspace_id: str,
    api_key: str = Depends(get_api_key),
    db: AsyncSession = Depends(get_async_db)
):
    if api_key != API_KEY:
        raise WrextAuthenticationException(
            message="Invalid API key provided",
            context={"api_key_provided": bool(api_key)}
        )

    try:
        # Resolve workspace ID from either UUID or slug
        actual_workspace_id = await get_workspace_id_from_identifier(db, workspace_id)
        if not actual_workspace_id:
            raise ResourceNotFoundException(
                message=f"Workspace '{workspace_id}' not found",
                resource_type="workspace",
                context={"workspace_identifier": workspace_id}
            )

        logger.info(f"Fetching topic with ID: {topic_id} for workspace: {workspace_id} (resolved to {actual_workspace_id})")
        result = await db.execute(select(Topics).where(
            Topics.id == topic_id,
            Topics.workspace_id == actual_workspace_id
        ))
        topic = result.scalar_one_or_none()

        if not topic:
            raise ResourceNotFoundException(
                message=f"Topic with ID '{topic_id}' not found in workspace '{workspace_id}'",
                resource_type="topic",
                context={"topic_id": topic_id, "workspace_id": workspace_id}
            )

        logger.info(f"Found topic: {topic.title}")

        # Convert topic to dict format for consistent response
        topic_data = {
            "id": topic.id,
            "workspace_id": topic.workspace_id,
            "title": topic.title,
            "angle": topic.angle,
            "description": topic.description,
            "channel_fit": topic.channel_fit,
            "audience_fit": topic.audience_fit,
            "why_it_works": topic.why_it_works,
            "scores": topic.scores,
            "tags": topic.tags,
            "approved": topic.approved,
            "suggested_defaults": topic.suggested_defaults,
            "goal_alignment": topic.goal_alignment,
            "content_guidance": topic.content_guidance,
            "audience_insights": topic.audience_insights,
            "internal_research_config": topic.internal_research_config,
            "user_settings": topic.user_settings,
            "created_at": topic.created_at.isoformat() if hasattr(topic, 'created_at') and topic.created_at else None,
            "updated_at": topic.updated_at.isoformat() if hasattr(topic, 'updated_at') and topic.updated_at else None,
            "approved_at": topic.approved_at.isoformat() if hasattr(topic, 'approved_at') and topic.approved_at else None
        }

        return success(
            data=topic_data,
            request=request,
            message=f"Topic '{topic.title}' retrieved successfully"
        )

    except (ResourceNotFoundException, WrextAuthenticationException):
        raise
    except Exception as e:
        logger.info(f"Error fetching topic {topic_id}: {e}")
        return error(
            message="Failed to retrieve topic",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            context={"error_details": str(e), "topic_id": topic_id},
            request=request
        )


@router.get("/get-topics")
async def get_topics(
    request: Request,
    workspace_id: str,
    api_key: str = Depends(get_api_key),
    db: AsyncSession = Depends(get_async_db)
):
    if api_key != API_KEY:
        raise WrextAuthenticationException(
            message="Invalid API key provided",
            context={"api_key_provided": bool(api_key)}
        )

    try:
        # Resolve workspace ID from either UUID or slug
        actual_workspace_id = await get_workspace_id_from_identifier(db, workspace_id)
        if not actual_workspace_id:
            raise ResourceNotFoundException(
                message=f"Workspace '{workspace_id}' not found",
                resource_type="workspace",
                context={"workspace_identifier": workspace_id}
            )

        logger.info(f"Fetching topics from DB for workspace {workspace_id} (resolved to {actual_workspace_id})...")
        # Filter by workspace_id and order by updated_at first (most recent updates), then by created_at (newest first)
        result = await db.execute(select(Topics).where(
            Topics.workspace_id == actual_workspace_id
        ).order_by(
            Topics.updated_at.desc().nulls_last(),
            Topics.created_at.desc()
        ))
        topics = result.scalars().all()
        logger.info(f"Fetched {len(topics)} topics for workspace {workspace_id} (ordered by latest date)")

        # Convert topics to dict format for consistent response
        topics_data = [
            {
                "id": topic.id,
                "workspace_id": topic.workspace_id,
                "title": topic.title,
                "angle": topic.angle,
                "description": topic.description,
                "channel_fit": topic.channel_fit,
                "audience_fit": topic.audience_fit,
                "why_it_works": topic.why_it_works,
                "scores": topic.scores,
                "tags": topic.tags,
                "approved": topic.approved,
                "created_at": topic.created_at.isoformat() if hasattr(topic, 'created_at') and topic.created_at else None,
                "updated_at": topic.updated_at.isoformat() if hasattr(topic, 'updated_at') and topic.updated_at else None,
                "approved_at": topic.approved_at.isoformat() if hasattr(topic, 'approved_at') and topic.approved_at else None
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
        logger.info(f"Error fetching topics: {e}")
        return error(
            message="Failed to retrieve topics",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            context={"error_details": str(e)},
            request=request
        )


@router.delete("/delete-topic", description="Delete multiple topics by IDs")
async def delete_topics(
    topic_ids: DeleteTopics,
    request: Request,
    workspace_id: str,
    api_key: str = Depends(get_api_key),
    db: AsyncSession = Depends(get_async_db)
):
    if api_key != API_KEY:
        raise WrextAuthenticationException(
            message="Invalid API key provided",
            context={"api_key_provided": bool(api_key)}
        )

    try:
        topic_id_list = topic_ids.topic_ids
        logger.info(f"Attempting to delete {len(topic_id_list)} topics from workspace {workspace_id}...")

        # Resolve workspace ID from either UUID or slug
        actual_workspace_id = await get_workspace_id_from_identifier(db, workspace_id)
        if not actual_workspace_id:
            raise ResourceNotFoundException(
                message=f"Workspace '{workspace_id}' not found",
                resource_type="workspace",
                context={"workspace_identifier": workspace_id}
            )

        # Fetch topics - only from the specified workspace
        result = await db.execute(select(Topics).where(
            Topics.id.in_(topic_id_list),
            Topics.workspace_id == actual_workspace_id
        ))
        topics = result.scalars().all()

        if not topics:
            return ResourceNotFoundException(
                status_code=400,
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
            await db.delete(topic)
            deleted_count += 1

        await db.commit()
        logger.info(f"Successfully deleted {deleted_count} topics")

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
    except Exception as e:
        logger.info(f"Error deleting topics: {e}")
        await db.rollback()
        return error(
            message="Failed to delete topics",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            context={"error_details": str(e), "topic_ids": topic_ids.topic_ids},
            request=request
        )


@router.put("/update-topic")
async def update_topic(
    data: UpdateTopicRequest,
    request: Request,
    workspace_id: str,
    api_key: str = Depends(get_api_key),
    db: AsyncSession = Depends(get_async_db)
):
    if api_key != API_KEY:
        raise WrextAuthenticationException(
            message="Invalid API key provided",
            context={"api_key_provided": bool(api_key)}
        )

    try:
        topic_id = data.topic_id
        logger.info(f"Attempting to update topic with ID: {topic_id} in workspace: {workspace_id}")

        # Resolve workspace ID from either UUID or slug
        actual_workspace_id = await get_workspace_id_from_identifier(db, workspace_id)
        if not actual_workspace_id:
            raise ResourceNotFoundException(
                message=f"Workspace '{workspace_id}' not found",
                resource_type="workspace",
                context={"workspace_identifier": workspace_id}
            )

        # Fetch the topic - only from the specified workspace
        result = await db.execute(select(Topics).where(
            Topics.id == topic_id,
            Topics.workspace_id == actual_workspace_id
        ))
        topic = result.scalar_one_or_none()

        if not topic:
            raise ResourceNotFoundException(
                message=f"Topic with ID '{topic_id}' not found in workspace '{workspace_id}'",
                resource_type="topic",
                context={"topic_id": topic_id, "workspace_id": workspace_id}
            )

        # Track what fields are being updated
        updated_fields = []

        # Update only the fields that are provided
        if data.title is not None:
            topic.title = data.title
            updated_fields.append("title")

        if data.angle is not None:
            topic.angle = data.angle
            updated_fields.append("angle")

        if data.description is not None:
            topic.description = data.description
            updated_fields.append("description")

        if data.channel_fit is not None:
            topic.channel_fit = data.channel_fit
            updated_fields.append("channel_fit")

        if data.audience_fit is not None:
            topic.audience_fit = data.audience_fit
            updated_fields.append("audience_fit")

        if data.why_it_works is not None:
            topic.why_it_works = data.why_it_works
            updated_fields.append("why_it_works")

        if data.tags is not None:
            topic.tags = data.tags
            updated_fields.append("tags")

        if data.approved is not None:
            # If topic is being approved for the first time, set approved_at
            if data.approved and not topic.approved:
                topic.approved_at = func.now()
                updated_fields.append("approved_at")
            # If topic is being unapproved, clear approved_at
            elif not data.approved and topic.approved:
                topic.approved_at = None
                updated_fields.append("approved_at")

            topic.approved = data.approved
            updated_fields.append("approved")

        # Always update the timestamp when any field is modified
        if updated_fields:
            topic.updated_at = func.now()
            updated_fields.append("updated_at")

        await db.commit()
        logger.info(f"Successfully updated topic '{topic.title}' - fields: {', '.join(updated_fields)}")

        return success(
            data={
                "updated_count": 1,
                "topic_id": topic_id,
                "topic_title": topic.title,
                "updated_fields": updated_fields,
                "approved": topic.approved
            },
            request=request,
            message=f"Topic '{topic.title}' updated successfully"
        )

    except (ResourceNotFoundException, WrextAuthenticationException):
        raise
    except Exception as e:
        logger.info(f"Error updating topic {data.topic_id}: {e}")
        await db.rollback()
        return error(
            message="Failed to update topic",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            context={"error_details": str(e), "topic_id": data.topic_id},
            request=request
        )

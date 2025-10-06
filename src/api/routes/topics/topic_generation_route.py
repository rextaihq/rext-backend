from fastapi import APIRouter, Depends, HTTPException, Request
from src.api.schema.topic_schema import TopicGenerationInput, DeleteTopics, UpdateTopicRequest
from langchain_core.messages import SystemMessage
from src.langgraph_flow.model.model import topic_generation_model
from src.langgraph_flow.prompts.topic_generation_prompts import topic_generation_prompt
from src.api.security.dependencies import get_current_user
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select
from src.api.models.topic_models.topic_models import TopicsModel as Topics
from src.api.database.async_database import get_async_db
from src.states.schemas import SaveTopicRequestList
from src.services.topic_enrichment_service import TopicEnrichmentService
from src.utils.response_utils import success, error, unauthorized, not_found, no_content
from src.utils.workspace_utils import resolve_and_verify_workspace
from src.utils.route_decorators import db_transaction_handler, require_permissions
from src.api.schema.response_schemas import ErrorCode, ErrorSeverity
from src.api.middleware.exceptions import (
    TopicGenerationException,
    ResourceNotFoundException,
    WrextAuthenticationException
)
from src.utils.db_utils import get_or_404
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
@db_transaction_handler("generate topics", auto_commit=False)
@require_permissions("topic.create", workspace_scoped=True)
async def generate_topic(
    data: TopicGenerationInput,
    request: Request,
    workspace_id: str,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user)
):
    """
    Generate content topics using AI based on workspace context.

    Requires:
    - JWT authentication
    - Workspace membership verification
    """
    user_id = user.get("identity")

    # Verify workspace access and membership in one call
    workspace, membership = await resolve_and_verify_workspace(db, workspace_id, uuid.UUID(user_id))

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

    # Return raw data - decorator handles success response
    # Note: auto_commit=False because this doesn't modify database
    return {
        "topics": display_topics,
        "total_generated": len(display_topics),
        "generation_params": {
            "industry": data.industry,
            "num_topics": getattr(data, 'num_topics', len(display_topics))
        }
    }


@router.post("/save-topic")
@db_transaction_handler("save topics")
@require_permissions("topic.create", workspace_scoped=True)
async def save_topic(
    data: SaveTopicRequestList,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user)
):
    """
    Save topics to database

    Requires user authentication. Verifies workspace membership for each topic's workspace.
    """
    user_id = user.get("identity")

    logger.info(f"Enriching and saving {len(data.topics)} topics to DB for user {user_id}...")
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

            # Verify workspace access and membership in one call
            workspace, membership = await resolve_and_verify_workspace(db, save_topic_data.workspace_id, uuid.UUID(user_id))

            # Create database record with fully enriched data
            db_topic = Topics(
                id=topic_uuid,
                workspace_id=workspace.id,
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
        raise WrextValidationException(
            message="No topics could be saved successfully",
            field_errors={"topics": ["All topic saves failed"]}
        )

    logger.info(f"Enriched and saved {len(saved)} topics")

    # Return raw data - decorator handles success response and commit
    return {
        "saved_count": len(saved),
        "saved_topic_ids": [str(topic.id) for topic in saved],
        "total_requested": len(data.topics)
    }


@router.get("/get-topic/{topic_id}")
@db_transaction_handler("get topic", auto_commit=False)
async def get_topic(
    topic_id: str,
    request: Request,
    workspace_id: str,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user)
):
    """
    Get a single topic by ID

    Requires user authentication and workspace membership.
    """
    user_id = user.get("identity")

    # Verify workspace access and membership in one call
    workspace, membership = await resolve_and_verify_workspace(db, workspace_id, uuid.UUID(user_id))

    logger.info(f"Fetching topic with ID: {topic_id} for workspace: {workspace_id} (resolved to {workspace.id}) for user {user_id}")
    topic = await get_or_404(
        db,
        Topics,
        topic_id,
        "topic",
        additional_filters=[Topics.workspace_id == workspace.id]
    )

    logger.info(f"Found topic: {topic.title}")

    # Convert topic to dict format for consistent response - decorator handles success response
    return {
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


@router.get("/get-topics")
@db_transaction_handler("get topics", auto_commit=False)
async def get_topics(
    request: Request,
    workspace_id: str,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user)
):
    """
    Get all topics for a workspace

    Requires user authentication and workspace membership.
    Accepts workspace UUID or slug.
    """
    user_id = user.get("identity")

    # Verify workspace access and membership in one call
    workspace, membership = await resolve_and_verify_workspace(db, workspace_id, uuid.UUID(user_id))

    logger.info(f"Fetching topics from DB for workspace {workspace_id} (resolved to {workspace.id}) for user {user_id}...")
    # Filter by workspace_id and order by updated_at first (most recent updates), then by created_at (newest first)
    result = await db.execute(select(Topics).where(
        Topics.workspace_id == workspace.id
    ).order_by(
        Topics.updated_at.desc().nulls_last(),
        Topics.created_at.desc()
    ))
    topics = result.scalars().all()
    logger.info(f"Fetched {len(topics)} topics for workspace {workspace_id} (ordered by latest date)")

    # Convert topics to dict format - decorator handles success response
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

    return {
        "topics": topics_data,
        "total_count": len(topics_data)
    }


@router.delete("/delete-topic", description="Delete multiple topics by IDs")
@db_transaction_handler("delete topics")
@require_permissions("topic.delete", workspace_scoped=True)
async def delete_topics(
    topic_ids: DeleteTopics,
    request: Request,
    workspace_id: str,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user)
):
    """
    Delete multiple topics by IDs

    Requires user authentication and workspace membership.
    """
    user_id = user.get("identity")

    topic_id_list = topic_ids.topic_ids
    logger.info(f"Attempting to delete {len(topic_id_list)} topics from workspace {workspace_id} by user {user_id}...")

    # Verify workspace access and membership in one call
    workspace, membership = await resolve_and_verify_workspace(db, workspace_id, uuid.UUID(user_id))

    # Fetch topics - only from the specified workspace
    result = await db.execute(select(Topics).where(
        Topics.id.in_(topic_id_list),
        Topics.workspace_id == workspace.id
    ))
    topics = result.scalars().all()

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
        await db.delete(topic)
        deleted_count += 1

    logger.info(f"Successfully deleted {deleted_count} topics")

    response_data = {
        "deleted_count": deleted_count,
        "deleted_ids": found_ids,
        "requested_count": len(topic_id_list)
    }

    # Include missing IDs if any
    if missing_ids:
        response_data["missing_ids"] = missing_ids

    # Return raw data - decorator handles success response and commit
    return response_data


@router.put("/update-topic")
@db_transaction_handler("update topic")
@require_permissions("topic.update", workspace_scoped=True)
async def update_topic(
    data: UpdateTopicRequest,
    request: Request,
    workspace_id: str,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user)
):
    """
    Update a topic

    Requires user authentication and workspace membership.
    """
    user_id = user.get("identity")

    topic_id = data.topic_id
    logger.info(f"Attempting to update topic with ID: {topic_id} in workspace: {workspace_id} by user {user_id}")

    # Verify workspace access and membership in one call
    workspace, membership = await resolve_and_verify_workspace(db, workspace_id, uuid.UUID(user_id))

    # Fetch the topic - only from the specified workspace
    topic = await get_or_404(
        db,
        Topics,
        topic_id,
        "topic",
        additional_filters=[Topics.workspace_id == workspace.id]
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
            # Check if user has permission to approve topics
            from src.utils.rbac_utils import require_permission
            from uuid import UUID as UUIDType
            await require_permission(
                db=db,
                user_id=UUIDType(user_id),
                permission_name="topic.approve",
                workspace_id=workspace.id,
                resource_name="topic"
            )
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

    logger.info(f"Successfully updated topic '{topic.title}' - fields: {', '.join(updated_fields)}")

    # Return raw data - decorator handles success response and commit
    return {
        "updated_count": 1,
        "topic_id": topic_id,
        "topic_title": topic.title,
        "updated_fields": updated_fields,
        "approved": topic.approved
    }

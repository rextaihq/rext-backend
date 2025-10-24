from fastapi import APIRouter, Depends, HTTPException, Request
from src.api.schema.topic_schema import TopicGenerationInput, DeleteTopics, UpdateTopicRequest
from langchain_core.messages import SystemMessage
from src.flow.prompts.prompt_manager import PromptManager
from src.flow.model.llm_manager import topic_generation_model
from src.api.security.dependencies import get_current_user
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select
from src.api.models.topic_models.topic_models import TopicsModel as Topics
from src.api.database.async_database import get_async_db
from src.states.schemas import SaveTopicRequestList
from src.services.topic_enrichment_service import TopicEnrichmentService
from src.services.topic_service import TopicService
from src.utils.response_utils import success, error, unauthorized, not_found, no_content
from src.utils.workspace_utils import resolve_and_verify_workspace
from src.utils.route_decorators import db_transaction_handler, require_permissions
from src.api.schema.response_schemas import ErrorCode, ErrorSeverity
from src.api.middleware.exceptions import (
    TopicGenerationException,
    ResourceNotFoundException,
    WrextAuthenticationException
)
from src.api.middleware.usage_limiter import check_topic_limit, check_api_limit
from src.api.middleware.rate_limiter import ai_topic_generation_rate_limit
from src.utils.db_utils import get_or_404
import uuid

from src.api.lib.logger import auto_logger
from langsmith import traceable, trace

logger = auto_logger()
prompt_manager = PromptManager()

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
@traceable(
    name="Generate Topics",
    metadata={
        "description": "Generates AI-based content topics for a workspace.",
        "inputs": ["industry", "num_topics", "workspace_id"],
        "outputs": ["topics", "total_generated"],
        "source": "LangGraph Content Workflow",
    },
    tags=["LLM", "TopicGeneration", "WREXT"],
    project_name="WREXT"
)
async def generate_topic(
    data: TopicGenerationInput,
    request: Request,
    workspace_id: str,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
    _api_limit: None = Depends(check_api_limit()),
    _rate_limit: None = Depends(ai_topic_generation_rate_limit())
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
    try:
        with trace(name="Load Topic Model") as model_trace:
            model = topic_generation_model()
            if not model:
                raise TopicGenerationException(
                    message="Failed to load topic generation model",
                    generation_params=data.model_dump()
                )
            model_trace.outputs = {"model_loaded": True}
    except Exception as model_load_err:
        logger.error(f"❌ Model loading failed: {model_load_err}")
        raise TopicGenerationException(
            message="Model loading failed",
            generation_params=data.model_dump(),
            context={"error": str(model_load_err)}
        )

    # Format the human message
    try:
        with trace(name="Topic Prompt Construction", inputs=data.model_dump()) as prompt_trace:
            prompt_template = prompt_manager.get_prompt("topic_generation_v1")
            topic_prompt = prompt_template.format_prompt(**data.model_dump()).to_messages()
            prompt_trace.outputs = {"prompt_preview": str(topic_prompt)[:400]}
    except Exception as e:
        logger.error(f"❌ Prompt formatting failed: {e}")
        raise TopicGenerationException(
            message="Prompt formatting failed",
            generation_params=data.model_dump(),
            context={"error": str(e)}
        )

    # Call the model (use async invoke to avoid blocking)
    try:
        with trace(name="LLM Topic Generation") as llm_trace:
            response = await model.ainvoke(topic_prompt)
            basic_topics = response.topics
            llm_trace.outputs = {"num_topics_generated": len(basic_topics)}
            logger.info(f"✅ Generated {len(basic_topics)} topics via LLM")
    except Exception as model_err:
        logger.error(f"❌ Model invocation failed: {model_err}")
        raise TopicGenerationException(
            message="Failed to generate topics using AI model",
            generation_params=data.model_dump(),
            context={"model_error": str(model_err)}
        )


    # Create lightweight enrichment for frontend display
    enrichment_service = TopicEnrichmentService()
    display_topics = []
    try:
        with trace(name="Topic Enrichment", inputs={"num_topics": len(basic_topics)}) as enrich_trace:
            for basic_topic in basic_topics:
                basic_topic_dict = (
                    basic_topic.model_dump() if hasattr(basic_topic, "model_dump") else basic_topic
                )
                basic_topic_dict["id"] = str(uuid.uuid4())
                basic_topic_dict["suggested_defaults"] = enrichment_service._create_suggested_defaults(
                    basic_topic_dict, data.model_dump()
                ).model_dump()
                display_topics.append(basic_topic_dict)

            enrich_trace.outputs = {"enriched_topics": len(display_topics)}
            logger.info(f"✨ Enriched {len(display_topics)} topics")
    except Exception as enrichment_err:
        logger.error(f"❌ Topic enrichment failed: {enrichment_err}")
        raise TopicGenerationException(
            message="Failed to enrich generated topics",
            generation_params=data.model_dump(),
            context={"enrichment_error": str(enrichment_err)}
        )

    # Return raw data - decorator handles success response
    # === Return Trace ===
    with trace(name="Finalize Response") as finalize_trace:
        result = {
            "topics": display_topics,
            "total_generated": len(display_topics),
            "generation_params": {
                "industry": data.industry,
                "num_topics": getattr(data, "num_topics", len(display_topics))
            },
        }
        finalize_trace.outputs = {"response_size": len(display_topics)}
        logger.info("✅ Topic generation completed successfully.")
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
    workspace_id: str,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
    _topic_limit: None = Depends(check_topic_limit()),
):
    """
    Save topics to database

    Requires user authentication. Verifies workspace membership for each topic's workspace.
    """
    user_id = user.get("identity")

    # Verify workspace access and membership in one call
    workspace, membership = await resolve_and_verify_workspace(db, workspace_id, uuid.UUID(user_id))

    # Save topics if provided
    if data.topics:

        # Use TopicService to create topics
        service = TopicService(db)
        saved = await service.create_topics(
            workspace_id=workspace.id,
            user_id=uuid.UUID(user_id),
            topics_data=data.topics
        )

        # Return raw data - decorator handles success response and commit
        return {
            "saved_count": len(saved),
            "saved_topic_ids": [str(topic.id) for topic in saved],
            "total_requested": len(data.topics)
        }

    return {"saved_count": 0, "saved_topic_ids": [], "total_requested": 0}


@router.get("/get-topic/{topic_id}")
@require_permissions(["topic.read"], workspace_scoped=True)
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
@require_permissions(["topic.read"], workspace_scoped=True)
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

    # Verify workspace access and membership in one call
    workspace, membership = await resolve_and_verify_workspace(db, workspace_id, uuid.UUID(user_id))

    # Use TopicService to delete topics
    service = TopicService(db)
    result = await service.delete_topics(
        topic_ids=topic_ids.topic_ids,
        workspace_id=workspace.id
    )

    response_data = {
        "deleted_count": result["deleted_count"],
        "deleted_ids": result["deleted_ids"],
        "requested_count": len(topic_ids.topic_ids)
    }

    # Include missing IDs if any
    if result["missing_ids"]:
        response_data["missing_ids"] = result["missing_ids"]

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

    # Verify workspace access and membership in one call
    workspace, membership = await resolve_and_verify_workspace(db, workspace_id, uuid.UUID(user_id))

    # Check if user is trying to approve topic
    if data.approved:
        from src.utils.rbac_utils import require_permission
        await require_permission(
            db=db,
            user_id=uuid.UUID(user_id),
            permission_name="topic.approve",
            workspace_id=workspace.id,
            resource_name="topic"
        )

    # Use TopicService to update topic
    service = TopicService(db)
    topic = await service.update_topic(
        topic_id=data.topic_id,
        workspace_id=workspace.id,
        data=data
    )

    # Return raw data - decorator handles success response and commit
    return {
        "updated_count": 1,
        "topic_id": data.topic_id,
        "topic_title": topic.title,
        "approved": topic.approved
    }

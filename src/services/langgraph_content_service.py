"""
LangGraph Content Generation Service

This service handles the integration between content management and LangGraph workflows.
It manages thread creation, execution, and tracking for AI-powered content generation.

Responsibilities:
- Generate and manage LangGraph thread IDs
- Execute content generation workflows
- Track workflow execution state
- Store thread references for rerun capability
"""

from typing import Optional, Dict, Any
from uuid import UUID, uuid4
from datetime import datetime, timezone
import asyncio
import json
import markdown

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.api.models.content_models.content import Content
from src.api.models.topic_models.topic_models import TopicsModel
from src.api.models.knowledge_models.knowledge_model import BrandVoice
from src.api.models.workspace_models.workspace_model import WorkspaceModel
from src.api.models.user_models.users import Users
from src.flow.flow import create_workflow
from src.flow.states.content_state import ContentState
from src.utils.logger import logger
from src.api.config import get_settings
from src.api.middleware.exceptions import (
    WrextValidationException,
    ResourceNotFoundException
)
from src.services.email_service import EmailService
from src.flow.service.process_manager import ProgressManager




# Get settings instance
settings = get_settings()
class LangGraphContentService:
    """Service for managing LangGraph content generation workflows"""

    def __init__(self, db: AsyncSession):
        """
        Initialize LangGraphContentService.

        Args:
            db: Async database session
        """
        self.db = db

    async def generate_content_with_langgraph(
        self,
        content_id: UUID,
        workspace_id: UUID,
        topic_id: Optional[UUID] = None,
        thread_id: Optional[UUID] = None,
        regenerate: bool = False
    ) -> Dict[str, Any]:
        """
        Generate content using LangGraph workflow.

        Args:
            content_id: Content UUID to update
            workspace_id: Workspace UUID
            topic_id: Optional topic UUID for context
            thread_id: Optional existing thread ID for continuation
            regenerate: Whether this is a regeneration of existing content

        Returns:
            Dict containing generated content and thread information

        Raises:
            WrextValidationException: If validation fails
            ResourceNotFoundException: If required resources not found
        """
        # Generate new thread ID if not provided
        if not thread_id:
            thread_id = uuid4()
            logger.info(f"Generated new LangGraph thread ID: {thread_id}")
        else:
            logger.info(f"Using existing LangGraph thread ID: {thread_id}")

        # Fetch required data for workflow
        content_data = await self._fetch_content_data(
            content_id, workspace_id, topic_id
        )

        # Prepare initial state for LangGraph
        initial_state = await self._prepare_workflow_state(
            content_data,
            thread_id,
            regenerate
        )

        # Send "generation started" email
        try:
            await self._send_generation_started_email(
                content_id, workspace_id, content_data
            )
        except Exception as e:
            logger.error(f"Failed to send generation started email: {str(e)}")
            # Don't fail workflow if email fails

        # Execute workflow
        try:
            logger.info(f"Starting LangGraph workflow for content {content_id} with thread {thread_id}")

            # Create and compile the workflow
            workflow = create_workflow()
            compiled_workflow = workflow.compile()

            # Execute workflow with thread configuration
            config = {
                "configurable": {
                    "thread_id": str(thread_id)
                }
            }

            # Node name to progress step mapping
            node_to_step_map = {
                "FetchUser": "fetching_user",
                "FetchWorkspace": "fetching_workspace",
                "FetchTopic": "fetching_topic",
                "WebContext": "gathering_web_context",
                "KnowledgeContext": "gathering_knowledge_context",
                "ScrapeContent": "scraping_content",
                "RerankContent": "reranking_documents",
                "BlogGeneration": "generating_blog",
                "SaveContent": "saving_content",
            }

            # Initialize progress manager for real-time updates
            progress_manager = ProgressManager(self.db)

            # Stream events and track progress
            result = None
            async for event in compiled_workflow.astream_events(initial_state, config, version="v2"):
                event_type = event.get("event")
                name = event.get("name", "")

                # Track node execution for progress updates
                if event_type == "on_chain_start" and name in node_to_step_map:
                    step = node_to_step_map[name]
                    logger.info(f"Node started: {name} -> {step}")
                    try:
                        await progress_manager.update_progress(
                            content_id=content_id,
                            step=step
                        )
                    except Exception as e:
                        logger.error(f"Failed to update progress for {step}: {e}")
                        # Don't fail workflow on progress update errors

                # Capture final result
                if event_type == "on_chain_end" and name == "LangGraph":
                    result = event.get("data", {}).get("output")

            if not result:
                raise Exception("Workflow did not produce a result")

            logger.info(f"LangGraph workflow completed for thread {thread_id}")

            # Extract generated content from result
            generated_blog = result.get("generated_blog")
            if generated_blog:
                # Update content with generated data
                await self._update_content_with_generated(
                    content_id,
                    generated_blog,
                    thread_id
                )

                # Send "generation completed" email
                try:
                    await self._send_generation_completed_email(
                        content_id, workspace_id, content_data, generated_blog
                    )
                except Exception as e:
                    logger.error(f"Failed to send generation completed email: {str(e)}")
                    # Don't fail workflow if email fails

                return {
                    "success": True,
                    "thread_id": str(thread_id),
                    "content_id": str(content_id),
                    "generated_content": {
                        "title": generated_blog.title if hasattr(generated_blog, 'title') else None,
                        "body": generated_blog.content if hasattr(generated_blog, 'content') else None,
                        "meta_description": generated_blog.meta_description if hasattr(generated_blog, 'meta_description') else None,
                        "keywords": generated_blog.keywords if hasattr(generated_blog, 'keywords') else None
                    }
                }
            else:
                raise WrextValidationException(
                    message="Workflow completed but no content was generated",
                    context={"thread_id": str(thread_id)}
                )

        except Exception as e:
            logger.error(f"LangGraph workflow failed for thread {thread_id}: {str(e)}")
            # Store thread ID even on failure for debugging
            await self._update_content_thread_id(content_id, thread_id, status="failed")

            # Send "generation failed" email
            try:
                await self._send_generation_failed_email(
                    content_id, workspace_id, content_data, str(e)
                )
            except Exception as email_error:
                logger.error(f"Failed to send generation failed email: {str(email_error)}")
                # Don't fail workflow if email fails

            raise WrextValidationException(
                message=f"Content generation failed: {str(e)}",
                context={"thread_id": str(thread_id), "error": str(e)}
            )

    async def _fetch_content_data(
        self,
        content_id: UUID,
        workspace_id: UUID,
        topic_id: Optional[UUID]
    ) -> Dict[str, Any]:
        """
        Fetch all required data for content generation.

        Returns dict with content, topic, workspace, and brand voice data.
        """
        # Fetch content with eager loading of relationships
        result = await self.db.execute(
            select(Content)
            .options(
                selectinload(Content.seo_data)
            )
            .where(
                Content.id == content_id,
                Content.workspace_id == workspace_id
            )
        )
        content = result.scalar_one_or_none()
        if not content:
            raise ResourceNotFoundException(
                resource_type="content",
                resource_id=str(content_id)
            )

        # Fetch workspace
        result = await self.db.execute(
            select(WorkspaceModel).where(WorkspaceModel.id == workspace_id)
        )
        workspace = result.scalar_one_or_none()
        if not workspace:
            raise ResourceNotFoundException(
                resource_type="workspace",
                resource_id=str(workspace_id)
            )

        # Fetch topic if provided
        topic = None
        if topic_id:
            result = await self.db.execute(
                select(TopicsModel).where(
                    TopicsModel.id == topic_id,
                    TopicsModel.workspace_id == workspace_id
                )
            )
            topic = result.scalar_one_or_none()

        # Fetch brand voice
        result = await self.db.execute(
            select(BrandVoice).where(BrandVoice.workspace_id == workspace_id)
        )
        brand_voice = result.scalar_one_or_none()

        return {
            "content": content,
            "workspace": workspace,
            "topic": topic,
            "brand_voice": brand_voice
        }

    async def _prepare_workflow_state(
        self,
        content_data: Dict[str, Any],
        thread_id: UUID,
        regenerate: bool
    ) -> ContentState:
        """
        Prepare the initial state for LangGraph workflow execution.
        """
        content = content_data["content"]
        workspace = content_data["workspace"]
        topic = content_data["topic"]
        brand_voice = content_data["brand_voice"]

        # Prepare topic data
        topics_data = []
        if topic:
            topics_data.append({
                "id": str(topic.id),
                "title": topic.title,
                "angle": topic.angle,
                "description": topic.description,
                "tags": topic.tags or [],
                "suggested_defaults": topic.suggested_defaults or {}
            })

        # Prepare payload with all content metadata
        payload = {
            "content_id": str(content.id),
            "workspace_id": str(workspace.id),
            "topic_id": str(topic.id) if topic else None,
            "thread_id": str(thread_id),
            "regenerate": regenerate,
            "title": content.title,
            "content_language": content.content_language,
            "content_format": content.content_format,
            "status": content.status,
            "author_id": str(content.author_id) if content.author_id else None,
            "created_at": content.created_at.isoformat() if content.created_at else None,
            "updated_at": content.updated_at.isoformat() if content.updated_at else None
        }

        # Add content metadata if exists (now in JSONB column)
        if content.metadata_json:
            payload["content_metadata"] = {
                "content_type": content.metadata_json.get("content_type"),
                "target_platform": content.metadata_json.get("target_platform"),
                "target_industry": content.metadata_json.get("target_industry"),
                "target_audience": content.metadata_json.get("target_audience"),
                "audience_size": content.metadata_json.get("audience_size"),
                "complexity_level": content.metadata_json.get("complexity_level"),
                "content_tone": content.metadata_json.get("content_tone"),
                "target_region": content.metadata_json.get("target_region"),
                "content_objectives": content.metadata_json.get("content_objectives"),
                "content_word_count": content.metadata_json.get("content_word_count")
            }

        # Add SEO data if exists
        if hasattr(content, 'seo_data') and content.seo_data:
            seo = content.seo_data
            payload["seo_data"] = {
                "content_primary_keywords": seo.content_primary_keywords,
                "content_secondary_keywords": seo.content_secondary_keywords,
                "content_meta_description": seo.content_meta_description,
                "content_search_intent": seo.content_search_intent
            }

        # Prepare workspace data
        workspace_data = {
            "id": str(workspace.id),
            "name": workspace.name,
            "slug": workspace.slug,
            "url": workspace.url
        }

        # Prepare user data (using workspace owner for now)
        user_data = {
            "id": str(workspace.user_id),  # user_id is the workspace owner
            "workspace_id": str(workspace.id)
        }

        # Initialize content state for LangGraph
        initial_state = ContentState(
            topics=topics_data,
            workspace=workspace_data,
            user=user_data,
            request_payload=payload,  # Changed from 'payload' to 'request_payload'
            relevant_context=[],  # Will be populated by workflow
            blog_feedback=""  # For future feedback iterations
        )

        # Add brand voice context if available
        if brand_voice:
            initial_state["brand_voice"] = {
                "about": brand_voice.about,
                "customer_profile": brand_voice.customer_profile,
                "selling_position": brand_voice.selling_position,
                "target_audience": brand_voice.target_audience,
                "brand_voice": brand_voice.brand_voice,
                "competitors": brand_voice.competitors,
                "content_strategy": brand_voice.content_strategy
            }

        return initial_state

    async def _update_content_with_generated(
        self,
        content_id: UUID,
        generated_blog: Any,
        thread_id: UUID
    ) -> None:
        """
        Update content record with generated data and thread ID.
        """
        result = await self.db.execute(
            select(Content).where(Content.id == content_id)
        )
        content = result.scalar_one_or_none()
        if not content:
            raise ResourceNotFoundException(
                resource_type="content",
                resource_id=str(content_id)
            )

        # Update content with generated data
        blog_content = None
        if hasattr(generated_blog, 'get_full_content'):
            blog_content = generated_blog.get_full_content()
        elif hasattr(generated_blog, 'content'):
            try:
                blog_content = generated_blog.content
            except Exception as e:
                logger.warning(f"Failed to access content property: {e}")

        if blog_content:
            content.body_markdown = blog_content
            logger.info(f"Updated body_markdown ({len(blog_content)} chars)")

            # Convert markdown to HTML
            try:
                html_content = markdown.markdown(
                    blog_content,
                    extensions=['extra', 'nl2br', 'sane_lists', 'tables', 'toc']
                )
                content.body_html = html_content
                logger.info(f"Updated body_html ({len(html_content)} chars)")
            except Exception as e:
                logger.warning(f"Failed to convert markdown to HTML: {e}")
        else:
            logger.warning(f"Generated blog content is empty or not found. Type: {type(generated_blog)}")

        if hasattr(generated_blog, 'title') and generated_blog.title:
            content.title = generated_blog.title

        # Update thread ID and status
        content.langgraph_thread_id = thread_id
        content.status = "ready"
        content.updated_at = datetime.now(timezone.utc)

        await self.db.flush()

        logger.info(f"Updated content {content_id} with LangGraph thread {thread_id}")

    async def _update_content_thread_id(
        self,
        content_id: UUID,
        thread_id: UUID,
        status: str = "generating"
    ) -> None:
        """
        Update only the thread ID and status for a content record.
        """
        result = await self.db.execute(
            select(Content).where(Content.id == content_id)
        )
        content = result.scalar_one_or_none()
        if content:
            content.langgraph_thread_id = thread_id
            content.status = status
            content.updated_at = datetime.now(timezone.utc)
            await self.db.flush()

    async def get_thread_history(
        self,
        thread_id: UUID
    ) -> Optional[Dict[str, Any]]:
        """
        Get the execution history for a specific thread.

        This is a placeholder for future implementation when we integrate
        with LangGraph's persistence layer.
        """
        # TODO: Implement when LangGraph persistence is configured
        logger.info(f"Thread history requested for {thread_id}")
        return {
            "thread_id": str(thread_id),
            "history": [],
            "message": "Thread history tracking will be implemented with LangGraph persistence"
        }

    async def _send_generation_started_email(
        self,
        content_id: UUID,
        workspace_id: UUID,
        content_data: Dict[str, Any]
    ) -> None:
        """Send email notification when content generation starts using professional template."""
        from emails.templates.content.content_generation_started import render_content_generation_started_email
        import os

        email_service = EmailService(self.db)

        content = content_data.get("content")
        workspace = content_data.get("workspace")
        user_id = content.created_by_user_id

        # Fetch user details
        result = await self.db.execute(select(Users).where(Users.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            logger.warning(f"User {user_id} not found, skipping email")
            return

        # Build content URL
        frontend_url = settings.FRONTEND_URL
        content_url = f"{frontend_url}/w/{workspace.slug}/content/{content_id}"

        # Render professional email
        user_name = user.first_name or user.username or user.email.split("@")[0]
        html_content = render_content_generation_started_email(
            user_name=user_name,
            content_title=content.title,
            content_type=content.content_format or 'Blog Post',
            workspace_name=workspace.name,
            content_url=content_url,
            frontend_url=frontend_url
        )

        await email_service.send_email(
            to=user.email,
            subject=f"Content Generation Started - {content.title}",
            html=html_content,
            user_id=user_id,
            workspace_id=workspace_id,
            template_type="content_generation_started"
        )

    async def _send_generation_completed_email(
        self,
        content_id: UUID,
        workspace_id: UUID,
        content_data: Dict[str, Any],
        generated_blog: Any
    ) -> None:
        """Send email notification when content generation completes using professional template."""
        from emails.templates.content.content_generation_completed import render_content_generation_completed_email
        import os

        email_service = EmailService(self.db)

        content = content_data.get("content")
        workspace = content_data.get("workspace")
        user_id = content.created_by_user_id

        # Fetch user details
        result = await self.db.execute(select(Users).where(Users.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            logger.warning(f"User {user_id} not found, skipping email")
            return

        # Calculate word count
        word_count = len(generated_blog.content.split()) if hasattr(generated_blog, 'content') else 0

        # Extract first 200 chars for excerpt
        content_body = generated_blog.content if hasattr(generated_blog, 'content') else ""
        content_excerpt = content_body[:200] if len(content_body) > 200 else content_body

        # Build content URL
        frontend_url = settings.FRONTEND_URL
        content_url = f"{frontend_url}/w/{workspace.slug}/content/{content_id}"

        # Render professional email
        user_name = user.first_name or user.username or user.email.split("@")[0]
        html_content = render_content_generation_completed_email(
            user_name=user_name,
            content_title=content.title,
            content_excerpt=content_excerpt,
            content_url=content_url,
            generated_at=datetime.now(timezone.utc).strftime("%b %d, %Y %I:%M %p UTC"),
            word_count=word_count,
            ai_model="Claude 3.5 Sonnet",
            frontend_url=frontend_url
        )

        await email_service.send_email(
            to=user.email,
            subject=f"Your Content is Ready! - {content.title}",
            html=html_content,
            user_id=user_id,
            workspace_id=workspace_id,
            template_type="content_generation_completed"
        )

    async def _send_generation_failed_email(
        self,
        content_id: UUID,
        workspace_id: UUID,
        content_data: Dict[str, Any],
        error_message: str
    ) -> None:
        """Send email notification when content generation fails using professional template."""
        from emails.templates.content.content_generation_failed import render_content_generation_failed_email
        import os

        email_service = EmailService(self.db)

        content = content_data.get("content")
        workspace = content_data.get("workspace")
        user_id = content.created_by_user_id

        # Fetch user details
        result = await self.db.execute(select(Users).where(Users.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            logger.warning(f"User {user_id} not found, skipping email")
            return

        # Build URLs
        frontend_url = settings.FRONTEND_URL
        retry_url = f"{frontend_url}/w/{workspace.slug}/content/{content_id}"
        support_url = f"{frontend_url}/support"

        # Sanitize error message for user display
        user_friendly_error = error_message[:200] if len(error_message) > 200 else error_message

        # Render professional email
        user_name = user.first_name or user.username or user.email.split("@")[0]
        html_content = render_content_generation_failed_email(
            user_name=user_name,
            content_title=content.title,
            error_message=user_friendly_error,
            retry_url=retry_url,
            support_url=support_url,
            frontend_url=frontend_url
        )

        await email_service.send_email(
            to=user.email,
            subject=f"Content Generation Failed - {content.title}",
            html=html_content,
            user_id=user_id,
            workspace_id=workspace_id,
            template_type="content_generation_failed"
        )
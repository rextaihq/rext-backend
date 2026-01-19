"""
Background Task for Content Generation

Handles asynchronous content generation using LangGraph workflows.
Updates progress in real-time via ContentProgressService and SSE.
"""

import asyncio
from typing import Dict, Any
from uuid import UUID

from fastapi import BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from src.flow.service.process_manager import ProgressManager

from src.api.database.async_database import get_async_db
from src.services.notification_helper import schedule_if_allowed
from src.utils.logger import logger


async def run_content_generation_background(
    content_id: UUID,
    workspace_id: UUID,
    topic_id: UUID,
    user_id: UUID,
    background_tasks: BackgroundTasks
) -> None:
    """
    Background task to run content generation workflow.

    This function:
    1. Initializes progress tracking
    2. Runs LangGraph workflow
    3. Updates progress at each step
    4. Handles errors and marks as failed if needed
    5. Sends notifications to user on completion/failure

    Args:
        content_id: Content UUID
        workspace_id: Workspace UUID
        topic_id: Topic UUID
        user_id: User UUID for notifications
        background_tasks: FastAPI BackgroundTasks for scheduling notifications

    Note:
        This function runs in a background thread and should not block the API response.
    """
    logger.info(
        f"Starting background content generation for content {content_id}",
        extra={"workspace_id": str(workspace_id), "topic_id": str(topic_id), "user_id": str(user_id)}
    )

    # Get a new database session for this background task
    async for db in get_async_db():
        try:
            # Initialize progress manager for tracking workflow steps
            # Note: Progress tracking strategy:
            #   - DB updates: Only for stable states (init, completed, failed)
            #   - SSE events: Emitted for ALL intermediate steps (real-time frontend updates)
            progress_service = ProgressManager(db)

            # Initialize LangGraph content service
            langgraph_service = LangGraphContentService(db)

            try:
                # Run the content generation workflow with timeout (10 minutes)
                result = await asyncio.wait_for(
                    langgraph_service.generate_content_with_langgraph(
                        content_id=content_id,
                        workspace_id=workspace_id,
                        topic_id=topic_id,
                        thread_id=None,  # Will generate new thread ID
                        regenerate=False
                    ),
                    timeout=600.0  # 10 minutes timeout
                )

                logger.info(
                    f"Content generation completed successfully for {content_id}",
                    extra={"thread_id": result.get("thread_id")}
                )
                
                # Mark as completed
                await progress_service.mark_completed(
                    content_id=content_id,
                    message="Content generated successfully!"
                )

                # Commit the transaction
                await db.commit()

                # Send success notification to user
                await schedule_if_allowed(
                    db=db,
                    user_id=str(user_id),
                    background_tasks=background_tasks,
                    pref_flag="gen_completed",
                    message="Content generation completed successfully",
                    payload={
                        "content_id": str(content_id),
                        "type": "content",
                        "status": "completed"
                    },
                    workspace_id=str(workspace_id),
                )

            except asyncio.TimeoutError:
                error_message = "Content generation timed out after 10 minutes"
                logger.error(
                    f"Timeout error for {content_id}",
                    exc_info=True
                )

                # Mark as failed with timeout error
                await progress_service.mark_failed(
                    content_id=content_id,
                    error_message=error_message,
                    error_details={"error_type": "TimeoutError", "timeout_seconds": 600}
                )

                # Send timeout notification to user
                await schedule_if_allowed(
                    db=db,
                    user_id=str(user_id),
                    background_tasks=background_tasks,
                    pref_flag="gen_failed",
                    message="Content generation timed out after 10 minutes",
                    payload={
                        "content_id": str(content_id),
                        "type": "content",
                        "status": "timeout",
                        "error": error_message
                    },
                    workspace_id=str(workspace_id),
                )

                # Commit the failure state
                await db.commit()

            except Exception as workflow_error:
                logger.error(
                    f"Content generation failed for {content_id}: {str(workflow_error)}",
                    exc_info=True
                )
                
                # Mark as failed
                await progress_service.mark_failed(
                    content_id=content_id,
                    error_message=str(workflow_error),
                    error_details={"error_type": type(workflow_error).__name__}
                )

                # Send failure notification to user
                await schedule_if_allowed(
                    db=db,
                    user_id=str(user_id),
                    background_tasks=background_tasks,
                    pref_flag="gen_failed",
                    message=f"Content generation failed: {str(workflow_error)}",
                    payload={
                        "content_id": str(content_id),
                        "type": "content",
                        "status": "failed",
                        "error": str(workflow_error)
                    },
                    workspace_id=str(workspace_id),
                )

                # Commit the failure state
                await db.commit()

        except Exception as e:
            logger.error(
                f"Critical error in background content generation for {content_id}: {str(e)}",
                exc_info=True
            )
            
            # Send critical error notification to user
            try:
                await schedule_if_allowed(
                    db=db,
                    user_id=str(user_id),
                    background_tasks=background_tasks,
                    pref_flag="gen_failed",
                    message=f"Critical error in content generation: {str(e)}",
                    payload={
                        "content_id": str(content_id),
                        "type": "content",
                        "status": "critical_error",
                        "error": str(e)
                    },
                    workspace_id=str(workspace_id),
                )
                await db.commit()
            except Exception as notification_error:
                logger.error(
                    f"Failed to send error notification: {str(notification_error)}",
                    exc_info=True
                )
            
            await db.rollback()

        finally:
            await db.close()


# Removed trigger_content_generation - use run_content_generation_background directly
# BackgroundTasks can handle async functions natively in FastAPI

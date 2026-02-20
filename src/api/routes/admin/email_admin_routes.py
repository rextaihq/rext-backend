"""
Admin Email Management Routes

Endpoints for querying and managing failed emails.
"""
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from datetime import datetime, timezone, timedelta

from src.api.database.async_database import get_async_db
from src.api.models.email_models.email_log import EmailLog
from src.api.schema.admin_email_schema import AdminEmailLogResponse, ResendEmailRequest
from src.services.email_service import EmailService
from src.api.lib.logger import auto_logger
from src.utils.response_utils import success, error
from src.utils.route_decorators import require_permissions

logger = auto_logger()
router = APIRouter(prefix="/api/v1/admin/emails", tags=["Admin - Emails"])


# ============================================================================
# ENDPOINTS
# ============================================================================

@router.get("/failed")
@require_permissions("audit.read", workspace_scoped=False)
async def get_failed_emails(
    db: AsyncSession = Depends(get_async_db),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    days_back: int = Query(default=7, ge=1, le=90)
):
    """
    Get failed emails from the last N days.

    Requires permission: audit.read (admin only)

    Args:
        limit: Maximum number of results (default 50, max 200)
        offset: Number of results to skip
        days_back: Number of days to look back (default 7, max 90)

    Returns:
        List of failed email logs
    """
    try:
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_back)

        stmt = (
            select(EmailLog)
            .where(
                and_(
                    EmailLog.status == "failed",
                    EmailLog.created_at >= cutoff_date
                )
            )
            .order_by(EmailLog.created_at.desc())
            .limit(limit)
            .offset(offset)
        )

        result = await db.execute(stmt)
        failed_emails = result.scalars().all()

        # Count total failed emails in this period
        count_stmt = (
            select(EmailLog)
            .where(
                and_(
                    EmailLog.status == "failed",
                    EmailLog.created_at >= cutoff_date
                )
            )
        )
        count_result = await db.execute(count_stmt)
        total_count = len(count_result.scalars().all())

        logger.info(
            f"Retrieved {len(failed_emails)} failed emails",
            extra={"total_count": total_count, "days_back": days_back}
        )

        return success(
            data={
                "emails": [AdminEmailLogResponse.model_validate(email).model_dump() for email in failed_emails],
                "total": total_count,
                "limit": limit,
                "offset": offset,
                "days_back": days_back
            },
            message=f"Found {total_count} failed emails in the last {days_back} days"
        )

    except Exception as e:
        logger.error(f"Error retrieving failed emails: {str(e)}", exc_info=True)
        return error(
            message="Failed to retrieve failed emails",
            status_code=500
        )


@router.post("/{email_log_id}/resend")
@require_permissions("audit.read", workspace_scoped=False)
async def resend_single_email(
    email_log_id: UUID,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Resend a single failed email.

    Requires permission: audit.read (admin monitoring)

    Args:
        email_log_id: ID of the email log to resend

    Returns:
        Result of resend operation
    """
    try:
        # Get original email log
        stmt = select(EmailLog).where(EmailLog.id == email_log_id)
        result = await db.execute(stmt)
        original_email = result.scalar_one_or_none()

        if not original_email:
            raise HTTPException(status_code=404, detail=f"Email log {email_log_id} not found")

        logger.info(
            f"Resending email: {email_log_id}",
            extra={
                "to_email": original_email.to_email,
                "subject": original_email.subject,
                "original_status": original_email.status
            }
        )

        # Create email service
        email_service = EmailService(db)

        # Resend email (creates new log entry)
        if not original_email.html_content:
            raise HTTPException(
                status_code=422,
                detail="Original email content not available for resend. "
                       "Only emails sent after the html_content migration can be resent."
            )

        new_email_log = await email_service.send_email(
            to=original_email.to_email,
            subject=original_email.subject,
            html=original_email.html_content,
            from_email=original_email.from_email,
            workspace_id=original_email.workspace_id,
            user_id=original_email.user_id,
            template_type=original_email.template_type,
            tags={**(original_email.tags or {}), "resent_from": str(email_log_id)},
            retry_on_failure=True,
            auto_commit=True
        )

        return success(
            data={
                "original_email_id": str(email_log_id),
                "new_email_id": str(new_email_log.id),
                "new_status": new_email_log.status,
                "retry_count": new_email_log.retry_count
            },
            message=f"Email resent successfully with status: {new_email_log.status}"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resending email {email_log_id}: {str(e)}", exc_info=True)
        return error(
            message=f"Failed to resend email: {str(e)}",
            status_code=500
        )


@router.post("/resend-batch")
@require_permissions("audit.read", workspace_scoped=False)
async def resend_batch_emails(
    request: ResendEmailRequest,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Resend multiple failed emails in batch.

    Requires permission: audit.read (admin only)

    Args:
        request: List of email log IDs to resend

    Returns:
        Results of batch resend operation
    """
    try:
        if len(request.email_log_ids) > 100:
            raise HTTPException(status_code=400, detail="Maximum 100 emails can be resent at once")

        results = {
            "successful": [],
            "failed": []
        }

        email_service = EmailService(db)

        for email_log_id in request.email_log_ids:
            try:
                # Get original email log
                stmt = select(EmailLog).where(EmailLog.id == email_log_id)
                result = await db.execute(stmt)
                original_email = result.scalar_one_or_none()

                if not original_email:
                    results["failed"].append({
                        "id": str(email_log_id),
                        "error": "Email log not found"
                    })
                    continue

                # Resend email
                if not original_email.html_content:
                    results["failed"].append({
                        "id": str(email_log_id),
                        "error": "Original email content not available for resend. "
                               "Only emails sent after the html_content migration can be resent."
                    })
                    continue

                new_email_log = await email_service.send_email(
                    to=original_email.to_email,
                    subject=original_email.subject,
                    html=original_email.html_content,
                    from_email=original_email.from_email,
                    workspace_id=original_email.workspace_id,
                    user_id=original_email.user_id,
                    template_type=original_email.template_type,
                    tags={**(original_email.tags or {}), "resent_from": str(email_log_id)},
                    retry_on_failure=True,
                    auto_commit=False  # Batch commit at end
                )

                results["successful"].append({
                    "original_id": str(email_log_id),
                    "new_id": str(new_email_log.id),
                    "status": new_email_log.status
                })

            except Exception as e:
                results["failed"].append({
                    "id": str(email_log_id),
                    "error": str(e)
                })

        # Commit all successful resends
        await db.commit()

        logger.info(
            f"Batch resend completed: {len(results['successful'])} successful, {len(results['failed'])} failed",
            extra=results
        )

        return success(
            data=results,
            message=f"Resent {len(results['successful'])}/{len(request.email_log_ids)} emails successfully"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in batch resend: {str(e)}", exc_info=True)
        await db.rollback()
        return error(
            message=f"Batch resend failed: {str(e)}",
            status_code=500
        )

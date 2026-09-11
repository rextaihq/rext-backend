"""
Account Recovery Service - admin-reviewed account recovery workflow.

A deleted or deactivated user files a recovery request from the recovery page.
It is stored as ``pending`` and surfaces in the admin "Account Recovery" tab.
An authorized admin approves it (which restores the account) or rejects it; the
requester is emailed the outcome.

Does NOT commit — the route's db_transaction_handler owns the transaction.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.api.config import get_settings
from src.api.middleware.exceptions import (
    ResourceNotFoundException,
    RextValidationException,
)
from src.api.models.enums import RecoveryRequestStatus
from src.api.models.user_models.account_recovery_request import AccountRecoveryRequest
from src.api.models.user_models.users import Users
from src.utils.logger import logger


class AccountRecoveryService:
    """Business logic for admin-reviewed account recovery requests."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------
    # Requester side
    # ------------------------------------------------------------------
    async def create_request(
        self,
        email: str,
        request_note: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> tuple[AccountRecoveryRequest, Users]:
        """
        Create a pending recovery request for a recoverable account.

        Raises so the caller can keep its response identical either way
        (the public endpoint must not leak whether an address has an account).

        Raises:
            ResourceNotFoundException: no account for that email
            RextValidationException: account is active, or past its retention window
        """
        settings = get_settings()
        normalized = email.strip().lower()

        user = (
            await self.db.execute(select(Users).where(Users.email == normalized))
        ).scalar_one_or_none()
        if not user:
            raise ResourceNotFoundException(resource_type="user", resource_id=email)

        retention_started_at = user.deleted_at or user.deactivated_at
        is_recoverable = user.is_deleted or user.status == "inactive"
        if not is_recoverable or not retention_started_at:
            raise RextValidationException(
                "This account is currently active and does not require recovery."
            )
        if user.status == "anonymized":
            raise RextValidationException(
                "This account has been permanently deleted and cannot be recovered."
            )

        restore_deadline = retention_started_at + timedelta(
            days=settings.USER_DELETION_RETENTION_DAYS
        )
        if datetime.now(timezone.utc) >= restore_deadline:
            raise RextValidationException(
                "Account recovery period has expired. The account is scheduled for permanent deletion."
            )

        # Reuse an existing open request rather than stacking duplicates.
        existing = (
            await self.db.execute(
                select(AccountRecoveryRequest).where(
                    AccountRecoveryRequest.email == normalized,
                    AccountRecoveryRequest.status == RecoveryRequestStatus.PENDING.value,
                )
            )
        ).scalar_one_or_none()
        if existing:
            logger.info(f"Reusing open recovery request {existing.id} for {normalized}")
            return existing, user

        req = AccountRecoveryRequest(
            user_id=user.id,
            email=normalized,
            status=RecoveryRequestStatus.PENDING.value,
            request_note=(request_note or None),
            requested_ip=ip_address,
            requested_user_agent=(user_agent or None),
        )
        self.db.add(req)
        await self.db.flush()
        logger.info(f"Account recovery request {req.id} created for user {user.id}")
        return req, user

    # ------------------------------------------------------------------
    # Admin side
    # ------------------------------------------------------------------
    async def list_requests(
        self,
        status: Optional[str] = None,
        page: int = 1,
        per_page: int = 50,
        search: Optional[str] = None,
    ) -> dict:
        """Paginated list of recovery requests for the admin tab."""
        base = select(AccountRecoveryRequest).options(
            selectinload(AccountRecoveryRequest.user),
            selectinload(AccountRecoveryRequest.reviewed_by),
        )

        if status and status != "all":
            if status not in {s.value for s in RecoveryRequestStatus}:
                raise RextValidationException(f"Invalid status filter: {status}")
            base = base.where(AccountRecoveryRequest.status == status)

        if search:
            term = f"%{search.strip().lower()}%"
            base = base.where(func.lower(AccountRecoveryRequest.email).like(term))

        total = (
            await self.db.execute(select(func.count()).select_from(base.subquery()))
        ).scalar() or 0

        page = max(1, page)
        per_page = min(max(1, per_page), 100)
        rows = (
            (
                await self.db.execute(
                    base.order_by(AccountRecoveryRequest.created_at.desc())
                    .offset((page - 1) * per_page)
                    .limit(per_page)
                )
            )
            .scalars()
            .all()
        )

        total_pages = (total + per_page - 1) // per_page if total else 0
        return {
            "requests": [self._serialize(r) for r in rows],
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": total,
                "total_pages": total_pages,
                "has_next": page < total_pages,
                "has_prev": page > 1,
            },
        }

    async def status_counts(self) -> dict:
        """Counts per status, for the tab badges."""
        rows = (
            await self.db.execute(
                select(AccountRecoveryRequest.status, func.count()).group_by(
                    AccountRecoveryRequest.status
                )
            )
        ).all()
        counts = {s.value: 0 for s in RecoveryRequestStatus}
        for status_value, count in rows:
            counts[status_value] = count
        counts["all"] = sum(counts[s.value] for s in RecoveryRequestStatus)
        return counts

    async def _get_pending_or_404(self, request_id: UUID) -> AccountRecoveryRequest:
        req = (
            await self.db.execute(
                select(AccountRecoveryRequest)
                .options(
                    selectinload(AccountRecoveryRequest.user),
                    selectinload(AccountRecoveryRequest.reviewed_by),
                )
                .where(AccountRecoveryRequest.id == request_id)
            )
        ).scalar_one_or_none()
        if not req:
            raise ResourceNotFoundException(
                resource_type="account recovery request", resource_id=str(request_id)
            )
        if req.status != RecoveryRequestStatus.PENDING.value:
            raise RextValidationException(f"This request has already been {req.status}.")
        return req

    async def approve(
        self, request_id: UUID, admin_id: UUID, review_note: Optional[str] = None
    ) -> AccountRecoveryRequest:
        """Approve a pending request and restore the account."""
        from src.services.user_service import UserService

        req = await self._get_pending_or_404(request_id)

        if not req.user_id:
            raise RextValidationException("The account for this request no longer exists.")

        user = req.user or await UserService(self.db).get_user_by_id(req.user_id)
        if user.status == "anonymized":
            raise RextValidationException(
                "This account has been permanently deleted and cannot be restored."
            )

        # Restore even if the retention window has since lapsed — an admin
        # approving is a deliberate override of the automatic cleanup.
        user.status = "active"
        user.deleted_at = None
        user.deactivated_at = None
        user.updated_at = datetime.now(timezone.utc)
        self.db.add(user)

        req.status = RecoveryRequestStatus.APPROVED.value
        req.review_note = review_note or None
        req.reviewed_at = datetime.now(timezone.utc)
        req.reviewed_by = await self._load_user(admin_id)
        self.db.add(req)
        await self.db.flush()

        logger.info(
            f"Recovery request {request_id} approved by {admin_id}; user {user.id} restored"
        )
        return req

    async def reject(
        self, request_id: UUID, admin_id: UUID, review_note: Optional[str] = None
    ) -> AccountRecoveryRequest:
        """Reject a pending request. The account stays deleted."""
        req = await self._get_pending_or_404(request_id)
        req.status = RecoveryRequestStatus.REJECTED.value
        req.review_note = review_note or None
        req.reviewed_at = datetime.now(timezone.utc)
        req.reviewed_by = await self._load_user(admin_id)
        self.db.add(req)
        await self.db.flush()
        logger.info(f"Recovery request {request_id} rejected by {admin_id}")
        return req

    async def _load_user(self, user_id: UUID) -> Optional[Users]:
        """
        Fetch a user into the session so assigning it to a relationship does not
        trigger an async lazy load later (SQLAlchemy raises MissingGreenlet).
        """
        return (
            await self.db.execute(select(Users).where(Users.id == user_id))
        ).scalar_one_or_none()

    # ------------------------------------------------------------------
    @staticmethod
    def _rel(obj, name):
        """Return a loaded relationship value, or None if it was never loaded.

        _serialize runs inside the request's async context where touching an
        unloaded relationship would raise, so anything not eager-loaded is
        simply treated as absent.
        """
        from sqlalchemy import inspect as sa_inspect

        try:
            if name in sa_inspect(obj).unloaded:
                return None
        except Exception:
            return None
        return getattr(obj, name, None)

    @classmethod
    def _serialize(cls, req: AccountRecoveryRequest) -> dict:
        user = cls._rel(req, "user")
        reviewer = cls._rel(req, "reviewed_by")
        return {
            "id": str(req.id),
            "user_id": str(req.user_id) if req.user_id else None,
            "email": req.email,
            "status": req.status,
            "request_note": req.request_note,
            "review_note": req.review_note,
            "requested_ip": req.requested_ip,
            "created_at": req.created_at.isoformat() if req.created_at else None,
            "reviewed_at": req.reviewed_at.isoformat() if req.reviewed_at else None,
            "reviewed_by": (
                {
                    "id": str(reviewer.id),
                    "full_name": reviewer.full_name,
                    "email": reviewer.email,
                }
                if reviewer
                else None
            ),
            "user": (
                {
                    "id": str(user.id),
                    "full_name": user.full_name,
                    "display_name": user.display_name,
                    "email": user.email,
                    "status": user.status,
                    "deleted_at": user.deleted_at.isoformat() if user.deleted_at else None,
                    "deactivated_at": (
                        user.deactivated_at.isoformat() if user.deactivated_at else None
                    ),
                }
                if user
                else None
            ),
        }

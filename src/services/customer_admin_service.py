"""
Customer Admin Service - Business Logic for Customer Management

This service encapsulates all business logic related to administrative
customer management operations.

Responsibilities:
- Customer listing with filtering and pagination
- Customer detail retrieval with related data
- Customer account actions (activate, deactivate, etc.)
- Customer notes management
- Usage metrics aggregation

Does NOT:
- Handle HTTP requests/responses (that's routes)
- Commit transactions (that's decorators)
- Check authentication (that's decorators)
"""

from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.models.subscription_models.subscriptions import UserSubscription
from src.api.models.subscription_models.plans import SubscriptionPlan
from src.api.models.user_models.users import Users
from src.api.models.workspace_models.workspace_model import WorkspaceModel
from src.api.models.content_models.content import Content
from src.api.models.knowledge_models.knowledge_model import KnowledgeBase
from src.api.models.admin_models.customer_note import CustomerNote
from src.api.middleware.exceptions import ResourceNotFoundException, RextValidationException
from src.utils.logger import logger


class CustomerAdminService:
    """Service for administrative customer management operations"""

    def __init__(self, db: AsyncSession):
        """
        Initialize CustomerAdminService.

        Args:
            db: Async database session
        """
        self.db = db

    async def list_customers(
        self,
        page: int = 1,
        per_page: int = 50,
        search: Optional[str] = None,
        status: Optional[str] = None,
        plan_id: Optional[UUID] = None,
        sort_by: str = "created_at",
        sort_order: str = "desc"
    ) -> Dict[str, Any]:
        """
        List customers with filtering and pagination.

        Args:
            page: Page number
            per_page: Items per page
            search: Search by name or email
            status: Filter by subscription status
            plan_id: Filter by plan ID
            sort_by: Sort field
            sort_order: Sort order (asc/desc)

        Returns:
            Dict with customers list and pagination metadata
        """
        # Build query
        query = (
            select(
                Users.id,
                Users.email,
                Users.display_name,
                Users.created_at,
                Users.status,
                Users.last_login_at,
                UserSubscription.id.label("subscription_id"),
                func.count(WorkspaceModel.id).label("workspaces_count")
            )
            .outerjoin(UserSubscription, and_(
                UserSubscription.user_id == Users.id,
                UserSubscription.status.in_(["active", "trial"])
            ))
            .outerjoin(WorkspaceModel, WorkspaceModel.user_id == Users.id)
            .group_by(
                Users.id,
                Users.email,
                Users.display_name,
                Users.created_at,
                Users.status,
                Users.last_login_at,
                UserSubscription.id
            )
        )

        # Apply search filter
        if search:
            search_filter = or_(
                Users.email.ilike(f"%{search}%"),
                Users.display_name.ilike(f"%{search}%")
            )
            query = query.where(search_filter)

        # Apply status filter
        if status:
            if status == "free":
                query = query.where(UserSubscription.id.is_(None))
            else:
                query = query.where(UserSubscription.status == status)

        # Apply plan filter
        if plan_id:
            query = query.where(UserSubscription.plan_id == plan_id)

        # Count total before pagination
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        # Apply sorting
        sort_column = getattr(Users, sort_by, Users.created_at)
        if sort_order == "desc":
            query = query.order_by(sort_column.desc())
        else:
            query = query.order_by(sort_column.asc())

        # Apply pagination
        offset = (page - 1) * per_page
        query = query.offset(offset).limit(per_page)

        # Execute query
        result = await self.db.execute(query)
        rows = result.all()

        # Format response
        customers = []
        for row in rows:
            # Get subscription details if exists
            subscription_info = None
            if row.subscription_id:
                subscription_info = await self._get_subscription_info(row.subscription_id)

            customers.append({
                "user_id": str(row.id),
                "name": row.display_name or row.email,
                "email": row.email,
                "subscription": subscription_info,
                "workspaces_count": row.workspaces_count,
                "is_active": row.status == "active",
                "status": row.status,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "last_active": row.last_login_at.isoformat() if row.last_login_at else None
            })

        # Calculate pagination
        total_pages = (total + per_page - 1) // per_page

        logger.info(f"Listed {len(customers)} customers (page {page}/{total_pages})")

        return {
            "customers": customers,
            "pagination": {
                "total": total,
                "page": page,
                "per_page": per_page,
                "total_pages": total_pages
            }
        }

    async def get_customer_detail(self, user_id: UUID) -> Dict[str, Any]:
        """
        Get detailed customer information.

        Args:
            user_id: User UUID

        Returns:
            Dict with customer details, subscription, workspaces, usage, etc.

        Raises:
            ResourceNotFoundException: If user not found
        """
        # Get user
        user_query = select(Users).where(Users.id == user_id)
        user_result = await self.db.execute(user_query)
        user = user_result.scalar_one_or_none()

        if not user:
            raise ResourceNotFoundException(
                resource_type="User",
                resource_id=str(user_id)
            )

        # Get subscription
        subscription = await self._get_user_subscription(user_id)

        # Get workspaces
        workspaces = await self._get_user_workspaces(user_id)

        # Get usage metrics
        usage = None
        if subscription:
            from src.services.usage_tracking_service import UsageTrackingService
            usage_service = UsageTrackingService(self.db)
            usage = await usage_service.get_usage_metrics(str(user_id))

        # Activity summary
        activity_summary = await self._get_activity_summary(user)

        # Get recent audit events
        from src.services.audit_service import AuditService
        audit_service = AuditService(self.db)
        audit_events = await audit_service.get_recent_user_events(str(user_id), limit=10)

        # Get customer notes
        notes = await self._get_customer_notes(user_id)

        logger.info(f"Retrieved customer detail for user {user_id}")

        return {
            "user": {
                "id": str(user.id),
                "email": user.email,
                "display_name": user.display_name,
                "is_active": user.status == "active",
                "status": user.status,
                "created_at": user.created_at.isoformat() if user.created_at else None,
                "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None
            },
            "subscription": subscription,
            "workspaces": workspaces,
            "usage": usage,
            "activity_summary": activity_summary,
            "audit_events": audit_events,
            "notes": notes
        }

    async def perform_customer_action(
        self,
        user_id: UUID,
        action: str,
        reason: str,
        metadata: Dict[str, Any],
        admin_user_id: str
    ) -> Dict[str, Any]:
        """
        Perform administrative action on customer account.

        Args:
            user_id: User UUID
            action: Action to perform
            reason: Reason for action
            metadata: Additional metadata
            admin_user_id: Admin user ID performing the action

        Returns:
            Dict with action result

        Raises:
            ResourceNotFoundException: If user not found
            RextValidationException: If action invalid
        """
        # Get user
        user = await self._get_user(user_id)

        result = {}
        audit_details = {
            "reason": reason,
            "metadata": metadata
        }

        if action == "deactivate":
            if user.status != "active":
                raise RextValidationException("User is already deactivated")
            audit_details["previous_status"] = user.status
            user.status = "deactivated"
            user.deactivated_at = datetime.now(timezone.utc)
            result = {"status": "deactivated"}

        elif action == "activate":
            if user.status == "active":
                raise RextValidationException("User is already active")
            audit_details["previous_status"] = user.status
            user.status = "active"
            user.deactivated_at = None
            result = {"status": "activated"}

        elif action == "reset_usage":
            sub = await self._get_active_subscription(user_id)
            if not sub:
                raise ResourceNotFoundException("No active subscription found", "subscription", str(user_id))
            audit_details["previous_api_calls"] = sub.current_api_calls
            sub.current_api_calls = 0
            sub.usage_reset_date = datetime.now(timezone.utc)
            result = {"status": "usage_reset", "new_api_calls": 0}

        elif action == "extend_trial":
            sub = await self._get_trial_subscription(user_id)
            if not sub:
                raise ResourceNotFoundException("No trial subscription found", "subscription", str(user_id))

            extension_days = metadata.get("days", 7)
            old_trial_end = sub.trial_end_date
            sub.trial_end_date = sub.trial_end_date + timedelta(days=extension_days)

            audit_details["old_trial_end"] = old_trial_end.isoformat() if old_trial_end else None
            audit_details["new_trial_end"] = sub.trial_end_date.isoformat()
            audit_details["extension_days"] = extension_days

            result = {
                "status": "trial_extended",
                "new_trial_end": sub.trial_end_date.isoformat()
            }

        elif action == "cancel_subscription":
            sub = await self._get_active_subscription(user_id)
            if not sub:
                raise ResourceNotFoundException("No active subscription found", "subscription", str(user_id))

            audit_details["previous_status"] = sub.status.value
            sub.status = "cancelled"
            sub.cancelled_at = datetime.now(timezone.utc)
            result = {"status": "subscription_cancelled"}

        else:
            raise RextValidationException(f"Invalid action: {action}")

        # Log to audit
        from src.services.audit_service import AuditService
        audit_service = AuditService(self.db)
        await audit_service.log_admin_action(
            admin_id=admin_user_id,
            action=action,
            entity_type="user",
            entity_id=str(user_id),
            details=audit_details,
            db=self.db
        )

        logger.info(f"Customer action '{action}' performed on user {user_id} by admin {admin_user_id}")

        return result

    async def add_customer_note(
        self,
        user_id: UUID,
        admin_user_id: UUID,
        note: str,
        category: str
    ) -> Dict[str, Any]:
        """
        Add internal note to customer account.

        Args:
            user_id: User UUID
            admin_user_id: Admin user UUID
            note: Note text
            category: Note category

        Returns:
            Dict with created note

        Raises:
            ResourceNotFoundException: If user not found
        """
        # Verify user exists
        await self._get_user(user_id)

        # Create note
        note_obj = CustomerNote(
            user_id=user_id,
            admin_id=admin_user_id,
            note=note,
            category=category
        )
        self.db.add(note_obj)
        await self.db.flush()
        await self.db.refresh(note_obj)

        # Log to audit
        from src.services.audit_service import AuditService
        audit_service = AuditService(self.db)
        await audit_service.log_admin_action(
            admin_id=str(admin_user_id),
            action="add_customer_note",
            entity_type="user",
            entity_id=str(user_id),
            details={"category": category},
            db=self.db
        )

        logger.info(f"Customer note added for user {user_id} by admin {admin_user_id}")

        return {
            "id": str(note_obj.id),
            "note": note_obj.note,
            "category": note_obj.category,
            "created_at": note_obj.created_at.isoformat() if note_obj.created_at else None
        }

    # ========================================================================
    # Private Helper Methods
    # ========================================================================

    async def _get_subscription_info(self, subscription_id: UUID) -> Optional[Dict[str, Any]]:
        """Get subscription info with MRR calculation."""
        sub_query = select(UserSubscription).where(UserSubscription.id == subscription_id)
        sub_result = await self.db.execute(sub_query)
        sub = sub_result.scalar_one_or_none()

        if not sub:
            return None

        plan_query = select(SubscriptionPlan).where(SubscriptionPlan.id == sub.plan_id)
        plan_result = await self.db.execute(plan_query)
        plan = plan_result.scalar_one_or_none()

        mrr = 0
        if plan:
            if sub.billing_period == "monthly":
                mrr = float(plan.price_monthly)
            else:
                mrr = float(plan.price_yearly) / 12

        return {
            "plan_name": plan.display_name if plan else "Unknown",
            "status": sub.status.value,
            "mrr": round(mrr, 2)
        }

    async def _get_user_subscription(self, user_id: UUID) -> Optional[Dict[str, Any]]:
        """Get user subscription details."""
        sub_query = (
            select(UserSubscription)
            .where(
                UserSubscription.user_id == user_id,
                UserSubscription.status.in_(["active", "trial"])
            )
        )
        sub_result = await self.db.execute(sub_query)
        sub = sub_result.scalar_one_or_none()

        if not sub:
            return None

        plan_query = select(SubscriptionPlan).where(SubscriptionPlan.id == sub.plan_id)
        plan_result = await self.db.execute(plan_query)
        plan = plan_result.scalar_one_or_none()

        return {
            "id": str(sub.id),
            "plan": {
                "id": str(plan.id) if plan else None,
                "name": plan.display_name if plan else "Unknown",
                "price_monthly": float(plan.price_monthly) if plan else 0,
                "price_yearly": float(plan.price_yearly) if plan else 0
            },
            "status": sub.status.value,
            "billing_period": sub.billing_period.value if sub.billing_period else None,
            "start_date": sub.start_date.isoformat() if sub.start_date else None,
            "end_date": sub.end_date.isoformat() if sub.end_date else None,
            "trial_end_date": sub.trial_end_date.isoformat() if sub.trial_end_date else None,
            "cancelled_at": sub.cancelled_at.isoformat() if sub.cancelled_at else None
        }

    async def _get_user_workspaces(self, user_id: UUID) -> List[Dict[str, Any]]:
        """Get user workspaces."""
        workspaces_query = (
            select(WorkspaceModel.id, WorkspaceModel.name, WorkspaceModel.created_at)
            .where(WorkspaceModel.user_id == user_id)
            .order_by(WorkspaceModel.created_at.desc())
        )
        workspaces_result = await self.db.execute(workspaces_query)
        workspaces_rows = workspaces_result.all()

        return [
            {
                "id": str(ws.id),
                "name": ws.name,
                "created_at": ws.created_at.isoformat() if ws.created_at else None
            }
            for ws in workspaces_rows
        ]

    async def _get_activity_summary(self, user: Users) -> Dict[str, Any]:
        """Get user activity summary."""
        content_count_query = select(func.count(Content.id)).join(
            WorkspaceModel, Content.workspace_id == WorkspaceModel.id
        ).where(WorkspaceModel.user_id == user.id)
        content_count_result = await self.db.execute(content_count_query)
        content_count = content_count_result.scalar() or 0

        kb_count_query = select(func.count(KnowledgeBase.id)).join(
            WorkspaceModel, KnowledgeBase.workspace_id == WorkspaceModel.id
        ).where(WorkspaceModel.user_id == user.id)
        kb_count_result = await self.db.execute(kb_count_query)
        kb_count = kb_count_result.scalar() or 0

        workspaces_count_query = select(func.count(WorkspaceModel.id)).where(
            WorkspaceModel.user_id == user.id
        )
        workspaces_count_result = await self.db.execute(workspaces_count_query)
        workspaces_count = workspaces_count_result.scalar() or 0

        return {
            "last_login": user.last_login_at.isoformat() if user.last_login_at else None,
            "total_content_created": content_count,
            "total_knowledge_items": kb_count,
            "workspaces_count": workspaces_count
        }

    async def _get_customer_notes(self, user_id: UUID) -> List[Dict[str, Any]]:
        """Get customer notes."""
        notes_query = (
            select(CustomerNote, Users.email.label("admin_email"))
            .join(Users, CustomerNote.admin_id == Users.id)
            .where(CustomerNote.user_id == user_id)
            .order_by(CustomerNote.created_at.desc())
            .limit(20)
        )
        notes_result = await self.db.execute(notes_query)
        notes_rows = notes_result.all()

        return [
            {
                "id": str(note.id),
                "note": note.note,
                "category": note.category,
                "admin_email": admin_email,
                "created_at": note.created_at.isoformat() if note.created_at else None
            }
            for note, admin_email in notes_rows
        ]

    async def _get_user(self, user_id: UUID) -> Users:
        """Get user or raise 404."""
        user_query = select(Users).where(Users.id == user_id)
        user_result = await self.db.execute(user_query)
        user = user_result.scalar_one_or_none()

        if not user:
            raise ResourceNotFoundException(
                resource_type="User",
                resource_id=str(user_id)
            )

        return user

    async def _get_active_subscription(self, user_id: UUID) -> Optional[UserSubscription]:
        """Get active subscription."""
        sub_query = (
            select(UserSubscription)
            .where(
                UserSubscription.user_id == user_id,
                UserSubscription.status.in_(["active", "trial"])
            )
        )
        sub_result = await self.db.execute(sub_query)
        return sub_result.scalar_one_or_none()

    async def _get_trial_subscription(self, user_id: UUID) -> Optional[UserSubscription]:
        """Get trial subscription."""
        sub_query = (
            select(UserSubscription)
            .where(
                UserSubscription.user_id == user_id,
                UserSubscription.status == "trial"
            )
        )
        sub_result = await self.db.execute(sub_query)
        return sub_result.scalar_one_or_none()

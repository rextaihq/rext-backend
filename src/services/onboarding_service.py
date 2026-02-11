"""Onboarding service for managing user onboarding flow."""

from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.models.user_models.onboarding import UserOnboarding
from src.api.models.user_models.users import Users


class OnboardingService:
    """Service for managing user onboarding."""

    @staticmethod
    async def get_or_create_onboarding(db: AsyncSession, user_id: UUID) -> UserOnboarding:
        """
        Get user onboarding status or create if doesn't exist.

        Args:
            db: Database session
            user_id: User ID

        Returns:
            UserOnboarding object

        Raises:
            ValueError: If user doesn't exist in the database
        """
        stmt = select(UserOnboarding).where(UserOnboarding.user_id == user_id)
        result = await db.execute(stmt)
        onboarding = result.scalar_one_or_none()

        if not onboarding:
            # Verify user exists before creating onboarding record
            user_stmt = select(Users).where(Users.id == user_id)
            user_result = await db.execute(user_stmt)
            user = user_result.scalar_one_or_none()

            if not user:
                raise ValueError(f"User with ID {user_id} not found")

            # Create new onboarding record
            onboarding = UserOnboarding(
                id=uuid4(),
                user_id=user_id,
                completed=False,
                current_step=0,
                completed_steps=[],
                skipped_steps=[],
            )
            db.add(onboarding)
            await db.commit()
            await db.refresh(onboarding)

        return onboarding

    @staticmethod
    async def get_onboarding_status(db: AsyncSession, user_id: UUID) -> Optional[UserOnboarding]:
        """
        Get user onboarding status.

        Args:
            db: Database session
            user_id: User ID

        Returns:
            UserOnboarding object or None
        """
        stmt = select(UserOnboarding).where(UserOnboarding.user_id == user_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def complete_step(db: AsyncSession, user_id: UUID, step: int) -> UserOnboarding:
        """
        Mark a step as completed.

        Args:
            db: Database session
            user_id: User ID
            step: Step number to complete

        Returns:
            Updated UserOnboarding object
        """
        onboarding = await OnboardingService.get_or_create_onboarding(db, user_id)

        # Add to completed steps if not already there
        if step not in onboarding.completed_steps:
            onboarding.completed_steps = onboarding.completed_steps + [step]

        # Remove from skipped steps if present
        if step in onboarding.skipped_steps:
            onboarding.skipped_steps = [s for s in onboarding.skipped_steps if s != step]

        # Update current step to next incomplete step
        all_steps = [0, 1]  # Updated to 2 steps
        next_step = None
        for s in all_steps:
            if s not in onboarding.completed_steps and s not in onboarding.skipped_steps:
                next_step = s
                break

        if next_step is not None:
            onboarding.current_step = next_step
        else:
            # All steps completed or skipped
            onboarding.current_step = 1  # Last step
            onboarding.completed = True
            onboarding.completed_at = datetime.now(timezone.utc)

        await db.commit()
        await db.refresh(onboarding)
        return onboarding

    @staticmethod
    async def skip_step(db: AsyncSession, user_id: UUID, step: int) -> UserOnboarding:
        """
        Mark a step as skipped.

        Args:
            db: Database session
            user_id: User ID
            step: Step number to skip

        Returns:
            Updated UserOnboarding object
        """
        onboarding = await OnboardingService.get_or_create_onboarding(db, user_id)

        # Don't allow skipping required steps (0, 1)
        required_steps = [0, 1]
        if step in required_steps:
            raise ValueError(f"Cannot skip required step {step}")

        # Add to skipped steps if not already there
        if step not in onboarding.skipped_steps:
            onboarding.skipped_steps = onboarding.skipped_steps + [step]

        # Remove from completed steps if present
        if step in onboarding.completed_steps:
            onboarding.completed_steps = [s for s in onboarding.completed_steps if s != step]

        # Update current step to next incomplete step
        all_steps = [0, 1]
        next_step = None
        for s in all_steps:
            if s not in onboarding.completed_steps and s not in onboarding.skipped_steps:
                next_step = s
                break

        if next_step is not None:
            onboarding.current_step = next_step
        else:
            # All steps completed or skipped
            onboarding.current_step = 1
            onboarding.completed = True
            onboarding.completed_at = datetime.now(timezone.utc)

        await db.commit()
        await db.refresh(onboarding)
        return onboarding

    @staticmethod
    async def set_current_step(db: AsyncSession, user_id: UUID, step: int) -> UserOnboarding:
        """
        Set the current step (for navigation).

        Args:
            db: Database session
            user_id: User ID
            step: Step number to set as current

        Returns:
            Updated UserOnboarding object
        """
        onboarding = await OnboardingService.get_or_create_onboarding(db, user_id)
        onboarding.current_step = step
        await db.commit()
        await db.refresh(onboarding)
        return onboarding

    @staticmethod
    async def complete_onboarding(db: AsyncSession, user_id: UUID) -> UserOnboarding:
        """
        Mark onboarding as fully completed.

        Args:
            db: Database session
            user_id: User ID

        Returns:
            Updated UserOnboarding object
        """
        onboarding = await OnboardingService.get_or_create_onboarding(db, user_id)
        onboarding.completed = True
        onboarding.completed_at = datetime.now(timezone.utc)
        onboarding.current_step = 2

        # Mark all required steps as completed if not already
        required_steps = [0, 2]
        for step in required_steps:
            if step not in onboarding.completed_steps:
                onboarding.completed_steps = onboarding.completed_steps + [step]

        await db.commit()
        await db.refresh(onboarding)
        return onboarding

    @staticmethod
    async def reset_onboarding(db: AsyncSession, user_id: UUID) -> UserOnboarding:
        """
        Reset onboarding to start from beginning.

        Args:
            db: Database session
            user_id: User ID

        Returns:
            Reset UserOnboarding object
        """
        onboarding = await OnboardingService.get_or_create_onboarding(db, user_id)
        onboarding.completed = False
        onboarding.current_step = 0
        onboarding.completed_steps = []
        onboarding.skipped_steps = []
        onboarding.completed_at = None
        onboarding.started_at = datetime.now(timezone.utc)

        await db.commit()
        await db.refresh(onboarding)
        return onboarding

    @staticmethod
    async def should_show_onboarding(db: AsyncSession, user_id: UUID) -> bool:
        """
        Determine if onboarding should be shown to user.

        Only shows onboarding to organic signups (not invited users or admins).

        Args:
            db: Database session
            user_id: User ID

        Returns:
            True if onboarding should be shown, False otherwise
        """
        from src.api.models.workspace_models.workspace_member import WorkspaceMembers
        from src.api.models.user_models.user_roles import UserRole
        from src.api.models.user_models.roles import Role

        # Check if user is an invited user (has workspace membership with invitation_id)
        result = await db.execute(
            select(WorkspaceMembers).where(
                WorkspaceMembers.user_id == user_id
            )
        )
        memberships = result.scalars().all()

        # If user has any membership with an invitation_id, they're an invited user
        for membership in memberships:
            if membership.invitation_id is not None:
                return False  # Don't show onboarding to invited users

        # Check if user is an admin (high hierarchy level)
        result = await db.execute(
            select(Role)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(UserRole.user_id == user_id)
        )
        roles = result.scalars().all()

        # If user has admin role (hierarchy_level >= 90), don't show onboarding
        for role in roles:
            if role.hierarchy_level >= 90:
                return False  # Don't show onboarding to admins

        # Check onboarding status
        onboarding = await OnboardingService.get_onboarding_status(db, user_id)

        if not onboarding:
            return True  # New user, show onboarding

        if onboarding.completed:
            return False  # Already completed

        return True  # In progress, show onboarding

    @staticmethod
    async def update_marketing_data(
        db: AsyncSession,
        user_id: UUID,
        user_industry: str | None = None,
        user_role: str | None = None,
        user_goal: str | None = None,
        heard_from: str | None = None,
    ) -> UserOnboarding:
        """
        Update marketing data for user onboarding.

        Args:
            db: Database session
            user_id: User ID
            user_industry: User's industry
            user_role: User's role
            user_goal: User's primary goal
            heard_from: How user heard about us

        Returns:
            Updated UserOnboarding object
        """
        onboarding = await OnboardingService.get_or_create_onboarding(db, user_id)

        if user_industry is not None:
            onboarding.user_industry = user_industry
        if user_role is not None:
            onboarding.user_role = user_role
        if user_goal is not None:
            onboarding.user_goal = user_goal
        if heard_from is not None:
            onboarding.heard_from = heard_from

        await db.commit()
        await db.refresh(onboarding)
        return onboarding


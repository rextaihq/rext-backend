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
        """
        stmt = select(UserOnboarding).where(UserOnboarding.user_id == user_id)
        result = await db.execute(stmt)
        onboarding = result.scalar_one_or_none()

        if not onboarding:
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
        all_steps = [0, 1, 2, 3, 4, 5]
        next_step = None
        for s in all_steps:
            if s not in onboarding.completed_steps and s not in onboarding.skipped_steps:
                next_step = s
                break

        if next_step is not None:
            onboarding.current_step = next_step
        else:
            # All steps completed or skipped
            onboarding.current_step = 5  # Last step
            onboarding.completed = True
            onboarding.completed_at = datetime.utcnow()

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

        # Don't allow skipping required steps (0, 1, 5)
        required_steps = [0, 1, 5]
        if step in required_steps:
            raise ValueError(f"Cannot skip required step {step}")

        # Add to skipped steps if not already there
        if step not in onboarding.skipped_steps:
            onboarding.skipped_steps = onboarding.skipped_steps + [step]

        # Remove from completed steps if present
        if step in onboarding.completed_steps:
            onboarding.completed_steps = [s for s in onboarding.completed_steps if s != step]

        # Update current step to next incomplete step
        all_steps = [0, 1, 2, 3, 4, 5]
        next_step = None
        for s in all_steps:
            if s not in onboarding.completed_steps and s not in onboarding.skipped_steps:
                next_step = s
                break

        if next_step is not None:
            onboarding.current_step = next_step
        else:
            # All steps completed or skipped
            onboarding.current_step = 5
            onboarding.completed = True
            onboarding.completed_at = datetime.utcnow()

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
        onboarding.completed_at = datetime.utcnow()
        onboarding.current_step = 5

        # Mark all required steps as completed if not already
        required_steps = [0, 1, 5]
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
        onboarding.started_at = datetime.utcnow()

        await db.commit()
        await db.refresh(onboarding)
        return onboarding

    @staticmethod
    async def should_show_onboarding(db: AsyncSession, user_id: UUID) -> bool:
        """
        Determine if onboarding should be shown to user.

        Args:
            db: Database session
            user_id: User ID

        Returns:
            True if onboarding should be shown, False otherwise
        """
        onboarding = await OnboardingService.get_onboarding_status(db, user_id)

        if not onboarding:
            return True  # New user, show onboarding

        if onboarding.completed:
            return False  # Already completed

        return True  # In progress, show onboarding

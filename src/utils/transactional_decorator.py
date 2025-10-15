"""
Transactional Decorator - Automatic Transaction Management

This decorator provides automatic transaction management for service methods.
It handles commits, rollbacks, and ensures proper cleanup of database sessions.

Usage:
    @transactional
    async def my_service_method(self, ...):
        # Database operations here
        # Commit/rollback handled automatically

Features:
- Automatic commit on success
- Automatic rollback on exception
- Proper exception propagation
- Session cleanup
- Logging for debugging
"""

import functools
from typing import Callable, Any
from sqlalchemy.ext.asyncio import AsyncSession
from src.utils.logger import logger


def transactional(func: Callable) -> Callable:
    """
    Decorator for automatic transaction management.

    Wraps async functions to:
    1. Commit transaction on successful completion
    2. Rollback transaction on exception
    3. Ensure proper error propagation

    Args:
        func: Async function to wrap

    Returns:
        Wrapped async function with transaction management

    Example:
        class MyService:
            def __init__(self, db: AsyncSession):
                self.db = db

            @transactional
            async def create_user(self, email: str):
                user = User(email=email)
                self.db.add(user)
                await self.db.flush()
                return user
    """
    @functools.wraps(func)
    async def wrapper(*args, **kwargs) -> Any:
        # Extract db session from first argument (self) or kwargs
        db_session = None

        # Try to get from self.db (service instance)
        if args and hasattr(args[0], 'db') and isinstance(args[0].db, AsyncSession):
            db_session = args[0].db
        # Try to get from kwargs
        elif 'db' in kwargs and isinstance(kwargs['db'], AsyncSession):
            db_session = kwargs['db']

        if not db_session:
            # If no session found, just execute the function without transaction management
            logger.warning(
                f"@transactional decorator on {func.__name__}: No AsyncSession found, "
                "skipping transaction management"
            )
            return await func(*args, **kwargs)

        try:
            # Execute the function
            result = await func(*args, **kwargs)

            # Commit transaction on success
            await db_session.commit()
            logger.debug(f"Transaction committed for {func.__name__}")

            return result

        except Exception as e:
            # Rollback transaction on error
            await db_session.rollback()
            logger.error(
                f"Transaction rolled back for {func.__name__}: {str(e)}",
                exc_info=True
            )
            # Re-raise the exception to preserve error handling
            raise

    return wrapper


def transactional_method(auto_commit: bool = True):
    """
    Decorator factory for configurable transaction management.

    Args:
        auto_commit: If True, automatically commit. If False, leave transaction open.

    Returns:
        Decorator function

    Example:
        class MyService:
            @transactional_method(auto_commit=True)
            async def create_user(self, email: str):
                # Commits automatically
                pass

            @transactional_method(auto_commit=False)
            async def get_user(self, user_id: UUID):
                # Read-only, no commit
                pass
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            # Extract db session
            db_session = None

            if args and hasattr(args[0], 'db') and isinstance(args[0].db, AsyncSession):
                db_session = args[0].db
            elif 'db' in kwargs and isinstance(kwargs['db'], AsyncSession):
                db_session = kwargs['db']

            if not db_session:
                logger.warning(
                    f"@transactional_method decorator on {func.__name__}: No AsyncSession found"
                )
                return await func(*args, **kwargs)

            try:
                # Execute the function
                result = await func(*args, **kwargs)

                # Commit if auto_commit is True
                if auto_commit:
                    await db_session.commit()
                    logger.debug(f"Transaction committed for {func.__name__}")

                return result

            except Exception as e:
                # Rollback on error
                await db_session.rollback()
                logger.error(
                    f"Transaction rolled back for {func.__name__}: {str(e)}",
                    exc_info=True
                )
                raise

        return wrapper

    return decorator

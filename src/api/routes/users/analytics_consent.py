"""
The person's answer on usage analytics, stored on their account (rext-control task 712).

The dashboard asks (or, outside the EEA, doesn't have to) and keeps the answer in the
browser. It writes it here too, so the backend's own events know whether they may say who
(src/services/server_events.py), and so a new browser can read the answer back instead of
asking again.
"""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database.async_database import get_async_db
from src.api.middleware.exceptions import (
    RextAuthenticationException,
    RextAuthorizationException,
)
from src.api.models.user_models.users import Users
from src.api.schema.analytics_consent_schema import (
    AnalyticsConsentResponse,
    UpdateAnalyticsConsentRequest,
)
from src.api.schema.response_schemas import SuccessResponse
from src.api.security.dependencies import get_current_user
from src.utils.response_utils import success
from src.utils.route_decorators import db_transaction_handler

# No permission gates: both routes read and write the caller's own account only.
router = APIRouter()


def _stored(user: Users) -> dict:
    answered_at = user.analytics_consent_at
    return {
        "answer": user.analytics_consent,
        "region": user.analytics_region,
        "answered_at": answered_at.isoformat() if answered_at else None,
    }


async def _own_account(db: AsyncSession, current_user: dict, *, lock: bool = False) -> Users:
    user = await db.get(Users, UUID(current_user.get("identity")), with_for_update=lock)
    if user is None:
        raise RextAuthenticationException(message="Account not found")
    return user


@router.get("/analytics-consent", response_model=SuccessResponse[AnalyticsConsentResponse])
@db_transaction_handler("get analytics consent", auto_commit=False)
async def get_analytics_consent(
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """
    The caller's stored answer on usage analytics.
    """
    user = await _own_account(db, current_user)
    return success(
        data=_stored(user), request=request, message="Analytics consent retrieved successfully"
    )


@router.put("/analytics-consent", response_model=SuccessResponse[AnalyticsConsentResponse])
@db_transaction_handler("update analytics consent", auto_commit=True)
async def update_analytics_consent(
    request: Request,
    consent: UpdateAnalyticsConsentRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Store what the caller's browser holds: their answer and their region.

    An answer replaces the stored one. No answer (null) stores the region only and leaves a
    stored answer as it is: a browser that has forgotten a refusal must not undo it. The
    response is what is stored afterwards, so that browser can take the answer back.

    Refused while impersonating: the browser is then the admin's, and its answer and
    its region are not the customer's to have written on their account.
    """
    if current_user.get("is_impersonating"):
        raise RextAuthorizationException(
            message="The answer on usage analytics can't be changed while impersonating."
        )
    user = await _own_account(db, current_user, lock=True)
    user.analytics_region = consent.region
    if consent.answer is not None and consent.answer != user.analytics_consent:
        user.analytics_consent = consent.answer
        user.analytics_consent_at = datetime.now(timezone.utc)
    await db.flush()
    return success(
        data=_stored(user), request=request, message="Analytics consent updated successfully"
    )

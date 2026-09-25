"""Duplicate-integration guard for workspace site connections.

The same external site (e.g. a WordPress blog) must not be connected twice
within one workspace. Sites are compared on a normalized URL so that
`https://Example.com/`, `http://example.com` and `https://www.example.com`
all resolve to the same site.
"""

from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.middleware.exceptions import RextValidationException
from src.api.models import WorkspaceIntegration


def normalize_site_url(value: str | None) -> str:
    """Normalize a site URL for duplicate comparison.

    Lowercases the scheme and host, drops a leading ``www.``, strips default
    ports and trailing slashes. Empty input normalizes to ``""``.
    """
    raw = (value or "").strip()
    if not raw:
        return ""

    if "//" not in raw:
        raw = f"https://{raw}"

    parts = urlsplit(raw)
    host = (parts.netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]
    if host.endswith(":80") and parts.scheme == "http":
        host = host[: -3]
    if host.endswith(":443") and parts.scheme == "https":
        host = host[: -4]

    path = parts.path.rstrip("/")
    return urlunsplit((parts.scheme.lower(), host, path, "", ""))


async def ensure_no_duplicate_integration(
    db: AsyncSession,
    workspace_id,
    integration_type: str,
    site_url: str | None,
) -> None:
    """Raise a validation error if the workspace already has this site connected.

    Only active (non-soft-deleted) integrations count as duplicates. Existing
    rows store the raw URL the user entered, so both sides are compared in
    their normalized form.
    """
    normalized = normalize_site_url(site_url)
    if not normalized:
        return

    result = await db.execute(
        select(WorkspaceIntegration).where(
            WorkspaceIntegration.workspace_id == workspace_id,
            WorkspaceIntegration.integration_type == integration_type,
            WorkspaceIntegration.deleted_at.is_(None),
            WorkspaceIntegration.site_url.isnot(None),
        )
    )
    for existing in result.scalars().all():
        if normalize_site_url(existing.site_url) == normalized:
            raise RextValidationException(
                message=(
                    "This site is already connected to this workspace. "
                    "Remove the existing integration before connecting it again."
                ),
            )

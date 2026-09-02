"""
Account Creation IP Allowlist Service
====================================

Business logic for the admin-managed list of public IPs / CIDR ranges that are
allowed to bypass the per-device cap on creating multiple non-paid accounts
(see ``check_device_account_limit`` in ``src/api/routes/users/auth.py``).

Responsibilities:
- CRUD over ``account_creation_ip_allowlist`` rows (used by the admin API)
- Answering ``is_ip_allowlisted(client_ip)`` for the registration flow, with a
  short Redis cache so a signup never pays for more than one lookup

Does NOT:
- Handle HTTP requests/responses (routes)
- Commit transactions (the ``db_transaction_handler`` decorator does)
- Check authentication / admin role (the ``is_admin`` dependency does)
"""

from typing import List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.cache.redis_client import cache
from src.api.middleware.exceptions import (
    DuplicateResourceException,
    ResourceNotFoundException,
    RextValidationException,
)
from src.api.models.admin_models.account_creation_ip_allowlist import (
    AccountCreationIpAllowlist,
)
from src.utils.ip_allowlist import (
    ip_matches_allowlist,
    normalize_allowlist_value,
    reject_reason_for_egress_ip,
)
from src.utils.logger import logger

_UNSET = object()


class AccountCreationAllowlistService:
    """Service for managing and evaluating the account-creation IP allowlist."""

    #: Redis key holding the JSON list of active, normalized IP/CIDR strings.
    CACHE_KEY = "account_creation_ip_allowlist:active"
    CACHE_TTL_SECONDS = 300

    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------
    # Read path used by the registration flow
    # ------------------------------------------------------------------
    async def is_ip_allowlisted(self, client_ip: Optional[str]) -> bool:
        """
        Return True only when ``client_ip`` matches an **active** allowlist entry.

        ``client_ip`` must be the proxy-verified ``request.client.host`` value.
        Fails closed: no entries, unparseable IP, or a cache/DB hiccup all
        resolve to False so the per-device cap stays in force.
        """
        if not client_ip:
            return False
        try:
            entries = await self._active_ip_values()
        except Exception as exc:  # pragma: no cover - defensive, never disable the cap
            logger.error(f"Account-creation allowlist lookup failed, failing closed: {exc}")
            return False
        return ip_matches_allowlist(client_ip, entries)

    async def _active_ip_values(self) -> List[str]:
        """Active IP/CIDR strings, from Redis when warm, else the DB."""
        cached = await cache.get(self.CACHE_KEY)
        if isinstance(cached, list):
            return cached

        stmt = select(AccountCreationIpAllowlist.ip_address).where(
            AccountCreationIpAllowlist.is_active.is_(True)
        )
        result = await self.db.execute(stmt)
        values = [row[0] for row in result.all()]

        await cache.set(self.CACHE_KEY, values, ttl=self.CACHE_TTL_SECONDS)
        return values

    async def _invalidate_cache(self) -> None:
        await cache.delete(self.CACHE_KEY)

    # ------------------------------------------------------------------
    # CRUD used by the admin API
    # ------------------------------------------------------------------
    async def list_entries(
        self, include_inactive: bool = True
    ) -> List[AccountCreationIpAllowlist]:
        stmt = select(AccountCreationIpAllowlist).order_by(
            AccountCreationIpAllowlist.created_at.desc()
        )
        if not include_inactive:
            stmt = stmt.where(AccountCreationIpAllowlist.is_active.is_(True))
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_entry(self, entry_id: UUID) -> AccountCreationIpAllowlist:
        entry = await self.db.get(AccountCreationIpAllowlist, entry_id)
        if entry is None:
            raise ResourceNotFoundException(
                resource_type="account creation allowlist entry",
                resource_id=str(entry_id),
            )
        return entry

    async def add_entry(
        self,
        ip_address: str,
        label: Optional[str] = None,
        admin_user_id: Optional[UUID] = None,
        is_active: bool = True,
    ) -> AccountCreationIpAllowlist:
        """Create a new allowlist entry from a raw IP/CIDR string."""
        normalized = self._normalize(ip_address)

        existing = await self.db.execute(
            select(AccountCreationIpAllowlist).where(
                AccountCreationIpAllowlist.ip_address == normalized
            )
        )
        if existing.scalar_one_or_none() is not None:
            raise DuplicateResourceException(
                resource_type="account creation allowlist entry",
                conflicting_field="ip_address",
                conflicting_value=normalized,
            )

        entry = AccountCreationIpAllowlist(
            ip_address=normalized,
            label=(label.strip() or None) if label else None,
            is_active=is_active,
            created_by=admin_user_id,
        )
        self.db.add(entry)
        try:
            await self.db.flush()
        except IntegrityError as exc:  # lost a race to insert the same IP
            # Transaction rollback is owned by the db_transaction_handler
            # decorator, which re-raises this for the exception middleware.
            raise DuplicateResourceException(
                resource_type="account creation allowlist entry",
                conflicting_field="ip_address",
                conflicting_value=normalized,
            ) from exc

        await self._invalidate_cache()
        logger.info(
            f"Account-creation allowlist entry added: {normalized} "
            f"(active={is_active}) by admin {admin_user_id}"
        )
        return entry

    async def update_entry(
        self,
        entry_id: UUID,
        label: object = _UNSET,
        is_active: object = _UNSET,
    ) -> AccountCreationIpAllowlist:
        """Patch the label and/or the active flag of an entry."""
        entry = await self.get_entry(entry_id)

        if label is not _UNSET:
            entry.label = (label.strip() or None) if isinstance(label, str) else None
        if is_active is not _UNSET:
            entry.is_active = bool(is_active)

        await self.db.flush()
        await self._invalidate_cache()
        logger.info(
            f"Account-creation allowlist entry {entry_id} updated "
            f"(active={entry.is_active})"
        )
        return entry

    async def delete_entry(self, entry_id: UUID) -> None:
        entry = await self.get_entry(entry_id)
        await self.db.delete(entry)
        await self.db.flush()
        await self._invalidate_cache()
        logger.info(f"Account-creation allowlist entry {entry_id} deleted")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _normalize(ip_address: str) -> str:
        try:
            normalized = normalize_allowlist_value(ip_address)
        except ValueError as exc:
            raise RextValidationException(
                message="Invalid IP address or CIDR range",
                field_errors={"ip_address": [str(exc)]},
            ) from exc

        reason = reject_reason_for_egress_ip(normalized)
        if reason:
            raise RextValidationException(
                message="IP address is not a valid public egress address",
                field_errors={"ip_address": [reason]},
            )
        return normalized

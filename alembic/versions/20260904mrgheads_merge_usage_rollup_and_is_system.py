"""merge api_usage_hourly and permissions.is_system heads

Revision ID: 20260904mrgheads
Revises: 20260903usagehr, 20260904isperm
Create Date: 2026-09-04

PRs #683 and #684 each branched a migration off 20260901ipallow and were
merged into stage independently, leaving two heads -- so `alembic upgrade head`
aborts with "Multiple head revisions are present".

The two branches touch disjoint schema (20260903usagehr creates the
api_usage_hourly / api_usage_rollup_state tables; 20260904isperm adds
permissions.is_system), so no reconciliation is needed here and this revision
carries no operations of its own.
"""
from typing import Sequence, Union

revision: str = "20260904mrgheads"
down_revision: Union[str, Sequence[str], None] = ("20260903usagehr", "20260904isperm")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass

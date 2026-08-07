"""update_lemonsqueezy_plan_ids_2026

Revision ID: update_ls_ids_2026
Revises: 9bf42d4f9b39
Create Date: 2026-04-02 00:00:00.000000

NOTE: This migration used to hardcode LemonSqueezy product/variant IDs
directly into the migration body. That meant every environment that ran
this migration (stage AND production) ended up with the same hardcoded
IDs, which is what caused production checkout to be misconfigured with
stage's test-mode variant IDs.

LemonSqueezy plan IDs are now resolved from environment variables and
synced into the subscription_plans table automatically on every
application startup - see src/config/lemonsqueezy_plan_sync.py, invoked
from the FastAPI lifespan in src/api/server.py. Changing the
LEMONSQUEEZY_<PLAN>_* env vars for an environment and redeploying is
sufficient; no migration is needed for a plan ID change.

This migration is kept as a no-op purely to preserve Alembic's revision
history/chain (it may already be applied in some environments).
"""
from typing import Sequence, Union

revision: str = 'update_ls_ids_2026'
down_revision: Union[str, Sequence[str], None] = '9bf42d4f9b39'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """No-op: LemonSqueezy plan IDs are synced from env at app startup, not via migration."""
    pass


def downgrade() -> None:
    """No-op: nothing to revert."""
    pass

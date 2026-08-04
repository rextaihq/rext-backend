"""persona brand voice redesign

Splits the old flat `brand_voice` table into `brand` (identity/positioning)
+ `brand_voice` (voice/style, restructured), renames `persona` to
`author_persona` and narrows it to author/E-E-A-T identity fields, adds a
new `audience` table for buyer/reader segments (split out of the old
Persona buyer-persona fields), adds `extraction_evidence` for
confidence/source/citation tracking, and adds website_type classification
to `website`.

Clean-break migration (no production data at time of writing) — data is
preserved via best-effort backfill rather than a staged dual-write rollout.

Revision ID: f4e9a1c7b2d8
Revises: a584ac4e355c
Create Date: 2026-08-03 00:00:00.000000

"""
import uuid
from datetime import datetime, timezone
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f4e9a1c7b2d8'
down_revision: Union[str, Sequence[str], None] = 'a584ac4e355c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    # ------------------------------------------------------------------
    # 1. Create `brand` (identity/positioning) — split out of brand_voice
    # ------------------------------------------------------------------
    op.create_table(
        "brand",
        sa.Column("id", PGUUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", PGUUID(as_uuid=True), sa.ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("brand_name", sa.String(255), nullable=True),
        sa.Column("about", sa.Text(), nullable=True),
        sa.Column("website_type", sa.String(50), nullable=True),
        sa.Column("website_type_confidence", sa.Float(), nullable=True),
        sa.Column("industry", sa.String(255), nullable=True),
        sa.Column("customer_profile", sa.Text(), nullable=True),
        sa.Column("selling_position", sa.Text(), nullable=True),
        sa.Column("competitors", JSONB(), nullable=True),
        sa.Column("content_pillar", JSONB(), nullable=True),
        sa.Column("target_audience_summary", JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_brand_workspace_id", "brand", ["workspace_id"])

    # Backfill: one brand row per existing brand_voice row, reusing the same
    # id (brand.id == old brand_voice.id) so the brand_voice table can later
    # be repointed via brand_id = id with zero ambiguity.
    op.execute(
        """
        INSERT INTO brand (
            id, workspace_id, brand_name, about, customer_profile,
            selling_position, competitors, content_pillar,
            target_audience_summary, created_at, updated_at
        )
        SELECT
            id, workspace_id, brand_name, about, customer_profile,
            selling_position, competitors, content_pillar,
            target_audience, created_at, COALESCE(updated_at, created_at)
        FROM brand_voice
        """
    )

    # ------------------------------------------------------------------
    # 2. Restructure `brand_voice` into voice/style-only, FK'd to `brand`
    # ------------------------------------------------------------------
    op.add_column("brand_voice", sa.Column("brand_id", PGUUID(as_uuid=True), nullable=True))
    op.execute("UPDATE brand_voice SET brand_id = id")
    op.alter_column("brand_voice", "brand_id", nullable=False)
    op.create_unique_constraint("uq_brand_voice_brand_id", "brand_voice", ["brand_id"])
    op.create_foreign_key(
        "fk_brand_voice_brand_id", "brand_voice", "brand", ["brand_id"], ["id"], ondelete="CASCADE"
    )

    op.alter_column("brand_voice", "brand_voice", new_column_name="tone_attributes")
    op.add_column("brand_voice", sa.Column("formality_level", sa.String(50), nullable=True))
    op.add_column("brand_voice", sa.Column("reading_level", sa.String(50), nullable=True))
    op.add_column("brand_voice", sa.Column("point_of_view", sa.String(50), nullable=True))
    op.add_column("brand_voice", sa.Column("sentence_length_preference", sa.String(50), nullable=True))
    op.add_column("brand_voice", sa.Column("preferred_terms", JSONB(), nullable=True))
    op.add_column("brand_voice", sa.Column("banned_terms", JSONB(), nullable=True))
    op.add_column("brand_voice", sa.Column("humor_tolerance", sa.String(50), nullable=True))
    op.add_column("brand_voice", sa.Column("cta_style", sa.Text(), nullable=True))

    op.drop_column("brand_voice", "workspace_id")
    op.drop_column("brand_voice", "brand_name")
    op.drop_column("brand_voice", "about")
    op.drop_column("brand_voice", "customer_profile")
    op.drop_column("brand_voice", "selling_position")
    op.drop_column("brand_voice", "target_audience")
    op.drop_column("brand_voice", "competitors")
    op.drop_column("brand_voice", "content_pillar")

    # ------------------------------------------------------------------
    # 3. Create `audience` (buyer/reader segments) — split out of Persona
    # ------------------------------------------------------------------
    op.create_table(
        "audience",
        sa.Column("id", PGUUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", PGUUID(as_uuid=True), sa.ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("demographics", JSONB(), nullable=True),
        sa.Column("psychographics", JSONB(), nullable=True),
        sa.Column("pain_points", JSONB(), nullable=True),
        sa.Column("goals", JSONB(), nullable=True),
        sa.Column("behaviors", JSONB(), nullable=True),
        sa.Column("objections", JSONB(), nullable=True),
        sa.Column("preferred_channels", JSONB(), nullable=True),
        sa.Column("buying_stage", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_audience_workspace_id", "audience", ["workspace_id"])

    # Backfill: one "General Audience" row per workspace that had at least
    # one persona with buyer-persona signal (demographics/pain_points/
    # goals/behaviors), aggregated from the most recently created such
    # persona. Best-effort — see migration docstring.
    _backfill_audience_from_legacy_personas(bind)

    # ------------------------------------------------------------------
    # 4. Rename `persona` -> `author_persona`, narrow to author identity
    # ------------------------------------------------------------------
    op.rename_table("persona", "author_persona")
    op.add_column("author_persona", sa.Column("experience_type", sa.String(50), nullable=True))
    op.add_column("author_persona", sa.Column("years_of_experience", sa.Integer(), nullable=True))
    op.add_column("author_persona", sa.Column("credentials", JSONB(), nullable=True))
    op.add_column("author_persona", sa.Column("employer", sa.String(255), nullable=True))
    op.add_column("author_persona", sa.Column("social_profiles", JSONB(), nullable=True))

    op.execute(
        """
        UPDATE author_persona
        SET social_profiles = jsonb_build_array(
            jsonb_build_object('platform', 'linkedin', 'url', linkedin_url)
        )
        WHERE linkedin_url IS NOT NULL AND linkedin_url <> ''
        """
    )

    op.alter_column("author_persona", "tone_of_voice", new_column_name="writing_voice")
    op.drop_column("author_persona", "demographics")
    op.drop_column("author_persona", "pain_points")
    op.drop_column("author_persona", "goals")
    op.drop_column("author_persona", "behaviors")
    op.drop_column("author_persona", "linkedin_url")

    # ------------------------------------------------------------------
    # 5. `extraction_evidence` — confidence/source/citation tracking
    # ------------------------------------------------------------------
    op.create_table(
        "extraction_evidence",
        sa.Column("id", PGUUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", PGUUID(as_uuid=True), sa.ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False),
        sa.Column("brand_id", PGUUID(as_uuid=True), sa.ForeignKey("brand.id", ondelete="CASCADE"), nullable=True),
        sa.Column("brand_voice_id", PGUUID(as_uuid=True), sa.ForeignKey("brand_voice.id", ondelete="CASCADE"), nullable=True),
        sa.Column("author_persona_id", PGUUID(as_uuid=True), sa.ForeignKey("author_persona.id", ondelete="CASCADE"), nullable=True),
        sa.Column("field_name", sa.String(100), nullable=False),
        sa.Column("extracted_value", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("source_url", sa.String(500), nullable=True),
        sa.Column("supporting_excerpt", sa.Text(), nullable=True),
        sa.Column("extraction_method", sa.String(50), nullable=False, server_default="llm_structured_output"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "(num_nonnulls(brand_id, brand_voice_id, author_persona_id) = 1)",
            name="ck_extraction_evidence_exactly_one_entity",
        ),
    )
    op.create_index("ix_extraction_evidence_workspace_id", "extraction_evidence", ["workspace_id"])
    op.create_index("ix_extraction_evidence_brand_id", "extraction_evidence", ["brand_id"])
    op.create_index("ix_extraction_evidence_brand_voice_id", "extraction_evidence", ["brand_voice_id"])
    op.create_index("ix_extraction_evidence_author_persona_id", "extraction_evidence", ["author_persona_id"])
    op.create_index("ix_extraction_evidence_workspace_field", "extraction_evidence", ["workspace_id", "field_name"])

    # ------------------------------------------------------------------
    # 6. `website` — add classification fields
    # ------------------------------------------------------------------
    op.add_column("website", sa.Column("website_type", sa.String(50), nullable=True))
    op.add_column("website", sa.Column("website_type_confidence", sa.Float(), nullable=True))


def _backfill_audience_from_legacy_personas(bind) -> None:
    """Best-effort: collapse each workspace's legacy persona buyer-fields
    into one Audience row, using the most recently created persona that
    had any such signal. Pre-launch data only — this is not meant to be a
    faithful reconstruction, just a starting point editors can refine.
    """
    rows = bind.execute(
        sa.text(
            """
            SELECT DISTINCT ON (workspace_id)
                workspace_id, demographics, pain_points, goals, behaviors
            FROM persona
            WHERE
                (demographics IS NOT NULL AND demographics <> '') OR
                (pain_points IS NOT NULL AND pain_points <> '') OR
                (goals IS NOT NULL AND goals <> '') OR
                (behaviors IS NOT NULL AND behaviors <> '')
            ORDER BY workspace_id, created_at DESC
            """
        )
    ).fetchall()

    if not rows:
        return

    now = datetime.now(timezone.utc)

    def _split(value):
        if not value:
            return []
        return [v.strip() for v in value.split(",") if v.strip()]

    audience_table = sa.table(
        "audience",
        sa.column("id", PGUUID(as_uuid=True)),
        sa.column("workspace_id", PGUUID(as_uuid=True)),
        sa.column("name", sa.String()),
        sa.column("description", sa.Text()),
        sa.column("demographics", JSONB()),
        sa.column("pain_points", JSONB()),
        sa.column("goals", JSONB()),
        sa.column("behaviors", JSONB()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )

    for row in rows:
        bind.execute(
            audience_table.insert().values(
                id=uuid.uuid4(),
                workspace_id=row.workspace_id,
                name="General Audience",
                description="Migrated from legacy persona demographic fields — review and refine.",
                demographics={"notes": row.demographics} if row.demographics else {},
                pain_points=_split(row.pain_points),
                goals=_split(row.goals),
                behaviors=_split(row.behaviors),
                created_at=now,
                updated_at=now,
            )
        )


def downgrade() -> None:
    op.drop_column("website", "website_type_confidence")
    op.drop_column("website", "website_type")

    op.drop_table("extraction_evidence")

    op.add_column("author_persona", sa.Column("linkedin_url", sa.String(500), nullable=True))
    op.execute(
        """
        UPDATE author_persona
        SET linkedin_url = social_profiles -> 0 ->> 'url'
        WHERE jsonb_array_length(COALESCE(social_profiles, '[]'::jsonb)) > 0
        """
    )
    op.add_column("author_persona", sa.Column("demographics", sa.Text(), nullable=True))
    op.add_column("author_persona", sa.Column("pain_points", sa.Text(), nullable=True))
    op.add_column("author_persona", sa.Column("goals", sa.Text(), nullable=True))
    op.add_column("author_persona", sa.Column("behaviors", sa.Text(), nullable=True))
    op.alter_column("author_persona", "writing_voice", new_column_name="tone_of_voice")
    op.drop_column("author_persona", "social_profiles")
    op.drop_column("author_persona", "employer")
    op.drop_column("author_persona", "credentials")
    op.drop_column("author_persona", "years_of_experience")
    op.drop_column("author_persona", "experience_type")
    op.rename_table("author_persona", "persona")

    op.drop_table("audience")

    op.add_column("brand_voice", sa.Column("workspace_id", PGUUID(as_uuid=True), nullable=True))
    op.add_column("brand_voice", sa.Column("brand_name", sa.String(255), nullable=True))
    op.add_column("brand_voice", sa.Column("about", sa.Text(), nullable=True))
    op.add_column("brand_voice", sa.Column("customer_profile", sa.Text(), nullable=True))
    op.add_column("brand_voice", sa.Column("selling_position", sa.Text(), nullable=True))
    op.add_column("brand_voice", sa.Column("target_audience", JSONB(), nullable=True))
    op.add_column("brand_voice", sa.Column("competitors", JSONB(), nullable=True))
    op.add_column("brand_voice", sa.Column("content_pillar", JSONB(), nullable=True))
    op.execute(
        """
        UPDATE brand_voice bv
        SET workspace_id = b.workspace_id,
            brand_name = b.brand_name,
            about = b.about,
            customer_profile = b.customer_profile,
            selling_position = b.selling_position,
            target_audience = b.target_audience_summary,
            competitors = b.competitors,
            content_pillar = b.content_pillar
        FROM brand b
        WHERE bv.brand_id = b.id
        """
    )
    op.alter_column("brand_voice", "workspace_id", nullable=False)
    op.alter_column("brand_voice", "tone_attributes", new_column_name="brand_voice")
    op.drop_constraint("fk_brand_voice_brand_id", "brand_voice", type_="foreignkey")
    op.drop_constraint("uq_brand_voice_brand_id", "brand_voice", type_="unique")
    op.drop_column("brand_voice", "brand_id")
    op.drop_column("brand_voice", "cta_style")
    op.drop_column("brand_voice", "humor_tolerance")
    op.drop_column("brand_voice", "banned_terms")
    op.drop_column("brand_voice", "preferred_terms")
    op.drop_column("brand_voice", "sentence_length_preference")
    op.drop_column("brand_voice", "point_of_view")
    op.drop_column("brand_voice", "reading_level")
    op.drop_column("brand_voice", "formality_level")
    op.create_index("ix_brand_voice_workspace_id", "brand_voice", ["workspace_id"])

    op.drop_table("brand")

"""Record Invest Saudi official identity, endpoint observations and memberships."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa

revision = "0011_invest_saudi_source_identity"
down_revision = "0010_source_taxonomy_columns"
branch_labels = None
depends_on = None

DATASET_NAMES = {
    "opportunity": "Opportunities",
    "project": "Investment projects",
    "pif": "PIF opportunities",
    "regional": "Regional opportunities",
}


def upgrade():
    bind = op.get_bind()
    columns = {c["name"] for c in sa.inspect(bind).get_columns("source_opportunities")}
    with op.batch_alter_table("source_opportunities") as batch:
        if "official_source_id_original" not in columns:
            batch.add_column(sa.Column("official_source_id_original", sa.String(200), nullable=True))
        if "official_source_id_normalized" not in columns:
            batch.add_column(sa.Column("official_source_id_normalized", sa.String(200), nullable=True))
    index_names = {i["name"] for i in sa.inspect(bind).get_indexes("source_opportunities")}
    if "ix_source_opportunities_official_source_id_original" not in index_names:
        op.create_index("ix_source_opportunities_official_source_id_original", "source_opportunities", ["official_source_id_original"])
    if "ix_source_opportunities_official_source_id_normalized" not in index_names:
        op.create_index("ix_source_opportunities_official_source_id_normalized", "source_opportunities", ["official_source_id_normalized"])

    tables = set(sa.inspect(bind).get_table_names())
    if "source_opportunity_dataset_memberships" not in tables:op.create_table(
        "source_opportunity_dataset_memberships",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_opportunity_id", sa.Integer(), sa.ForeignKey("source_opportunities.id"), nullable=False),
        sa.Column("dataset_name", sa.String(100), nullable=False),
        sa.Column("endpoint", sa.String(600), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("missing_successful_checks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("dataset_specific_metadata", sa.JSON(), nullable=False, server_default="{}"),
        sa.UniqueConstraint("source_opportunity_id", "dataset_name", name="uq_source_dataset_membership"),
    )
    if "ix_source_opportunity_dataset_memberships_source_opportunity_id" not in {i["name"] for i in sa.inspect(bind).get_indexes("source_opportunity_dataset_memberships")}:op.create_index("ix_source_opportunity_dataset_memberships_source_opportunity_id", "source_opportunity_dataset_memberships", ["source_opportunity_id"])

    if "source_observations" not in tables:op.create_table(
        "source_observations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_opportunity_id", sa.Integer(), sa.ForeignKey("source_opportunities.id"), nullable=False),
        sa.Column("dataset_name", sa.String(100), nullable=False),
        sa.Column("endpoint", sa.String(600), nullable=False),
        sa.Column("official_source_id_original", sa.String(200), nullable=False),
        sa.Column("official_source_id_normalized", sa.String(200), nullable=False),
        sa.Column("raw_data_json", sa.JSON(), nullable=False),
        sa.Column("source_updated_at", sa.String(80), nullable=True),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("source_opportunity_id", "endpoint", "content_hash", name="uq_source_observation_version"),
    )
    obs_indexes={i["name"] for i in sa.inspect(bind).get_indexes("source_observations")}
    if "ix_source_observations_source_opportunity_id" not in obs_indexes:op.create_index("ix_source_observations_source_opportunity_id", "source_observations", ["source_opportunity_id"])
    if "ix_source_observations_official_source_id_normalized" not in obs_indexes:op.create_index("ix_source_observations_official_source_id_normalized", "source_observations", ["official_source_id_normalized"])
    if "ix_source_observations_content_hash" not in obs_indexes:op.create_index("ix_source_observations_content_hash", "source_observations", ["content_hash"])

    if "source_opportunity_taxonomies" not in tables:op.create_table(
        "source_opportunity_taxonomies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_opportunity_id", sa.Integer(), sa.ForeignKey("source_opportunities.id"), nullable=False),
        sa.Column("dataset_name", sa.String(100), nullable=False),
        sa.Column("source_taxonomy_value", sa.String(200), nullable=False),
        sa.Column("normalized_taxonomy_value", sa.String(80), nullable=False),
        sa.Column("mapping_rule", sa.String(300), nullable=False),
        sa.Column("mapping_version", sa.String(40), nullable=False, server_default="1"),
        sa.UniqueConstraint("source_opportunity_id", "dataset_name", "source_taxonomy_value", name="uq_source_taxonomy_membership"),
    )
    if "ix_source_opportunity_taxonomies_source_opportunity_id" not in {i["name"] for i in sa.inspect(bind).get_indexes("source_opportunity_taxonomies")}:op.create_index("ix_source_opportunity_taxonomies_source_opportunity_id", "source_opportunity_taxonomies", ["source_opportunity_id"])

    sources = sa.table("sources", sa.column("id", sa.Integer()), sa.column("source_key", sa.String()))
    invest_id = bind.execute(sa.select(sources.c.id).where(sources.c.source_key == "invest-saudi")).scalar_one_or_none()
    if invest_id is None:
        return

    records = sa.table(
        "source_opportunities",
        sa.column("id", sa.Integer()), sa.column("source_id", sa.Integer()), sa.column("source_opportunity_id", sa.String()),
        sa.column("raw_data_json", sa.JSON()), sa.column("first_seen_at", sa.DateTime(timezone=True)),
        sa.column("last_seen_at", sa.DateTime(timezone=True)), sa.column("official_source_id_original", sa.String()),
        sa.column("official_source_id_normalized", sa.String()),
    )
    rows = bind.execute(sa.select(records).where(records.c.source_id == invest_id)).mappings().all()
    normalized_seen = set()
    existing_members = []
    existing_observations = []
    existing_taxonomies = []
    id_map = {}
    now = datetime.now(timezone.utc)
    for row in rows:
        raw = row["raw_data_json"] or {}
        original = raw.get("id")
        if original is None:
            continue
        original = str(original).strip()
        normalized = str(int(original)) if original.isdigit() else original.casefold()
        if normalized in normalized_seen:
            raise RuntimeError(f"Invest Saudi official ID collision during identity migration: {normalized}")
        normalized_seen.add(normalized)
        family = raw.get("source_record_family")
        dataset = DATASET_NAMES.get(family)
        endpoint = raw.get("source_api")
        if not dataset or not endpoint:
            continue
        canonical_external_id = f"investsaudi:{normalized}"
        id_map[row["source_opportunity_id"]] = canonical_external_id
        raw["official_source_id_original"] = original
        raw["official_source_id_normalized"] = normalized
        content_hash = hashlib.sha256(json.dumps(raw, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()
        bind.execute(
            sa.update(records).where(records.c.id == row["id"]).values(
                source_opportunity_id=canonical_external_id, raw_data_json=raw,
                official_source_id_original=original, official_source_id_normalized=normalized,
            )
        )
        seen = row["last_seen_at"] or now
        first = row["first_seen_at"] or seen
        existing_members.append({
            "source_opportunity_id": row["id"], "dataset_name": dataset, "endpoint": endpoint,
            "first_seen_at": first, "last_seen_at": seen, "missing_successful_checks": 0,
            "is_current": True, "dataset_specific_metadata": {
                "source_record_family": family,
                "source_taxonomy": raw.get("source_taxonomy") or {},
                "normalized_taxonomy": raw.get("normalized_taxonomy") or {},
            },
        })
        existing_observations.append({
            "source_opportunity_id": row["id"], "dataset_name": dataset, "endpoint": endpoint,
            "official_source_id_original": original, "official_source_id_normalized": normalized,
            "raw_data_json": raw, "source_updated_at": raw.get("updated_at") or raw.get("date") or raw.get("published_at"),
            "content_hash": content_hash, "first_seen_at": first, "last_seen_at": seen,
        })
        source_tax = (raw.get("source_taxonomy") or {}).get("sector")
        norm_tax = (raw.get("normalized_taxonomy") or {}).get("sector")
        if source_tax:
            existing_taxonomies.append({
                "source_opportunity_id": row["id"], "dataset_name": dataset,
                "source_taxonomy_value": str(source_tax), "normalized_taxonomy_value": str(norm_tax or "Other"),
                "mapping_rule": f"broad-sector mapping v1: {source_tax} → {norm_tax or 'Other'}", "mapping_version": "1",
            })
    if existing_members:
        insert_table=sa.table("source_opportunity_dataset_memberships",sa.column("source_opportunity_id",sa.Integer()),sa.column("dataset_name",sa.String()),sa.column("endpoint",sa.String()),sa.column("first_seen_at",sa.DateTime()),sa.column("last_seen_at",sa.DateTime()),sa.column("missing_successful_checks",sa.Integer()),sa.column("is_current",sa.Boolean()),sa.column("dataset_specific_metadata",sa.JSON()))
        bind.execute(insert_table.insert(), existing_members)
    if existing_observations:
        insert_table=sa.table("source_observations",sa.column("source_opportunity_id",sa.Integer()),sa.column("dataset_name",sa.String()),sa.column("endpoint",sa.String()),sa.column("official_source_id_original",sa.String()),sa.column("official_source_id_normalized",sa.String()),sa.column("raw_data_json",sa.JSON()),sa.column("source_updated_at",sa.String()),sa.column("content_hash",sa.String()),sa.column("first_seen_at",sa.DateTime()),sa.column("last_seen_at",sa.DateTime()))
        bind.execute(insert_table.insert(), existing_observations)
    if existing_taxonomies:
        insert_table=sa.table("source_opportunity_taxonomies",sa.column("source_opportunity_id",sa.Integer()),sa.column("dataset_name",sa.String()),sa.column("source_taxonomy_value",sa.String()),sa.column("normalized_taxonomy_value",sa.String()),sa.column("mapping_rule",sa.String()),sa.column("mapping_version",sa.String()))
        bind.execute(insert_table.insert(), existing_taxonomies)

    reviews = sa.table("location_reviews", sa.column("external_id", sa.String()), sa.column("source_id", sa.Integer()))
    for old_id, new_id in id_map.items():
        bind.execute(sa.update(reviews).where(reviews.c.source_id == invest_id, reviews.c.external_id == old_id).values(external_id=new_id))


def downgrade():
    op.drop_index("ix_source_opportunity_taxonomies_source_opportunity_id", table_name="source_opportunity_taxonomies")
    op.drop_table("source_opportunity_taxonomies")
    op.drop_index("ix_source_observations_content_hash", table_name="source_observations")
    op.drop_index("ix_source_observations_official_source_id_normalized", table_name="source_observations")
    op.drop_index("ix_source_observations_source_opportunity_id", table_name="source_observations")
    op.drop_table("source_observations")
    op.drop_index("ix_source_opportunity_dataset_memberships_source_opportunity_id", table_name="source_opportunity_dataset_memberships")
    op.drop_table("source_opportunity_dataset_memberships")
    op.drop_index("ix_source_opportunities_official_source_id_normalized", table_name="source_opportunities")
    op.drop_index("ix_source_opportunities_official_source_id_original", table_name="source_opportunities")
    with op.batch_alter_table("source_opportunities") as batch:
        batch.drop_column("official_source_id_normalized")
        batch.drop_column("official_source_id_original")

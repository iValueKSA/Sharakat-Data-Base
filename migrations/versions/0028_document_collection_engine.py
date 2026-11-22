"""Add private document-collection staging and immutable verification history.

Revision ID: 0028_document_collection_engine
Revises: 0027_opportunity_documents_mvp

This is an isolated candidate only. It never inserts into or changes
opportunity_documents and is not deployed by this task.
"""
from alembic import op
import sqlalchemy as sa


revision = "0028_document_collection_engine"
down_revision = "0027_opportunity_documents_mvp"
branch_labels = None
depends_on = None


def upgrade():
    # Schema-only revision; already present on a clean install (migrations/env.py).
    if sa.inspect(op.get_bind()).has_table("document_collection_runs"):
        return
    op.create_table(
        "document_collection_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_id", sa.Integer(), sa.ForeignKey("sources.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("source_key", sa.String(80), nullable=False),
        sa.Column("scope", sa.String(40), nullable=False, server_default="ALLOWLIST"),
        sa.Column("status", sa.String(20), nullable=False, server_default="RUNNING"),
        sa.Column("requested_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("processed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("discovered_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("verified_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ready_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("review_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rejected_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duplicate_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("temporary_failure_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("checkpoint_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("summary_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('RUNNING','COMPLETED','PARTIAL','FAILED','CANCELLED')", name="ck_doc_collection_run_status"),
    )
    op.create_index("ix_document_collection_runs_source_id", "document_collection_runs", ["source_id"])
    op.create_index("ix_document_collection_runs_source_key", "document_collection_runs", ["source_key"])
    op.create_index("ix_document_collection_runs_status", "document_collection_runs", ["status"])

    op.create_table(
        "document_collection_candidates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("document_collection_runs.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("source_id", sa.Integer(), sa.ForeignKey("sources.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("source_opportunity_id", sa.Integer(), sa.ForeignKey("source_opportunities.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("opportunity_id", sa.Integer(), sa.ForeignKey("opportunities.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("provider_opportunity_id", sa.String(200), nullable=False),
        sa.Column("source_document_id", sa.String(500), nullable=True),
        sa.Column("identity_key", sa.String(64), nullable=False),
        sa.Column("document_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("original_title", sa.String(500), nullable=False),
        sa.Column("document_type", sa.String(100), nullable=True),
        sa.Column("document_category", sa.String(50), nullable=False),
        sa.Column("document_scope", sa.String(30), nullable=False, server_default="OPPORTUNITY"),
        sa.Column("url", sa.String(1200), nullable=True),
        sa.Column("source_opportunity_url", sa.String(1200), nullable=False),
        sa.Column("official_purchase_url", sa.String(1200), nullable=True),
        sa.Column("purchase_url_verified", sa.Boolean(), nullable=True),
        sa.Column("access_status", sa.String(40), nullable=False, server_default="UNKNOWN"),
        sa.Column("rights_status", sa.String(40), nullable=False, server_default="UNVERIFIED"),
        sa.Column("participation_requirement", sa.String(50), nullable=False, server_default="UNKNOWN"),
        sa.Column("authentication_required", sa.Boolean(), nullable=True),
        sa.Column("payment_required_for_document", sa.Boolean(), nullable=True),
        sa.Column("link_verification_status", sa.String(40), nullable=False, server_default="UNVERIFIED"),
        sa.Column("verification_status", sa.String(40), nullable=False, server_default="DISCOVERED"),
        sa.Column("review_status", sa.String(20), nullable=False, server_default="PENDING"),
        sa.Column("raw_amount", sa.Numeric(14, 2), nullable=True),
        sa.Column("raw_currency", sa.String(20), nullable=True),
        sa.Column("verified_amount", sa.Numeric(14, 2), nullable=True),
        sa.Column("verified_currency", sa.String(3), nullable=True),
        sa.Column("publicly_displayable_price", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("evidence_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("provenance_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("missing_evidence_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("source_payload_sha256", sa.String(64), nullable=False),
        sa.Column("parser_version", sa.String(80), nullable=False),
        sa.Column("collector_version", sa.String(80), nullable=False),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("failure_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("source_opportunity_id", "identity_key", "document_version", name="uq_doc_candidate_source_identity_version"),
        sa.CheckConstraint("verification_status IN ('DISCOVERED','EXTRACTED','IDENTITY_VERIFIED','ACCESS_VERIFIED','NEEDS_REVIEW','READY_FOR_APPROVAL','RESTRICTED','TEMPORARILY_UNREACHABLE','CHANGED','WITHDRAWAL_PROPOSED')", name="ck_doc_candidate_verification_status"),
        sa.CheckConstraint("review_status IN ('PENDING','APPROVED','REJECTED')", name="ck_doc_candidate_review_status"),
        sa.CheckConstraint("raw_amount IS NULL OR raw_amount >= 0", name="ck_doc_candidate_raw_amount_nonnegative"),
        sa.CheckConstraint("verified_amount IS NULL OR verified_amount >= 0", name="ck_doc_candidate_verified_amount_nonnegative"),
        sa.CheckConstraint("publicly_displayable_price = false OR (verified_amount IS NOT NULL AND verified_currency IS NOT NULL)", name="ck_doc_candidate_display_price_requires_currency"),
    )
    for name, column in (
        ("ix_document_collection_candidates_run_id", "run_id"),
        ("ix_document_collection_candidates_source_id", "source_id"),
        ("ix_document_collection_candidates_source_opportunity_id", "source_opportunity_id"),
        ("ix_document_collection_candidates_opportunity_id", "opportunity_id"),
        ("ix_document_collection_candidates_provider_opportunity_id", "provider_opportunity_id"),
        ("ix_document_collection_candidates_verification_status", "verification_status"),
        ("ix_document_collection_candidates_review_status", "review_status"),
    ):
        op.create_index(name, "document_collection_candidates", [column])
    op.create_index("ix_doc_candidate_review_status", "document_collection_candidates", ["review_status", "verification_status"])

    op.create_table(
        "document_verification_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("document_collection_runs.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("candidate_id", sa.Integer(), sa.ForeignKey("document_collection_candidates.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("source_id", sa.Integer(), sa.ForeignKey("sources.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("source_opportunity_id", sa.Integer(), sa.ForeignKey("source_opportunities.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("outcome", sa.String(50), nullable=False),
        sa.Column("evidence_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("before_sha256", sa.String(64), nullable=True),
        sa.Column("after_sha256", sa.String(64), nullable=True),
        sa.Column("parser_version", sa.String(80), nullable=False),
        sa.Column("collector_version", sa.String(80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_document_verification_events_run_id", "document_verification_events", ["run_id"])
    op.create_index("ix_document_verification_events_candidate_id", "document_verification_events", ["candidate_id"])
    op.create_index("ix_document_verification_events_source_id", "document_verification_events", ["source_id"])
    op.create_index("ix_document_verification_events_source_opportunity_id", "document_verification_events", ["source_opportunity_id"])
    op.create_index("ix_document_verification_events_event_type", "document_verification_events", ["event_type"])
    op.create_index("ix_document_verification_events_created_at", "document_verification_events", ["created_at"])
    op.create_index("ix_doc_verification_candidate_created", "document_verification_events", ["candidate_id", "created_at"])


def downgrade():
    op.drop_index("ix_doc_verification_candidate_created", table_name="document_verification_events")
    op.drop_table("document_verification_events")
    op.drop_index("ix_doc_candidate_review_status", table_name="document_collection_candidates")
    for name in (
        "ix_document_collection_candidates_review_status", "ix_document_collection_candidates_verification_status",
        "ix_document_collection_candidates_provider_opportunity_id", "ix_document_collection_candidates_opportunity_id",
        "ix_document_collection_candidates_source_opportunity_id", "ix_document_collection_candidates_source_id",
        "ix_document_collection_candidates_run_id",
    ):
        op.drop_index(name, table_name="document_collection_candidates")
    op.drop_table("document_collection_candidates")
    for name in ("ix_document_collection_runs_status", "ix_document_collection_runs_source_key", "ix_document_collection_runs_source_id"):
        op.drop_index(name, table_name="document_collection_runs")
    op.drop_table("document_collection_runs")

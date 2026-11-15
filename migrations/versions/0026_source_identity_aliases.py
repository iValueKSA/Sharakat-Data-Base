"""Add namespace-constrained, auditable source identity aliases."""
from alembic import op
import sqlalchemy as sa

revision = "0026_source_identity_aliases"
down_revision = "0025_source_geographic_coverage"
branch_labels = None
depends_on = None


def _inspector():
    return sa.inspect(op.get_bind())


def upgrade():
    inspector = _inspector()
    source_constraints = {item.get("name") for item in inspector.get_unique_constraints("sources")}
    if "uq_source_id_key_namespace" not in source_constraints:
        op.create_unique_constraint("uq_source_id_key_namespace", "sources", ["id", "source_key"])
    constraints = {item.get("name") for item in inspector.get_unique_constraints("source_opportunities")}
    if "uq_source_opportunity_id_source_namespace" not in constraints:
        op.create_unique_constraint("uq_source_opportunity_id_source_namespace", "source_opportunities", ["id", "source_id"])

    if not _inspector().has_table("source_identity_aliases"):
        op.create_table(
            "source_identity_aliases",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("source_id", sa.Integer(), sa.ForeignKey("sources.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("source_namespace", sa.String(length=80), nullable=False),
            sa.Column("alias_provider_id", sa.String(length=200), nullable=False),
            sa.Column("target_source_opportunity_id", sa.Integer(), nullable=False),
            sa.Column("canonical_source_key", sa.String(length=200), nullable=False),
            sa.Column("expected_master_opportunity_id", sa.Integer(), sa.ForeignKey("opportunities.id", ondelete="RESTRICT"), nullable=True),
            sa.Column("evidence_reference_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("approval_artifact_reference", sa.String(length=1200), nullable=False),
            sa.Column("approval_artifact_sha256", sa.String(length=64), nullable=False),
            sa.Column("approval_decision_fingerprint", sa.String(length=64), nullable=False),
            sa.Column("approval_method", sa.String(length=100), nullable=False),
            sa.Column("approval_authority", sa.String(length=120), nullable=False),
            sa.Column("approval_timestamp", sa.DateTime(timezone=True), nullable=False),
            sa.Column("application_timestamp", sa.DateTime(timezone=True), nullable=False),
            sa.Column("application_batch_id", sa.String(length=100), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="ACTIVE"),
            sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("deactivation_reason", sa.Text(), nullable=True),
            sa.Column("audit_metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("source_id", "alias_provider_id", name="uq_source_identity_alias_provider"),
            sa.ForeignKeyConstraint(
                ["source_id", "source_namespace"], ["sources.id", "sources.source_key"],
                ondelete="RESTRICT", name="fk_source_identity_alias_namespace"),
            sa.ForeignKeyConstraint(
                ["target_source_opportunity_id", "source_id"],
                ["source_opportunities.id", "source_opportunities.source_id"],
                ondelete="RESTRICT", name="fk_source_identity_alias_target_namespace"),
            sa.CheckConstraint("alias_provider_id <> canonical_source_key", name="ck_source_identity_alias_not_canonical_key"),
            sa.CheckConstraint("status IN ('ACTIVE','INACTIVE')", name="ck_source_identity_alias_status"),
        )
    indexes = {item.get("name") for item in _inspector().get_indexes("source_identity_aliases")}
    for name, column in (
        ("ix_source_identity_aliases_source_id", "source_id"),
        ("ix_source_identity_aliases_target_source_opportunity_id", "target_source_opportunity_id"),
        ("ix_source_identity_aliases_expected_master_opportunity_id", "expected_master_opportunity_id"),
        ("ix_source_identity_aliases_status", "status"),
    ):
        if name not in indexes:
            op.create_index(name, "source_identity_aliases", [column])

    if not _inspector().has_table("source_identity_alias_audits"):
        op.create_table(
            "source_identity_alias_audits",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("alias_id", sa.Integer(), sa.ForeignKey("source_identity_aliases.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("action", sa.String(length=20), nullable=False),
            sa.Column("application_batch_id", sa.String(length=100), nullable=False),
            sa.Column("actor", sa.String(length=120), nullable=False),
            sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("before_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("after_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("reason", sa.Text(), nullable=True),
            sa.Column("evidence_reference", sa.String(length=1200), nullable=True),
            sa.UniqueConstraint("alias_id", "action", "application_batch_id", name="uq_source_identity_alias_audit_action_batch"),
            sa.CheckConstraint("action IN ('APPLIED','ROLLED_BACK')", name="ck_source_identity_alias_audit_action"),
        )
    audit_indexes = {item.get("name") for item in _inspector().get_indexes("source_identity_alias_audits")}
    if "ix_source_identity_alias_audits_alias_id" not in audit_indexes:
        op.create_index("ix_source_identity_alias_audits_alias_id", "source_identity_alias_audits", ["alias_id"])


def downgrade():
    inspector = _inspector()
    if inspector.has_table("source_identity_aliases"):
        applied = op.get_bind().execute(sa.text("SELECT COUNT(*) FROM source_identity_aliases")).scalar_one()
        if applied:
            raise RuntimeError("Refusing to drop applied alias/crosswalk history; deactivate the batch and preserve the audit table")
    if inspector.has_table("source_identity_alias_audits"):
        audit_count = op.get_bind().execute(sa.text("SELECT COUNT(*) FROM source_identity_alias_audits")).scalar_one()
        if audit_count:
            raise RuntimeError("Refusing to drop source identity alias audit history")
        indexes = {item.get("name") for item in inspector.get_indexes("source_identity_alias_audits")}
        if "ix_source_identity_alias_audits_alias_id" in indexes:
            op.drop_index("ix_source_identity_alias_audits_alias_id", table_name="source_identity_alias_audits")
        op.drop_table("source_identity_alias_audits")
    if _inspector().has_table("source_identity_aliases"):
        indexes = {item.get("name") for item in _inspector().get_indexes("source_identity_aliases")}
        for name in (
            "ix_source_identity_aliases_status",
            "ix_source_identity_aliases_expected_master_opportunity_id",
            "ix_source_identity_aliases_target_source_opportunity_id",
            "ix_source_identity_aliases_source_id",
        ):
            if name in indexes:
                op.drop_index(name, table_name="source_identity_aliases")
        op.drop_table("source_identity_aliases")
    constraints = {item.get("name") for item in _inspector().get_unique_constraints("source_opportunities")}
    if "uq_source_opportunity_id_source_namespace" in constraints:
        op.drop_constraint("uq_source_opportunity_id_source_namespace", "source_opportunities", type_="unique")
    source_constraints = {item.get("name") for item in _inspector().get_unique_constraints("sources")}
    if "uq_source_id_key_namespace" in source_constraints:
        op.drop_constraint("uq_source_id_key_namespace", "sources", type_="unique")

"""Add provenance, access and publication gates to opportunity documents.

Revision ID: 0027_opportunity_documents_mvp
Revises: 0026_source_identity_aliases
"""
from alembic import op
import sqlalchemy as sa


revision = "0027_opportunity_documents_mvp"
down_revision = "0026_source_identity_aliases"
branch_labels = None
depends_on = None


def _inspector():
    return sa.inspect(op.get_bind())


def _add_column_if_missing(table, column):
    if column.name not in {item["name"] for item in _inspector().get_columns(table)}:
        op.add_column(table, column)


def _add_check_if_missing(table, name, expression):
    names = {item.get("name") for item in _inspector().get_check_constraints(table)}
    if name not in names:
        op.create_check_constraint(name, table, expression)


def upgrade():
    inspector = _inspector()
    if not inspector.has_table("opportunity_documents"):
        raise RuntimeError("opportunity_documents must exist before the MVP extension")

    columns = [
        sa.Column("source_opportunity_id", sa.Integer(), nullable=True),
        sa.Column("official_provider_document_id", sa.String(length=500), nullable=True),
        sa.Column("official_purchase_url", sa.String(length=1200), nullable=True),
        sa.Column("purchase_url_verified", sa.Boolean(), nullable=True),
        sa.Column("document_category", sa.String(length=50), nullable=True),
        sa.Column("source_opportunity_url", sa.String(length=1200), nullable=True),
        sa.Column("access_status", sa.String(length=40), nullable=False, server_default="UNKNOWN"),
        sa.Column("rights_status", sa.String(length=40), nullable=False, server_default="UNVERIFIED"),
        sa.Column("authentication_required", sa.Boolean(), nullable=True),
        sa.Column("payment_required_for_document", sa.Boolean(), nullable=True),
        sa.Column("participation_requirement", sa.String(length=50), nullable=False, server_default="UNKNOWN"),
        sa.Column("booklet_price_amount", sa.Numeric(14, 2), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("link_verification_status", sa.String(length=40), nullable=False, server_default="UNVERIFIED"),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_provenance_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("document_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("deduplication_key", sa.String(length=64), nullable=True),
        sa.Column("supersedes_document_id", sa.Integer(), nullable=True),
        sa.Column("publication_status", sa.String(length=20), nullable=False, server_default="DRAFT"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    ]
    for column in columns:
        _add_column_if_missing("opportunity_documents", column)

    constraints = {item.get("name") for item in _inspector().get_foreign_keys("opportunity_documents")}
    if "fk_opportunity_document_source_namespace" not in constraints:
        op.create_foreign_key(
            "fk_opportunity_document_source_namespace", "opportunity_documents", "source_opportunities",
            ["source_opportunity_id", "source_id"], ["id", "source_id"], ondelete="RESTRICT")
    if "fk_opportunity_document_supersedes" not in constraints:
        op.create_foreign_key(
            "fk_opportunity_document_supersedes", "opportunity_documents", "opportunity_documents",
            ["supersedes_document_id"], ["id"], ondelete="RESTRICT")

    checks = [
        ("ck_opportunity_document_version_positive", "document_version >= 1"),
        ("ck_opportunity_document_price_nonnegative", "booklet_price_amount IS NULL OR booklet_price_amount >= 0"),
        ("ck_opportunity_document_publication_status", "publication_status IN ('DRAFT','APPROVED','REVOKED')"),
        ("ck_opportunity_document_access_status", "access_status IN ('PUBLIC_DIRECT_DOWNLOAD','PUBLIC_SOURCE_PAGE','LOGIN_REQUIRED','PAYMENT_REQUIRED_FOR_DOCUMENT','RESTRICTED','UNKNOWN','UNAVAILABLE')"),
        ("ck_opportunity_document_rights_status", "rights_status IN ('DIRECT_LINK_APPROVED','SOURCE_PAGE_LINK_ONLY','RESTRICTED','UNVERIFIED')"),
        ("ck_opportunity_document_participation_status", "participation_requirement IN ('PURCHASE_REQUIRED_FOR_PARTICIPATION','PURCHASE_NOT_REQUIRED_CONFIRMED','UNKNOWN')"),
        ("ck_opportunity_document_link_status", "link_verification_status IN ('VERIFIED_PUBLIC','VERIFIED_SOURCE_PAGE','UNVERIFIED','UNAVAILABLE')"),
        ("ck_opportunity_document_category", "document_category IS NULL OR document_category IN ('TERMS_AND_CONDITIONS_BOOKLET','TENDER_SPECIFICATIONS','DRAFT_CONTRACT','SITE_MAP','TECHNICAL_ATTACHMENT','INVESTMENT_BROCHURE','GENERAL_ATTACHMENT','UNKNOWN_DOCUMENT_TYPE')"),
        ("ck_opportunity_document_approved_gate", "publication_status <> 'APPROVED' OR (source_opportunity_id IS NOT NULL AND source_opportunity_url IS NOT NULL AND rights_status IN ('DIRECT_LINK_APPROVED','SOURCE_PAGE_LINK_ONLY') AND access_status NOT IN ('RESTRICTED','UNAVAILABLE','UNKNOWN') AND (access_status <> 'LOGIN_REQUIRED' OR authentication_required IS TRUE) AND (access_status <> 'PAYMENT_REQUIRED_FOR_DOCUMENT' OR payment_required_for_document IS TRUE) AND ((rights_status = 'DIRECT_LINK_APPROVED' AND access_status = 'PUBLIC_DIRECT_DOWNLOAD' AND link_verification_status = 'VERIFIED_PUBLIC' AND authentication_required IS FALSE AND payment_required_for_document IS FALSE) OR (rights_status = 'SOURCE_PAGE_LINK_ONLY' AND link_verification_status = 'VERIFIED_SOURCE_PAGE')))"),
        ("ck_opportunity_document_price_currency_pair", "booklet_price_amount IS NULL OR currency IS NOT NULL"),
    ]
    for name, expression in checks:
        _add_check_if_missing("opportunity_documents", name, expression)

    indexes = {item["name"] for item in _inspector().get_indexes("opportunity_documents")}
    if "ix_opportunity_documents_source_opportunity_id" not in indexes:
        op.create_index("ix_opportunity_documents_source_opportunity_id", "opportunity_documents", ["source_opportunity_id"])
    if "ix_opportunity_documents_publication_status" not in indexes:
        op.create_index("ix_opportunity_documents_publication_status", "opportunity_documents", ["publication_status"])
    if "uq_opportunity_document_source_dedupe_version" not in indexes:
        op.create_index(
            "uq_opportunity_document_source_dedupe_version", "opportunity_documents",
            ["source_opportunity_id", "deduplication_key", "document_version"], unique=True,
            postgresql_where=sa.text("source_opportunity_id IS NOT NULL AND deduplication_key IS NOT NULL"))


def downgrade():
    inspector = _inspector()
    if not inspector.has_table("opportunity_documents"):
        return
    indexes = {item["name"] for item in inspector.get_indexes("opportunity_documents")}
    for name in (
        "uq_opportunity_document_source_dedupe_version",
        "ix_opportunity_documents_publication_status",
        "ix_opportunity_documents_source_opportunity_id",
    ):
        if name in indexes:
            op.drop_index(name, table_name="opportunity_documents")
    constraints = {item.get("name") for item in _inspector().get_foreign_keys("opportunity_documents")}
    for name in ("fk_opportunity_document_supersedes", "fk_opportunity_document_source_namespace"):
        if name in constraints:
            op.drop_constraint(name, "opportunity_documents", type_="foreignkey")
    check_names = {item.get("name") for item in _inspector().get_check_constraints("opportunity_documents")}
    for name in (
        "ck_opportunity_document_version_positive", "ck_opportunity_document_price_nonnegative",
        "ck_opportunity_document_publication_status", "ck_opportunity_document_access_status",
        "ck_opportunity_document_rights_status", "ck_opportunity_document_participation_status",
        "ck_opportunity_document_link_status", "ck_opportunity_document_category", "ck_opportunity_document_approved_gate",
        "ck_opportunity_document_price_currency_pair",
    ):
        if name in check_names:
            op.drop_constraint(name, "opportunity_documents", type_="check")
    columns = {item["name"] for item in _inspector().get_columns("opportunity_documents")}
    for name in (
        "updated_at", "created_at", "publication_status", "supersedes_document_id", "deduplication_key",
        "document_version", "source_provenance_json", "last_verified_at", "link_verification_status",
        "currency", "booklet_price_amount", "participation_requirement", "payment_required_for_document",
        "authentication_required", "rights_status", "access_status", "source_opportunity_url", "document_category", "purchase_url_verified", "official_purchase_url",
        "official_provider_document_id", "source_opportunity_id",
    ):
        if name in columns:
            op.drop_column("opportunity_documents", name)

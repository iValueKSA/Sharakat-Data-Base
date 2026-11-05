from datetime import datetime, timezone
from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

class Base(DeclarativeBase): pass

class Source(Base):
    __tablename__ = "sources"
    id: Mapped[int] = mapped_column(primary_key=True)
    source_key: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    source_name_ar: Mapped[str] = mapped_column(String(200))
    organization_name: Mapped[str] = mapped_column(String(200))
    base_url: Mapped[str] = mapped_column(String(500))
    opportunities_url: Mapped[str] = mapped_column(String(800))
    source_type: Mapped[str] = mapped_column(Text, default="official")
    priority: Mapped[int] = mapped_column(Integer, default=99)
    polling_frequency_minutes: Mapped[int] = mapped_column(Integer, default=360)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    extraction_method: Mapped[str] = mapped_column(Text, default="structured_html")
    notes: Mapped[str] = mapped_column(Text, default="")
    technical_health: Mapped[str] = mapped_column(String(30), default="UNKNOWN")
    coverage_status: Mapped[str] = mapped_column(String(40), default="UNKNOWN_COVERAGE")
    coverage_notes: Mapped[str] = mapped_column(Text, default="")
    sync_status: Mapped[str] = mapped_column(String(40), default="NEVER_SYNCED")
    last_attempted_sync: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_successful_sync: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_record_count: Mapped[int] = mapped_column(Integer, default=0)
    last_source_total_reported: Mapped[int | None] = mapped_column(Integer)
    last_collection_completeness_percent: Mapped[float | None] = mapped_column(Float)
    last_pagination_complete: Mapped[bool | None] = mapped_column(Boolean)
    missing_confirmation_threshold: Mapped[int] = mapped_column(Integer, default=3)

class Opportunity(Base):
    __tablename__ = "opportunities"
    __table_args__ = (CheckConstraint(
        "geographic_scope IS NULL OR geographic_scope IN ('SPECIFIC_LOCATION','MULTIPLE_VERIFIED_LOCATIONS','REGION_WIDE','NATIONWIDE','UNSPECIFIED')",
        name="ck_opportunity_geographic_scope"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    merged_into_id: Mapped[int | None] = mapped_column(ForeignKey("opportunities.id"), nullable=True, index=True)
    canonical_id: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    title_ar: Mapped[str] = mapped_column(Text)
    title_en: Mapped[str | None] = mapped_column(Text)
    normalized_title: Mapped[str] = mapped_column(Text, index=True)
    reference_number: Mapped[str | None] = mapped_column(String(200), index=True)
    reference_number_normalized: Mapped[str | None] = mapped_column(String(200), index=True)
    opportunity_owner: Mapped[str | None] = mapped_column(String(300))
    primary_publication_platform: Mapped[str] = mapped_column(String(200))
    sector: Mapped[str | None] = mapped_column(String(200))
    activity: Mapped[str | None] = mapped_column(String(300))
    sub_activity: Mapped[str | None] = mapped_column(String(300))
    subsector: Mapped[str | None] = mapped_column(String(200))
    opportunity_type: Mapped[str | None] = mapped_column(String(200))
    investment_model: Mapped[str | None] = mapped_column(String(200))
    city: Mapped[str] = mapped_column(String(100), default="الأحساء")
    district: Mapped[str | None] = mapped_column(String(200))
    location_description: Mapped[str | None] = mapped_column(Text)
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    land_area_sqm: Mapped[float | None] = mapped_column(Float)
    plot_number: Mapped[str | None] = mapped_column(String(100))
    investment_value: Mapped[float | None] = mapped_column(Float)
    currency: Mapped[str | None] = mapped_column(String(10), nullable=True)
    contract_duration_years: Mapped[float | None] = mapped_column(Float)
    publication_date: Mapped[str | None] = mapped_column(String(40))
    submission_deadline: Mapped[str | None] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(80), default="متاحة")
    short_description: Mapped[str | None] = mapped_column(Text)
    full_description: Mapped[str | None] = mapped_column(Text)
    location_confidence_score: Mapped[float] = mapped_column(Float, default=0)
    location_detection_method: Mapped[str] = mapped_column(String(100), default="")
    location_evidence: Mapped[str] = mapped_column(Text, default="")
    # Optional national-geography projection. Legacy Al-Ahsa records remain NULL
    # until their scope is explicitly verified against an approved reference.
    geographic_scope: Mapped[str | None] = mapped_column(String(40), nullable=True)
    geography_reference_unit_id: Mapped[int | None] = mapped_column(ForeignKey("geographic_reference_units.id"), nullable=True, index=True)
    geography_evidence_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    coordinate_provenance_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    data_quality_score: Mapped[float] = mapped_column(Float, default=0)
    manual_review_required: Mapped[bool] = mapped_column(Boolean, default=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    source_records: Mapped[list["SourceOpportunity"]] = relationship(back_populates="master")
    asset_facility_type_assignments: Mapped[list["OpportunityAssetFacilityType"]] = relationship(back_populates="opportunity", cascade="all, delete-orphan")

class AssetFacilityType(Base):
    """Reviewed business-facing asset/site-type registry."""
    __tablename__ = "asset_facility_types"
    canonical_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    label_ar: Mapped[str] = mapped_column(String(200), unique=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

class AssetFacilityTypeAlias(Base):
    """Source and field scoped aliases; raw source values remain in payloads."""
    __tablename__ = "asset_facility_type_aliases"
    __table_args__ = (UniqueConstraint("source_key", "source_field", "source_value", name="uq_asset_type_alias_source_field_value"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    source_key: Mapped[str] = mapped_column(String(80), index=True)
    source_field: Mapped[str] = mapped_column(String(120))
    source_value: Mapped[str] = mapped_column(String(300))
    canonical_id: Mapped[str] = mapped_column(ForeignKey("asset_facility_types.canonical_id"), index=True)

class OpportunityAssetFacilityType(Base):
    """Many-to-many Master assignments retaining source-level evidence."""
    __tablename__ = "opportunity_asset_facility_types"
    __table_args__ = (UniqueConstraint("opportunity_id", "canonical_id", "source_record_id", name="uq_master_asset_type_source"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    opportunity_id: Mapped[int] = mapped_column(ForeignKey("opportunities.id", ondelete="CASCADE"), index=True)
    canonical_id: Mapped[str] = mapped_column(ForeignKey("asset_facility_types.canonical_id"), index=True)
    source_record_id: Mapped[int] = mapped_column(ForeignKey("source_opportunities.id", ondelete="CASCADE"), index=True)
    raw_value: Mapped[str] = mapped_column(String(600))
    opportunity: Mapped[Opportunity] = relationship(back_populates="asset_facility_type_assignments")
    asset_type: Mapped[AssetFacilityType] = relationship()
    source_record: Mapped["SourceOpportunity"] = relationship()

class SourceOpportunity(Base):
    __tablename__ = "source_opportunities"
    __table_args__ = (UniqueConstraint("source_id", "source_opportunity_id", name="uq_source_external_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), index=True)
    master_opportunity_id: Mapped[int | None] = mapped_column(ForeignKey("opportunities.id"), index=True, nullable=True)
    source_opportunity_id: Mapped[str] = mapped_column(String(200))
    official_source_id_original: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    official_source_id_normalized: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    source_reference_number: Mapped[str | None] = mapped_column(String(200))
    source_reference_number_normalized: Mapped[str | None] = mapped_column(String(200), index=True)
    source_title: Mapped[str] = mapped_column(Text)
    normalized_source_title: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str] = mapped_column(String(1000))
    source_owner: Mapped[str | None] = mapped_column(String(300))
    source_sector: Mapped[str | None] = mapped_column(String(200))
    source_activity: Mapped[str | None] = mapped_column(String(300))
    source_sub_activity: Mapped[str | None] = mapped_column(String(300))
    source_subsector: Mapped[str | None] = mapped_column(String(200))
    normalized_sector: Mapped[str | None] = mapped_column(String(80))
    normalized_subsector: Mapped[str | None] = mapped_column(String(80))
    raw_location: Mapped[str | None] = mapped_column(Text)
    raw_area: Mapped[str | None] = mapped_column(String(100))
    raw_value: Mapped[str | None] = mapped_column(String(100))
    raw_dates: Mapped[dict] = mapped_column(JSON, default=dict)
    raw_status: Mapped[str | None] = mapped_column(String(100))
    canonical_status: Mapped[str] = mapped_column(String(80), default="غير محددة", index=True)
    raw_data_json: Mapped[dict] = mapped_column(JSON, default=dict)
    standardized_data_json: Mapped[dict] = mapped_column(JSON, default=dict)
    standardization_version: Mapped[str] = mapped_column(String(40), default="0")
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    content_hash: Mapped[str] = mapped_column(String(64))
    parser_version: Mapped[str] = mapped_column(String(40))
    missing_successful_checks: Mapped[int] = mapped_column(Integer, default=0)
    last_missing_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    master: Mapped[Opportunity | None] = relationship(back_populates="source_records")
    source: Mapped[Source] = relationship()
    opportunity_locations: Mapped[list["OpportunityLocation"]] = relationship(back_populates="source_opportunity")

class OpportunityLocation(Base):
    """Source-preserved place names for projects covering one or several cities."""
    __tablename__ = "opportunity_locations"
    __table_args__ = (UniqueConstraint("source_opportunity_id", "location_name", name="uq_opportunity_location_source_name"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    source_opportunity_id: Mapped[int] = mapped_column(ForeignKey("source_opportunities.id"), index=True)
    location_name: Mapped[str] = mapped_column(String(200))
    location_scope: Mapped[str] = mapped_column(String(40), default="SINGLE_LOCATION")
    is_al_ahsa: Mapped[bool] = mapped_column(Boolean, default=False)
    source_location_text: Mapped[str | None] = mapped_column(Text)
    geography_reference_unit_id: Mapped[int | None] = mapped_column(ForeignKey("geographic_reference_units.id"), nullable=True, index=True)
    source_evidence_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    source_opportunity: Mapped[SourceOpportunity] = relationship(back_populates="opportunity_locations")

class GeographicReferenceDataset(Base):
    """Versioned, provenance-bearing administrative reference import registry."""
    __tablename__ = "geographic_reference_datasets"
    __table_args__ = (UniqueConstraint("dataset_key", "version", name="uq_geography_dataset_version"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    dataset_key: Mapped[str] = mapped_column(String(120), index=True)
    version: Mapped[str] = mapped_column(String(100))
    effective_date: Mapped[str | None] = mapped_column(String(40), nullable=True)
    operator: Mapped[str] = mapped_column(String(300))
    source_url: Mapped[str] = mapped_column(String(1200))
    license_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    license_url: Mapped[str | None] = mapped_column(String(1200), nullable=True)
    license_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    coverage_json: Mapped[dict] = mapped_column(JSON, default=dict)
    provenance_json: Mapped[dict] = mapped_column(JSON, default=dict)
    content_sha256: Mapped[str] = mapped_column(String(64))
    import_status: Mapped[str] = mapped_column(String(30), default="IMPORTED")
    is_current: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    imported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

class GeographicReferenceUnit(Base):
    """Administrative unit identity within a single imported dataset version."""
    __tablename__ = "geographic_reference_units"
    __table_args__ = (UniqueConstraint("dataset_id", "level", "external_id", name="uq_geography_unit_dataset_level_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    dataset_id: Mapped[int] = mapped_column(ForeignKey("geographic_reference_datasets.id", ondelete="CASCADE"), index=True)
    level: Mapped[str] = mapped_column(String(30), index=True)
    external_id: Mapped[str] = mapped_column(String(200))
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("geographic_reference_units.id"), nullable=True, index=True)
    parent_external_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    name_ar: Mapped[str] = mapped_column(String(300))
    name_en: Mapped[str | None] = mapped_column(String(300), nullable=True)
    aliases_json: Mapped[list] = mapped_column(JSON, default=list)
    geometry_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    source_record_json: Mapped[dict] = mapped_column(JSON, default=dict)

class SourceGeographicCoverage(Base):
    """Explicit source coverage assessment for one verified region reference unit."""
    __tablename__ = "source_geographic_coverage"
    __table_args__ = (
        UniqueConstraint("source_id", "geographic_reference_unit_id", name="uq_source_geographic_coverage_unit"),
        CheckConstraint("coverage_status IN ('COVERED','NOT_COVERED','PARTIAL')", name="ck_source_geographic_coverage_status"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), index=True)
    geographic_reference_unit_id: Mapped[int] = mapped_column(ForeignKey("geographic_reference_units.id", ondelete="CASCADE"), index=True)
    coverage_status: Mapped[str] = mapped_column(String(20))
    assessment_json: Mapped[dict] = mapped_column(JSON, default=dict)
    assessed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

class QualificationReview(Base):
    """Human review queue for source content with unresolved investment eligibility."""
    __tablename__ = "qualification_reviews"
    __table_args__ = (UniqueConstraint("source_id", "external_id", name="uq_qualification_review_source_external"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), index=True)
    source_record_id: Mapped[int | None] = mapped_column(ForeignKey("source_opportunities.id"), nullable=True)
    external_id: Mapped[str] = mapped_column(String(200))
    title: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str] = mapped_column(String(1200))
    proposed_type: Mapped[str | None] = mapped_column(String(80))
    reason: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(30), default="PENDING")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

class SourceOpportunityDatasetMembership(Base):
    """Current and historical endpoint membership for a canonical source listing."""
    __tablename__ = "source_opportunity_dataset_memberships"
    __table_args__ = (UniqueConstraint("source_opportunity_id", "dataset_name", name="uq_source_dataset_membership"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    source_opportunity_id: Mapped[int] = mapped_column(ForeignKey("source_opportunities.id"), index=True)
    dataset_name: Mapped[str] = mapped_column(String(100))
    endpoint: Mapped[str] = mapped_column(String(600))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    missing_successful_checks: Mapped[int] = mapped_column(Integer, default=0)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)
    dataset_specific_metadata: Mapped[dict] = mapped_column(JSON, default=dict)

class SourceObservation(Base):
    """Immutable payload versions observed from a source endpoint."""
    __tablename__ = "source_observations"
    __table_args__ = (UniqueConstraint("source_opportunity_id", "endpoint", "content_hash", name="uq_source_observation_version"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    source_opportunity_id: Mapped[int] = mapped_column(ForeignKey("source_opportunities.id"), index=True)
    dataset_name: Mapped[str] = mapped_column(String(100))
    endpoint: Mapped[str] = mapped_column(String(600))
    official_source_id_original: Mapped[str] = mapped_column(String(200))
    official_source_id_normalized: Mapped[str] = mapped_column(String(200), index=True)
    raw_data_json: Mapped[dict] = mapped_column(JSON)
    source_updated_at: Mapped[str | None] = mapped_column(String(80))
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

class SourceOpportunityTaxonomy(Base):
    """Dataset taxonomy memberships, independent of cross-source conflicts."""
    __tablename__ = "source_opportunity_taxonomies"
    __table_args__ = (UniqueConstraint("source_opportunity_id", "dataset_name", "source_taxonomy_value", name="uq_source_taxonomy_membership"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    source_opportunity_id: Mapped[int] = mapped_column(ForeignKey("source_opportunities.id"), index=True)
    dataset_name: Mapped[str] = mapped_column(String(100))
    source_taxonomy_value: Mapped[str] = mapped_column(String(200))
    normalized_taxonomy_value: Mapped[str] = mapped_column(String(80))
    mapping_rule: Mapped[str] = mapped_column(String(300))
    mapping_version: Mapped[str] = mapped_column(String(40), default="1")

class SourceContentItem(Base):
    """Discovered publisher pages retained independently from qualified opportunities."""
    __tablename__ = "source_content_items"
    __table_args__ = (UniqueConstraint("source_id", "external_key", name="uq_source_content_key"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), index=True)
    external_key: Mapped[str] = mapped_column(String(1000))
    url: Mapped[str] = mapped_column(String(1200))
    title: Mapped[str] = mapped_column(Text, default="")
    publication_date: Mapped[str | None] = mapped_column(String(40))
    content_type: Mapped[str] = mapped_column(String(60), default="NON_INVESTMENT_CONTENT")
    raw_text: Mapped[str] = mapped_column(Text, default="")
    extracted_description: Mapped[str] = mapped_column(Text, default="")
    attachments_json: Mapped[list] = mapped_column(JSON, default=list)
    detected_keywords_json: Mapped[list] = mapped_column(JSON, default=list)
    fingerprint: Mapped[str] = mapped_column(String(64))
    extracted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    parser_version: Mapped[str] = mapped_column(String(40))
    material_change: Mapped[bool] = mapped_column(Boolean, default=False)

class SourceLimitation(Base):
    __tablename__ = "source_limitations"
    __table_args__ = (UniqueConstraint("source_id", "limitation_type", "evidence_url", name="uq_source_limitation_evidence"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), index=True)
    limitation_type: Mapped[str] = mapped_column(String(40))
    description: Mapped[str] = mapped_column(Text)
    evidence_url: Mapped[str] = mapped_column(String(1200))
    first_detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    affects_completeness: Mapped[bool] = mapped_column(Boolean, default=True)
    resolution: Mapped[str | None] = mapped_column(Text)

class ModonLocation(Base):
    __tablename__ = "modon_locations"
    __table_args__ = (UniqueConstraint("source_identifier", name="uq_modon_location_source_identifier"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    official_name_ar: Mapped[str | None] = mapped_column(String(300))
    official_name_en: Mapped[str] = mapped_column(String(300))
    location_type: Mapped[str] = mapped_column(String(60))
    source_identifier: Mapped[str] = mapped_column(String(200))
    region: Mapped[str | None] = mapped_column(String(200))
    governorate: Mapped[str | None] = mapped_column(String(200))
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    source_url: Mapped[str] = mapped_column(String(1200))
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

class NcpProjectEvent(Base):
    __tablename__ = "ncp_project_events"
    __table_args__ = (UniqueConstraint("project_source_opportunity_id", "source_url", "event_type", name="uq_ncp_project_event_source"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    project_source_opportunity_id: Mapped[int] = mapped_column(ForeignKey("source_opportunities.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(40))
    event_date: Mapped[str | None] = mapped_column(String(40))
    source_url: Mapped[str] = mapped_column(String(1200))
    stage_before: Mapped[str | None] = mapped_column(String(40))
    stage_after: Mapped[str] = mapped_column(String(40))
    raw_title: Mapped[str] = mapped_column(Text)
    raw_data: Mapped[dict] = mapped_column(JSON, default=dict)

class LocationReview(Base):
    __tablename__ = "location_reviews"
    __table_args__ = (UniqueConstraint("source_id", "external_id", name="uq_location_review_source_external"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), index=True)
    external_id: Mapped[str] = mapped_column(String(200))
    source_record_id: Mapped[int | None] = mapped_column(ForeignKey("source_opportunities.id"), nullable=True)
    title: Mapped[str] = mapped_column(Text)
    sector: Mapped[str | None] = mapped_column(String(200))
    source_location: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    evidence: Mapped[str] = mapped_column(Text, default="")
    confidence_score: Mapped[float] = mapped_column(Float)
    reason: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(30), default="PENDING")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

class TaxonomyMapping(Base):
    __tablename__ = "taxonomy_mappings"
    __table_args__ = (UniqueConstraint("source_key", "source_value", name="uq_taxonomy_source_value"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    source_key: Mapped[str] = mapped_column(String(80), index=True)
    source_value: Mapped[str] = mapped_column(String(200))
    normalized_value: Mapped[str] = mapped_column(String(80))
    mapping_rule: Mapped[str] = mapped_column(String(300))
    mapping_version: Mapped[str] = mapped_column(String(40), default="1")

class OrganizationAlias(Base):
    __tablename__ = "organization_aliases"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[str] = mapped_column(String(80), index=True)
    canonical_name_ar: Mapped[str] = mapped_column(String(300))
    canonical_name_en: Mapped[str] = mapped_column(String(300))
    alias: Mapped[str] = mapped_column(String(300), unique=True)
    source_key: Mapped[str | None] = mapped_column(String(80))

class ChangeHistory(Base):
    __tablename__ = "opportunity_change_history"
    id: Mapped[int] = mapped_column(primary_key=True)
    opportunity_id: Mapped[int] = mapped_column(ForeignKey("opportunities.id"), index=True)
    changed_field: Mapped[str] = mapped_column(String(100))
    previous_value: Mapped[str | None] = mapped_column(Text)
    new_value: Mapped[str | None] = mapped_column(Text)
    source_id: Mapped[int | None] = mapped_column(ForeignKey("sources.id"))
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

class SyncJob(Base):
    __tablename__ = "source_sync_jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(40))
    pages_scanned: Mapped[int] = mapped_column(Integer, default=0)
    raw_count: Mapped[int] = mapped_column(Integer, default=0)
    ahsa_count: Mapped[int] = mapped_column(Integer, default=0)
    new_count: Mapped[int] = mapped_column(Integer, default=0)
    duplicate_count: Mapped[int] = mapped_column(Integer, default=0)
    update_count: Mapped[int] = mapped_column(Integer, default=0)
    rejected_count: Mapped[int] = mapped_column(Integer, default=0)
    unchanged_count: Mapped[int] = mapped_column(Integer, default=0)
    source_total_reported: Mapped[int | None] = mapped_column(Integer)
    pages_requested: Mapped[int] = mapped_column(Integer, default=0)
    pages_successful: Mapped[int] = mapped_column(Integer, default=0)
    records_received: Mapped[int] = mapped_column(Integer, default=0)
    records_parsed: Mapped[int] = mapped_column(Integer, default=0)
    unique_records: Mapped[int] = mapped_column(Integer, default=0)
    duplicate_candidates_count: Mapped[int] = mapped_column(Integer, default=0)
    merged_records_count: Mapped[int] = mapped_column(Integer, default=0)
    removed_records_count: Mapped[int] = mapped_column(Integer, default=0)
    active_count: Mapped[int] = mapped_column(Integer, default=0)
    expired_count: Mapped[int] = mapped_column(Integer, default=0)
    duplicate_items_between_pages: Mapped[int] = mapped_column(Integer, default=0)
    collection_completeness_percent: Mapped[float | None] = mapped_column(Float)
    pagination_complete: Mapped[bool | None] = mapped_column(Boolean)
    location_review_count: Mapped[int] = mapped_column(Integer, default=0)
    metrics_json: Mapped[dict] = mapped_column(JSON, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text)
    job_state: Mapped[str] = mapped_column(String(40), default="RUNNING", index=True)
    trigger_type: Mapped[str] = mapped_column(String(20), default="manual")
    queued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    worker_id: Mapped[str | None] = mapped_column(String(200))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    correlation_id: Mapped[str | None] = mapped_column(String(100), index=True)
    attempt_number: Mapped[int] = mapped_column(Integer, default=1)
    celery_task_id: Mapped[str | None] = mapped_column(String(100), index=True)

class SourceError(Base):
    __tablename__ = "source_errors"
    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    category: Mapped[str] = mapped_column(String(80))
    message: Mapped[str] = mapped_column(Text)

class DuplicateCandidate(Base):
    __tablename__ = "duplicate_candidates"
    id: Mapped[int] = mapped_column(primary_key=True)
    left_opportunity_id: Mapped[int] = mapped_column(ForeignKey("opportunities.id"), index=True)
    right_opportunity_id: Mapped[int] = mapped_column(ForeignKey("opportunities.id"), index=True)
    confidence_score: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(30), default="PENDING")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    explanation_json: Mapped[dict | None] = mapped_column(JSON)

class FieldProvenance(Base):
    __tablename__ = "opportunity_field_provenance"
    id: Mapped[int] = mapped_column(primary_key=True)
    opportunity_id: Mapped[int] = mapped_column(ForeignKey("opportunities.id"), index=True)
    field_name: Mapped[str] = mapped_column(String(100))
    selected_value: Mapped[str | None] = mapped_column(Text)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"))
    source_record_id: Mapped[int] = mapped_column(ForeignKey("source_opportunities.id"))
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    confidence: Mapped[float] = mapped_column(Float, default=1)
    source: Mapped[Source] = relationship()

class OpportunityDocument(Base):
    __tablename__ = "opportunity_documents"
    id: Mapped[int] = mapped_column(primary_key=True)
    opportunity_id: Mapped[int] = mapped_column(ForeignKey("opportunities.id"), index=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"))
    title: Mapped[str] = mapped_column(String(500))
    url: Mapped[str] = mapped_column(String(1200))
    document_type: Mapped[str | None] = mapped_column(String(100))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

class SystemEvent(Base):
    __tablename__ = "system_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    event_type: Mapped[str] = mapped_column(String(100), index=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

class SystemSetting(Base):
    __tablename__ = "system_settings"
    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(120), unique=True)
    value: Mapped[str] = mapped_column(Text)

class OpportunityConflict(Base):
    __tablename__ = "opportunity_data_conflicts"
    id: Mapped[int] = mapped_column(primary_key=True)
    opportunity_id: Mapped[int] = mapped_column(ForeignKey("opportunities.id"), index=True)
    field_name: Mapped[str] = mapped_column(String(100))
    conflict_type: Mapped[str] = mapped_column(String(40), default="FIELD_VALUE_CONFLICT")
    selected_value: Mapped[str] = mapped_column(Text)
    conflicting_value: Mapped[str] = mapped_column(Text)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"))
    source_record_id: Mapped[int] = mapped_column(ForeignKey("source_opportunities.id"))
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(30), default="OPEN")

class MergeAudit(Base):
    __tablename__ = "opportunity_merge_audit"
    id: Mapped[int] = mapped_column(primary_key=True)
    merged_opportunity_id: Mapped[int] = mapped_column(ForeignKey("opportunities.id"), index=True)
    target_opportunity_id: Mapped[int] = mapped_column(ForeignKey("opportunities.id"), index=True)
    source_record_ids: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    merged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    undone_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    merge_reason: Mapped[str | None] = mapped_column(Text)
    merge_evidence: Mapped[dict | None] = mapped_column(JSON)
    performed_by: Mapped[str | None] = mapped_column(String(200))
    target_before_json: Mapped[dict | None] = mapped_column(JSON)
    target_after_json: Mapped[dict | None] = mapped_column(JSON)
    source_history_ids: Mapped[list] = mapped_column(JSON, default=list)
    source_provenance_ids: Mapped[list] = mapped_column(JSON, default=list)
    source_conflict_ids: Mapped[list] = mapped_column(JSON, default=list)
    source_document_ids: Mapped[list] = mapped_column(JSON, default=list)
    merge_history_ids: Mapped[list] = mapped_column(JSON, default=list)

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    display_name: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(40), default="admin")
    password_hash: Mapped[str] = mapped_column(String(255), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    failed_login_count: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class UserSession(Base):
    __tablename__ = "user_sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(100), index=True)
    entity_type: Mapped[str | None] = mapped_column(String(100))
    entity_id: Mapped[str | None] = mapped_column(String(200))
    before_json: Mapped[dict | None] = mapped_column(JSON)
    after_json: Mapped[dict | None] = mapped_column(JSON)
    request_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

class AlertEvent(Base):
    __tablename__ = "alert_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    event_type: Mapped[str] = mapped_column(String(100), index=True)
    severity: Mapped[str] = mapped_column(String(20), index=True)
    source_id: Mapped[int | None] = mapped_column(ForeignKey("sources.id"), nullable=True, index=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="OPEN", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    acknowledged_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notification_state: Mapped[str] = mapped_column(String(20), default="PENDING")
    notification_error: Mapped[str | None] = mapped_column(Text)

"""Populate only an isolated 0027-compatible preview database for Master 597."""
import hashlib
import os
from datetime import datetime, timezone

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.models import Base, Opportunity, OpportunityDocument, Source, SourceOpportunity


PAGE = "https://furas.momah.gov.sa/index.php/ar/opportunity/01-26-017001-42008?type=Investment"
REFERENCE = "01-26-017001-42008"
NOW = datetime.now(timezone.utc)
engine = create_engine(os.environ["DATABASE_URL"])
Base.metadata.create_all(engine)

with Session(engine) as db:
    source = db.query(Source).filter_by(source_key="furas").one_or_none()
    if source is None:
        source = Source(
            source_key="furas", source_name_ar="فرص", organization_name="وزارة البلديات والإسكان",
            base_url="https://furas.momah.gov.sa", opportunities_url="https://furas.momah.gov.sa/",
            source_type="official", priority=1, enabled=False, technical_health="UNKNOWN",
            coverage_status="UNKNOWN_COVERAGE",
        )
        db.add(source)
        db.flush()

    master = db.get(Opportunity, 597)
    if master is None:
        master = Opportunity(
            id=597, canonical_id="FURAS-3188", title_ar="مبنى تجاري سكني",
            normalized_title="مبنى تجاري سكني", reference_number=REFERENCE,
            reference_number_normalized=REFERENCE, opportunity_owner="أمانة محافظة الأحساء",
            primary_publication_platform="فرص", city="الأحساء", district="ضاحية هجر",
            status="متاحة", submission_deadline="2026-12-28", first_seen_at=NOW,
            last_seen_at=NOW, last_updated_at=NOW, created_at=NOW, updated_at=NOW,
        )
        db.add(master)
        db.flush()

    source_record = db.get(SourceOpportunity, 3188)
    if source_record is None:
        source_record = SourceOpportunity(
            id=3188, source_id=source.id, master_opportunity_id=master.id,
            source_opportunity_id=REFERENCE, source_reference_number=REFERENCE,
            source_reference_number_normalized=REFERENCE, source_title=master.title_ar,
            normalized_source_title=master.normalized_title, source_url=PAGE,
            source_owner="أمانة محافظة الأحساء", raw_status="متاحة", canonical_status="متاحة",
            raw_dates={}, raw_data_json={}, standardized_data_json={}, standardization_version="0",
            first_seen_at=NOW, last_seen_at=NOW, content_hash="f" * 64, parser_version="isolated-preview",
        )
        db.add(source_record)
        db.flush()

    document = db.query(OpportunityDocument).filter_by(
        source_opportunity_id=3188, official_provider_document_id="270741756", document_version=1,
    ).one_or_none()
    if document is None:
        document = OpportunityDocument(
            opportunity_id=master.id, source_id=source.id, source_opportunity_id=source_record.id,
            official_provider_document_id="270741756", title="كراسة الشروط والمواصفات", url=PAGE,
            document_type="HTML_SOURCE_PAGE", document_category="TERMS_AND_CONDITIONS_BOOKLET",
            first_seen_at=NOW, source_opportunity_url=PAGE, access_status="PUBLIC_SOURCE_PAGE",
            rights_status="SOURCE_PAGE_LINK_ONLY", authentication_required=False,
            payment_required_for_document=None,
            participation_requirement="PURCHASE_REQUIRED_FOR_PARTICIPATION",
            booklet_price_amount=None, currency=None,
            link_verification_status="VERIFIED_SOURCE_PAGE", last_verified_at=NOW,
            source_provenance_json={
                "preview_only": True,
                "direct_download_status": "UNAVAILABLE",
                "direct_download_http_status": 302,
                "direct_download_destination": "/list-opportunities",
                "direct_download_content_type": "text/html",
                "displayed_amount": "1500",
                "displayed_amount_label": "سعر الكراسة",
                "currency": None,
                "currency_status": "UNVERIFIED",
                "participation_purchase_evidence": "Individual Furas page offers booklet purchase; official service workflow places purchase before bid submission.",
                "page_lifecycle_observation": "Page displayed live countdown on 2026-11-18; submission opening date 2026-12-28.",
            },
            document_version=1,
            deduplication_key=hashlib.sha256(b"furas|3188|270741756|page-only|v1").hexdigest(),
            publication_status="APPROVED",
        )
        db.add(document)
    db.commit()
    print("PREVIEW_SEED_OK source=furas source_opportunity=3188 master=597 document=1 amount=NULL currency=NULL")

engine.dispose()

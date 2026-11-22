import json
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app import main
from app.documents import DocumentCandidateError, document_json, is_official_http_url, validate_document_candidate
from app.models import Base, Opportunity, OpportunityDocument, Source, SourceOpportunity


FIXTURES = json.loads((Path(__file__).parent / "fixtures/opportunity_documents/scenarios.json").read_text(encoding="utf-8"))
NOW = datetime(2026, 11, 15, tzinfo=timezone.utc)


@pytest.fixture
def isolated_documents_db(monkeypatch):
    database_url = os.getenv("DOCUMENTS_TEST_DATABASE_URL", "")
    if not database_url:
        # These tests DROP the public schema, so they only run against the
        # dedicated disposable database; skip (don't fail) when none is configured.
        pytest.skip("DOCUMENTS_TEST_DATABASE_URL not set (needs the disposable documents-mvp-pg-test PostgreSQL)")
    parsed = urlparse(database_url)
    if (parsed.hostname != "documents-mvp-pg-test" or parsed.username != "documents_test"
            or parsed.path != "/documents_mvp_test" or os.getenv("DATABASE_URL") != database_url):
        raise RuntimeError("Database tests require the named disposable documents-mvp-pg-test PostgreSQL database")
    engine = create_engine(database_url, pool_pre_ping=True)
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(main, "SessionLocal", factory)
    monkeypatch.setattr(main, "engine", engine)
    with factory() as db:
        source = Source(
            source_key="synthetic-docs", source_name_ar="مصدر تجريبي", organization_name="جهة اختبار",
            base_url=FIXTURES["source_host"], opportunities_url=FIXTURES["source_host"] + "/opportunities",
            source_type="official", priority=1, enabled=True, technical_health="UNKNOWN",
            coverage_status="UNKNOWN_COVERAGE")
        db.add(source)
        db.flush()
        masters = []
        for index in range(2):
            master = Opportunity(
                canonical_id=f"SYNTHETIC-DOC-{index}", title_ar=f"فرصة تجريبية {index}",
                normalized_title=f"فرصة تجريبية {index}", opportunity_owner="جهة اختبار",
                primary_publication_platform="مصدر تجريبي", city="الأحساء", status="متاحة",
                first_seen_at=NOW, last_seen_at=NOW, last_updated_at=NOW, created_at=NOW, updated_at=NOW)
            db.add(master)
            db.flush()
            masters.append(master)
        source_records = []
        for index, master in enumerate((masters[0], masters[0], masters[1])):
            record = SourceOpportunity(
                source_id=source.id, master_opportunity_id=master.id, source_opportunity_id=f"fixture-{index}",
                source_title=master.title_ar, normalized_source_title=master.normalized_title,
                source_url=f"{FIXTURES['source_host']}/opportunities/fixture-{index}",
                raw_status="متاحة", canonical_status="متاحة", raw_dates={}, raw_data_json={},
                standardized_data_json={}, first_seen_at=NOW, last_seen_at=NOW,
                content_hash=f"synthetic-{index}", parser_version="fixture")
            db.add(record)
            db.flush()
            source_records.append(record)
        db.commit()
        identity = {"source": source, "masters": masters, "source_records": source_records}
    client = TestClient(main.app)
    try:
        yield factory, client, identity
    finally:
        client.close()
        engine.dispose()


def make_document(source, source_record, master, **overrides):
    values = {
        "opportunity_id": master.id,
        "source_id": source.id,
        "source_opportunity_id": source_record.id,
        "official_provider_document_id": "synthetic-doc-1",
        "title": "كراسة الشروط التجريبية",
        "url": FIXTURES["source_host"] + "/documents/booklet.pdf",
        "document_type": "PDF",
        "document_category": "TERMS_AND_CONDITIONS_BOOKLET",
        "first_seen_at": NOW,
        "source_opportunity_url": source_record.source_url,
        "access_status": "PUBLIC_DIRECT_DOWNLOAD",
        "rights_status": "DIRECT_LINK_APPROVED",
        "authentication_required": False,
        "payment_required_for_document": False,
        "participation_requirement": "UNKNOWN",
        "link_verification_status": "VERIFIED_PUBLIC",
        "last_verified_at": NOW,
        "source_provenance_json": {"synthetic_only": True, "evidence": "fixture"},
        "document_version": 1,
        "deduplication_key": "a" * 64,
        "publication_status": "APPROVED",
    }
    values.update(overrides)
    return OpportunityDocument(**values)


def test_fixture_inventory_is_synthetic_and_covers_all_required_scenarios():
    assert FIXTURES["synthetic_only"] is True
    assert len(FIXTURES["scenarios"]) == 12
    assert {case["id"] for case in FIXTURES["scenarios"]} == set("ABCDEFGHIJKL")
    assert "example.invalid" in FIXTURES["source_host"]
    scenarios = {case["id"]: case for case in FIXTURES["scenarios"]}
    assert scenarios["A"]["price"] is None and scenarios["A"]["currency"] is None
    assert scenarios["B"]["price"] == 300 and scenarios["B"]["currency"] == "SAR"
    assert scenarios["F"]["rights_status"] == "UNVERIFIED"
    assert scenarios["E"]["publication_status"] == "DRAFT"


def test_api_exposes_only_exact_approved_documents_grouped_by_source(isolated_documents_db):
    factory, client, data = isolated_documents_db
    source = data["source"]
    master, other_master = data["masters"]
    first, second, other = data["source_records"]
    with factory() as db:
        db.add(make_document(source, first, master, official_provider_document_id="first", deduplication_key="1" * 64,
                             participation_requirement="PURCHASE_REQUIRED_FOR_PARTICIPATION",
                             booklet_price_amount=300, currency="SAR"))
        db.add(make_document(source, first, master, official_provider_document_id="second", deduplication_key="2" * 64,
                             title="مخطط الموقع", document_category="SITE_MAP"))
        db.add(make_document(source, second, master, official_provider_document_id="third", deduplication_key="3" * 64,
                             access_status="LOGIN_REQUIRED", authentication_required=True, rights_status="SOURCE_PAGE_LINK_ONLY",
                             link_verification_status="VERIFIED_SOURCE_PAGE"))
        db.add(make_document(source, second, master, official_provider_document_id="fourth", deduplication_key="4" * 64,
                             access_status="PAYMENT_REQUIRED_FOR_DOCUMENT", rights_status="SOURCE_PAGE_LINK_ONLY",
                             link_verification_status="VERIFIED_SOURCE_PAGE", payment_required_for_document=True,
                             official_purchase_url=second.source_url,
                             purchase_url_verified=True, participation_requirement="PURCHASE_REQUIRED_FOR_PARTICIPATION"))
        db.add(make_document(source, second, master, official_provider_document_id="fifth", deduplication_key="5" * 64,
                             access_status="UNKNOWN", rights_status="SOURCE_PAGE_LINK_ONLY",
                             link_verification_status="VERIFIED_SOURCE_PAGE", publication_status="DRAFT"))
        db.add(make_document(source, second, master, official_provider_document_id="unverified-rights", deduplication_key="9" * 64,
                             title="مستند بحقوق غير مؤكدة", rights_status="UNVERIFIED", publication_status="DRAFT"))
        db.add(make_document(source, second, master, official_provider_document_id="unapproved", deduplication_key="d" * 64,
                             title="مستند غير معتمد", publication_status="DRAFT"))
        db.add(make_document(source, other, other_master, official_provider_document_id="restricted", deduplication_key="6" * 64,
                             access_status="RESTRICTED", rights_status="RESTRICTED", publication_status="DRAFT"))
        # A mismatched Master field is valid legacy shape but cannot be serialized through this SourceOpportunity.
        db.add(make_document(source, first, other_master, official_provider_document_id="conflict", deduplication_key="7" * 64))
        # Host mismatch is rejected at serialization even if a row is incorrectly marked approved.
        db.add(make_document(source, first, master, official_provider_document_id="unsafe", deduplication_key="8" * 64,
                             url="https://evil.example.invalid/document.pdf"))
        db.commit()

    response = client.get(f"/api/opportunities/{master.id}")
    assert response.status_code == 200
    result = response.json()
    docs = result["documents"]
    assert len(docs) == 4
    assert all(doc["access_status"] != "UNKNOWN" for doc in docs)
    assert all(doc["title"] not in {"مستند غير معتمد", "مستند بحقوق غير مؤكدة"} for doc in docs)
    assert {doc["source_opportunity_id"] for doc in docs} == {first.id, second.id}
    assert all(doc["master_opportunity_id"] == master.id for doc in docs)
    assert all(doc["provider_opportunity_reference"] in {"fixture-0", "fixture-1"} for doc in docs)
    booklet = next(doc for doc in docs if doc["title"] == "كراسة الشروط التجريبية")
    assert booklet["booklet_price_amount"] == 300 and booklet["currency"] == "SAR"
    assert booklet["participation_requirement"] == "PURCHASE_REQUIRED_FOR_PARTICIPATION"
    assert booklet["payment_required_for_document"] is False
    login_doc = next(doc for doc in docs if doc["access_status"] == "LOGIN_REQUIRED")
    assert login_doc["link_url"] == second.source_url and login_doc["authentication_required"] is True
    payment_doc = next(doc for doc in docs if doc["access_status"] == "PAYMENT_REQUIRED_FOR_DOCUMENT")
    assert payment_doc["link_url"] == second.source_url and payment_doc["official_purchase_url"] == second.source_url
    assert payment_doc["payment_required_for_document"] is True
    assert next(doc for doc in docs if doc["title"] == "مخطط الموقع")["document_category"] == "SITE_MAP"
    assert result["document_source_pages"]
    other_result = client.get(f"/api/opportunities/{other_master.id}").json()
    assert all(doc["title"] != "كراسة الشروط التجريبية" for doc in other_result["documents"])


def test_document_publication_constraints_and_source_scoped_deduplication(isolated_documents_db):
    factory, _, data = isolated_documents_db
    source = data["source"]
    master = data["masters"][0]
    source_record = data["source_records"][0]
    with factory() as db:
        first = make_document(source, source_record, master)
        db.add(first)
        db.commit()
        duplicate = make_document(source, source_record, master, official_provider_document_id="dup")
        db.add(duplicate)
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
        bad_published_restricted = make_document(source, source_record, master, official_provider_document_id="bad",
            deduplication_key="b" * 64, access_status="RESTRICTED", rights_status="RESTRICTED")
        db.add(bad_published_restricted)
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
        bad_public_unknown_access = make_document(source, source_record, master, official_provider_document_id="unknown-flags",
            deduplication_key="f" * 64, authentication_required=None, payment_required_for_document=None)
        db.add(bad_public_unknown_access)
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
        legacy = OpportunityDocument(opportunity_id=master.id, source_id=source.id, title="Legacy row",
                                     url="https://legacy.invalid/item", document_type="legacy-pdf", first_seen_at=NOW)
        db.add(legacy)
        db.commit()
        assert legacy.id is not None and legacy.publication_status == "DRAFT"


def test_api_returns_only_latest_approved_document_version(isolated_documents_db):
    factory, client, data = isolated_documents_db
    source, master = data["source"], data["masters"][0]
    source_record = data["source_records"][0]
    with factory() as db:
        old = make_document(source, source_record, master, title="نسخة قديمة", deduplication_key="e" * 64)
        db.add(old)
        db.flush()
        db.add(make_document(source, source_record, master, title="نسخة أحدث", deduplication_key="e" * 64,
                             document_version=2, supersedes_document_id=old.id))
        db.commit()
    documents = client.get(f"/api/opportunities/{master.id}").json()["documents"]
    assert len(documents) == 1
    assert documents[0]["title"] == "نسخة أحدث"


def test_url_validation_rejects_unsafe_and_unassociated_destinations(isolated_documents_db):
    _, _, data = isolated_documents_db
    source = data["source"]
    source_record = data["source_records"][0]
    master = data["masters"][0]
    assert is_official_http_url(FIXTURES["source_host"] + "/document.pdf", [source.base_url])
    for url in FIXTURES["scenarios"][-1]["unsafe_urls"]:
        assert not is_official_http_url(url, [source.base_url])
    assert not is_official_http_url("https://source.example.invalid/document.pdf?access%5Ftoken=secret", [source.base_url])
    assert not is_official_http_url("https://source.example.invalid/document.pdf?api_key=secret", [source.base_url])
    assert not is_official_http_url("https://source.example.invalid/document.pdf#access_token=secret", [source.base_url])
    base_candidate = {
        "source_opportunity_id": source_record.id, "source_id": source.id,
        "master_opportunity_id": master.id, "association_status": "EXACT_ASSOCIATION_VERIFIED",
        "document_category": "TERMS_AND_CONDITIONS_BOOKLET", "access_status": "PUBLIC_DIRECT_DOWNLOAD",
        "rights_status": "DIRECT_LINK_APPROVED", "participation_requirement": "UNKNOWN",
        "authentication_required": False, "payment_required_for_document": False,
        "link_verification_status": "VERIFIED_PUBLIC",
        "source_opportunity_url": source_record.source_url,
        "url": FIXTURES["source_host"] + "/documents/booklet.pdf", "publication_status": "DRAFT",
    }
    assert validate_document_candidate(base_candidate, source_record, source)["validation_status"] == "VALIDATED_NO_WRITE"
    bad_master = {**base_candidate, "master_opportunity_id": data["masters"][1].id}
    with pytest.raises(DocumentCandidateError, match="Master association"):
        validate_document_candidate(bad_master, source_record, source)
    bad_link = {**base_candidate, "url": "http://127.0.0.1/admin"}
    with pytest.raises(DocumentCandidateError, match="Document URL"):
        validate_document_candidate(bad_link, source_record, source)
    unknown_security = {**base_candidate, "publication_status": "APPROVED", "authentication_required": None}
    with pytest.raises(DocumentCandidateError, match="confirmed public access"):
        validate_document_candidate(unknown_security, source_record, source)
    bad_rights = {**base_candidate, "rights_status": "UNVERIFIED"}
    with pytest.raises(DocumentCandidateError, match="rights"):
        validate_document_candidate(bad_rights, source_record, source)
    unknown_access = {**base_candidate, "publication_status": "APPROVED", "access_status": "UNKNOWN",
                      "rights_status": "SOURCE_PAGE_LINK_ONLY", "link_verification_status": "VERIFIED_SOURCE_PAGE"}
    with pytest.raises(DocumentCandidateError, match="Unknown access"):
        validate_document_candidate(unknown_access, source_record, source)


def test_source_page_fallback_and_rights_gate_hide_direct_urls(isolated_documents_db):
    factory, client, data = isolated_documents_db
    source = data["source"]
    master = data["masters"][0]
    source_record = data["source_records"][0]
    with factory() as db:
        db.add(make_document(source, source_record, master, rights_status="SOURCE_PAGE_LINK_ONLY",
            access_status="PUBLIC_SOURCE_PAGE", link_verification_status="VERIFIED_SOURCE_PAGE",
            url="https://source.example.invalid/private-or-unreviewed.pdf", deduplication_key="c" * 64,
            source_provenance_json={"direct_download_status": "UNAVAILABLE", "direct_download_http_status": 302,
                                    "redirect_target": "/list-opportunities"}))
        db.add(make_document(source, source_record, master, title="wrong page", rights_status="SOURCE_PAGE_LINK_ONLY",
            access_status="PUBLIC_SOURCE_PAGE", link_verification_status="VERIFIED_SOURCE_PAGE",
            source_opportunity_url="https://source.example.invalid/opportunities/other", deduplication_key="f" * 64))
        db.commit()
    detail = client.get(f"/api/opportunities/{master.id}").json()
    doc = detail["documents"][0]
    assert doc["link_url"] == source_record.source_url
    assert doc["direct_download_status"] == "UNAVAILABLE"
    assert "private-or-unreviewed.pdf" not in json.dumps(doc)
    assert detail["document_source_pages"][0]["url"] == source_record.source_url


def test_mode_d_candidate_keeps_unknown_currency_hidden_and_page_only(isolated_documents_db):
    _, _, data = isolated_documents_db
    source = data["source"]
    master = data["masters"][0]
    source_record = data["source_records"][0]
    candidate = {
        "source_opportunity_id": source_record.id, "source_id": source.id,
        "master_opportunity_id": master.id, "association_status": "EXACT_ASSOCIATION_VERIFIED",
        "document_category": "TERMS_AND_CONDITIONS_BOOKLET", "access_status": "PUBLIC_SOURCE_PAGE",
        "rights_status": "SOURCE_PAGE_LINK_ONLY", "participation_requirement": "PURCHASE_REQUIRED_FOR_PARTICIPATION",
        "authentication_required": None, "payment_required_for_document": None,
        "link_verification_status": "VERIFIED_SOURCE_PAGE", "source_opportunity_url": source_record.source_url,
        "url": source_record.source_url, "publication_status": "APPROVED",
        "booklet_price_amount": None, "currency": None,
        "source_provenance_json": {"direct_download_status": "UNAVAILABLE", "observed_amount": "1500",
                                    "currency_status": "UNVERIFIED"},
    }
    validated = validate_document_candidate(candidate, source_record, source)
    assert validated["validation_status"] == "VALIDATED_NO_WRITE"
    assert validated["booklet_price_amount"] is None and validated["currency"] is None
    assert validated["source_provenance_json"]["observed_amount"] == "1500"


def test_furas_3188_booklet_mode_d_is_exact_and_page_only_in_disposable_api(isolated_documents_db):
    factory, client, data = isolated_documents_db
    source_id = data["source"].id
    provider_ref = "01-26-017001-42008"
    page_url = f"https://furas.momah.gov.sa/index.php/ar/opportunity/{provider_ref}?type=Investment"
    dedupe = __import__("hashlib").sha256(f"furas:{provider_ref}:270741756:v1".encode()).hexdigest()
    with factory() as db:
        source = db.get(Source, source_id)
        source.source_key = "furas"
        source.source_name_ar = "فرص"
        source.organization_name = "وزارة البلديات والإسكان"
        source.base_url = "https://furas.momah.gov.sa"
        source.opportunities_url = "https://furas.momah.gov.sa/ar/list-opportunities"
        master = Opportunity(
            id=597, canonical_id="FURAS-3188", title_ar="فرصة مبنى تجاري سكني",
            normalized_title="فرصة مبنى تجاري سكني", opportunity_owner="أمانة محافظة الأحساء",
            primary_publication_platform="فرص", city="الأحساء", status="متاحة",
            first_seen_at=NOW, last_seen_at=NOW, last_updated_at=NOW, created_at=NOW, updated_at=NOW)
        db.add(master)
        db.flush()
        source_record = SourceOpportunity(
            id=3188, source_id=source.id, master_opportunity_id=master.id,
            source_opportunity_id=provider_ref, source_reference_number=provider_ref,
            source_reference_number_normalized=provider_ref, source_title="فرصة مبنى تجاري سكني",
            normalized_source_title="فرصة مبنى تجاري سكني", source_url=page_url,
            raw_status="Announced", canonical_status="متاحة", raw_dates={},
            raw_data_json={"attributes": {"OPPORTUNITYID": provider_ref, "RFPPRICE": "1500"}},
            standardized_data_json={}, first_seen_at=NOW, last_seen_at=NOW,
            content_hash="f" * 64, parser_version="real-candidate-isolated")
        db.add(source_record)
        db.flush()
        candidate = {
            "source_opportunity_id": source_record.id, "source_id": source.id,
            "master_opportunity_id": master.id, "association_status": "EXACT_ASSOCIATION_VERIFIED",
            "document_category": "TERMS_AND_CONDITIONS_BOOKLET", "access_status": "PUBLIC_SOURCE_PAGE",
            "rights_status": "SOURCE_PAGE_LINK_ONLY", "participation_requirement": "PURCHASE_REQUIRED_FOR_PARTICIPATION",
            "authentication_required": None, "payment_required_for_document": None,
            "link_verification_status": "VERIFIED_SOURCE_PAGE", "source_opportunity_url": page_url,
            "url": page_url, "publication_status": "APPROVED", "booklet_price_amount": None, "currency": None,
            "source_provenance_json": {
                "verification_mode": "MODE_D_OFFICIAL_SOURCE_PAGE_ONLY",
                "provider_reference": provider_ref, "official_attachment_id": "270741756",
                "direct_download_status": "UNAVAILABLE", "direct_download_http_status": 302,
                "redirect_target": "/list-opportunities", "amount_raw": "1500",
                "amount_label_ar": "سعر الكراسة", "currency_status": "UNVERIFIED",
                "currency_displayed": None,
                "participation_purchase_evidence": "Official service workflow plus this opportunity page purchase action",
            },
        }
        assert validate_document_candidate(candidate, source_record, source)["validation_status"] == "VALIDATED_NO_WRITE"
        document = make_document(
            source, source_record, master, official_provider_document_id="270741756",
            title="كراسة الشروط والمواصفات", url=page_url, source_opportunity_url=page_url,
            access_status="PUBLIC_SOURCE_PAGE", rights_status="SOURCE_PAGE_LINK_ONLY",
            authentication_required=None, payment_required_for_document=None,
            participation_requirement="PURCHASE_REQUIRED_FOR_PARTICIPATION",
            booklet_price_amount=None, currency=None, link_verification_status="VERIFIED_SOURCE_PAGE",
            last_verified_at=NOW, source_provenance_json=candidate["source_provenance_json"],
            deduplication_key=dedupe)
        db.add(document)
        db.commit()

    response = client.get("/api/opportunities/597")
    assert response.status_code == 200
    result = response.json()
    assert len(result["documents"]) == 1
    booklet = result["documents"][0]
    assert booklet["source_opportunity_id"] == 3188
    assert booklet["master_opportunity_id"] == 597
    assert booklet["provider_opportunity_reference"] == provider_ref
    assert booklet["link_url"] == page_url
    assert booklet["direct_download_status"] == "UNAVAILABLE"
    assert booklet["participation_requirement"] == "PURCHASE_REQUIRED_FOR_PARTICIPATION"
    assert booklet["booklet_price_amount"] is None and booklet["currency"] is None
    assert "270741756" not in booklet["link_url"] and "/list-opportunities" not in booklet["link_url"]
    assert client.get(f"/api/opportunities/{data['masters'][0].id}").json()["documents"] == []

    with factory() as db:
        source = db.get(Source, source_id)
        master = db.get(Opportunity, 597)
        source_record = db.get(SourceOpportunity, 3188)
        duplicate = make_document(
            source, source_record, master, official_provider_document_id="270741756-duplicate",
            title="كراسة الشروط والمواصفات", url=page_url, source_opportunity_url=page_url,
            access_status="PUBLIC_SOURCE_PAGE", rights_status="SOURCE_PAGE_LINK_ONLY",
            authentication_required=None, payment_required_for_document=None,
            participation_requirement="PURCHASE_REQUIRED_FOR_PARTICIPATION",
            booklet_price_amount=None, currency=None, link_verification_status="VERIFIED_SOURCE_PAGE",
            source_provenance_json=candidate["source_provenance_json"], deduplication_key=dedupe)
        db.add(duplicate)
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

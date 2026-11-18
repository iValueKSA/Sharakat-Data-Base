from __future__ import annotations

import hashlib
import json
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from pathlib import Path

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine

from app.document_collection.contracts import PageCapture
from app.document_collection.engine import approve_candidate, collect_allowlisted
from app.models import (AuditEvent, DocumentCandidate, DocumentVerificationEvent,
                        Opportunity, OpportunityDocument, Source, SourceOpportunity)


FIXTURE = Path(__file__).parent / "fixtures" / "document_collection" / "furas_booklet_with_attachment.html"
EXPECTED_HOST = "doccollection-pilot-pg16-20261118"
EXPECTED_DATABASE = "document_collection_phase2_test"


@pytest.fixture(scope="module")
def pg_factory():
    raw = os.getenv("DOCUMENT_COLLECTION_CONCURRENCY_DATABASE_URL")
    if not raw:
        pytest.skip("Set DOCUMENT_COLLECTION_CONCURRENCY_DATABASE_URL to the named disposable phase-2 database")
    parsed = make_url(raw)
    if parsed.host != EXPECTED_HOST or parsed.database != EXPECTED_DATABASE:
        raise RuntimeError("Refusing concurrency integration test outside the exact disposable database")
    engine = create_engine(raw, pool_size=8, max_overflow=0, pool_pre_ping=True)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        engine.dispose()


class FixtureVerifier:
    def __init__(self, provider_id: str, *, page_entered: Event | None = None,
                 release_page: Event | None = None, title: str | None = None,
                 document_id: str | None = None, multiple: bool = False):
        self.provider_id = provider_id
        self.page_entered = page_entered
        self.release_page = release_page
        fixture = (Path(__file__).parent / "fixtures" / "document_collection" / "furas_multiple_documents.html"
                   if multiple else FIXTURE)
        body = fixture.read_text(encoding="utf-8")
        body = body.replace("01-26-TEST-10003" if multiple else "01-26-TEST-10001", provider_id)
        if document_id:
            body = body.replace("CONTRACT-3", document_id)
        if title:
            body = body.replace("مسودة العقد</h2><a", f"{title}</h2><a")
            body = body.replace(">مسودة العقد</a>", f">{title}</a>")
        self.body = body.encode("utf-8")

    def verify(self, url, *, allowed_hosts, expected_kind="DOCUMENT", expected_provider_id=None):
        if expected_kind == "PAGE":
            if self.page_entered:
                self.page_entered.set()
                if not self.release_page.wait(15):
                    raise TimeoutError("concurrency gate expired")
            return PageCapture(200, url, "text/html", self.body, [], "CONFIRMED_OFFICIAL_PAGE",
                               {"provider_reference": self.provider_id})
        return PageCapture(206, url, "application/pdf", b"%PDF-1.7\nlimited metadata verification",
                           [], "CONFIRMED_DOCUMENT", {"signature": "%PDF-"})


def _new_source_record(factory, provider_id: str):
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    with factory.begin() as db:
        source = db.scalar(select(Source).where(Source.source_key == "furas"))
        assert source is not None
        master = Opportunity(canonical_id=f"PHASE2-{uuid.uuid4().hex}", title_ar="فرصة اختبار مرحلية",
            normalized_title="فرصة اختبار مرحلية", primary_publication_platform="فرص", status="متاحة",
            first_seen_at=now, last_seen_at=now, last_updated_at=now, created_at=now, updated_at=now)
        db.add(master); db.flush()
        source_url = f"https://furas.momah.gov.sa/index.php/ar/opportunity/{provider_id}?type=Investment"
        record = SourceOpportunity(source_id=source.id, master_opportunity_id=master.id,
            source_opportunity_id=provider_id, source_title="فرصة اختبار مرحلية",
            normalized_source_title="فرصة اختبار مرحلية", source_url=source_url,
            raw_status="Announced", canonical_status="متاحة", raw_dates={}, raw_data_json={},
            standardized_data_json={}, first_seen_at=now, last_seen_at=now,
            content_hash=uuid.uuid4().hex, parser_version="phase2-test")
        db.add(record); db.flush()
        return record.id, master.id


def _document_hash(row) -> str:
    values = {column.name: getattr(row, column.name) for column in row.__table__.columns}
    return hashlib.sha256(json.dumps(values, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def test_two_concurrent_celery_invocations_serialize_then_replay_idempotently(pg_factory, monkeypatch):
    import app.document_collection.tasks as tasks
    from app.document_collection.tasks import collect_source_opportunity
    from app.models import DocumentCollectionRun

    monkeypatch.setenv("DOCUMENT_COLLECTION_ENGINE_ENABLED", "true")
    monkeypatch.setenv("DOCUMENT_COLLECTION_MANUAL_ENABLED", "true")
    monkeypatch.setenv("DOCUMENT_COLLECTION_STAGING_ENABLED", "true")
    provider_id = f"02-26-TEST-{uuid.uuid4().hex[:12]}"
    source_record_id, master_id = _new_source_record(pg_factory, provider_id)
    entered, release = Event(), Event()
    monkeypatch.setattr(tasks, "collect_allowlisted", lambda ids, resume_run_id=None:
        collect_allowlisted(ids, session_factory=pg_factory, resume_run_id=resume_run_id,
            verifier=FixtureVerifier(provider_id, page_entered=entered, release_page=release)))
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(collect_source_opportunity.run, source_record_id, None)
            assert entered.wait(10), "first real database task did not reach source verification"
            class RetrySignal(Exception):
                def __init__(self, args, countdown):
                    self.retry_args = args
                    self.countdown = countdown
            monkeypatch.setattr(collect_source_opportunity, "retry",
                lambda *, args, countdown: (_ for _ in ()).throw(RetrySignal(args, countdown)))
            second = pool.submit(collect_source_opportunity.run, source_record_id, None)
            try:
                second_outcome = second.result(timeout=10)
            except RetrySignal as retry:
                assert retry.retry_args == [source_record_id, None]
                assert retry.countdown >= 30
            else:
                pytest.fail(f"contending Celery task should be explicitly retried, got {second_outcome!r}")
            release.set()
            first_result = first.result(timeout=20)
        assert first_result["status"] == "COMPLETED"

        replay = collect_source_opportunity.run(source_record_id, None)
        assert replay["status"] == "COMPLETED"
        with pg_factory() as db:
            candidates = db.scalars(select(DocumentCandidate).where(
                DocumentCandidate.source_opportunity_id == source_record_id)).all()
            assert len(candidates) == 1
            assert candidates[0].review_status == "PENDING"
            assert candidates[0].opportunity_id == master_id
            assert db.scalar(select(func.count()).select_from(DocumentCollectionRun).where(
                DocumentCollectionRun.source_id == candidates[0].source_id)) >= 2
            assert db.scalar(select(func.count()).select_from(OpportunityDocument)) == 1
    finally:
        release.set()


def test_postgres_staging_interruption_resumes_without_partial_candidate_or_lost_history(pg_factory):
    provider_id = f"02-26-FAIL-{uuid.uuid4().hex[:12]}"
    source_record_id, master_id = _new_source_record(pg_factory, provider_id)
    failed = {"once": False}

    def interrupt_before_candidate_flush(session, _context, instances):
        if not failed["once"] and any(isinstance(row, DocumentCandidate) for row in session.new):
            failed["once"] = True
            raise RuntimeError("phase2 simulated process interruption before candidate flush")

    event.listen(pg_factory, "before_flush", interrupt_before_candidate_flush)
    try:
        first = collect_allowlisted([source_record_id], session_factory=pg_factory,
                                    verifier=FixtureVerifier(provider_id))
    finally:
        event.remove(pg_factory, "before_flush", interrupt_before_candidate_flush)
    assert first["status"] == "PARTIAL"
    assert first["failures"][0]["status"] == "PROCESSING_ERROR"
    with pg_factory() as db:
        assert db.scalar(select(func.count()).select_from(DocumentCandidate).where(
            DocumentCandidate.source_opportunity_id == source_record_id)) == 0
    second = collect_allowlisted([source_record_id], session_factory=pg_factory,
        verifier=FixtureVerifier(provider_id), resume_run_id=first["run_id"])
    assert second["status"] == "COMPLETED"
    with pg_factory() as db:
        candidate = db.scalar(select(DocumentCandidate).where(
            DocumentCandidate.source_opportunity_id == source_record_id))
        assert candidate is not None and candidate.opportunity_id == master_id
        assert db.scalar(select(func.count()).select_from(DocumentCandidate).where(
            DocumentCandidate.source_opportunity_id == source_record_id)) == 1
        assert db.scalar(select(func.count()).select_from(DocumentVerificationEvent).where(
            DocumentVerificationEvent.source_opportunity_id == source_record_id)) >= 4
        master = db.get(Opportunity, master_id)
        assert master.merged_into_id is None


def test_postgres_refresh_versions_candidate_and_rediscovery_preserves_published_document(pg_factory):
    provider_id = "01-26-017001-42008"
    with pg_factory() as db:
        source_record = db.scalar(select(SourceOpportunity).where(
            SourceOpportunity.source_opportunity_id == provider_id))
        assert source_record is not None
        source_record_id = source_record.id
        master_id = source_record.master_opportunity_id
        published = db.scalar(select(OpportunityDocument).where(OpportunityDocument.id == 1))
        assert published is not None and published.source_opportunity_id == source_record_id
        before_hash = _document_hash(published)
    base = FixtureVerifier(provider_id, multiple=True)
    first = collect_allowlisted([source_record_id], session_factory=pg_factory, verifier=base)
    with pg_factory() as db:
        candidate = db.scalar(select(DocumentCandidate).where(
            DocumentCandidate.source_opportunity_id == source_record_id,
            DocumentCandidate.document_category == "DRAFT_CONTRACT"))
        assert candidate is not None
        candidate_id = candidate.id
        source_document_id = candidate.source_document_id
        assert source_document_id
    assert first["duplicates_prevented"] == 1
    changed = FixtureVerifier(provider_id, document_id=str(source_document_id),
        title="مسودة العقد المعدلة", multiple=True)
    second = collect_allowlisted([source_record_id], session_factory=pg_factory, verifier=changed)
    assert first["duplicates_prevented"] == 1 and second["duplicates_prevented"] == 1
    with pg_factory() as db:
        published = db.get(OpportunityDocument, 1)
        assert _document_hash(published) == before_hash
        assert db.scalar(select(func.count()).select_from(OpportunityDocument)) == 1
        updated = db.get(DocumentCandidate, candidate_id)
        assert updated is not None and updated.original_title == "مسودة العقد المعدلة"
        assert updated.document_version == 1 and updated.opportunity_id == master_id
        assert db.scalar(select(func.count()).select_from(DocumentCandidate).where(
            DocumentCandidate.source_opportunity_id == source_record_id,
            DocumentCandidate.identity_key == updated.identity_key)) == 1
        assert db.scalar(select(func.count()).select_from(DocumentVerificationEvent).where(
            DocumentVerificationEvent.candidate_id == candidate_id,
            DocumentVerificationEvent.event_type == "CANDIDATE_UPDATED")) >= 1


def test_concurrent_candidate_approval_is_idempotent_and_never_publishes(pg_factory):
    from app.models import AuditEvent
    with pg_factory() as db:
        candidate = db.scalar(select(DocumentCandidate).where(
            DocumentCandidate.verification_status == "READY_FOR_APPROVAL",
            DocumentCandidate.review_status == "PENDING").order_by(DocumentCandidate.id).limit(1))
        if candidate is None:
            pytest.skip("The verified snapshot must contain a pending ready candidate for approval concurrency")
        candidate_id = candidate.id
        prior_audits = db.scalar(select(func.count()).select_from(AuditEvent).where(
            AuditEvent.event_type == "DOCUMENT_CANDIDATE_REVIEW_APPROVED",
            AuditEvent.entity_id == str(candidate_id)))
    def approve():
        return approve_candidate(candidate_id, actor_id=None, actor_role="admin_token",
            reason="Concurrent isolated evidence review.", session_factory=pg_factory)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: approve(), range(2)))
    assert len(results) == 2
    with pg_factory() as db:
        candidate = db.get(DocumentCandidate, candidate_id)
        assert candidate.review_status == "APPROVED"
        assert db.scalar(select(func.count()).select_from(AuditEvent).where(
            AuditEvent.event_type == "DOCUMENT_CANDIDATE_REVIEW_APPROVED",
            AuditEvent.entity_id == str(candidate_id))) == prior_audits + 1
        assert db.scalar(select(func.count()).select_from(OpportunityDocument)) == 1

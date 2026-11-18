from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.document_collection.adapters.furas import FurasDocumentAdapter
from app.document_collection.contracts import PageCapture, SourceOpportunityContext
from app.document_collection.engine import _source_lock, approve_candidate, collect_allowlisted
from app.document_collection.registry import adapter_for, capability_for, capability_matrix
from app.document_collection.verifier import SafeURLVerifier
from app.models import (AuditEvent, Base, DocumentCandidate, DocumentCollectionRun,
                        DocumentVerificationEvent, Opportunity, OpportunityDocument,
                        Source, SourceOpportunity)


NOW = datetime(2026, 11, 18, tzinfo=timezone.utc)
FIXTURES = Path(__file__).parent / "fixtures" / "document_collection"
PROVIDER_ID = "01-26-TEST-10001"
PAGE_URL = f"https://furas.momah.gov.sa/index.php/ar/opportunity/{PROVIDER_ID}?type=Investment"


@pytest.fixture
def doc_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory.begin() as db:
        source = Source(source_key="furas", source_name_ar="فرص", organization_name="وزارة البلديات والإسكان",
            base_url="https://furas.momah.gov.sa", opportunities_url="https://furas.momah.gov.sa/ar/list-opportunities",
            source_type="official", enabled=True, technical_health="HEALTHY", coverage_status="UNKNOWN_COVERAGE")
        db.add(source); db.flush()
        master = Opportunity(canonical_id="AH-TEST-1", title_ar="فرصة اختبارية", normalized_title="فرصة اختبارية",
            primary_publication_platform="فرص", status="متاحة", first_seen_at=NOW,last_seen_at=NOW,last_updated_at=NOW,
            created_at=NOW,updated_at=NOW)
        db.add(master); db.flush()
        record = SourceOpportunity(source_id=source.id,master_opportunity_id=master.id,
            source_opportunity_id=PROVIDER_ID,source_title=master.title_ar,normalized_source_title=master.normalized_title,
            source_url=PAGE_URL,raw_status="Announced",canonical_status="متاحة",raw_dates={},
            raw_data_json={"feature":{"RFPPRICE":1500,"OPPORTUNITYACTIVESTATUS":"Announced"}},
            standardized_data_json={},first_seen_at=NOW,last_seen_at=NOW,content_hash="fixture-hash",parser_version="test")
        db.add(record); db.flush()
        ids={"source":source.id,"master":master.id,"source_record":record.id}
    try:
        yield factory, ids
    finally:
        engine.dispose()


class FixtureVerifier:
    def __init__(self, *, page_file="furas_booklet_with_attachment.html", document_outcome="CONFIRMED_DOCUMENT"):
        self.page_body=(FIXTURES/page_file).read_bytes()
        self.document_outcome=document_outcome
        self.calls=[]

    def verify(self, url, *, allowed_hosts, expected_kind="DOCUMENT", expected_provider_id=None):
        self.calls.append((url,expected_kind))
        if expected_kind=="PAGE":
            return PageCapture(200,url,"text/html",self.page_body,[],"CONFIRMED_OFFICIAL_PAGE",
                {"provider_reference":expected_provider_id})
        if self.document_outcome=="CONFIRMED_DOCUMENT":
            return PageCapture(206,url,"application/pdf",b"%PDF-1.7\nfixture",[],"CONFIRMED_DOCUMENT",{"signature":"%PDF-"})
        if self.document_outcome=="LISTING_REDIRECT":
            return PageCapture(200,"https://furas.momah.gov.sa/ar/list-opportunities","text/html",
                b"<html>list-opportunities</html>",["https://furas.momah.gov.sa/ar/list-opportunities"],"LISTING_REDIRECT",{})
        if self.document_outcome=="LOGIN_REDIRECT":
            return PageCapture(302,url,"text/html",b"",["https://furas.momah.gov.sa/account/login"],"LOGIN_REDIRECT",{})
        if self.document_outcome=="PAYMENT_REDIRECT":
            return PageCapture(302,url,"text/html",b"",["https://furas.momah.gov.sa/payment/checkout"],"PAYMENT_REDIRECT",{})
        if self.document_outcome=="AUTH_FAILURE":
            return PageCapture(403,url,"application/pdf",b"",[],"AUTH_FAILURE",{})
        return PageCapture(0,url,"",b"",[],self.document_outcome,{})


def _context(source_id,record_id,master_id,provider=PROVIDER_ID,page_url=PAGE_URL,raw=None):
    return SourceOpportunityContext(source_id,"furas","فرص",record_id,provider,page_url,master_id,False,
        "https://furas.momah.gov.sa","https://furas.momah.gov.sa/ar/list-opportunities",
        raw or {"RFPPRICE":1500},"Announced")


def test_furas_adapter_extracts_exact_booklet_purchase_requirement_and_price_evidence():
    body=(FIXTURES/"furas_booklet_with_attachment.html").read_bytes()
    page=PageCapture(200,PAGE_URL,"text/html",body,[],"CONFIRMED_OFFICIAL_PAGE",{})
    adapter=FurasDocumentAdapter()
    observations=adapter.discover(_context(1,3188,597),page)
    assert len(observations)==1
    doc=observations[0]
    assert doc.source_document_id=="BOOK-100"
    assert doc.document_category=="TERMS_AND_CONDITIONS_BOOKLET"
    assert doc.original_title=="تحميل كراسة الشروط والمواصفات"
    assert doc.participation_requirement=="PURCHASE_REQUIRED_FOR_PARTICIPATION"
    assert doc.raw_amount==1500 and doc.verified_amount==1500 and doc.verified_currency is None
    assert doc.official_purchase_url is None
    assert doc.purchase_url_verified is None
    assert doc.evidence["purchase_action_url"]=="https://furas.momah.gov.sa/ar/services/117"
    assert doc.evidence["price"]["verification"]=="FIELD_MATCHED_TO_BOOKLET_PRICE_LABEL"
    assert "investor-guide" not in doc.document_url


def test_furas_page_fallback_and_empty_section_do_not_invent_documents():
    adapter=FurasDocumentAdapter()
    fallback_url="https://furas.momah.gov.sa/index.php/ar/opportunity/01-26-TEST-10002?type=Investment"
    fallback=adapter.discover(_context(1,3188,597,"01-26-TEST-10002",fallback_url,{}),
        PageCapture(200,fallback_url,"text/html",(FIXTURES/"furas_page_fallback.html").read_bytes(),[],"CONFIRMED_OFFICIAL_PAGE",{}))
    assert len(fallback)==1
    assert fallback[0].document_url is None
    assert fallback[0].document_category=="TERMS_AND_CONDITIONS_BOOKLET"
    assert fallback[0].participation_requirement=="PURCHASE_REQUIRED_FOR_PARTICIPATION"
    empty_url="https://furas.momah.gov.sa/index.php/ar/opportunity/01-26-TEST-10004?type=Investment"
    empty=adapter.discover(_context(1,3188,597,"01-26-TEST-10004",empty_url,{}),
        PageCapture(200,empty_url,"text/html",(FIXTURES/"furas_empty_documents.html").read_bytes(),[],"CONFIRMED_OFFICIAL_PAGE",{}))
    assert empty==[]


def test_furas_multiple_document_types_are_page_scoped_and_general_guide_is_excluded():
    url="https://furas.momah.gov.sa/index.php/ar/opportunity/01-26-TEST-10003?type=Investment"
    docs=FurasDocumentAdapter().discover(_context(1,1,1,"01-26-TEST-10003",url,{}),
        PageCapture(200,url,"text/html",(FIXTURES/"furas_multiple_documents.html").read_bytes(),[],"CONFIRMED_OFFICIAL_PAGE",{}))
    assert {doc.document_type for doc in docs}=={
        "TERMS_AND_SPECIFICATIONS_BOOKLET","DRAFT_CONTRACT","APPLICATION_FORM","OFFICIAL_DRAWINGS_OR_SITE_PLAN"}
    assert all(doc.document_scope=="OPPORTUNITY" for doc in docs)
    assert all("investor-guide" not in (doc.document_url or "") for doc in docs)


def test_furas_adapter_fails_closed_on_wrong_provider_and_missing_master():
    body=(FIXTURES/"furas_booklet_with_attachment.html").read_bytes()
    page=PageCapture(200,PAGE_URL,"text/html",body,[],"CONFIRMED_OFFICIAL_PAGE",{})
    with pytest.raises(ValueError,match="exact SourceOpportunity"):
        FurasDocumentAdapter().discover(_context(1,3188,597,"different-provider"),page)
    with pytest.raises(ValueError,match="non-merged Master"):
        FurasDocumentAdapter().discover(_context(1,3188,None),page)


def test_cross_opportunity_attachment_is_rejected():
    body=(FIXTURES/"furas_booklet_with_attachment.html").read_text(encoding="utf-8")
    body=body.replace("BOOK-100", "BOOK-OTHER").replace(
        f"/opportunity/attachment/{PROVIDER_ID}/", "/opportunity/attachment/OTHER-PROVIDER/")
    page=PageCapture(200,PAGE_URL,"text/html",body.encode(),[],"CONFIRMED_OFFICIAL_PAGE",{})
    with pytest.raises(ValueError,match="Cross-opportunity attachment"):
        FurasDocumentAdapter().discover(_context(1,3188,597),page)


def test_unscoped_static_pdf_link_is_not_attached_to_opportunity():
    body=f"""<html><body><main><h1>فرصة {PROVIDER_ID}</h1>
    <section><h2>مرفقات الفرصة</h2><a href="/opportunity/attachment/{PROVIDER_ID}/BOOK/terms.pdf">كراسة الشروط</a></section>
    <footer><a href="/sites/default/files/guide.pdf">https://furas.momah.gov.sa/sites/default/files/guide.pdf</a></footer>
    </main></body></html>""".encode()
    page=PageCapture(200,PAGE_URL,"text/html",body,[],"CONFIRMED_OFFICIAL_PAGE",{})
    docs=FurasDocumentAdapter().discover(_context(1,3188,597),page)
    assert len(docs)==1 and docs[0].document_category=="TERMS_AND_CONDITIONS_BOOKLET"


def test_exact_attachment_identity_does_not_invent_a_document_category():
    body=f"<html><body><main><h1>فرصة {PROVIDER_ID}</h1><a href=\"/opportunity/attachment/{PROVIDER_ID}/DOC-1/file.pdf\">تحميل</a></main></body></html>".encode()
    page=PageCapture(200,PAGE_URL,"text/html",body,[],"CONFIRMED_OFFICIAL_PAGE",{})
    docs=FurasDocumentAdapter().discover(_context(1,3188,597),page)
    assert len(docs)==1
    assert docs[0].document_scope=="OPPORTUNITY"
    assert docs[0].document_type=="UNKNOWN_DOCUMENT_TYPE"
    assert docs[0].document_category=="UNKNOWN_DOCUMENT_TYPE"


def test_adapter_registry_marks_other_registered_sources_not_configured():
    assert adapter_for("furas") is not None
    assert adapter_for("ncp") is None
    assert capability_for("ncp").status=="NOT_CONFIGURED"
    assert capability_for("ncp").capabilities==()
    matrix=capability_matrix(["furas","ncp"])
    assert [row["status"] for row in matrix]==["IMPLEMENTED","NOT_CONFIGURED"]


def test_isolated_engine_stages_idempotently_and_never_publishes(doc_db):
    factory,ids=doc_db
    verifier=FixtureVerifier()
    first=collect_allowlisted([ids["source_record"]],session_factory=factory,verifier=verifier)
    second=collect_allowlisted([ids["source_record"]],session_factory=factory,verifier=FixtureVerifier())
    with factory() as db:
        candidates=db.scalars(select(DocumentCandidate)).all()
        docs=db.scalars(select(OpportunityDocument)).all()
        events=db.scalars(select(DocumentVerificationEvent)).all()
        assert len(candidates)==1 and candidates[0].verification_status=="READY_FOR_APPROVAL"
        assert candidates[0].review_status=="PENDING"
        assert candidates[0].publicly_displayable_price is False
        assert candidates[0].raw_amount==1500 and candidates[0].verified_amount==1500
        assert candidates[0].verified_currency is None
        assert candidates[0].participation_requirement=="PURCHASE_REQUIRED_FOR_PARTICIPATION"
        assert candidates[0].access_status=="PUBLIC_DIRECT_DOWNLOAD"
        assert docs==[]
        assert len(events)>=4
        assert first["discovered"]==1 and second["discovered"]==1
        assert first["status"]==second["status"]=="COMPLETED"
        assert db.scalar(select(func.count()).select_from(DocumentCollectionRun))==2


def test_listing_redirect_falls_back_to_official_page_and_stays_hidden(doc_db):
    factory,ids=doc_db
    result=collect_allowlisted([ids["source_record"]],session_factory=factory,
        verifier=FixtureVerifier(document_outcome="LISTING_REDIRECT"))
    with factory() as db:
        candidate=db.scalar(select(DocumentCandidate))
        assert result["discovered"]==1
        assert candidate.url==PAGE_URL
        assert candidate.access_status=="PUBLIC_SOURCE_PAGE"
        assert candidate.rights_status=="SOURCE_PAGE_LINK_ONLY"
        assert candidate.link_verification_status=="VERIFIED_SOURCE_PAGE"
        assert candidate.verification_status=="READY_FOR_APPROVAL"
        assert "DIRECT_DOWNLOAD_LISTING_REDIRECT" in candidate.missing_evidence_json
        assert "DOCUMENT_ACCESS_NOT_VERIFIED" not in candidate.missing_evidence_json
        assert "list-opportunities" not in candidate.url
        assert db.scalar(select(func.count()).select_from(OpportunityDocument))==0


@pytest.mark.parametrize(("outcome","expected_access","expected_auth","expected_payment"),[
    ("LOGIN_REDIRECT","LOGIN_REQUIRED",True,None),
    ("PAYMENT_REDIRECT","PAYMENT_REQUIRED_FOR_DOCUMENT",None,True),
    ("AUTH_FAILURE","UNKNOWN",None,None),
])
def test_restricted_file_access_stays_unverified_and_needs_review(
        doc_db,outcome,expected_access,expected_auth,expected_payment):
    factory,ids=doc_db
    collect_allowlisted([ids["source_record"]],session_factory=factory,
        verifier=FixtureVerifier(document_outcome=outcome))
    with factory() as db:
        candidate=db.scalar(select(DocumentCandidate))
        assert candidate.access_status==expected_access
        assert candidate.authentication_required is expected_auth
        assert candidate.payment_required_for_document is expected_payment
        assert candidate.verification_status=="NEEDS_REVIEW"
        assert candidate.review_status=="PENDING"
        assert db.scalar(select(func.count()).select_from(OpportunityDocument))==0


def test_published_document_id_one_is_preserved_and_duplicate_not_staged(doc_db):
    factory,ids=doc_db
    with factory.begin() as db:
        db.add(OpportunityDocument(id=1,opportunity_id=ids["master"],source_id=ids["source"],
            source_opportunity_id=ids["source_record"],official_provider_document_id="BOOK-100",
            title="كراسة الشروط والمواصفات",url=PAGE_URL,document_type="HTML_SOURCE_PAGE",
            document_category="TERMS_AND_CONDITIONS_BOOKLET",first_seen_at=NOW,source_opportunity_url=PAGE_URL,
            access_status="PUBLIC_SOURCE_PAGE",rights_status="SOURCE_PAGE_LINK_ONLY",authentication_required=False,
            participation_requirement="PURCHASE_REQUIRED_FOR_PARTICIPATION",link_verification_status="VERIFIED_SOURCE_PAGE",
            source_provenance_json={"direct_download_status":"UNAVAILABLE"},document_version=1,
            deduplication_key="a"*64,publication_status="APPROVED",created_at=NOW,updated_at=NOW))
    result=collect_allowlisted([ids["source_record"]],session_factory=factory,verifier=FixtureVerifier())
    with factory() as db:
        doc=db.get(OpportunityDocument,1)
        assert doc is not None and doc.publication_status=="APPROVED"
        assert doc.title=="كراسة الشروط والمواصفات" and doc.booklet_price_amount is None and doc.currency is None
        assert db.scalar(select(func.count()).select_from(OpportunityDocument))==1
        assert db.scalar(select(func.count()).select_from(DocumentCandidate))==0
        assert any(event.event_type=="EXISTING_PUBLISHED_DOCUMENT_PRESERVED"
                   for event in db.scalars(select(DocumentVerificationEvent)).all())
        assert result["duplicates_prevented"]==1


def test_admin_candidate_approval_passes_mvp_gate_but_does_not_publish(doc_db):
    factory,ids=doc_db
    result=collect_allowlisted([ids["source_record"]],session_factory=factory,verifier=FixtureVerifier())
    candidate_id=result["records"][0]["candidate_ids"][0]
    review=approve_candidate(candidate_id,actor_id=7,actor_role="admin",reason="Evidence verified in isolated review.",session_factory=factory)
    with factory() as db:
        candidate=db.get(DocumentCandidate,candidate_id)
        assert review["gate"]=="VALIDATED_NO_WRITE"
        assert review["document_publication"]=="NOT_PUBLISHED"
        assert candidate.review_status=="APPROVED"
        assert db.scalar(select(func.count()).select_from(OpportunityDocument))==0
        assert db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.event_type=="DOCUMENT_CANDIDATE_REVIEW_APPROVED"))==1
    repeated=approve_candidate(candidate_id,actor_id=7,actor_role="admin",reason="Repeated evidence review.",session_factory=factory)
    assert repeated["gate"]=="IDEMPOTENT_ALREADY_REVIEWED"
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(AuditEvent).where(
            AuditEvent.event_type=="DOCUMENT_CANDIDATE_REVIEW_APPROVED"))==1
        assert db.scalar(select(func.count()).select_from(OpportunityDocument))==0


def test_temporary_page_failure_preserves_last_verified_candidate(doc_db):
    factory,ids=doc_db
    collect_allowlisted([ids["source_record"]],session_factory=factory,verifier=FixtureVerifier())
    class TemporaryVerifier:
        def verify(self,*args,**kwargs):return PageCapture(0,PAGE_URL,"",b"",[],"TEMPORARY_FAILURE",{"error_class":"Timeout"})
    result=collect_allowlisted([ids["source_record"]],session_factory=factory,verifier=TemporaryVerifier())
    with factory() as db:
        candidate=db.scalar(select(DocumentCandidate))
        assert candidate.verification_status=="TEMPORARILY_UNREACHABLE"
        assert candidate.url.endswith("BOOK-100/%D9%83%D8%B1%D8%A7%D8%B3%D8%A9-%D8%A7%D9%84%D8%B4%D8%B1%D9%88%D8%B7.pdf") or "BOOK-100" in candidate.url
        assert candidate.last_verified_at is not None
        assert result["temporary_failures"]==1
        assert db.scalar(select(func.count()).select_from(DocumentCandidate))==1
    recovered=collect_allowlisted([ids["source_record"]],session_factory=factory,verifier=FixtureVerifier())
    with factory() as db:
        candidate=db.scalar(select(DocumentCandidate))
        assert recovered["status"]=="COMPLETED"
        assert candidate.verification_status=="READY_FOR_APPROVAL"
        assert candidate.failure_count==0
        assert db.scalar(select(func.count()).select_from(DocumentVerificationEvent).where(
            DocumentVerificationEvent.event_type=="CANDIDATE_RECOVERED"))==1


def test_allowlist_is_bounded_and_rejects_duplicate_or_invalid_ids(doc_db):
    factory,ids=doc_db
    with pytest.raises(ValueError,match="25-record"):
        collect_allowlisted(list(range(1,27)),session_factory=factory,verifier=FixtureVerifier())
    with pytest.raises(ValueError,match="positive SourceOpportunity"):
        collect_allowlisted([True],session_factory=factory,verifier=FixtureVerifier())
    result=collect_allowlisted([ids["source_record"],ids["source_record"]],session_factory=factory,
                               verifier=FixtureVerifier())
    assert result["requested"]==1
    assert result["duplicates_prevented"]>=1


def test_missing_or_merged_master_association_fails_before_source_access(doc_db):
    factory,ids=doc_db
    with factory.begin() as db:
        record=db.get(SourceOpportunity,ids["source_record"])
        record.master_opportunity_id=None
    with pytest.raises(ValueError,match="EXACT_NONMERGED_MASTER_ASSOCIATION_REQUIRED"):
        collect_allowlisted([ids["source_record"]],session_factory=factory,verifier=FixtureVerifier())
    with factory.begin() as db:
        master=db.get(Opportunity,ids["master"])
        other=Opportunity(canonical_id="AH-TEST-MERGED-INTO",title_ar="وجهة دمج",normalized_title="وجهة دمج",
            primary_publication_platform="فرص",status="متاحة",first_seen_at=NOW,last_seen_at=NOW,last_updated_at=NOW,
            created_at=NOW,updated_at=NOW)
        db.add(other);db.flush()
        master.merged_into_id=other.id
        db.get(SourceOpportunity,ids["source_record"]).master_opportunity_id=master.id
    with pytest.raises(ValueError,match="EXACT_NONMERGED_MASTER_ASSOCIATION_REQUIRED"):
        collect_allowlisted([ids["source_record"]],session_factory=factory,verifier=FixtureVerifier())


def test_source_lock_prevents_concurrent_collection_for_same_source(doc_db):
    factory,ids=doc_db
    with _source_lock(ids["source"],factory):
        with pytest.raises(RuntimeError,match="COLLECTION_ALREADY_RUNNING_FOR_SOURCE"):
            with _source_lock(ids["source"],factory):
                pass


def test_resumable_collection_keeps_cumulative_run_metrics_after_retry(doc_db):
    factory,ids=doc_db

    class FailOnceForPage:
        failed=False
        def verify(self,url,*,allowed_hosts,expected_kind="DOCUMENT",expected_provider_id=None):
            if expected_kind=="PAGE" and not self.failed:
                self.failed=True
                return PageCapture(0,url,"",b"",[],"TEMPORARY_FAILURE",{"error_class":"TimeoutError"})
            return FixtureVerifier().verify(url,allowed_hosts=allowed_hosts,expected_kind=expected_kind,
                expected_provider_id=expected_provider_id)

    first=collect_allowlisted([ids["source_record"]],session_factory=factory,verifier=FailOnceForPage())
    assert first["status"]=="PARTIAL" and first["processed"]==1
    second=collect_allowlisted([ids["source_record"]],session_factory=factory,
        verifier=FixtureVerifier(),resume_run_id=first["run_id"])
    assert second["status"]=="COMPLETED"
    assert second["processed"]==1 and second["discovered"]==1
    assert len(second["records"])==1


def test_candidate_transaction_interruption_is_recoverable(doc_db):
    factory,ids=doc_db
    failed={"once":False}

    def interrupt_candidate_flush(session,flush_context,instances):
        if not failed["once"] and any(isinstance(value,DocumentCandidate) for value in session.new):
            failed["once"]=True
            raise RuntimeError("synthetic interruption before candidate transaction commit")

    event.listen(factory,"before_flush",interrupt_candidate_flush)
    first=collect_allowlisted([ids["source_record"]],session_factory=factory,verifier=FixtureVerifier())
    event.remove(factory,"before_flush",interrupt_candidate_flush)
    assert first["status"]=="PARTIAL" and first["temporary_failures"]==1
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(DocumentCandidate))==0
    second=collect_allowlisted([ids["source_record"]],session_factory=factory,
        verifier=FixtureVerifier(),resume_run_id=first["run_id"])
    with factory() as db:
        run=db.get(DocumentCollectionRun,first["run_id"])
        assert second["status"]=="COMPLETED"
        assert second["discovered"]==1 and second["ready_for_approval"]==1
        assert run.discovered_count==1 and len(run.summary_json["processed_records"])==1
        assert db.scalar(select(func.count()).select_from(DocumentCandidate))==1


from __future__ import annotations

import socket

import pytest

from app.document_collection.verifier import SafeURLVerifier


HOST="furas.momah.gov.sa"
ALLOWED=(HOST,)


class FakeResponse:
    def __init__(self,status=200,headers=None,body=b""):
        self.status=status;self._headers=headers or {};self._body=body
    def getheader(self,name):return self._headers.get(name)
    def read(self,amount=-1):return self._body[:amount] if amount>=0 else self._body


class FakeConnection:
    responses=[]
    error=None
    calls=[]
    def __init__(self,host,port,pinned_ip,timeout):
        self.host=host;self.port=port;self.pinned_ip=pinned_ip;self.timeout=timeout
        type(self).calls.append((host,port,pinned_ip,timeout))
    def request(self,method,path,headers):
        if type(self).error:raise type(self).error
        self.path=path
    def getresponse(self):return type(self).responses.pop(0)
    def close(self):pass


def verifier(monkeypatch,responses=(),*,dns="93.184.216.34",error=None,max_bytes=4096):
    FakeConnection.responses=list(responses);FakeConnection.error=error;FakeConnection.calls=[]
    monkeypatch.setattr("app.document_collection.verifier._PinnedHTTPSConnection",FakeConnection)
    def resolve(host,port,type=socket.SOCK_STREAM):
        return [(socket.AF_INET,socket.SOCK_STREAM,6,"",(dns,port))]
    return SafeURLVerifier(timeout_seconds=3,max_redirects=3,max_page_bytes=max_bytes,
        request_interval_seconds=0,resolver=resolve)


def test_pdf_response_requires_pdf_signature(monkeypatch):
    safe=verifier(monkeypatch,[FakeResponse(206,{"Content-Type":"application/pdf"},b"%PDF-1.7 data")])
    result=safe.verify(f"https://{HOST}/opportunity/attachment/1/2/booklet.pdf",allowed_hosts=ALLOWED)
    assert result.outcome=="CONFIRMED_DOCUMENT"
    assert result.evidence["signature"]=="%PDF-"


def test_http_200_html_is_not_mistaken_for_a_document(monkeypatch):
    safe=verifier(monkeypatch,[FakeResponse(200,{"Content-Type":"text/html"},b"<html><body>not a PDF</body></html>")])
    result=safe.verify(f"https://{HOST}/file.pdf",allowed_hosts=ALLOWED)
    assert result.status_code==200 and result.outcome=="INVALID_FILE_RESPONSE"


def test_listing_redirect_and_login_payment_failures_are_distinguished(monkeypatch):
    safe=verifier(monkeypatch,[
        FakeResponse(302,{"Location":"/ar/list-opportunities"}),
        FakeResponse(200,{"Content-Type":"text/html"},b"<html>list-opportunities</html>")])
    result=safe.verify(f"https://{HOST}/opportunity/attachment/1/2/a.pdf",allowed_hosts=ALLOWED)
    assert result.outcome=="LISTING_REDIRECT"
    assert len(result.redirect_chain)==1
    for status,outcome in ((401,"AUTH_FAILURE"),(403,"AUTH_FAILURE"),(402,"PAYMENT_REQUIRED"),
                           (404,"NOT_FOUND"),(429,"TEMPORARY_FAILURE")):
        safe=verifier(monkeypatch,[FakeResponse(status)])
        result=safe.verify(f"https://{HOST}/file",allowed_hosts=ALLOWED)
        assert result.outcome==outcome


def test_retry_after_is_recorded_and_source_circuit_opens_after_repeated_transients(monkeypatch):
    safe=verifier(monkeypatch,[FakeResponse(429,{"Retry-After":"90"})])
    result=safe.verify(f"https://{HOST}/page",allowed_hosts=ALLOWED,expected_kind="PAGE")
    assert result.outcome=="TEMPORARY_FAILURE"
    assert result.evidence["retry_after_seconds"]==90

    safe=verifier(monkeypatch,[FakeResponse(503) for _ in range(5)])
    url=f"https://{HOST}/page"
    for _ in range(5):
        assert safe.verify(url,allowed_hosts=ALLOWED,expected_kind="PAGE").outcome=="TEMPORARY_FAILURE"
    calls=len(FakeConnection.calls)
    blocked=safe.verify(url,allowed_hosts=ALLOWED,expected_kind="PAGE")
    assert blocked.outcome=="CIRCUIT_OPEN"
    assert blocked.evidence["retry_after_seconds"]>0
    assert len(FakeConnection.calls)==calls


def test_login_and_payment_redirects_do_not_follow_restricted_actions(monkeypatch):
    safe=verifier(monkeypatch,[FakeResponse(302,{"Location":"/account/login"})])
    assert safe.verify(f"https://{HOST}/file",allowed_hosts=ALLOWED).outcome=="LOGIN_REDIRECT"
    safe=verifier(monkeypatch,[FakeResponse(302,{"Location":"/payment/checkout"})])
    assert safe.verify(f"https://{HOST}/file",allowed_hosts=ALLOWED).outcome=="PAYMENT_REDIRECT"


@pytest.mark.parametrize("url",[
    "http://furas.momah.gov.sa/document.pdf",
    "https://user:password@furas.momah.gov.sa/document.pdf",
    "https://furas.momah.gov.sa/document.pdf#fragment",
    "https://furas.momah.gov.sa/document.pdf?access_token=secret",
    "https://evil.example/document.pdf",
])
def test_unsafe_url_structures_and_hosts_are_rejected_without_request(monkeypatch,url):
    safe=verifier(monkeypatch,[])
    result=safe.verify(url,allowed_hosts=ALLOWED)
    assert result.outcome=="UNSAFE_DESTINATION"
    assert not FakeConnection.calls


def test_private_dns_answer_is_blocked_and_socket_is_never_opened(monkeypatch):
    safe=verifier(monkeypatch,[],dns="127.0.0.1")
    result=safe.verify(f"https://{HOST}/file",allowed_hosts=ALLOWED)
    assert result.outcome=="UNSAFE_DESTINATION"
    assert result.evidence["reason"]=="DNS_RESOLVED_TO_NON_PUBLIC_ADDRESS"
    assert not FakeConnection.calls


def test_unsafe_redirect_is_rejected_before_second_request(monkeypatch):
    safe=verifier(monkeypatch,[FakeResponse(302,{"Location":"https://evil.example/redirect"})])
    result=safe.verify(f"https://{HOST}/file",allowed_hosts=ALLOWED)
    assert result.outcome=="UNSAFE_REDIRECT"
    assert len(FakeConnection.calls)==1


def test_timeouts_are_temporary_and_page_size_is_bounded(monkeypatch):
    safe=verifier(monkeypatch,[],error=TimeoutError("fake timeout"))
    result=safe.verify(f"https://{HOST}/file",allowed_hosts=ALLOWED)
    assert result.outcome=="TEMPORARY_FAILURE"
    assert result.evidence["error_phase"]=="HTTP_REQUEST"
    safe=verifier(monkeypatch,[FakeResponse(200,{"Content-Type":"text/html"},b"x"*4097)],max_bytes=4096)
    result=safe.verify(f"https://{HOST}/index",allowed_hosts=ALLOWED,expected_kind="PAGE",expected_provider_id="p1")
    assert result.outcome=="RESPONSE_TOO_LARGE"


def test_page_requires_exact_provider_reference_in_url_and_body(monkeypatch):
    safe=verifier(monkeypatch,[FakeResponse(200,{"Content-Type":"text/html"},
        b"<html>Opportunity 01-26-TEST-10001</html>")])
    result=safe.verify(f"https://{HOST}/index.php/ar/opportunity/01-26-TEST-10001?type=Investment",
        allowed_hosts=ALLOWED,expected_kind="PAGE",expected_provider_id="01-26-TEST-10001")
    assert result.outcome=="CONFIRMED_OFFICIAL_PAGE"


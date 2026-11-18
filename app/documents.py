"""Publication gates and link validation for opportunity documents.

This module never fetches or proxies external URLs. It only decides whether a
reviewed, already persisted record can be serialized as a safe official link.
"""
from __future__ import annotations

import ipaddress
import re
from urllib.parse import parse_qsl, urlsplit

ACCESS_STATUSES = {
    "PUBLIC_DIRECT_DOWNLOAD", "PUBLIC_SOURCE_PAGE", "LOGIN_REQUIRED",
    "PAYMENT_REQUIRED_FOR_DOCUMENT", "RESTRICTED", "UNKNOWN", "UNAVAILABLE",
}
RIGHTS_STATUSES = {"DIRECT_LINK_APPROVED", "SOURCE_PAGE_LINK_ONLY", "RESTRICTED", "UNVERIFIED"}
PARTICIPATION_REQUIREMENTS = {
    "PURCHASE_REQUIRED_FOR_PARTICIPATION", "PURCHASE_NOT_REQUIRED_CONFIRMED", "UNKNOWN",
}
DOCUMENT_CATEGORIES = {
    "TERMS_AND_CONDITIONS_BOOKLET", "TENDER_SPECIFICATIONS", "DRAFT_CONTRACT",
    "SITE_MAP", "TECHNICAL_ATTACHMENT", "INVESTMENT_BROCHURE",
    "GENERAL_ATTACHMENT", "UNKNOWN_DOCUMENT_TYPE",
}


class DocumentCandidateError(ValueError):
    """Raised when a candidate fails an explicit source/provenance gate."""


def _host(url: str | None) -> str | None:
    if not isinstance(url, str) or not url or any(ord(char) < 32 for char in url):
        return None
    try:
        parsed = urlsplit(url.strip())
        host = parsed.hostname
        if parsed.scheme.lower() not in {"http", "https"} or not host or parsed.username or parsed.password:
            return None
        port = parsed.port  # Validate malformed/out-of-range ports.
    except (ValueError, UnicodeError):
        return None
    if port is not None and port != (80 if parsed.scheme.lower() == "http" else 443):
        return None
    sensitive_query_keys = {
        "access_token", "access-token", "accesskeyid", "api-key", "api_key", "apikey", "auth",
        "authorization", "client_secret", "credential", "jwt", "key",
        "oauth_token", "secret", "session", "sessionid", "signature", "sig", "token", "x-amz-credential",
        "x-amz-signature", "x-amz-security-token", "x-goog-credential", "x-goog-signature",
    }
    if any(key.lower() in sensitive_query_keys for part in (parsed.query, parsed.fragment)
           for key, _ in parse_qsl(part, keep_blank_values=True)):
        return None
    host = host.rstrip(".").lower()
    if not host or "%" in host:
        return None
    try:
        address = ipaddress.ip_address(host)
        if not address.is_global:
            return None
        return host
    except ValueError:
        pass
    if host in {"localhost", "localhost.localdomain"} or host.endswith((".localhost", ".local", ".internal", ".test")):
        return None
    if not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", host):
        return None
    if ".." in host:
        return None
    return host


def is_official_http_url(url: str | None, trusted_urls: list[str | None]) -> bool:
    """Accept an external URL only on the source's configured public host tree."""
    candidate_host = _host(url)
    if not candidate_host:
        return False
    trusted_hosts = {host for host in (_host(value) for value in trusted_urls) if host}
    return any(candidate_host == host or candidate_host.endswith("." + host) for host in trusted_hosts)


def validate_document_candidate(candidate: dict, source_opportunity, source) -> dict:
    """Validate a synthetic/future candidate without persisting or fetching it."""
    required_source_id = candidate.get("source_opportunity_id")
    if required_source_id is None or int(required_source_id) != source_opportunity.id:
        raise DocumentCandidateError("Exact SourceOpportunity ID is required")
    if int(candidate.get("source_id", -1)) != source_opportunity.source_id or source.id != source_opportunity.source_id:
        raise DocumentCandidateError("Source namespace does not match the SourceOpportunity")
    supplied_master = candidate.get("master_opportunity_id")
    if source_opportunity.master_opportunity_id is None or supplied_master != source_opportunity.master_opportunity_id:
        raise DocumentCandidateError("Master association must match the linked SourceOpportunity")
    if candidate.get("association_status") != "EXACT_ASSOCIATION_VERIFIED":
        raise DocumentCandidateError("Inferred or conflicting associations cannot be imported")
    category = candidate.get("document_category")
    if category not in DOCUMENT_CATEGORIES:
        raise DocumentCandidateError("Unsupported document category")
    if candidate.get("access_status") not in ACCESS_STATUSES:
        raise DocumentCandidateError("Unsupported access status")
    if candidate.get("rights_status") not in RIGHTS_STATUSES:
        raise DocumentCandidateError("Unsupported rights status")
    if candidate.get("participation_requirement") not in PARTICIPATION_REQUIREMENTS:
        raise DocumentCandidateError("Unsupported participation requirement")
    url = candidate.get("url")
    source_page_url = candidate.get("source_opportunity_url")
    trusted = [source.base_url, source.opportunities_url, source_opportunity.source_url]
    if source_page_url != source_opportunity.source_url:
        raise DocumentCandidateError("Opportunity page must match the exact stored SourceOpportunity URL")
    if not is_official_http_url(source_page_url, trusted):
        raise DocumentCandidateError("Official opportunity page is unsafe or outside the source domain")
    if url and not is_official_http_url(url, trusted):
        raise DocumentCandidateError("Document URL is unsafe or outside the verified source domain")
    if candidate.get("rights_status") == "DIRECT_LINK_APPROVED" and not is_official_http_url(url, trusted):
        raise DocumentCandidateError("Direct document URL is unsafe or outside the source domain")
    if candidate.get("rights_status") == "SOURCE_PAGE_LINK_ONLY" and not is_official_http_url(source_page_url, trusted):
        raise DocumentCandidateError("Source-page-only destination is not an approved official URL")
    purchase_url = candidate.get("official_purchase_url")
    if purchase_url and (not is_official_http_url(purchase_url, trusted) or candidate.get("purchase_url_verified") is not True):
        raise DocumentCandidateError("Purchase action must be verified and remain on the official source domain")
    if candidate.get("rights_status") in {"RESTRICTED", "UNVERIFIED"}:
        raise DocumentCandidateError("Unverified or restricted rights cannot pass the publication gate")
    if candidate.get("access_status") in {"RESTRICTED", "UNAVAILABLE"}:
        raise DocumentCandidateError("Restricted or unavailable documents cannot be published")
    if candidate.get("publication_status", "DRAFT") == "APPROVED":
        if candidate.get("access_status") == "UNKNOWN":
            raise DocumentCandidateError("Unknown access cannot pass the publication gate")
        if candidate.get("access_status") == "LOGIN_REQUIRED" and candidate.get("authentication_required") is not True:
            raise DocumentCandidateError("Login-required publication needs confirmed authentication metadata")
        if candidate.get("access_status") == "PAYMENT_REQUIRED_FOR_DOCUMENT" and candidate.get("payment_required_for_document") is not True:
            raise DocumentCandidateError("Payment-gated publication needs confirmed document-payment metadata")
        required_link_status = "VERIFIED_PUBLIC" if candidate.get("rights_status") == "DIRECT_LINK_APPROVED" else "VERIFIED_SOURCE_PAGE"
        if candidate.get("link_verification_status") != required_link_status:
            raise DocumentCandidateError("Approved publication requires a verified rights-appropriate destination")
        if candidate.get("rights_status") == "DIRECT_LINK_APPROVED" and candidate.get("access_status") != "PUBLIC_DIRECT_DOWNLOAD":
            raise DocumentCandidateError("Direct download publication requires verified public direct access")
        if candidate.get("rights_status") == "DIRECT_LINK_APPROVED" and (
            candidate.get("authentication_required") is not False
            or candidate.get("payment_required_for_document") is not False
        ):
            raise DocumentCandidateError("Direct download publication requires confirmed public access without login or document payment")
    amount = candidate.get("booklet_price_amount")
    currency = candidate.get("currency")
    if amount is not None and (float(amount) < 0 or not isinstance(currency, str) or not re.fullmatch(r"[A-Z]{3}", currency)):
        raise DocumentCandidateError("Price requires a non-negative amount and ISO-style currency")
    return {**candidate, "validation_status": "VALIDATED_NO_WRITE"}


def document_json(document, source_opportunity, source) -> dict | None:
    """Serialize only a verified, approved, source-bound external destination."""
    if document.publication_status != "APPROVED":
        return None
    if (document.source_opportunity_id != source_opportunity.id
            or document.source_id != source_opportunity.source_id
            or source.id != source_opportunity.source_id
            or document.opportunity_id != source_opportunity.master_opportunity_id
            or source_opportunity.master_opportunity_id is None):
        return None
    if document.rights_status not in {"DIRECT_LINK_APPROVED", "SOURCE_PAGE_LINK_ONLY"}:
        return None
    if document.access_status in {"RESTRICTED", "UNAVAILABLE", "UNKNOWN"}:
        return None
    if document.access_status == "LOGIN_REQUIRED" and document.authentication_required is not True:
        return None
    if document.access_status == "PAYMENT_REQUIRED_FOR_DOCUMENT" and document.payment_required_for_document is not True:
        return None

    trusted = [source.base_url, source.opportunities_url, source_opportunity.source_url]
    page_url = document.source_opportunity_url
    if page_url != source_opportunity.source_url:
        return None
    if not is_official_http_url(page_url, trusted):
        return None
    if document.rights_status == "DIRECT_LINK_APPROVED":
        if document.access_status != "PUBLIC_DIRECT_DOWNLOAD" or document.link_verification_status != "VERIFIED_PUBLIC":
            return None
        if document.authentication_required is not False or document.payment_required_for_document is not False:
            return None
        if not is_official_http_url(document.url, trusted):
            return None
        destination = document.url
    else:
        if document.link_verification_status != "VERIFIED_SOURCE_PAGE":
            return None
        destination = page_url

    price = document.booklet_price_amount
    purchase_url = document.official_purchase_url
    if purchase_url and (document.purchase_url_verified is not True or not is_official_http_url(purchase_url, trusted)):
        purchase_url = None
    provenance = document.source_provenance_json if isinstance(document.source_provenance_json, dict) else {}
    direct_download_status = provenance.get("direct_download_status")
    if direct_download_status not in {"AVAILABLE_VERIFIED", "UNAVAILABLE", "UNVERIFIED"}:
        direct_download_status = None
    return {
        "id": document.id,
        "source_id": source.id,
        "source_key": source.source_key,
        "source_name": source.source_name_ar,
        "source_opportunity_id": source_opportunity.id,
        "provider_opportunity_reference": source_opportunity.source_opportunity_id,
        "master_opportunity_id": source_opportunity.master_opportunity_id,
        "title": document.title,
        "document_category": document.document_category or "UNKNOWN_DOCUMENT_TYPE",
        "source_opportunity_url": page_url,
        "official_purchase_url": purchase_url if document.purchase_url_verified is True else None,
        "link_url": destination,
        "access_status": document.access_status,
        "rights_status": document.rights_status,
        "authentication_required": document.authentication_required,
        "payment_required_for_document": document.payment_required_for_document,
        "participation_requirement": document.participation_requirement,
        "booklet_price_amount": float(price) if price is not None else None,
        "currency": document.currency if price is not None else None,
        "direct_download_status": direct_download_status,
        "link_verification_status": document.link_verification_status,
        "last_verified_at": document.last_verified_at.isoformat() if document.last_verified_at else None,
        "document_version": document.document_version,
        "publication_status": document.publication_status,
    }


def official_source_pages(source_opportunities) -> list[dict]:
    """Return safe, source-bound opportunity page links for empty-state fallback."""
    pages = []
    seen = set()
    for record in source_opportunities:
        source = record.source
        url = record.source_url
        if not source or not is_official_http_url(url, [source.base_url, source.opportunities_url]):
            continue
        identity = (source.id, record.id, url)
        if identity in seen:
            continue
        seen.add(identity)
        pages.append({
            "source_id": source.id,
            "source_key": source.source_key,
            "source_name": source.source_name_ar,
            "source_opportunity_id": record.id,
            "provider_opportunity_reference": record.source_opportunity_id,
            "url": url,
        })
    return pages

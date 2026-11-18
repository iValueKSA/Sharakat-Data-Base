from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Protocol


@dataclass(frozen=True)
class SourceOpportunityContext:
    source_id: int
    source_key: str
    source_name: str
    source_record_id: int
    provider_opportunity_id: str
    source_opportunity_url: str
    master_opportunity_id: int | None
    master_merged: bool
    source_base_url: str | None = None
    source_opportunities_url: str | None = None
    raw_data: dict[str, Any] = field(default_factory=dict)
    raw_status: str | None = None


@dataclass
class DocumentObservation:
    """Normalized source evidence before persistence; never implies approval."""
    source_document_id: str | None
    original_title: str
    document_type: str | None
    document_category: str
    document_scope: str
    document_url: str | None
    official_purchase_url: str | None = None
    purchase_url_verified: bool | None = None
    access_status: str = "UNKNOWN"
    rights_status: str = "UNVERIFIED"
    participation_requirement: str = "UNKNOWN"
    authentication_required: bool | None = None
    payment_required_for_document: bool | None = None
    link_verification_status: str = "UNVERIFIED"
    raw_amount: Decimal | None = None
    raw_currency: str | None = None
    verified_amount: Decimal | None = None
    verified_currency: str | None = None
    evidence: dict[str, Any] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=dict)
    missing_evidence: list[str] = field(default_factory=list)
    verified_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    identity_verified: bool = False
    verification_status: str = "EXTRACTED"

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        for key in ("raw_amount", "verified_amount"):
            if result[key] is not None:
                result[key] = str(result[key])
        if isinstance(result.get("verified_at"), datetime):
            result["verified_at"] = result["verified_at"].isoformat()
        return result


@dataclass
class PageCapture:
    status_code: int
    final_url: str
    content_type: str
    body: bytes
    redirect_chain: list[str] = field(default_factory=list)
    outcome: str = "UNVERIFIED"
    evidence: dict[str, Any] = field(default_factory=dict)


class DocumentAdapter(Protocol):
    source_key: str
    parser_version: str
    capabilities: dict[str, bool]

    def discover(self, context: SourceOpportunityContext, page: PageCapture) -> list[DocumentObservation]: ...


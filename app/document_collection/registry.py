from __future__ import annotations

from dataclasses import asdict, dataclass

from .adapters.furas import FurasDocumentAdapter


@dataclass(frozen=True)
class SourceCapability:
    source_key: str
    status: str
    adapter: str | None
    capabilities: tuple[str, ...]
    note: str


FURAS = FurasDocumentAdapter()
_CAPABILITIES = {
    "discovery": True,
    "booklet": True,
    "draft_contract": True,
    "application_form": True,
    "additional_attachments": True,
    "purchase_requirement": True,
    "page_fallback": True,
    "gis_price_evidence": True,
    "lifecycle_evidence": True,
}


def adapter_for(source_key: str):
    return FURAS if source_key == "furas" else None


def capability_for(source_key: str) -> SourceCapability:
    if source_key == "furas":
        return SourceCapability(source_key, "IMPLEMENTED", "FurasDocumentAdapter",
                                tuple(k for k, enabled in _CAPABILITIES.items() if enabled),
                                "Official opportunity detail page; allowlisted existing records only.")
    return SourceCapability(source_key, "NOT_CONFIGURED", None, (),
                            "No document adapter is configured; no document results are synthesized.")


def capability_matrix(source_keys: list[str] | tuple[str, ...]) -> list[dict]:
    return [asdict(capability_for(key)) for key in sorted(set(source_keys))]


"""Auditable, write-once manifests for read-only Furas public captures."""
from __future__ import annotations

import hashlib
import json
from typing import Any


SCHEMA = "furas-national-durable-capture-v1"


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    ).encode("utf-8")


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def record_payload_sha256(attributes: dict, geometry: dict | None) -> str:
    """Hash the unmodified provider attributes and geometry, including nulls/types."""
    return sha256_json({"attributes": attributes, "geometry": geometry})


def validate_capture_manifest(document: dict) -> dict:
    """Raise ValueError unless a complete capture and all record/page hashes reconcile."""
    if not isinstance(document, dict) or document.get("schema") != SCHEMA:
        raise ValueError("Unsupported Furas capture manifest schema")
    capture = document.get("capture") or {}
    records = document.get("records")
    pages = document.get("pages")
    requests = document.get("requests")
    if capture.get("production_writes") is not False:
        raise ValueError("Manifest must explicitly attest that production writes were false")
    if capture.get("read_only_official_public_source") is not True:
        raise ValueError("Manifest must explicitly attest a read-only public capture")
    if capture.get("pagination_complete") is not True:
        raise ValueError("Incomplete capture cannot be accepted as a baseline")
    if not isinstance(records, list) or not isinstance(pages, list) or not isinstance(requests, list):
        raise ValueError("Manifest records, pages, and request provenance must be arrays")
    expected = capture.get("source_total_reported")
    if not isinstance(expected, int) or expected != len(records):
        raise ValueError("Captured record count does not reconcile to the reported snapshot")
    if capture.get("records_received") != len(records) or capture.get("unique_records") != len(records):
        raise ValueError("Received/unique provider record counts do not reconcile")
    if capture.get("duplicate_source_ids") not in (0, None):
        raise ValueError("Capture reports duplicate provider IDs")
    if capture.get("missing_object_ids") not in (0, None):
        raise ValueError("Capture reports missing OBJECTIDs")

    provider_ids: list[str] = []
    object_ids: list[str] = []
    index: list[dict] = []
    record_by_id: dict[str, dict] = {}
    for record in records:
        raw_id = record.get("provider_id_raw")
        provider_id = record.get("provider_id_adapter_key")
        object_id = record.get("objectid_raw")
        raw = record.get("raw_payload") or {}
        attributes = raw.get("attributes")
        geometry = raw.get("geometry")
        if raw_id is None or provider_id is None or object_id is None:
            raise ValueError("Provider ID and OBJECTID must be retained as received")
        if str(raw_id) != str(provider_id):
            raise ValueError("Adapter provider key differs from the raw Furas OPPORTUNITYID")
        if not isinstance(attributes, dict):
            raise ValueError("Raw provider attributes are missing")
        if record.get("raw_record_sha256") != record_payload_sha256(attributes, geometry):
            raise ValueError(f"Record checksum mismatch for {provider_id}")
        key = str(provider_id)
        if key in record_by_id:
            raise ValueError(f"Duplicate provider ID {key}")
        record_by_id[key] = record
        provider_ids.append(key)
        object_ids.append(str(object_id))
        index.append({
            "provider_id_raw": raw_id,
            "objectid_raw": object_id,
            "raw_record_sha256": record["raw_record_sha256"],
        })
    if len(set(object_ids)) != len(object_ids):
        raise ValueError("Duplicate OBJECTID in captured provider records")

    page_ids: list[str] = []
    page_object_ids: list[str] = []
    seen_page_numbers: set[int] = set()
    for page in pages:
        number = page.get("page_number")
        if not isinstance(number, int) or number in seen_page_numbers:
            raise ValueError("Page numbers must be unique integers")
        seen_page_numbers.add(number)
        ids = [str(x) for x in page.get("provider_ids", [])]
        oids = [str(x) for x in page.get("object_ids", [])]
        if len(ids) != int(page.get("record_count", -1)) or len(oids) != len(ids):
            raise ValueError(f"Page {number} record/object membership does not reconcile")
        page_record_oids = set()
        for provider_id in ids:
            record = record_by_id.get(provider_id)
            if record is None:
                raise ValueError(f"Page {number} contains an unknown provider ID")
            page_record_oids.add(str(record["objectid_raw"]))
        if page_record_oids != set(oids):
            raise ValueError(f"Page {number} provider/ObjectID membership does not reconcile")
        page_ids.extend(ids)
        page_object_ids.extend(oids)
    if len(page_ids) != len(records) or len(set(page_ids)) != len(page_ids):
        raise ValueError("Page membership does not cover every provider record exactly once")
    if set(page_ids) != set(provider_ids) or set(page_object_ids) != set(object_ids):
        raise ValueError("Page membership differs from the complete capture set")
    if capture.get("page_count") != len(pages) or capture.get("request_count") != len(requests):
        raise ValueError("Page/request counts do not reconcile to retained provenance")
    if capture.get("membership_sha256_sorted_provider_ids") != sha256_json(sorted(provider_ids)):
        raise ValueError("Sorted provider membership checksum mismatch")
    if capture.get("membership_sha256_sorted_objectids") != sha256_json(sorted(object_ids)):
        raise ValueError("Sorted OBJECTID membership checksum mismatch")
    if capture.get("ordered_capture_index_sha256") != sha256_json(index):
        raise ValueError("Ordered capture index checksum mismatch")
    for number, request in enumerate(requests, start=1):
        if request.get("request_number") != number or not request.get("requested_url"):
            raise ValueError("Request provenance is missing or out of order")
        if len(str(request.get("response_sha256") or "")) != 64:
            raise ValueError(f"Request {number} response checksum is missing")
    return {"records": len(records), "pages": len(pages), "requests": len(requests)}

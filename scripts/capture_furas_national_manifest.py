"""Capture the official public Furas national enumeration without DB writes."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import httpx

from app.adapters import FurasAdapter
from app.furas_capture_manifest import record_payload_sha256, validate_capture_manifest


class RecordingClient:
    def __init__(self, client):
        self.client = client
        self.requests = []

    async def get(self, url, **kwargs):
        started = datetime.now(timezone.utc).isoformat()
        response = await self.client.get(url, **kwargs)
        self.requests.append({
            "request_number": len(self.requests) + 1,
            "requested_url": str(response.request.url),
            "final_url": str(response.url),
            "http_status": response.status_code,
            "started_at_utc": started,
            "completed_at_utc": datetime.now(timezone.utc).isoformat(),
            "response_bytes": len(response.content),
            "response_sha256": hashlib.sha256(response.content).hexdigest(),
            "content_type": response.headers.get("content-type"),
        })
        return response


async def capture_document() -> dict:
    started = datetime.now(timezone.utc).isoformat()
    adapter = FurasAdapter()
    pages = []

    async def on_batch(records, checkpoint):
        ids = list(checkpoint.get("processed_snapshot_object_ids") or [])
        count = len(records)
        page_ids = ids[-count:] if count else []
        pages.append({
            "page_number": int(checkpoint.get("pages_completed") or 0),
            "offset": int(checkpoint.get("last_committed_offset") or 0) - len(page_ids),
            "record_count": count,
            "object_ids": page_ids,
            "provider_ids": [record.external_id for record in records],
            "batch_sha256": (checkpoint.get("batch_sha256s") or [None])[-1],
            "checkpoint_offset": checkpoint.get("last_committed_offset"),
        })

    with patch.dict(os.environ, {
        "FURAS_NATIONAL_ENUMERATION_ENABLED": "true",
        "FURAS_REMOVALS_ENABLED": "false",
    }):
        async with httpx.AsyncClient(timeout=httpx.Timeout(45), follow_redirects=True) as raw:
            client = RecordingClient(raw)
            records, _ = await adapter.fetch(client, on_batch=on_batch)
    completed = datetime.now(timezone.utc).isoformat()
    output_records = []
    page_for_id = {str(pid): page["page_number"] for page in pages for pid in page["provider_ids"]}
    for record in records:
        raw = record.raw or {}
        attrs = raw.get("attributes") or {}
        geometry = raw.get("geometry")
        output_records.append({
            "provider_id_raw": attrs.get("OPPORTUNITYID"),
            "provider_id_adapter_key": record.external_id,
            "provider_id_normalized": record.external_id,
            "objectid_raw": attrs.get("OBJECTID"),
            "official_reference_raw": attrs.get("OPPORTUNITYID"),
            "title_raw": attrs.get("OPPORTUNITYDESCRIPTION"),
            "official_detail_url": record.url,
            "source_status_raw": attrs.get("OPPORTUNITYACTIVESTATUS", attrs.get("STATUS")),
            "location_raw": {
                "city": attrs.get("CITYNAME"), "city_id": attrs.get("CITY_ID"),
                "district": attrs.get("DISTRICT"), "street": attrs.get("STREET"),
                "region": attrs.get("REGIONNAME"), "region_id": attrs.get("REGION_ID"),
                "amana": attrs.get("AMANA"), "baladya": attrs.get("BALADYA"),
                "geometry": geometry,
            },
            "deadline_fields_raw": {key: attrs.get(key) for key in (
                "STARTDATE", "ENDDATE", "LASTRFPSELLDATE", "ENVELOPESOPENDATE",
                "LASTBIDATE", "CREATED_DATE", "LAST_EDITED_DATE",
            )},
            "raw_payload": {"attributes": attrs, "geometry": geometry},
            "raw_record_sha256": record_payload_sha256(attrs, geometry),
            "source_endpoint": raw.get("source_endpoint"),
            "enumeration_scope": raw.get("enumeration_scope"),
            "page_number": page_for_id.get(str(record.external_id)),
        })
    provider_ids = [str(record["provider_id_raw"]) for record in output_records if record["provider_id_raw"] is not None]
    object_ids = [str(record["objectid_raw"]) for record in output_records if record["objectid_raw"] is not None]
    index = [{"provider_id_raw": record["provider_id_raw"], "objectid_raw": record["objectid_raw"],
              "raw_record_sha256": record["raw_record_sha256"]} for record in output_records]
    metrics = adapter.metrics
    document = {
        "schema": "furas-national-durable-capture-v1",
        "capture": {
            "started_at_utc": started, "completed_at_utc": completed,
            "execution_environment": "read-only capture process; no production database session",
            "read_only_official_public_source": True, "production_writes": False,
            "adapter": "app.adapters.FurasAdapter", "collector_scope": "SAUDI_NATIONAL_V1",
            "source_url": adapter.url,
            "requested_endpoints": list(dict.fromkeys(r["requested_url"].split("?")[0] for r in client.requests)),
            "request_count": len(client.requests), "page_count": len(pages),
            "pagination_complete": metrics.get("pagination_complete"),
            "source_total_reported": metrics.get("source_total_reported"),
            "records_received": metrics.get("records_received"),
            "records_parsed": metrics.get("records_parsed"), "unique_records": metrics.get("unique_records"),
            "duplicate_source_ids": metrics.get("duplicate_source_ids"),
            "missing_object_ids": metrics.get("missing_object_ids"),
            "where": metrics.get("where"), "adapter_metrics": metrics,
            "membership_sha256_sorted_provider_ids": hashlib.sha256(
                json.dumps(sorted(provider_ids), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest(),
            "membership_sha256_sorted_objectids": hashlib.sha256(
                json.dumps(sorted(object_ids), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest(),
            "ordered_capture_index_sha256": hashlib.sha256(
                json.dumps(index, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest(),
            "ordering": "Adapter OBJECTID snapshot order; feature batches ordered by provider OBJECTID",
            "record_hash": "SHA-256 of canonical UTF-8 JSON {attributes,geometry}; original JSON scalar types retained",
        },
        "requests": client.requests, "pages": pages, "records": output_records,
    }
    validate_capture_manifest(document)
    return document


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="New manifest path; existing paths are never overwritten")
    parser.add_argument("--confirm-read-only-public-capture", action="store_true",
                        help="Required acknowledgement; no authentication or production writes are used")
    args = parser.parse_args()
    if not args.confirm_read_only_public_capture:
        parser.error("pass --confirm-read-only-public-capture to run the public read-only enumerator")
    if args.output.exists():
        raise SystemExit(f"Refusing to overwrite existing capture manifest: {args.output}")
    document = asyncio.run(capture_document())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_name(args.output.name + ".part")
    if temporary.exists():
        raise SystemExit(f"Refusing to overwrite existing temporary capture file: {temporary}")
    with temporary.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(document, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    # Hard-link creation is atomic and fails if another process created the
    # destination after the initial exists() guard; an audit file is never
    # replaced by a racing capture.
    os.link(temporary, args.output)
    temporary.unlink()
    print(json.dumps({"path": str(args.output), **validate_capture_manifest(document)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

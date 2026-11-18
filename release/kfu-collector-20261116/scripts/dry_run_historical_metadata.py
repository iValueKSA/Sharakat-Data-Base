"""Always-rollback simulation; deliberately rejects non-disposable databases."""
from __future__ import annotations

import copy
import hashlib
import json
import os
from datetime import date, datetime

from sqlalchemy import func, select, text
from sqlalchemy.engine import make_url

from app.database import SessionLocal, engine
from app.models import (
    Opportunity,
    OpportunityDocument,
    Source,
    SourceContentItem,
    SourceObservation,
    SourceOpportunity,
    SyncJob,
)

KFU_SOURCE_ID = 5
TARGET_SOURCE_RECORD_ID = 2928
TARGET_PROVIDER_ID = "kfu-announcement:0aac035af08807f4f1755ee5"
TARGET_MASTER_ID = 326
CORRECTION_KEY = "KFU-2928-METADATA-ONLY-2026-11-16"
EXPECTED_URLS = {
    "https://www.kfu.edu.sa/ar/Departments/Investment/Documents/Newdesign/assets/%d8%b1%d8%ad%d9%84%d8%a9-%d8%a7%d9%84%d9%85%d8%b3%d8%aa%d8%ab%d9%85%d8%b1.pdf",
    "https://www.kfu.edu.sa/ar/Departments/Investment/Documents/Newdesign/assets/%d9%83%d8%b1%d8%a7%d8%b3%d8%a9%d9%85%d8%b7%d8%a7%d8%b9%d9%85-%d9%88%d9%85%d8%aa%d8%a7%d8%ac%d8%b1-%d8%b9%d8%a7%d9%85%d8%a9.pdf",
}


def fingerprint(value):
    packed = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(packed.encode("utf-8")).hexdigest()


def source_state(db):
    rows = db.scalars(select(SourceOpportunity).where(SourceOpportunity.id.in_([2773, 2774, 2775, 2776, 2777, 2928])).order_by(SourceOpportunity.id)).all()
    return {
        row.id: {
            "provider_id": row.source_opportunity_id,
            "master_id": row.master_opportunity_id,
            "source_url": row.source_url,
            "status": row.canonical_status,
            "raw_status": row.raw_status,
            "content_hash": row.content_hash,
            "parser_version": row.parser_version,
            "last_seen_at": str(row.last_seen_at),
            "missing_successful_checks": row.missing_successful_checks,
            "raw_data_json": copy.deepcopy(row.raw_data_json or {}),
        }
        for row in rows
    }


def page_state(db):
    rows = db.scalars(select(SourceContentItem).where(SourceContentItem.source_id == KFU_SOURCE_ID).order_by(SourceContentItem.id)).all()
    return {
        row.id: {
            "external_key": row.external_key,
            "url": row.url,
            "fingerprint": row.fingerprint,
            "raw_text_sha256": hashlib.sha256((row.raw_text or "").encode("utf-8")).hexdigest(),
            "attachments_sha256": fingerprint(row.attachments_json or []),
        }
        for row in rows
    }


def observation_state(db):
    rows = db.scalars(select(SourceObservation).order_by(SourceObservation.id)).all()
    return {
        row.id: (row.source_opportunity_id, row.endpoint, row.content_hash, str(row.first_seen_at), str(row.last_seen_at))
        for row in rows
    }


def master_state(db):
    rows = db.scalars(select(Opportunity).where(Opportunity.id.in_([224, 225, 326])).order_by(Opportunity.id)).all()
    return {
        row.id: (row.canonical_id, row.merged_into_id, row.title_ar, row.status, str(row.updated_at))
        for row in rows
    }


def main():
    url = make_url(os.environ.get("DATABASE_URL", ""))
    if (
        os.environ.get("KFU_CORRECTION_DRY_RUN") != "YES"
        or url.get_backend_name() != "postgresql"
        or url.host != "kfu-snapshot-pg"
        or url.database != "kfu_snapshot"
    ):
        raise SystemExit("Refusing to run: this script only accepts the named disposable kfu_snapshot PostgreSQL database.")

    if engine.dialect.name != "postgresql":
        raise SystemExit("Refusing to run: PostgreSQL is required.")

    with SessionLocal() as db:
        try:
            db.execute(text("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE"))
            source = db.get(Source, KFU_SOURCE_ID)
            if source is None or source.source_key != "kfu":
                raise RuntimeError("KFU source id/key precondition failed.")
            row = db.get(SourceOpportunity, TARGET_SOURCE_RECORD_ID)
            if (
                row is None
                or row.source_id != KFU_SOURCE_ID
                or row.source_opportunity_id != TARGET_PROVIDER_ID
                or row.master_opportunity_id != TARGET_MASTER_ID
            ):
                raise RuntimeError("Target record/provider/Master allowlist precondition failed.")
            original = copy.deepcopy(row.raw_data_json or {})
            original_refs = original.get("attachments") or []
            original_urls = {item.get("url") for item in original_refs}
            if len(original_refs) != 2 or original_urls != EXPECTED_URLS:
                raise RuntimeError("Target attachment list does not exactly match the two reviewed links; refusing candidate.")

            original_source_state = source_state(db)
            if set(original_source_state) != {2773, 2774, 2775, 2776, 2777, 2928}:
                raise RuntimeError("The six-record allowlist does not match the restored snapshot.")
            original_pages = page_state(db)
            if not original_pages:
                raise RuntimeError("Historical KFU SourceContentItem evidence is missing.")
            if not any(
                EXPECTED_URLS.issubset({item.get("url") for item in (db.get(SourceContentItem, page_id).attachments_json or [])})
                for page_id in original_pages
            ):
                raise RuntimeError("Exact original link references are not preserved in historical listing evidence.")
            original_observations = observation_state(db)
            original_masters = master_state(db)
            before_counts = {
                "source_opportunities": db.scalar(select(func.count()).select_from(SourceOpportunity)),
                "masters": db.scalar(select(func.count()).select_from(Opportunity)),
                "kfu_content_items": len(original_pages),
                "source_observations": len(original_observations),
                "sync_jobs": db.scalar(select(func.count()).select_from(SyncJob)),
                "documents": db.scalar(select(func.count()).select_from(OpportunityDocument)),
            }

            after = copy.deepcopy(original)
            after["attachments"] = []
            after["attachment_provenance_review"] = {
                "correction_key": CORRECTION_KEY,
                "classification": "CONFIRMED_WRONG_REMOVE_FROM_DERIVED_METADATA",
                "reason": "The current KFU seasonal-rental panel contains an application form and no booklet; the investor guide is outside all notice panels, and the old booklet belongs to the separate 2025 tender panel.",
                "original_references_preserved": original_refs,
                "preservation_location": "Existing SourceContentItem listing snapshots and this review field; source observations remain unchanged.",
                "review_date": date.today().isoformat(),
            }
            row.raw_data_json = after
            db.flush()

            updated_sources = source_state(db)
            expected_source_state = copy.deepcopy(original_source_state)
            expected_source_state[TARGET_SOURCE_RECORD_ID]["raw_data_json"] = after
            if updated_sources != expected_source_state:
                raise RuntimeError("Unexpected SourceOpportunity changes detected in the dry-run transaction.")
            if page_state(db) != original_pages:
                raise RuntimeError("SourceContentItem evidence changed during dry run.")
            if observation_state(db) != original_observations:
                raise RuntimeError("SourceObservation history changed during dry run.")
            if master_state(db) != original_masters:
                raise RuntimeError("Master identity or lifecycle changed during dry run.")
            after_counts = {
                "source_opportunities": db.scalar(select(func.count()).select_from(SourceOpportunity)),
                "masters": db.scalar(select(func.count()).select_from(Opportunity)),
                "kfu_content_items": db.scalar(select(func.count()).select_from(SourceContentItem).where(SourceContentItem.source_id == KFU_SOURCE_ID)),
                "source_observations": db.scalar(select(func.count()).select_from(SourceObservation)),
                "sync_jobs": db.scalar(select(func.count()).select_from(SyncJob)),
                "documents": db.scalar(select(func.count()).select_from(OpportunityDocument)),
            }
            if after_counts != before_counts:
                raise RuntimeError("Row counts changed in the dry-run transaction.")

            result = {
                "status": "DRY_RUN_PASS_ROLLBACK_ONLY",
                "correction_key": CORRECTION_KEY,
                "target": {
                    "source_opportunity_id": TARGET_SOURCE_RECORD_ID,
                    "provider_id": TARGET_PROVIDER_ID,
                    "master_id": TARGET_MASTER_ID,
                    "field_changed": "source_opportunities.raw_data_json",
                    "nested_change": "attachments: two references -> []; original links retained in attachment_provenance_review.original_references",
                },
                "confirmed_wrong_urls": sorted(EXPECTED_URLS),
                "before_attachment_count": len(original_refs),
                "after_derived_attachment_count": len(after["attachments"]),
                "historical_content_items_preserved": len(original_pages),
                "source_observations_preserved": len(original_observations),
                "master_links_preserved": True,
                "all_other_allowlisted_rows_unchanged": True,
                "counts_before_and_after_equal": before_counts == after_counts,
                "counts": before_counts,
                "commit_called": False,
            }
            db.rollback()
            db.expire_all()
            rolled_back = db.get(SourceOpportunity, TARGET_SOURCE_RECORD_ID)
            if (rolled_back.raw_data_json or {}) != original:
                raise RuntimeError("Dry-run transaction did not roll back to the exact original payload.")
            result["rollback_verified"] = True
            print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        except Exception:
            db.rollback()
            raise


if __name__ == "__main__":
    main()

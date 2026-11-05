"""Create a read-only census of source-side raw Sector values for review."""
from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

from sqlalchemy import func, select

from app.database import SessionLocal
from app.models import Source, SourceOpportunity
from app.standardization import canonical_identity, canonical_value, STANDARDIZATION_VERSION
from app.adapters import normalize_sector

OUT = Path("docs/validation/data/sector-taxonomy")
ACTIVITY_CANDIDATES = {
    "أنشطة التجارة العامة", "أنشطة تجارة المواد الغذائية", "أنشطة وخدمات انتاج المواد غير الغذائية",
    "خدمات الصرافة", "خدمات تعليمية أخرى", "خدمي", "محلات تجارية", "منشآت تقديم الغذاء",
    "الساحات الميادين", "العربات المتنقلة", "المباني",
}
TYPE_CODES = {
    "INVESTMENT_OPPORTUNITY", "GENERAL_ANNOUNCEMENT", "INVESTMENT_ANNOUNCEMENT",
    "INVESTMENT_SECTOR_INFORMATION", "STRATEGIC_PROJECT", "LEASE_OPPORTUNITY",
    "COMMERCIAL_FACILITY_OPPORTUNITY", "PPP_PROJECT", "PPP_PROJECT_ANNOUNCEMENT",
    "WASTE_SECTOR_INVESTMENT",
}


def classify(raw: str) -> tuple[str, str, str]:
    normalized = canonical_value("sector", raw)
    adapter_label = normalize_sector(raw)
    canonical_label = adapter_label or normalized
    identity = canonical_identity("sector", canonical_label)
    canonical_id = identity["id"] if identity else f"unmapped:sector:{raw}"
    if raw in TYPE_CODES or normalized in TYPE_CODES or raw == "فرصة استثمارية":
        return "wrong_dimension_opportunity_type", canonical_id, "غير محدد"
    if normalized in ACTIVITY_CANDIDATES:
        return "possible_activity_review", canonical_id, "غير محدد"
    if canonical_id == "sector:unspecified":
        return "missing_or_wrong_dimension", canonical_id, "غير محدد"
    if canonical_id.startswith("unmapped:"):
        subtype = "unmapped_english_or_source_label" if raw.isascii() else "unmapped_arabic_review"
        return subtype, canonical_id, raw
    if canonical_label != raw:
        return "approved_alias", canonical_id, canonical_label
    return "canonical_sector", canonical_id, canonical_label


def main() -> None:
    with SessionLocal() as db:
        rows = db.execute(
            select(Source.source_key, SourceOpportunity.source_sector, func.count(SourceOpportunity.id))
            .join(Source, Source.id == SourceOpportunity.source_id)
            .group_by(Source.source_key, SourceOpportunity.source_sector)
            .order_by(Source.source_key, SourceOpportunity.source_sector)
        ).all()
    items = []
    totals = Counter()
    distinct_classifications = Counter()
    distinct_raw: set[str] = set()
    for source_key, raw_value, count in rows:
        raw = raw_value if raw_value not in (None, "") else None
        if raw is None:
            classification, identity, label = "missing_raw_sector", "sector:unspecified", "غير محدد"
        else:
            classification, identity, label = classify(str(raw))
            if str(raw) not in distinct_raw:
                distinct_classifications[classification] += 1
            distinct_raw.add(str(raw))
        item = {"source_key": source_key, "raw_sector": raw, "source_record_count": int(count),
                "classification": classification, "canonical_id": identity,
                "proposed_business_label": label, "auto_mapping_applied_to_source_row": False}
        items.append(item)
        totals[classification] += int(count)
    OUT.mkdir(parents=True, exist_ok=True)
    payload = {
        "standardization_version_for_future_ingestion": STANDARDIZATION_VERSION,
        "source_opportunity_count": sum(int(count) for _, _, count in rows),
        "source_rows_with_sector": sum(int(count) for _, raw_value, count in rows if raw_value not in (None, "")),
        "source_rows_missing_sector": sum(int(count) for _, raw_value, count in rows if raw_value in (None, "")),
        "distinct_nonempty_raw_source_sector_values": len(distinct_raw),
        "distinct_value_classification_counts": dict(sorted(distinct_classifications.items())),
        "classification_record_counts": dict(sorted(totals.items())),
        "values": items,
    }
    (OUT / "source-sector-taxonomy-candidates.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    with (OUT / "source-sector-taxonomy-candidates.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(items[0]))
        writer.writeheader()
        writer.writerows(items)
    print(json.dumps({key: value for key, value in payload.items() if key != "values"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

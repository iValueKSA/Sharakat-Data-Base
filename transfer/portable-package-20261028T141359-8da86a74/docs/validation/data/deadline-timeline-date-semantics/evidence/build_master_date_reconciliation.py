"""Read-only fixed-snapshot date reconciliation; writes evidence files only."""
from __future__ import annotations

import csv
import json
import os
from collections import Counter
from datetime import date
from pathlib import Path

from sqlalchemy import select, text

from app.database import SessionLocal
from app.models import Opportunity, Source, SourceOpportunity

OUT = Path(os.environ.get("DATE_REVIEW_OUT", Path(__file__).resolve().parent))
OUT.mkdir(parents=True, exist_ok=True)
AS_OF = date(2026, 10, 20)

with SessionLocal() as db:
    db.connection().execute(text("SET TRANSACTION READ ONLY"))
    masters = db.scalars(select(Opportunity).where(Opportunity.merged_into_id.is_(None)).order_by(Opportunity.id)).all()
    sources = {s.id: s for s in db.scalars(select(Source)).all()}
    source_rows = db.scalars(select(SourceOpportunity)).all()

by_master: dict[int, list[SourceOpportunity]] = {}
for row in source_rows:
    if row.master_opportunity_id is not None:
        by_master.setdefault(row.master_opportunity_id, []).append(row)

def source_dates(rows, allow_furas=False):
    found = []
    for row in rows:
        source = sources[row.source_id]
        if source.source_key == "furas" and not allow_furas:
            continue
        raw = row.raw_dates or {}
        deadline = raw.get("deadline")
        if deadline not in (None, ""):
            found.append((source.source_key, str(deadline)))
    return found

def furas_attrs(rows):
    for row in rows:
        if sources[row.source_id].source_key != "furas":
            continue
        raw = row.raw_data_json or {}
        attrs = raw.get("attributes") or {}
        return attrs
    return {}

master_rows = []
furas_review_rows = []
publication_review_rows = []
pub_classes = Counter()
classes = Counter()
trusted_buckets = Counter()
conflicts = []
canonical_source_mismatches = []
source_date_counts = {s.source_key: {"records": 0, "deadline_values": 0, "publication_values": 0} for s in sources.values()}
for row in source_rows:
    skey = sources[row.source_id].source_key
    source_date_counts[skey]["records"] += 1
    if (row.raw_dates or {}).get("deadline") not in (None, ""):
        source_date_counts[skey]["deadline_values"] += 1
    # Historical Furas wrapper JSON may retain a derived STARTDATE projection
    # under publication_date; it is not a source-declared publication field.
    if (row.raw_dates or {}).get("publication_date") or (skey != "furas" and (row.raw_data_json or {}).get("publication_date")):
        source_date_counts[skey]["publication_values"] += 1
for master in masters:
    rows = by_master.get(master.id, [])
    trusted = source_dates(rows)
    all_raw = source_dates(rows, allow_furas=True)
    attrs = furas_attrs(rows)
    stored = master.submission_deadline or ""
    parsed = None
    try:
        parsed = date.fromisoformat(stored) if stored else None
    except ValueError:
        pass
    if parsed is not None and trusted:
        classification = "RELIABLE_EXPLICIT_NON_FURAS_SOURCE"
        classes["reliable"] += 1
        days = (parsed - AS_OF).days
        if days < 0: bucket = "PAST"
        elif days == 0: bucket = "TODAY"
        elif days <= 7: bucket = "NEXT_7_DAYS"
        elif days <= 30: bucket = "NEXT_8_TO_30_DAYS"
        else: bucket = "LATER"
        trusted_buckets[bucket] += 1
        trusted_values = sorted({d for _, d in trusted})
        if len(trusted_values) > 1:
            conflicts.append({"master_id": master.id, "values": trusted_values, "sources": trusted})
        if trusted_values != [stored]:
            canonical_source_mismatches.append({"master_id": master.id, "canonical": stored, "source_values": trusted_values, "sources": trusted})
    elif parsed is not None and all_raw and any(sources[r.source_id].source_key == "furas" for r in rows):
        classification = "SEMANTIC_REVIEW_FURAS_LASTRFPSELLDATE_OR_ENDDATE"
        classes["semantic_review"] += 1
        furas_review_rows.append({
            "master_id": master.id,
            "canonical_deadline_current_unmodified": stored,
            "raw_LASTRFPSELLDATE": attrs.get("LASTRFPSELLDATE", ""),
            "raw_ENDDATE": attrs.get("ENDDATE", ""),
            "raw_LASTBIDATE": attrs.get("LASTBIDATE", ""),
            "raw_ENVELOPESOPENDATE": attrs.get("ENVELOPESOPENDATE", ""),
            "other_explicit_source_deadlines": json.dumps(trusted, ensure_ascii=False),
        })
    elif stored and parsed is None:
        classification = "INVALID_CANONICAL_DATE"
        classes["invalid"] += 1
    else:
        classification = "NO_RELIABLE_DEADLINE"
        classes["no_deadline"] += 1

    pub_source = []
    for row in rows:
        source = sources[row.source_id]
        raw = row.raw_dates or {}
        pub_value = raw.get("publication_date") or (row.raw_data_json or {}).get("publication_date")
        if pub_value:
            pub_source.append((source.source_key, str(pub_value)))
    pub_stored = master.publication_date or ""
    if pub_stored and any(k == "ncp" for k, _ in pub_source):
        pub_class = "SOURCE_CONFIRMED_NCP_ARTICLE_START_DATE"
        pub_classes["confirmed"] += 1
    elif pub_stored and any(sources[r.source_id].source_key == "furas" for r in rows):
        pub_class = "SEMANTIC_REVIEW_FURAS_STARTDATE"
        pub_classes["review"] += 1
        publication_review_rows.append({
            "master_id": master.id,
            "canonical_publication_date_current_unmodified": pub_stored,
            "raw_STARTDATE": attrs.get("STARTDATE", ""),
            "raw_CREATED_DATE": attrs.get("CREATED_DATE", ""),
            "raw_LAST_EDITED_DATE": attrs.get("LAST_EDITED_DATE", ""),
        })
    elif pub_stored:
        pub_class = "PRESENT_SOURCE_SEMANTICS_REVIEW"
        pub_classes["review"] += 1
    else:
        pub_class = "UNSPECIFIED"
        pub_classes["unspecified"] += 1
    master_rows.append({
        "master_id": master.id,
        "canonical_status": master.status,
        "publication_date_current_unmodified": pub_stored,
        "publication_evidence_class": pub_class,
        "submission_deadline_current_unmodified": stored,
        "deadline_evidence_class": classification,
        "explicit_non_furas_source_deadline_evidence": json.dumps(trusted, ensure_ascii=False),
        "all_source_deadline_evidence": json.dumps(all_raw, ensure_ascii=False),
    })

def write_csv(path, rows):
    if not rows:
        return
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

write_csv(OUT / "master-date-reconciliation.csv", master_rows)
write_csv(OUT / "furas-date-semantic-review-masters.csv", furas_review_rows)
write_csv(OUT / "publication-date-semantic-review-masters.csv", publication_review_rows)
summary = {
    "fixed_date_saudi": AS_OF.isoformat(),
    "non_merged_masters": len(masters),
    "deadline_classes_exclusive": dict(classes),
    "deadline_class_sum": sum(classes.values()),
    "trusted_deadline_buckets_with_no_reliable_in_bucket": {**dict(trusted_buckets), "NO_DEADLINE": classes["no_deadline"] + classes["semantic_review"]},
    "trusted_deadline_bucket_sum": sum(trusted_buckets.values()) + classes["no_deadline"] + classes["semantic_review"],
    "distinct_explicit_source_deadline_conflict_masters": conflicts,
    "canonical_deadline_vs_explicit_source_mismatches": canonical_source_mismatches,
    "publication_classes": dict(pub_classes),
    "source_date_counts": source_date_counts,
    "furas_review_master_count": len(furas_review_rows),
    "publication_review_master_count": len(publication_review_rows),
    "furas_review_master_ids": [r["master_id"] for r in furas_review_rows],
    "stored_deadlines": sum(bool(m.submission_deadline) for m in masters),
}
(OUT / "master-date-reconciliation-summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(summary, ensure_ascii=False, indent=2))

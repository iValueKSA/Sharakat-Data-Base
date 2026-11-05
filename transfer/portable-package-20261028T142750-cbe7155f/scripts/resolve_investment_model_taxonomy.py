"""Dry-run and audited backfill for the canonical Investment Model dimension.

The default mode is read-only. Pass --apply only after reviewing the generated
pre-apply CSV/JSON and applying migration 0020.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import inspect, text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.database import SessionLocal
from app.standardization import (
    INVESTMENT_MODEL_UNSPECIFIED_LABEL,
    STANDARDIZATION_VERSION,
    canonical_identity,
    standardize_field,
)

OUT = Path("docs/validation/data/investment-model-taxonomy")
LEASE_RE = re.compile(r"(?:تأجير|إيجار)\s+(?:موقع(?:ة|ات)?|مواقع|أرض|أراضٍ|مساحة|مساحات)", re.I)
MULTIPLE_MODEL_OPTIONS_RE = re.compile(r"نموذج\s+الاستثمار\s*:\s*خيارات\s+متعددة\s*\(([^)]{1,400})\)", re.I)


def json_dict(value):
    return value if isinstance(value, dict) else {}


def raw_hash(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def source_model(record):
    """Return (canonical identity, evidence, review, wrong-dimension) for one source row."""
    source = record["source_key"]
    raw = json_dict(record["raw_data_json"])
    title = str(record["source_title"] or raw.get("title") or "")
    description = str(raw.get("description") or raw.get("raw_text") or "")
    model_raw = raw.get("investment_model")
    candidates = raw.get("investment_model_candidates")
    if model_raw:
        field = standardize_field("investment_model", model_raw, source_key=source)
        identity = canonical_identity("investment_model", model_raw, source_key=source)
        if field["mapping_status"] == "MAPPED" and identity:
            return identity, f"حقل investment_model؛ {model_raw}", False, False
        return None, f"قيمة نموذج غير معتمدة: {model_raw}", True, False
    if isinstance(candidates, list) and candidates:
        return None, "مرشحات متعددة في نص المصدر: " + "، ".join(map(str, candidates)), True, False
    if source == "kfu":
        source_class = raw.get("content_type") or raw.get("opportunity_type")
        lease = LEASE_RE.search(f"{title} {description}")
        if str(source_class or "").upper() == "LEASE_OPPORTUNITY" and lease:
            return canonical_identity("investment_model", "تأجير", source_key="kfu"), f"تصنيف KFU LEASE_OPPORTUNITY مع نص العنوان «{lease.group(0)}»", False, False
        if str(source_class or "").upper() == "COMMERCIAL_FACILITY_OPPORTUNITY":
            return None, "تصنيف منشأة تجارية؛ لا يحدد آلية التعاقد", True, True
    if source == "invest-saudi":
        lease = LEASE_RE.search(f"{title} {description}")
        if lease:
            return canonical_identity("investment_model", "تأجير", source_key="invest-saudi"), f"نص العرض يذكر صراحة «{lease.group(0)}»", False, False
    if source == "ahda":
        text_content = " ".join(str(value or "") for value in (
            raw.get("description"), raw.get("raw_text"), title, description,
        ))
        options = MULTIPLE_MODEL_OPTIONS_RE.search(text_content)
        if options:
            return None, f"المصدر يصرح بخيارات نموذج متعددة: {options.group(1)}", True, False
    old_model = json_dict(json_dict(record["standardized_data_json"]).get("fields")).get("investment_model") or {}
    old_raw = old_model.get("raw")
    if source == "furas" and old_raw and str(old_raw).strip() == "تأجير مؤقت":
        return None, "قيمة قديمة مشتقة من نوع الفرصة Furas OPPORTUNITYTYPE=TemporaryRental؛ تصحيح بُعد فقط", False, True
    return None, "لا يوجد دليل موثق كافٍ على نموذج الاستثمار", False, False


def load_rows(db):
    masters = db.execute(text("""
        SELECT id, canonical_id, title_ar, opportunity_type, sector, activity, investment_model
        FROM opportunities WHERE merged_into_id IS NULL ORDER BY id
    """)).mappings().all()
    records = db.execute(text("""
        SELECT so.id, so.master_opportunity_id, so.source_id, s.source_key, s.source_name_ar, so.source_title,
               so.raw_data_json, so.standardized_data_json, so.standardization_version
        FROM source_opportunities so JOIN sources s ON s.id=so.source_id
        ORDER BY so.id
    """)).mappings().all()
    return [dict(row) for row in masters], [dict(row) for row in records]


def build_plan(masters, records, has_model_column):
    master_by_id = {row["id"]: row for row in masters}
    model_evidence = defaultdict(list)
    review_evidence = defaultdict(list)
    wrong_dimension_records = []
    source_keys = defaultdict(set)
    source_rows_by_master = defaultdict(list)
    for record in records:
        mid = record["master_opportunity_id"]
        if mid in master_by_id:
            source_keys[mid].add(record["source_key"])
            source_rows_by_master[mid].append(record)
        identity, evidence, review, wrong_dimension = source_model(record)
        if wrong_dimension:
            wrong_dimension_records.append({"source_record_id": record["id"], "master_id": mid,
                                            "source": record["source_key"], "evidence": evidence})
        if mid not in master_by_id:
            continue
        if identity:
            model_evidence[mid].append((identity, evidence, record))
        if review:
            review_evidence[mid].append((evidence, record))

    rows = []
    for master in masters:
        mid = master["id"]
        candidates = model_evidence[mid]
        distinct = {candidate[0]["id"] for candidate in candidates}
        review = list(review_evidence[mid])
        if len(distinct) > 1:
            review.extend((entry[1], entry[2]) for entry in candidates)
        assigned = candidates[0][0] if len(distinct) == 1 else None
        current = master.get("investment_model") if has_model_column else None
        if assigned:
            status = "DETERMINISTIC_CANONICAL" if current != assigned["label"] else "NO_CHANGE"
            proposed = assigned["label"]
        elif review:
            status = "REVIEW_REQUIRED"
            proposed = INVESTMENT_MODEL_UNSPECIFIED_LABEL
        else:
            status = "UNSPECIFIED"
            proposed = INVESTMENT_MODEL_UNSPECIFIED_LABEL
        evidence_items = [item[1] for item in candidates] + [item[0] for item in review]
        source_names = sorted(source_keys[mid])
        raw_values = []
        for record in source_rows_by_master[mid]:
            raw = json_dict(record["raw_data_json"])
            if raw.get("investment_model"):
                raw_values.append(f"{record['source_key']}:{raw['investment_model']}")
            elif record["source_key"] in {"kfu", "invest-saudi"}:
                title = str(record["source_title"] or "")
                match = LEASE_RE.search(title)
                if match:
                    raw_values.append(f"{record['source_key']}:{match.group(0)}")
        rows.append({
            "master_id": mid, "canonical_id": master["canonical_id"], "title": master["title_ar"],
            "sources": " | ".join(source_names), "raw_model_candidate": " | ".join(sorted(set(raw_values))),
            "source_field": "investment_model / title evidence / content_type",
            "current_model": current or INVESTMENT_MODEL_UNSPECIFIED_LABEL,
            "proposed_model": proposed,
            "proposed_model_id": assigned["id"] if assigned else "investment_model:missing",
            "wrong_dimension_movement": "Furas temporary-rental Type projection cleared" if any(x["master_id"] == mid for x in wrong_dimension_records) else "",
            "evidence": " || ".join(evidence_items) or "لا يوجد دليل بنيوي حاسم",
            "deterministic": bool(assigned), "status": status,
            "auto_apply": bool(assigned), "review_required": bool(review),
        })
    counts = Counter(row["status"] for row in rows)
    summary = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "read_only": True,
        "standardization_engine_version_target": STANDARDIZATION_VERSION,
        "total_eligible_masters": len(masters), "source_opportunity_records": len(records),
        "master_investment_model_column_present": has_model_column,
        "deterministic_model_mappings": sum(row["status"] == "DETERMINISTIC_CANONICAL" for row in rows),
        "mapped_to_unspecified": sum(row["status"] in {"UNSPECIFIED", "REVIEW_REQUIRED"} for row in rows),
        "wrong_dimension_values": len(wrong_dimension_records),
        "remain_review_required": sum(row["review_required"] for row in rows),
        "no_change": sum(row["status"] == "NO_CHANGE" for row in rows) + sum(row["status"] == "UNSPECIFIED" for row in rows),
        "master_status_counts": dict(counts),
        "wrong_dimension_source_records": wrong_dimension_records,
        "canonical_model_bucket_counts": dict(Counter(row["proposed_model"] for row in rows if row["deterministic"])),
        "decision": "Dry-run only; database rows were not modified.",
    }
    return rows, summary


def write_dry_run(rows, summary, records):
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "resolution-dry-run.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]) if rows else ["master_id"])
        writer.writeheader(); writer.writerows(rows)
    (OUT / "resolution-dry-run.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest = [{"source_record_id": row["id"], "master_id": row["master_opportunity_id"],
                 "source": row["source_key"], "raw_sha256": raw_hash(row["raw_data_json"])} for row in records]
    (OUT / "raw-provenance-before.json").write_text(json.dumps({
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_record_count": len(records), "raw_hashes": manifest,
    }, ensure_ascii=False), encoding="utf-8")
    (OUT / "identity-links-before.json").write_text(json.dumps({
        "masters": [{"id": row["master_id"], "canonical_id": row["canonical_id"]} for row in rows],
        "source_links": [{"source_record_id": row["id"], "source_id": row["source_id"],
                          "master_id": row["master_opportunity_id"]} for row in records],
    }, ensure_ascii=False), encoding="utf-8")


def write_source_coverage(db, records):
    source_rows = db.execute(text("SELECT source_key, source_name_ar FROM sources ORDER BY priority, source_key")).all()
    masters_by_source = defaultdict(set)
    for record in records:
        if record["master_opportunity_id"] is not None:
            masters_by_source[record["source_key"]].add(record["master_opportunity_id"])
    field = defaultdict(Counter)
    for record in records:
        key = record["source_key"]
        identity, evidence, review, wrong_dimension = source_model(record)
        raw = json_dict(record["raw_data_json"])
        field[key]["records"] += 1
        field[key]["raw_model_present"] += int(bool(raw.get("investment_model")))
        field[key]["canonical_source_records"] += int(identity is not None)
        field[key]["review_or_unmapped_source_records"] += int(review)
        field[key]["wrong_dimension_source_records"] += int(wrong_dimension)
    with (OUT / "source-coverage-after.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["source_key", "source", "records", "linked_masters", "linked_masters_with_canonical_model", "linked_masters_with_unspecified_model", "open_model_review_masters", "raw_model_present_records", "canonical_source_records", "review_or_unmapped_source_records", "wrong_dimension_source_records"])
        for source_key, source_name in source_rows:
            linked = masters_by_source[source_key]
            model_counts = db.execute(text("""SELECT COUNT(DISTINCT o.id) FROM opportunities o
                JOIN source_opportunities so ON so.master_opportunity_id=o.id
                JOIN sources s ON s.id=so.source_id WHERE s.source_key=:source AND o.merged_into_id IS NULL
                AND o.investment_model IS NOT NULL AND o.investment_model<>''"""), {"source": source_key}).scalar_one()
            review_count = db.execute(text("""SELECT COUNT(DISTINCT c.opportunity_id) FROM opportunity_data_conflicts c
                JOIN sources s ON s.id=c.source_id WHERE s.source_key=:source AND c.field_name='investment_model'
                AND c.status='OPEN'"""), {"source": source_key}).scalar_one()
            counts = field[source_key]
            writer.writerow([source_key, source_name, counts["records"], len(linked), model_counts,
                             len(linked) - model_counts, review_count, counts["raw_model_present"],
                             counts["canonical_source_records"], counts["review_or_unmapped_source_records"],
                             counts["wrong_dimension_source_records"]])


def projection_for(record):
    source = record["source_key"]
    raw = json_dict(record["raw_data_json"])
    old_meta = json_dict(record["standardized_data_json"])
    fields = json_dict(old_meta.get("fields"))
    old = json_dict(fields.get("investment_model"))
    identity, evidence, review, wrong_dimension = source_model(record)
    raw_value = raw.get("investment_model")
    title = str(record["source_title"] or raw.get("title") or "")
    if identity:
        incoming = raw_value or "تأجير"
        projection = standardize_field("investment_model", incoming, source_key=source)
        projection["canonical_id"] = identity["id"]
        projection["canonical_label"] = identity["label"]
        projection["mapping_status"] = "MAPPED"
        if source in {"kfu", "invest-saudi"} and not raw_value:
            projection.update({"raw": incoming, "evidence": evidence, "evidence_field": "title_or_description", "rule": "explicit_source_lease_text_v12"})
    else:
        projection = standardize_field("investment_model", None, source_key=source)
        if old.get("raw") and source == "furas" and str(old.get("raw")) == "تأجير مؤقت":
            fields["investment_model_evidence"] = {"raw": old.get("raw"), "normalized": "temporary_rental",
                "candidate_dimension": "opportunity_type", "canonical_id": None, "canonical_label": None,
                "mapping_status": "DIMENSION_REDIRECT", "rule": "furas_opportunity_type_not_model_v12"}
        elif review or wrong_dimension:
            fields["investment_model_evidence"] = {"raw": evidence, "normalized": None,
                "candidate_dimension": "review", "canonical_id": None, "canonical_label": None,
                "mapping_status": "REVIEW_REQUIRED", "rule": "investment_model_review_v15"}
    fields["investment_model"] = projection
    issues = [issue for issue in old_meta.get("issues", []) if issue.get("field") != "investment_model"]
    if projection.get("mapping_status") in {"UNMAPPED", "DIMENSION_REDIRECT"} or review:
        issues.append({"field": "investment_model", "code": "INVESTMENT_MODEL_REVIEW_REQUIRED", "source_key": source})
    old_meta.update({"version": STANDARDIZATION_VERSION, "source_key": source, "fields": fields, "issues": issues})
    return old_meta


def apply(db, rows, records, summary):
    if "investment_model" not in {column["name"] for column in inspect(db.get_bind()).get_columns("opportunities")}:
        raise RuntimeError("Apply requires migration 0020_investment_model to be applied first.")
    now = datetime.now(timezone.utc)
    changed_masters = 0
    history_rows = 0
    projection_rows = 0
    reviews_created = 0
    for row in rows:
        if not row["auto_apply"]:
            continue
        current = db.execute(text("SELECT investment_model FROM opportunities WHERE id=:id"), {"id": row["master_id"]}).scalar_one()
        if current == row["proposed_model"]:
            continue
        db.execute(text("UPDATE opportunities SET investment_model=:value, updated_at=:now WHERE id=:id"),
                   {"value": row["proposed_model"], "now": now, "id": row["master_id"]})
        source_record = next((record for record in records if record["master_opportunity_id"] == row["master_id"]
                              and source_model(record)[0] and source_model(record)[0]["id"] == row["proposed_model_id"]), None)
        source_id = source_record["source_id"] if source_record else None
        db.execute(text("""INSERT INTO opportunity_change_history
            (opportunity_id, changed_field, previous_value, new_value, source_id, detected_at)
            VALUES (:opportunity_id, 'investment_model', :previous_value, :new_value, :source_id, :detected_at)"""), {
                "opportunity_id": row["master_id"], "previous_value": current or INVESTMENT_MODEL_UNSPECIFIED_LABEL,
                "new_value": row["proposed_model"], "source_id": source_id, "detected_at": now})
        changed_masters += 1; history_rows += 1
    for record in records:
        metadata = projection_for(record)
        db.execute(text("UPDATE source_opportunities SET standardized_data_json=CAST(:metadata AS JSON), standardization_version=:version WHERE id=:id"), {
            "metadata": json.dumps(metadata, ensure_ascii=False), "version": STANDARDIZATION_VERSION, "id": record["id"]})
        projection_rows += 1
    for wrong in summary["wrong_dimension_source_records"]:
        if wrong["source"] != "furas":
            continue
        mid = wrong["master_id"]
        if mid is None:
            continue
        exists = db.execute(text("""SELECT id FROM opportunity_change_history
            WHERE opportunity_id=:mid AND changed_field='investment_model_source_projection'
              AND source_id=(SELECT id FROM sources WHERE source_key=:source)
              AND previous_value LIKE 'تأجير مؤقت%' LIMIT 1"""), {"mid": mid, "source": wrong["source"]}).first()
        if exists:
            continue
        source_id = db.execute(text("SELECT id FROM sources WHERE source_key=:source"), {"source": wrong["source"]}).scalar_one()
        db.execute(text("""INSERT INTO opportunity_change_history
            (opportunity_id, changed_field, previous_value, new_value, source_id, detected_at)
            VALUES (:opportunity_id, 'investment_model_source_projection', :previous_value, :new_value, :source_id, :detected_at)"""), {
                "opportunity_id": mid, "previous_value": "تأجير مؤقت (مُستمد من نوع الفرصة)",
                "new_value": "غير محدد (فصل الأبعاد)", "source_id": source_id, "detected_at": now})
        history_rows += 1
    for row in rows:
        if not row["review_required"]:
            continue
        master_id = row["master_id"]
        review_records = [item for item in records if item["master_opportunity_id"] == master_id
                          and source_model(item)[2]]
        for review in review_records:
            exists = db.execute(text("""SELECT id FROM opportunity_data_conflicts WHERE opportunity_id=:mid
                AND field_name='investment_model' AND source_record_id=:record_id AND status='OPEN' LIMIT 1"""),
                {"mid": master_id, "record_id": review["id"]}).first()
            if exists:
                continue
            _, evidence, _, _ = source_model(review)
            db.execute(text("""INSERT INTO opportunity_data_conflicts
                (opportunity_id, field_name, conflict_type, selected_value, conflicting_value, source_id, source_record_id, detected_at, status)
                VALUES (:opportunity_id, 'investment_model', 'TAXONOMY_CONFLICT', 'غير محدد',
                        :conflicting_value, :source_id, :source_record_id, :detected_at, 'OPEN')"""), {
                "opportunity_id": master_id, "conflicting_value": evidence,
                "source_id": review["source_id"], "source_record_id": review["id"], "detected_at": now})
            reviews_created += 1
    db.commit()
    raw_after = db.execute(text("SELECT so.id, so.master_opportunity_id, so.source_id, s.source_key, so.raw_data_json FROM source_opportunities so JOIN sources s ON s.id=so.source_id ORDER BY so.id")).mappings().all()
    raw_manifest = [{"source_record_id": row["id"], "master_id": row["master_opportunity_id"],
                     "source": row["source_key"], "raw_sha256": raw_hash(row["raw_data_json"])} for row in raw_after]
    raw_before = json.loads((OUT / "raw-provenance-before.json").read_text(encoding="utf-8"))["raw_hashes"]
    identity_before = json.loads((OUT / "identity-links-before.json").read_text(encoding="utf-8"))
    masters_after = db.execute(text("SELECT id, canonical_id FROM opportunities WHERE merged_into_id IS NULL ORDER BY id")).mappings().all()
    links_after = [{"source_record_id": row["id"], "source_id": row["source_id"], "master_id": row["master_opportunity_id"]} for row in raw_after]
    provenance = {
        "raw_payloads_unchanged": raw_before == raw_manifest,
        "master_identity_unchanged": identity_before["masters"] == [{"id": row["id"], "canonical_id": row["canonical_id"]} for row in masters_after],
        "source_links_unchanged": identity_before["source_links"] == links_after,
        "source_record_count": len(raw_after),
    }
    (OUT / "raw-provenance-after.json").write_text(json.dumps({"generated_at_utc": now.isoformat(), "checks": provenance, "raw_hashes": raw_manifest}, ensure_ascii=False), encoding="utf-8")
    return {"applied_at_utc": now.isoformat(), "engine_version": STANDARDIZATION_VERSION,
            "masters_updated": changed_masters, "change_history_rows_added": history_rows,
            "source_projection_records_updated": projection_rows, "open_model_reviews_created": reviews_created,
            "raw_provenance_checks": provenance}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Apply the reviewed plan after migration 0020.")
    args = parser.parse_args()
    with SessionLocal() as db:
        has_model_column = "investment_model" in {column["name"] for column in inspect(db.get_bind()).get_columns("opportunities")}
        masters, records = load_rows(db)
        rows, summary = build_plan(masters, records, has_model_column)
        write_dry_run(rows, summary, records)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        if args.apply:
            result = apply(db, rows, records, summary)
            write_source_coverage(db, records)
            (OUT / "resolution-apply.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

"""Read-only Activity taxonomy audit and guarded, deterministic local backfill.

Run in the application container. Without --apply this script never commits.
The raw payload and all source identity/link fields are excluded from writes.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select, func

from app.database import SessionLocal
from app.models import Opportunity, OpportunityConflict, Source, SourceOpportunity
from app.standardization import canonical_id, canonical_value, comparison_key, standardize_text

ASSET_ACTIVITY_TYPES = {comparison_key(x) for x in ("الساحات الميادين", "العربات المتنقلة", "المباني")}
TECHNICAL_ACTIVITY_SOURCES = {"ahda", "kfu", "mwan", "ncp", "pif"}
ACTIVITY_KEYS = {
    "الأنشطة التجارية", "الأنشطة المالية", "الأنشطة الصناعية", "أنشطة الصيانة والتصليح والتركيب",
    "الأنشطة التعليمية", "أنشطة المرافق العامة", "الأنشطة الزراعية والحيوانية", "الأنشطة الرياضية و الترفيهية", "أخرى",
    "صناعي", "تجاري", "خدمي",
}


def clean(value):
    return standardize_text(value) or None


def raw_dimensions(row, source_key):
    payload = row.raw_data_json or {}
    attrs = payload.get("attributes") or {}
    if source_key == "furas":
        return attrs.get("ACTIVITYTYPE"), attrs.get("SUBACTIVITYTYPE"), "Furas ACTIVITYTYPE / SUBACTIVITYTYPE"
    if source_key == "alahsa-opportunities":
        return (payload.get("details") or {}).get("نوع النشاط"), None, "Al-Ahsa details['نوع النشاط']"
    if source_key == "invest-saudi" and payload.get("source_record_family") == "project":
        return payload.get("activity"), payload.get("subActivity"), "Invest Saudi project activity / subActivity"
    if source_key == "ahda":
        return payload.get("content_type"), None, "AHDA publication content_type; not an Activity dimension"
    if source_key == "kfu":
        return payload.get("content_type"), None, "KFU opportunity/content enum; classified as opportunity type"
    if source_key in {"mwan", "ncp", "pif"}:
        return payload.get("opportunity_type") or payload.get("record_semantic_type"), None, "Source semantic/opportunity enum; not an Activity dimension"
    if row.source_activity or row.source_sub_activity:
        return row.source_activity, row.source_sub_activity, "persisted source dimension columns"
    return None, None, "no source activity field"


def source_key_for(db, source_id):
    source = db.get(Source, source_id)
    return source.source_key if source else "unknown"


def integrity_snapshot(masters, source_rows):
    master_identity = [(row.id, row.canonical_id) for row in masters]
    links = [(row.id, row.source_id, row.master_opportunity_id, row.source_opportunity_id) for row in source_rows]
    raw = [(row.id, row.raw_data_json or {}) for row in source_rows]
    sector_counts = dict(Counter(clean(row.sector) or "غير محدد" for row in masters))
    encode = lambda value: json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"),default=str).encode("utf-8")
    return {"master_count":len(masters),"source_record_count":len(source_rows),
        "master_identity_sha256":hashlib.sha256(encode(master_identity)).hexdigest(),
        "source_identity_and_link_sha256":hashlib.sha256(encode(links)).hexdigest(),
        "raw_payload_sha256":hashlib.sha256(encode(raw)).hexdigest(),"sector_bucket_counts":sector_counts}


def proposed_source_values(row, source_key):
    activity, sub_activity, evidence = raw_dimensions(row, source_key)
    activity = clean(activity)
    sub_activity = clean(sub_activity)
    if source_key in TECHNICAL_ACTIVITY_SOURCES:
        activity = None
    if source_key == "furas" and activity:
        activity = clean(activity.strip('"\'“”«»'))
    if source_key == "furas" and comparison_key(activity or "") in ASSET_ACTIVITY_TYPES:
        activity = None
    return activity, sub_activity, evidence


def master_proposal(master, linked_rows, sources):
    current_activity = clean(master.activity)
    current_sub = clean(master.sub_activity)
    furas_rows = [(r, proposed_source_values(r, sources[r.source_id])) for r in linked_rows if sources[r.source_id] == "furas"]
    notes = []
    review = False
    new_activity, new_sub = current_activity, current_sub
    if current_activity and comparison_key(current_activity) == comparison_key("Environment") and comparison_key(master.sector or "") == comparison_key("البيئة"):
        new_activity = None
        notes.append("Exact sector duplicate: Activity=Environment equals the Master's established Sector; clear Activity and retain Sector.")
    child_values = {comparison_key(values[1] or ""): values[1] for _, values in furas_rows if values[1]}
    parent_values = {comparison_key(values[0] or ""): values[0] for _, values in furas_rows if values[0]}
    furas_asset_evidence = any(
        comparison_key(clean((raw_dimensions(row, "furas")[0] or "").strip('\"\'“”«»')) or "") in ASSET_ACTIVITY_TYPES
        for row, _ in furas_rows
    )
    if (current_activity and comparison_key(current_activity) in ASSET_ACTIVITY_TYPES
            and comparison_key(clean((master.opportunity_type or "").strip('\"\'“”«»')) or "") in ASSET_ACTIVITY_TYPES
            and furas_asset_evidence):
        new_activity = None
        notes.append("Furas ACTIVITYTYPE is an asset/format category and the Master retains that category in Opportunity Type; clear it from Activity.")
    if len(child_values) > 1 or len(parent_values) > 1:
        review = True
        notes.append("Linked Furas records disagree on parent or sub-activity.")
    elif child_values:
        proposed_child = next(iter(child_values.values()))
        if not current_sub or comparison_key(current_sub) == comparison_key(proposed_child):
            new_sub = proposed_child
        else:
            review = True
            notes.append("Existing Master sub-activity conflicts with explicit Furas sub-activity.")
        parent = next(iter(parent_values.values()), None)
        if parent and comparison_key(parent) not in ASSET_ACTIVITY_TYPES:
            external_activity_values = {
                comparison_key(values[0]): values[0]
                for r in linked_rows if sources[r.source_id] != "furas"
                for values in [proposed_source_values(r, sources[r.source_id])]
                if values[0]
            }
            # An explicit non-Furas activity is preserved; disagreement is reviewable.
            if external_activity_values:
                if len(external_activity_values) == 1 and comparison_key(next(iter(external_activity_values.values()))) == comparison_key(parent):
                    new_activity = parent
                    notes.append("Top-level Activity is corroborated by Furas and another source.")
                    external_sub_values = {
                        comparison_key(values[1]): values[1]
                        for r in linked_rows if sources[r.source_id] != "furas"
                        for values in [proposed_source_values(r, sources[r.source_id])]
                        if values[1]
                    }
                    if external_sub_values and (len(external_sub_values) > 1 or comparison_key(next(iter(external_sub_values.values()))) != comparison_key(proposed_child)):
                        review = True
                        new_sub = current_sub
                        notes.append("The linked sources disagree on Sub-Activity; leave that field unchanged for review.")
                elif not current_activity:
                    new_activity = parent
                else:
                    review = True
                    notes.append("Cross-source Activity evidence conflicts; no parent value selected.")
            elif not current_activity or comparison_key(current_activity) == comparison_key(proposed_child):
                new_activity = parent
            elif comparison_key(current_activity) != comparison_key(parent):
                review = True
                notes.append("Existing Master Activity conflicts with explicit Furas parent Activity.")
        elif parent and not current_activity:
            review = True
            notes.append("Furas parent is an asset/format category, not an Activity; keep Activity unspecified.")
        notes.append("Furas names SUBACTIVITYTYPE explicitly; store it in the separate Sub-Activity field.")
    elif parent_values:
        parent = next(iter(parent_values.values()))
        if comparison_key(parent) in ASSET_ACTIVITY_TYPES:
            if current_activity:
                review = True
                notes.append("Furas top-level label is an asset/format category; do not promote it to Activity.")
        elif not current_activity:
            new_activity = parent
            notes.append("Only explicit Furas ACTIVITYTYPE evidence; populate top-level Activity.")
        elif comparison_key(current_activity) != comparison_key(parent):
            review = True
            notes.append("Existing Master Activity conflicts with explicit Furas ACTIVITYTYPE.")
    return new_activity, new_sub, review, " ".join(dict.fromkeys(notes))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="commit only deterministic source/master dimension projections")
    parser.add_argument("--out", default="/tmp/activity-taxonomy-review", help="directory for JSON and CSV reports")
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    as_of = datetime.now(timezone.utc).isoformat()
    db = SessionLocal()
    try:
        masters = db.scalars(select(Opportunity).where(Opportunity.merged_into_id.is_(None)).order_by(Opportunity.id)).all()
        sources = {source.id: source.source_key for source in db.scalars(select(Source)).all()}
        source_rows = db.scalars(select(SourceOpportunity).order_by(SourceOpportunity.id)).all()
        integrity_before = integrity_snapshot(masters, source_rows)
        by_master = {}
        for row in source_rows:
            if row.master_opportunity_id:
                by_master.setdefault(row.master_opportunity_id, []).append(row)

        master_values = Counter(clean(m.activity) or "" for m in masters)
        master_sub_values = Counter(clean(m.sub_activity) or "" for m in masters)
        master_csv = out / "master-activity-values.csv"
        with master_csv.open("w", newline="", encoding="utf-8-sig") as stream:
            writer = csv.writer(stream)
            writer.writerow(["raw_activity", "normalized_activity", "canonical_id", "count", "current_dimension", "notes"])
            for value, count in sorted(master_values.items(), key=lambda x: (-x[1], x[0])):
                canonical = canonical_value("activity", value)
                note = "Sector duplicate; deterministic clear" if value == "Environment" else "Source-specific values require projection review" if value else "Missing Activity"
                writer.writerow([value, standardize_text(value), canonical_id("activity", value), count, "Master.activity", note])

        source_value_counts = Counter()
        source_sub_counts = Counter()
        source_totals = Counter()
        source_raw_activity = Counter()
        source_raw_sub = Counter()
        source_linked_counts = Counter()
        source_only_sub = Counter()
        source_unresolved = Counter()
        source_wrong_dimension = Counter()
        source_canonical_activity = Counter()
        candidate_rows = []
        source_changes = []
        for row in source_rows:
            key = sources.get(row.source_id, "unknown")
            source_totals[key] += 1
            if row.master_opportunity_id:
                source_linked_counts[key] += 1
            raw_activity, raw_sub, evidence = raw_dimensions(row, key)
            new_activity, new_sub, _ = proposed_source_values(row, key)
            if new_activity:
                source_value_counts[(key, new_activity)] += 1
                source_raw_activity[key] += 1
                if canonical_id("activity", new_activity).startswith("activity:"):
                    source_canonical_activity[key] += 1
            if new_sub:
                source_sub_counts[(key, new_sub)] += 1
                source_raw_sub[key] += 1
                if not new_activity:
                    source_only_sub[key] += 1
            target_source_activity = raw_activity
            target_source_sub_activity = raw_sub
            if key in TECHNICAL_ACTIVITY_SOURCES:
                target_source_activity = None
            if key == "furas" and comparison_key(clean((raw_activity or "").strip('\"\'“”«»')) or "") in ASSET_ACTIVITY_TYPES:
                target_source_activity = None
            target_source_activity = str(target_source_activity).strip() if target_source_activity not in (None, "") else None
            target_source_sub_activity = str(target_source_sub_activity).strip() if target_source_sub_activity not in (None, "") else None
            if target_source_activity != row.source_activity or target_source_sub_activity != row.source_sub_activity:
                source_changes.append((row, target_source_activity, target_source_sub_activity))
            proposed_dimension = "activity+sub_activity" if new_activity and new_sub else "activity" if new_activity else "sub_activity" if new_sub else "unknown/wrong-dimension/missing"
            status = "SOURCE_EXPLICIT" if new_activity or new_sub else "UNRESOLVED_OR_MISSING"
            if key == "furas" and comparison_key(clean((raw_activity or "").strip('\"\'“”«»')) or "") in ASSET_ACTIVITY_TYPES:
                proposed_dimension = "asset/opportunity format"
                status = "WRONG_DIMENSION_RETAIN_RAW"
            if key in TECHNICAL_ACTIVITY_SOURCES and raw_activity:
                proposed_dimension = "publication/opportunity enum"
                status = "WRONG_DIMENSION_RETAIN_RAW"
            if status == "WRONG_DIMENSION_RETAIN_RAW":
                source_wrong_dimension[key] += 1
            elif not new_activity and not new_sub:
                source_unresolved[key] += 1
            candidate_rows.append({"raw_activity": raw_activity or "", "raw_sub_activity": raw_sub or "", "normalized_activity": clean(raw_activity) or "", "source": key, "source_record_id": row.id, "master_id": row.master_opportunity_id or "", "count": 1, "current_dimension": "source raw payload", "proposed_dimension": proposed_dimension, "canonical_activity": canonical_value("activity", new_activity) if new_activity else "", "canonical_sub_activity": canonical_value("sub_activity", new_sub) if new_sub else "", "confidence_status": status, "auto_fix_allowed": bool(new_activity or new_sub), "evidence": evidence})

        source_csv = out / "source-activity-values.csv"
        with source_csv.open("w", newline="", encoding="utf-8-sig") as stream:
            writer = csv.writer(stream)
            writer.writerow(["source", "raw_activity", "raw_sub_activity", "count", "dimension", "canonical_activity", "canonical_sub_activity", "status"])
            for (key, value), count in sorted(source_value_counts.items()):
                writer.writerow([key, value, "", count, "source Activity", canonical_value("activity", value), "", "explicit source value"])
            for (key, value), count in sorted(source_sub_counts.items()):
                writer.writerow([key, "", value, count, "source Sub-Activity", "", canonical_value("sub_activity", value), "explicit source sub-activity"])
        candidate_csv = out / "taxonomy-candidates.csv"
        with candidate_csv.open("w", newline="", encoding="utf-8-sig") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(candidate_rows[0]) if candidate_rows else ["source"])
            writer.writeheader(); writer.writerows(candidate_rows)

        coverage = []
        for key in sorted(set(sources.values())):
            total = source_totals[key]
            coverage.append({"source": key, "source_records": total, "linked_records": source_linked_counts[key], "records_with_activity": source_raw_activity[key], "records_without_top_level_activity": total-source_raw_activity[key], "records_with_sub_activity": source_raw_sub[key], "records_with_only_sub_activity": source_only_sub[key], "records_with_canonical_activity": source_canonical_activity[key], "wrong_dimension_values": source_wrong_dimension[key], "unresolved_or_missing": source_unresolved[key], "coverage_note": "Each source record is counted once by row state; Activity and Sub-Activity presence can overlap. Explicit enums/asset types are reported separately as wrong-dimension evidence."})
        with (out / "source-coverage.csv").open("w", newline="", encoding="utf-8-sig") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(coverage[0]) if coverage else ["source"]); writer.writeheader(); writer.writerows(coverage)

        proposals = []
        for master in masters:
            old_activity, old_sub = clean(master.activity), clean(master.sub_activity)
            new_activity, new_sub, review, notes = master_proposal(master, by_master.get(master.id, []), sources)
            if (old_activity, old_sub) != (new_activity, new_sub):
                proposals.append({"master_id":master.id,"title":master.title_ar,"old_activity":old_activity or "","new_activity":new_activity or "","old_sub_activity":old_sub or "","new_sub_activity":new_sub or "","review_required":review,"auto_apply":(not review or new_activity==old_activity or "Top-level Activity is corroborated by Furas and another source." in notes),"notes":notes})
        review_queue = [p for p in proposals if p["review_required"]]
        for master in masters:
            if comparison_key(master.activity or "") != comparison_key("خدمي"):
                continue
            source_row = next((r for r in by_master.get(master.id, []) if sources[r.source_id]=="alahsa-opportunities"), None)
            if source_row:
                review_queue.append({"master_id":master.id,"title":master.title_ar,"old_activity":"خدمي","new_activity":"خدمي","old_sub_activity":"","new_sub_activity":"","review_required":True,"auto_apply":False,"source_record_id":source_row.id,"source_key":"alahsa-opportunities","notes":"The source explicitly labels this broad activity family as خدمي; preserve it but review whether the platform taxonomy should retain it as a top-level Activity or classify it more narrowly."})
        with (out / "dry-run-master-changes.csv").open("w", newline="", encoding="utf-8-sig") as stream:
            headers=["master_id","title","old_activity","new_activity","old_sub_activity","new_sub_activity","review_required","auto_apply","notes"]
            writer=csv.DictWriter(stream,fieldnames=headers);writer.writeheader();writer.writerows(proposals)
        with (out / "taxonomy-review-queue-candidates.csv").open("w", newline="", encoding="utf-8-sig") as stream:
            headers=["master_id","title","old_activity","new_activity","old_sub_activity","new_sub_activity","review_required","auto_apply","source_key","source_record_id","notes"]
            writer=csv.DictWriter(stream,fieldnames=headers);writer.writeheader()
            for review in review_queue:
                row=dict(review)
                if "source_record_id" not in row:
                    linked=next((r for r in by_master.get(row["master_id"],[]) if sources[r.source_id]=="furas"),None)
                    row["source_record_id"]=linked.id if linked else ""
                    row["source_key"]="furas" if linked else ""
                writer.writerow(row)

        # Apply only the deterministic projection. No identity, source links, raw payload,
        # Sector, Opportunity Type or status is written here.
        applied_masters = 0
        applied_sources = 0
        review_items_created = 0
        if args.apply:
            for row, activity, sub_activity in source_changes:
                row.source_activity = activity
                row.source_sub_activity = sub_activity
                applied_sources += 1
            for proposal in proposals:
                if not proposal["auto_apply"]:
                    continue
                master = db.get(Opportunity, proposal["master_id"])
                master.activity = proposal["new_activity"] or None
                master.sub_activity = proposal["new_sub_activity"] or None
                applied_masters += 1
            for proposal in review_queue:
                source_key=proposal.get("source_key") or "furas"
                review_source = db.scalar(select(Source).where(Source.source_key==source_key))
                source_record_id = proposal.get("source_record_id")
                review_row = db.get(SourceOpportunity, source_record_id) if source_record_id else next((r for r in by_master.get(proposal["master_id"], []) if sources[r.source_id]==source_key), None)
                if not review_source or not review_row:
                    continue
                context = json.dumps({"proposed_activity":proposal["new_activity"],"proposed_sub_activity":proposal["new_sub_activity"],"reason":proposal["notes"]},ensure_ascii=False,sort_keys=True)
                existing = db.scalar(select(OpportunityConflict.id).where(OpportunityConflict.opportunity_id==proposal["master_id"],OpportunityConflict.field_name=="activity",OpportunityConflict.source_id==review_source.id,OpportunityConflict.source_record_id==review_row.id,OpportunityConflict.conflicting_value==context,OpportunityConflict.status=="OPEN"))
                if not existing:
                    db.add(OpportunityConflict(opportunity_id=proposal["master_id"],field_name="activity",conflict_type="TAXONOMY_CONFLICT",selected_value=proposal["old_activity"] or "غير محدد",conflicting_value=context,source_id=review_source.id,source_record_id=review_row.id,detected_at=datetime.now(timezone.utc),status="OPEN"))
                    review_items_created += 1
            db.commit()
        else:
            db.rollback()

        masters_after = db.scalars(select(Opportunity).where(Opportunity.merged_into_id.is_(None)).order_by(Opportunity.id)).all()
        sources_after = db.scalars(select(SourceOpportunity).order_by(SourceOpportunity.id)).all()
        integrity_after = integrity_snapshot(masters_after, sources_after)

        open_activity_reviews = db.scalar(select(func.count(OpportunityConflict.id)).where(OpportunityConflict.status=="OPEN", OpportunityConflict.field_name.in_(["activity","sub_activity"]))) or 0
        report = {
            "as_of_utc": as_of, "mode": "APPLY" if args.apply else "DRY_RUN_READ_ONLY",
            "database_head_required": "0019_activity_sub_activity", "standardization_version": "7",
            "eligible_master_total": len(masters), "active_masters": sum(1 for m in masters if m.status not in {"منتهية","منتهي","ملغاة","ملغي","تم الترسية","REMOVED_FROM_SOURCE","EXPIRED","CANCELLED","AWARDED","DELETED_FROM_SOURCE"}),
            "historical_masters": sum(1 for m in masters if m.status in {"منتهية","منتهي","ملغاة","ملغي","تم الترسية","REMOVED_FROM_SOURCE","EXPIRED","CANCELLED","AWARDED","DELETED_FROM_SOURCE"}),
            "master_activity_value_counts_before": dict(master_values), "master_sub_activity_value_counts_before": dict(master_sub_values),
            "source_record_total": len(source_rows), "source_activity_value_counts": {f"{s}|{v}":n for (s,v),n in sorted(source_value_counts.items())},
            "source_sub_activity_value_counts": {f"{s}|{v}":n for (s,v),n in sorted(source_sub_counts.items())},
            "source_changes_proposed": len(source_changes), "master_changes_proposed": len(proposals),
            "master_changes_auto_apply": sum(1 for p in proposals if p["auto_apply"]), "master_changes_review_required": sum(1 for p in review_queue),
            "environment_wrong_dimension_clear_count": sum(1 for p in proposals if p["old_activity"]=="Environment" and not p["new_activity"]),
            "explicit_furas_sub_activity_source_records": source_raw_sub["furas"], "currently_open_activity_conflicts": open_activity_reviews,
            "applied_master_updates": applied_masters, "applied_source_updates": applied_sources,
            "taxonomy_review_queue_items_created": review_items_created,
            "source_coverage": coverage,
            "cardinality": {"master_activity":"single-valued nullable scalar", "master_sub_activity":"single-valued nullable scalar", "source_values":"one value per source record and dimension; multiple source records can disagree for one Master", "relationship":"Sub-Activity is stored as a scalar label; no parent/child table or multi-valued Activity relation exists."},
            "data_safety": {"raw_payload_written": False, "source_links_written": False, "master_identity_written": False, "sector_written": False, "opportunity_type_written": False, "status_written": False},
            "integrity_before":integrity_before,"integrity_after":integrity_after,
            "integrity_invariants": {"master_identity_unchanged":integrity_before["master_identity_sha256"]==integrity_after["master_identity_sha256"],"source_identity_and_links_unchanged":integrity_before["source_identity_and_link_sha256"]==integrity_after["source_identity_and_link_sha256"],"raw_payload_unchanged":integrity_before["raw_payload_sha256"]==integrity_after["raw_payload_sha256"],"sector_counts_unchanged":integrity_before["sector_bucket_counts"]==integrity_after["sector_bucket_counts"]},
        }
        (out / "activity-taxonomy-review.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
        print(json.dumps(report,ensure_ascii=False))
    finally:
        db.close()


if __name__ == "__main__":
    main()

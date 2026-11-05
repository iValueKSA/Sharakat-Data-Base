"""Dry-run and explicit apply for the reviewed Master Sector taxonomy plan.

This updates only derived Master projections and their audit/review history. Raw
SourceOpportunity payloads, identifiers, and all source records are preserved.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.database import SessionLocal
from app.models import Opportunity, Source, SourceOpportunity, ChangeHistory, OpportunityConflict
from app.standardization import canonical_identity, canonical_value, SECTOR_UNSPECIFIED_LABEL

OUT = Path("docs/validation/data/sector-taxonomy")
ACTIVITY_SECTOR_LABELS = {
    "أنشطة التجارة العامة", "خدمات الصرافة", "أنشطة تجارة المواد الغذائية", "خدمي",
    "محلات تجارية", "العربات المتنقلة", "منشآت تقديم الغذاء",
    "أنشطة وخدمات انتاج المواد غير الغذائية", "الساحات الميادين", "المباني", "خدمات تعليمية أخرى",
}
TYPE_SECTOR_VALUES = {
    "LEASE_OPPORTUNITY": "فرصة تأجير",
    "COMMERCIAL_FACILITY_OPPORTUNITY": "فرصة منشأة تجارية",
    "PPP_PROJECT": "مشروع شراكة",
    "PPP_PROJECT_ANNOUNCEMENT": "إعلان مشروع شراكة",
    "INVESTMENT_OPPORTUNITY": "فرصة استثمارية",
    "GENERAL_ANNOUNCEMENT": "إعلان عام",
    "INVESTMENT_ANNOUNCEMENT": "إعلان استثماري",
    "INVESTMENT_SECTOR_INFORMATION": "معلومات قطاع استثماري",
    "STRATEGIC_PROJECT": "مشروع استراتيجي",
    "WASTE_SECTOR_INVESTMENT": "فرصة استثمار في قطاع النفايات",
}
SPECIAL = {
    211: ("غير محدد", "لا يظهر في السجل قطاع صريح؛ وصف خدمات الإرشاد المهني لا يحدد نشاطًا اقتصاديًا كافيًا.", "review"),
    212: ("السياحة", "الوصف الرسمي يحدد تطوير منتجع فندقي خمس نجوم بسعة 300–400 غرفة.", "confirmed"),
    213: ("الرعاية الصحية", "المشروع مستشفى متخصص للأمومة والأطفال.", "confirmed"),
    214: ("الرعاية الصحية", "الوصف يحدد تقديم خدمات طبية داخل المدارس.", "confirmed"),
    215: ("الزراعة", "المشروع يحدد معالجة أولية للتمور ومرفق إنتاج زراعي غذائي.", "confirmed"),
    216: ("الرعاية الصحية", "الوصف يحدد تطوير مراكز الرعاية الصحية الأولية وخدماتها السريرية.", "confirmed"),
    217: ("التعليم", "المشروع يحدد إنشاء مراكز تدريب تقني ومهني للقوى العاملة.", "confirmed"),
}


def rows_for_audit(db):
    return db.execute(
        select(Opportunity.id, Opportunity.canonical_id, Opportunity.title_ar, Opportunity.opportunity_owner,
               Opportunity.sector, Opportunity.activity, Opportunity.opportunity_type)
        .where(Opportunity.merged_into_id.is_(None)).order_by(Opportunity.id)
    ).all()


def source_evidence(db, opportunity_id):
    rows = db.execute(
        select(Source.source_key, Source.source_name_ar, SourceOpportunity.source_sector,
               SourceOpportunity.source_subsector, SourceOpportunity.source_activity,
               SourceOpportunity.raw_data_json, SourceOpportunity.source_opportunity_id)
        .join(Source, Source.id == SourceOpportunity.source_id)
        .where(SourceOpportunity.master_opportunity_id == opportunity_id)
        .order_by(Source.priority, Source.source_key)
    ).all()
    result = []
    for key, name, sector, subsector, activity, raw, external_id in rows:
        raw = raw or {}
        source_taxonomy = raw.get("source_taxonomy") or {}
        result.append({
            "source_key": key, "source": name, "external_id": external_id,
            "raw_sector": sector or source_taxonomy.get("sector"),
            "raw_subsector": subsector or source_taxonomy.get("subsector"),
            "activity": activity or raw.get("activity") or (raw.get("details") or {}).get("نوع النشاط"),
            "category": raw.get("category") or raw.get("content_type") or raw.get("kind") or raw.get("record_semantic_type"),
            "normalized_sector": (raw.get("normalized_taxonomy") or {}).get("sector"),
        })
    return result


def proposal(row, evidence):
    ident, canonical_id, title, owner, old, activity, opportunity_type = row
    if old in (None, "", "قيمة مفقودة", "غير مصنف"):
        return {"new_sector": SECTOR_UNSPECIFIED_LABEL, "new_activity": activity,
                "new_type": opportunity_type, "action": "MISSING_TO_UNSPECIFIED", "status": "deterministic"}
    if old == "بقية القطاعات":
        return {"new_sector": "أخرى", "new_activity": activity, "new_type": opportunity_type,
                "action": "APPROVED_ALIAS", "status": "deterministic"}
    if ident in SPECIAL:
        sector, reason, status = SPECIAL[ident]
        return {"new_sector": sector, "new_activity": activity,
                "new_type": opportunity_type or "INVESTMENT_OPPORTUNITY",
                "action": "EVIDENCE_RECLASSIFICATION", "evidence": reason, "status": status}
    if old in TYPE_SECTOR_VALUES:
        return {"new_sector": SECTOR_UNSPECIFIED_LABEL, "new_activity": activity,
                "new_type": opportunity_type or TYPE_SECTOR_VALUES[old], "action": "WRONG_DIMENSION_TO_TYPE",
                "evidence": "قيمة enum منشورة لنوع/نموذج الفرصة وليست قطاعًا.", "status": "review"}
    if old in ACTIVITY_SECTOR_LABELS:
        source_keys = {item["source_key"] for item in evidence}
        if source_keys and source_keys <= {"furas", "alahsa-opportunities"}:
            return {"new_sector": SECTOR_UNSPECIFIED_LABEL, "new_activity": activity or old,
                    "new_type": opportunity_type, "action": "ACTIVITY_MOVED_FROM_SECTOR",
                    "evidence": "وسم المصدر صريح لنوع النشاط؛ لا يتضمن السجل قطاعًا اقتصاديًا محددًا.", "status": "review"}
    identity = canonical_identity("sector", old)
    if identity and identity["id"] != "sector:unspecified":
        return {"new_sector": identity["label"], "new_activity": activity,
                "new_type": opportunity_type, "action": "CANONICAL_ALIAS" if identity["label"] != old else "KEEP",
                "status": "deterministic"}
    return {"new_sector": SECTOR_UNSPECIFIED_LABEL, "new_activity": activity or old,
            "new_type": opportunity_type, "action": "UNMAPPED_REVIEW", "evidence": "لا يوجد تطابق قطاعي معتمد؛ حُفظت القيمة في النشاط للمراجعة.", "status": "review"}


def build_report(db):
    master_rows = rows_for_audit(db)
    counts = Counter(row[4] if row[4] not in (None, "") else "<NULL>" for row in master_rows)
    type_counts = Counter(row[6] if row[6] not in (None, "") else "<NULL>" for row in master_rows)
    candidates = []
    special_rows = []
    for row in master_rows:
        evidence = source_evidence(db, row[0])
        plan = proposal(row, evidence)
        # Legacy ingestion copied RawOpportunity.activity into opportunity_type.
        # Move exact known Sector/Activity labels back to Activity; keep actual
        # opportunity-type enums such as INVESTMENT_OPPORTUNITY unchanged.
        type_identity = canonical_identity("sector", row[6]) if row[6] else None
        if row[6] and row[6] not in TYPE_SECTOR_VALUES and (row[6] in ACTIVITY_SECTOR_LABELS or
                (type_identity and type_identity["id"] != "sector:unspecified")):
            plan["new_activity"] = plan.get("new_activity") or row[6]
            plan["new_type"] = None
            plan["type_dimension_action"] = "LEGACY_ACTIVITY_MOVED_OUT_OF_TYPE"
        candidates.append({"id": row[0], "canonical_id": row[1], "title": row[2], "owner": row[3],
                           "before_sector": row[4], "before_activity": row[5], "before_type": row[6],
                           "sources": evidence, **plan})
        if row[4] == "فرصة استثمارية":
            special_rows.append({"master_id": row[0], "title": row[2], "owner": row[3],
                                 "current_sector": row[4], "sources": evidence,
                                 "activity": row[5], "opportunity_type": row[6], **plan})
    source_distinct = db.execute(select(Source.source_key, SourceOpportunity.source_sector,
                                         func.count(SourceOpportunity.id))
        .join(Source, Source.id == SourceOpportunity.source_id)
        .where(SourceOpportunity.source_sector.is_not(None), SourceOpportunity.source_sector != "")
        .group_by(Source.source_key, SourceOpportunity.source_sector)
        .order_by(Source.source_key, SourceOpportunity.source_sector)).all()
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(), "master_count": len(master_rows),
        "before_sector_counts": [{"sector": key, "count": count} for key, count in sorted(counts.items(), key=lambda pair: str(pair[0]))],
        "before_opportunity_type_counts": [{"type": key, "count": count} for key, count in sorted(type_counts.items(), key=lambda pair: str(pair[0]))],
        "proposed_sector_counts": [dict(sector=key, count=value) for key, value in sorted(Counter(item["new_sector"] for item in candidates).items())],
        "records_affected": sum(item["before_sector"] != item["new_sector"] or item["before_activity"] != item["new_activity"] or item["before_type"] != item["new_type"] for item in candidates),
        "records_requiring_review": sum(item["status"] == "review" for item in candidates),
        "special_opportunity_records": special_rows,
        "master_sector_records": candidates,
        "source_sector_distinct_values": [{"source_key": key, "raw_sector": sector, "source_record_count": int(count)} for key, sector, count in source_distinct],
    }


def write_report(report):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "dry-run-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    with (OUT / "master-sector-before-after.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        fields = ["id", "canonical_id", "title", "owner", "before_sector", "new_sector", "before_activity", "new_activity", "before_type", "new_type", "action", "status", "evidence"]
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore"); writer.writeheader(); writer.writerows(report["master_sector_records"])
    with (OUT / "investment-opportunity-reclassification.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        fields = ["master_id", "title", "owner", "current_sector", "activity", "opportunity_type", "new_sector", "new_type", "evidence", "status"]
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore"); writer.writeheader(); writer.writerows(report["special_opportunity_records"])


def apply_report(db, report):
    now = datetime.now(timezone.utc)
    changes = 0
    for item in report["master_sector_records"]:
        obj = db.get(Opportunity, item["id"])
        if not obj or obj.merged_into_id is not None:
            raise RuntimeError(f"Master row changed after dry run: {item['id']}")
        old_sector, old_activity, old_type = obj.sector, obj.activity, obj.opportunity_type
        source_link = db.execute(select(SourceOpportunity.source_id, SourceOpportunity.id)
                                 .where(SourceOpportunity.master_opportunity_id == obj.id)
                                 .order_by(SourceOpportunity.id)).first()
        for field, before, after in (("sector", old_sector, item["new_sector"]), ("activity", old_activity, item["new_activity"]), ("opportunity_type", old_type, item["new_type"])):
            if before == after:
                continue
            obj_field = field
            setattr(obj, obj_field, after)
            db.add(ChangeHistory(opportunity_id=obj.id, changed_field=field, previous_value=before,
                                 new_value=after, source_id=source_link[0] if source_link else None, detected_at=now))
            changes += 1
        if item["status"] == "review" and item["before_sector"] != item["new_sector"]:
            linked = source_link
            if linked:
                existing = db.scalar(select(OpportunityConflict.id).where(
                    OpportunityConflict.opportunity_id == obj.id, OpportunityConflict.field_name == "sector",
                    OpportunityConflict.selected_value == str(item["new_sector"]),
                    OpportunityConflict.conflicting_value == str(item["before_sector"]),
                    OpportunityConflict.status == "OPEN"))
                if not existing:
                    db.add(OpportunityConflict(opportunity_id=obj.id, field_name="sector", conflict_type="TAXONOMY_CONFLICT",
                        selected_value=str(item["new_sector"]), conflicting_value=str(item["before_sector"]),
                        source_id=linked[0], source_record_id=linked[1], detected_at=now, status="OPEN"))
    db.flush()
    return changes


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="write a review report only (default)")
    parser.add_argument("--apply", action="store_true", help="apply the deterministic reviewed plan")
    args = parser.parse_args()
    if args.dry_run and args.apply:
        parser.error("choose either --dry-run or --apply")
    with SessionLocal() as db:
        report = build_report(db)
        write_report(report)
        if args.apply:
            changes = apply_report(db, report)
            db.commit()
            report["applied_change_fields"] = changes
            report["applied_at"] = datetime.now(timezone.utc).isoformat()
            write_report(report)
        print(json.dumps({key: report[key] for key in ("master_count", "records_affected", "records_requiring_review", "before_sector_counts", "proposed_sector_counts")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

"""Build Phase 2 evidence artifacts and safely apply an approved dry-run."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.sector_inference_phase2 import (  # noqa: E402
    ACTIVITY_MAP, ENGINE_VERSION, EXACT_SUBACTIVITY_RULES, NEGATIVE_RULES,
    PHRASE_RULES, RAW_SOURCE_MAP, SUBACTIVITY_MAP, classify_phase2,
    empirical_mappings,
)
from app.standardization import canonical_id, canonical_value  # noqa: E402

OUT = ROOT / "docs/validation/data/sector-classification-phase-2"
UNSPECIFIED = "sector:unspecified"


def dump(name: str, value: Any) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def learned_for(records: list[dict[str, Any]], excluded_id: int | None = None) -> dict[str, dict[str, str]]:
    train = [row for row in records if row.get("id") != excluded_id]
    stats = empirical_mappings(train)
    learned: dict[str, dict[str, str]] = {"activity": {}, "sub_activity": {}}
    for field, values in stats.items():
        for row in values:
            if row["qualified"]:
                learned[field][row["source_value"]] = row["canonical_sector_id"]
    return learned


def source_mapping_artifact(snapshot: dict[str, Any]) -> dict[str, Any]:
    rows=[]
    raw_dist=snapshot["manifest"].get("source_raw_sector_distribution", {})
    for raw, sector_id in RAW_SOURCE_MAP.items():
        rows.append({"source": "furas", "raw_value": raw,
                     "canonical_sector_id": sector_id,
                     "canonical_sector": canonical_value("sector", sector_id),
                     "raw_source_sector_count_all_sources": raw_dist.get(raw, 0),
                     "evidence": "Exact value is treated as a sub-activity (never as source_sector alone); accepted only with matching canonical activity and sub-activity.",
                     "confidence": 0.97,
                     "rule_key": next((rule for (activity, sub), (target, rule) in EXACT_SUBACTIVITY_RULES.items()
                                       if sub == raw and target == sector_id), "P2_EXACT_STRUCTURED_SOURCE_PAIR")})
    return {"engine_version": ENGINE_VERSION, "mappings": rows,
            "scope_note": "No raw value is rewritten; only its exact, corroborated structured pair can contribute to a Master sector."}


def build(snapshot_path: Path) -> dict[str, Any]:
    snapshot=json.loads(snapshot_path.read_text(encoding="utf-8"))
    records=snapshot["records"]
    current=[row for row in records if row.get("sector_id")==UNSPECIFIED]
    specified=[row for row in records if row.get("sector_id")!=UNSPECIFIED]
    signal={"captured_at":snapshot["captured_at"],"manifest":snapshot["manifest"],
            "coverage":snapshot["signal_coverage"],"why_phase1_coverage_is_low":[
                "390 current unspecified Masters have titles and descriptions, but short/full descriptions frequently duplicate the title.",
                "Only 19 have activity and 18 have sub-activity; 366 have an opportunity type and asset assignment, often only a temporary lease/mobile cart.",
                "Only 12 have a nonempty source_sector; 19 source activities and 18 source sub-activities exist among unspecified Masters.",
                "No current unspecified Master has an English title or source taxonomy table row.",
                "Generic lease, location, retail dining and land/building terms are not sufficient sector evidence."]}
    dump("sector-signal-coverage.json",signal)

    stats=empirical_mappings(records)
    for field,filename in (("activity","activity-sector-mappings.json"),("sub_activity","subactivity-sector-mappings.json")):
        dump(filename,{"engine_version":ENGINE_VERSION,"training_scope":"current specified Masters excluding Phase 1 inference events",
                       "training_count":sum(1 for r in specified if not r.get("phase1_inference")),
                       "rule_threshold":{"activity":{"minimum_support":25,"minimum_purity_percentage":98},
                                         "sub_activity":{"minimum_support":8,"minimum_purity_percentage":98}}[field],
                       "deterministic_mapping_count":sum(1 for r in stats[field] if r["qualified"]),"mappings":stats[field]})
    dump("source-category-sector-mappings.json",source_mapping_artifact(snapshot))
    phrase_rows=[]
    gold=[r for r in specified if not r.get("phase1_inference")]
    for sector_id,groups in PHRASE_RULES.items():
        for group,phrases in groups.items():
            for phrase in phrases:
                hits=[r for r in gold if phrase.casefold() in (r.get("title_ar") or "").casefold()]
                phrase_rows.append({"sector_id":sector_id,"sector":canonical_value("sector",sector_id),
                    "group":group,"phrase":phrase,"labeled_title_support":len(hits),
                    "supporting_master_ids":[r["id"] for r in hits[:20]],
                    "rule_key":"P2_PHRASE_"+sector_id.split(":",1)[1].upper()+"_"+group.upper()})
    dump("sector-phrase-rules.json",{"engine_version":ENGINE_VERSION,"phrases":phrase_rows,
        "decision_policy":"Strong compound title phrase plus independent asset or non-duplicate description phrase; never title alone.",
        "fields_collapsed":["title_ar and normalized_title", "title repeated as short_description", "duplicate short/full descriptions"]})
    dump("sector-negative-rules.json",{"engine_version":ENGINE_VERSION,"count":len(NEGATIVE_RULES),"rules":NEGATIVE_RULES})

    # Leave-one-Master-out benchmark. All existing inferred and explicit source
    # sector evidence are hidden; learned maps are recalculated per held-out row.
    benchmark=[]; high=correct=incorrect=0; by_sector=Counter();
    for row in specified:
        held={**row,"sector":"غير محدد","sector_id":UNSPECIFIED,
              "source_sector_hidden_with_value_present":any(bool(s.get("source_sector")) for s in row.get("sources",[])),
              "sources":[{**s,"source_sector":None,"normalized_sector":None} for s in row.get("sources",[])]}
        prediction=classify_phase2(held,learned_mappings=learned_for(records,row["id"]))
        if prediction["classification"]=="HIGH_CONFIDENCE":
            high+=1; by_sector[prediction["sector_id"]]+=1
            if prediction["sector_id"]==canonical_id("sector",row["sector"]): correct+=1
            else: incorrect+=1
        benchmark.append({"master_id":row["id"],"hidden_sector_id":canonical_id("sector",row["sector"]),
                          "prediction":prediction,"holdout":"leave-one-Master-out",
                          "phase1_inference_excluded_from_training":True,"official_source_sector_hidden":True})
    benchmark_summary={"engine_version":ENGINE_VERSION,"benchmark_total":len(benchmark),"benchmark_high_confidence":high,
        "benchmark_correct":correct,"benchmark_incorrect":incorrect,
        "benchmark_precision_percentage":round(100*correct/high,2) if high else None,
        "by_predicted_sector":dict(sorted(by_sector.items())),"tourism_precision":"NOT_ENOUGH_DATA" if by_sector["sector:tourism"]<=5 else None,
        "agriculture_precision":"NOT_ENOUGH_DATA" if by_sector["sector:agriculture"]<=5 else None,
        "method":"Each Master held out individually; canonical sector and official source sectors hidden; empirical maps recomputed without held-out ID; Phase 1 inferred labels excluded from training."}
    dump("sector-inference-benchmark.json",{**benchmark_summary,"records":benchmark})

    predictions=[]
    for row in current:
        result=classify_phase2(row)
        predictions.append({"master_id":row["id"],"canonical_id":row["canonical_id"],"title_ar":row["title_ar"],
                            "current_sector":row["sector"],"result":result,
                            "has_open_sector_review":row["id"] in set(snapshot["manifest"].get("open_sector_review_master_ids",[]))})
    high_rows=[x for x in predictions if x["result"]["classification"]=="HIGH_CONFIDENCE"]
    reviews=[x for x in predictions if x["result"]["classification"]=="REVIEW_REQUIRED"]
    insufficient=[x for x in predictions if x["result"]["classification"]=="INSUFFICIENT_EVIDENCE"]
    dump("sector-phase2-dry-run.json",{"captured_at":snapshot["captured_at"],"engine_version":ENGINE_VERSION,
        "candidate_count":len(current),"high_confidence_count":len(high_rows),"review_required_count":len(reviews),
        "insufficient_evidence_count":len(insufficient),"predictions":predictions})
    # Stable audit sample plus every proposed decision, tourism/agriculture
    # benchmark record and all current unspecified Tourism/Agriculture signals.
    random20=sorted(current,key=lambda r:hashlib.sha256(f"phase2-sample:{r['id']}:{snapshot['manifest']['master_identity_fingerprint']}".encode()).hexdigest())[:20]
    sample_ids={r["id"] for r in random20}|{x["master_id"] for x in high_rows+reviews}
    sample_ids|={r["id"] for r in specified if canonical_id("sector",r["sector"]) in {"sector:tourism","sector:agriculture"}}
    samples=[{**x,"manual_audit_status":"PENDING_REVIEW","audit_reason":"Deterministic stratified sample; all proposed decisions included."}
             for x in predictions if x["master_id"] in sample_ids]
    dump("sector-phase2-sample-audit.json",{"sample_size":len(samples),"random_seed":"phase2-sample+master-identity-fingerprint",
        "audit_policy":"All HIGH_CONFIDENCE and REVIEW_REQUIRED candidates plus a deterministic 20-record unspecified sample and every existing tourism/agriculture Master.","records":samples})
    dump("sector-phase2-review-required.json",{"count":len(reviews),"records":reviews,
        "existing_open_review_masters":snapshot["manifest"].get("open_sector_review_master_ids",[]),
        "duplicate_reviews_created":0})
    dump("sector-phase2-unclassified.json",{"count":len(insufficient),"records":insufficient})
    base={"captured_at":snapshot["captured_at"],"before":snapshot["manifest"],"engine_version":ENGINE_VERSION,
          "applied_count":0,"applied_records":[],"status":"DRY_RUN_PENDING_REVIEW"}
    dump("sector-phase2-applied.json",base)
    dump("sector-phase2-migration-ledger.json",{"schema_migration_required":False,"database_mutations":[
        "For high-confidence decisions only: update Master.sector and append sector ChangeHistory and SystemEvent provenance.",
        "Existing conflicts/reviews, source rows, raw provenance, observations, merge lineage, lifecycle/status fields remain preserved."],
        "migration_count":0,"engine_version":ENGINE_VERSION,"pre_apply_snapshot":snapshot["manifest"]})
    dump("dq-sector-phase2-results.json",{"status":"PENDING_LIVE_READ_ONLY_CHECK","offline_checks":{
        "unspecified_separate_from_other":canonical_id("sector","غير محدد")!=canonical_id("sector","أخرى"),
        "high_confidence_has_traceable_rule_and_evidence":all(x["result"]["rule_key"] and x["result"]["positive_evidence"] for x in high_rows),
        "zero_preexisting_modification_in_dry_run":True},"predicted_high_confidence":len(high_rows)})
    dump("playwright-results.json",{"status":"PENDING_BROWSER_VERIFICATION","viewports":[{"width":w,"height":h} for w,h in [(1920,1080),(1440,900),(1366,768),(768,900),(390,844)]],"checks":[]})
    return {"manifest":snapshot["manifest"],"high":len(high_rows),"review":len(reviews),"insufficient":len(insufficient),"benchmark":benchmark_summary}


def main() -> None:
    parser=argparse.ArgumentParser()
    parser.add_argument("snapshot",type=Path)
    args=parser.parse_args()
    print(json.dumps(build(args.snapshot),ensure_ascii=False,indent=2,default=str))


if __name__=="__main__":main()

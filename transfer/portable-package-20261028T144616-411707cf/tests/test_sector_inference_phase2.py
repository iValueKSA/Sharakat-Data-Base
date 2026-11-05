from app.sector_inference_phase2 import classify_phase2, empirical_mappings
from app.standardization import canonical_id
from datetime import datetime, timezone
from types import SimpleNamespace


def _record(**overrides):
    row={"id":1,"sector":"غير محدد","activity":None,"sub_activity":None,
         "title_ar":"فرصة","normalized_title":"فرصة","short_description":"فرصة",
         "full_description":"فرصة","asset_facility_type":None,"sources":[]}
    row.update(overrides)
    return row


def test_existing_canonical_sector_is_preserved():
    result=classify_phase2(_record(sector="تجاري"))
    assert result["classification"]=="EXISTING_CLASSIFIED" and result["sector"]=="تجاري"


def test_explicit_official_sector_wins():
    result=classify_phase2(_record(sources=[{"source_key":"fixture","source_sector":"Tourism"}]))
    assert result["classification"]=="HIGH_CONFIDENCE" and result["sector_id"]=="sector:tourism"
    assert result["classification_origin"]=="SOURCE_EXPLICIT"


def test_exact_commercial_subactivity_pair_maps():
    result=classify_phase2(_record(activity="الأنشطة التجارية",sub_activity="أنشطة تجارة المواد الغذائية"))
    assert result["classification"]=="HIGH_CONFIDENCE" and result["sector_id"]=="sector:commercial"


def test_empirical_high_purity_activity_maps():
    result=classify_phase2(_record(activity="تجاري"))
    assert result["classification"]=="HIGH_CONFIDENCE" and result["sector_id"]=="sector:commercial"


def test_low_purity_activity_does_not_map():
    result=classify_phase2(_record(activity="الأنشطة التجارية"))
    assert result["classification"]!="HIGH_CONFIDENCE"


def test_small_sample_logistics_activity_does_not_map():
    result=classify_phase2(_record(activity="الخدمات اللوجستية"))
    assert result["classification"]!="HIGH_CONFIDENCE"


def test_raw_subactivity_sector_value_requires_exact_activity_pair():
    safe=classify_phase2(_record(activity="الأنشطة التجارية",sub_activity="محلات تجارية",
        sources=[{"source_key":"furas","source_sector":"محلات تجارية"}]))
    unsafe=classify_phase2(_record(sources=[{"source_key":"furas","source_sector":"محلات تجارية"}]))
    assert safe["sector_id"]=="sector:commercial" and unsafe["classification"]!="HIGH_CONFIDENCE"


def test_compound_tourism_title_with_independent_support_classifies():
    result=classify_phase2(_record(title_ar="إنشاء وتشغيل فندق بالأحساء",normalized_title="انشاء وتشغيل فندق بالاحساء",
        short_description="إنشاء وتشغيل فندق بالأحساء",full_description="مرفق سياحي يقدم ضيافة فندقية",
        asset_facility_type="منشأة ضيافة فندقية"))
    assert result["classification"]=="HIGH_CONFIDENCE" and result["sector_id"]=="sector:tourism"


def test_generic_keyword_alone_never_classifies():
    assert classify_phase2(_record(title_ar="استثمار موقع",activity=None))["classification"]=="INSUFFICIENT_EVIDENCE"


def test_cafe_is_not_automatically_tourism():
    result=classify_phase2(_record(title_ar="تأجير موقع مقهى بالمستشفى",short_description="تأجير موقع مقهى بالمستشفى"))
    assert result["sector_id"]!="sector:tourism"


def test_multi_signal_tourism_rule_is_explainable():
    result=classify_phase2(_record(title_ar="إنشاء وتشغيل فندق سياحي",short_description="إنشاء وتشغيل فندق سياحي",
        full_description="مرفق سياحي يقدم ضيافة فندقية",asset_facility_type="فندق سياحي"))
    assert result["sector_id"]=="sector:tourism" and result["positive_evidence"] and result["rule_keys"]


def test_food_retail_is_not_agriculture():
    result=classify_phase2(_record(title_ar="تموينات وميني ماركت",activity="الأنشطة التجارية",
        sub_activity="أنشطة تجارة المواد الغذائية"))
    assert result["sector_id"]=="sector:commercial"


def test_multi_signal_agriculture_rule_is_explainable():
    result=classify_phase2(_record(title_ar="استثمار وتشغيل مزرعة لإنتاج التمور",short_description="استثمار وتشغيل مزرعة لإنتاج التمور",
        full_description="نشاط زراعي لإنتاج المحاصيل",asset_facility_type="مزرعة إنتاج"))
    assert result["sector_id"]=="sector:agriculture" and result["positive_evidence"]


def test_conflicting_agricultural_activity_and_industrial_subactivity_review():
    result=classify_phase2(_record(activity="الأنشطة الزراعية والحيوانية",
        sub_activity="أنشطة وخدمات انتاج المواد غير الغذائية"))
    assert result["classification"]=="REVIEW_REQUIRED"
    assert set(result["candidates"])=={"sector:agriculture","sector:industrial"}


def test_insufficient_evidence_remains_unspecified():
    assert classify_phase2(_record())["classification"]=="INSUFFICIENT_EVIDENCE"


def test_other_remains_distinct_from_unspecified():
    assert canonical_id("sector","أخرى")!="sector:unspecified"
    assert classify_phase2(_record(sector="أخرى"))["sector"]=="أخرى"


def test_competing_sector_margin_is_not_ignored():
    result=classify_phase2(_record(activity="الأنشطة الزراعية والحيوانية",
        sub_activity="أنشطة وخدمات انتاج المواد غير الغذائية"))
    assert result["classification"]=="REVIEW_REQUIRED" and result["confidence_margin"]==0


def test_duplicate_title_and_description_do_not_create_independent_evidence():
    result=classify_phase2(_record(title_ar="إنشاء وتشغيل فندق سياحي",normalized_title="انشاء وتشغيل فندق سياحي",
        short_description="إنشاء وتشغيل فندق سياحي",full_description="إنشاء وتشغيل فندق سياحي"))
    assert result["classification"]!="HIGH_CONFIDENCE"


def test_inferred_decision_contains_traceable_provenance():
    result=classify_phase2(_record(activity="الأنشطة المالية",sub_activity="خدمات الصرافة"))
    assert result["classification_origin"]=="INFERRED_RULE"
    assert result["rule_key"] and result["rule_keys"] and result["positive_evidence"]


def test_repeated_classifier_result_is_idempotent():
    row=_record(activity="الأنشطة التجارية",sub_activity="محلات تجارية")
    assert classify_phase2(row)==classify_phase2(row)


def test_labeled_mapping_statistics_enforce_sample_and_purity():
    rows=[{"id":i,"sector":"صناعي","activity":"صناعي","sub_activity":None} for i in range(1,26)]
    rows.append({"id":26,"sector":"تجاري","activity":"صناعي","sub_activity":None})
    rows += [{"id":27,"sector":"تجاري","activity":"عينة صغيرة","sub_activity":None}]
    result=empirical_mappings(rows)["activity"]
    industrial=next(x for x in result if x["source_value"]=="صناعي")
    small=next(x for x in result if x["source_value"]=="عينة صغيرة")
    assert industrial["total_labeled_records"]==26 and industrial["qualified"] is False
    assert small["total_labeled_records"]==1 and small["qualified"] is False


def test_phase1_inferred_labels_are_excluded_from_training_statistics():
    rows=[{"id":1,"sector":"تجاري","activity":"متكرر","phase1_inference":None},
          {"id":2,"sector":"صناعي","activity":"متكرر","phase1_inference":{"rule_key":"old"}}]
    stats=empirical_mappings(rows)["activity"]
    row=next(x for x in stats if x["source_value"]=="متكرر")
    assert row["total_labeled_records"]==1 and row["sector_counts"]=={"sector:commercial":1}


def test_future_official_source_evidence_supersedes_a_phase2_inference_safely():
    from app.service import apply_sector_phase2_after_ingestion
    from app.models import ChangeHistory
    master=SimpleNamespace(id=5,sector="صناعي",updated_at=None,last_updated_at=None)
    linked=SimpleNamespace(source=SimpleNamespace(source_key="alahsa-opportunities"),source_id=1,
        id=11,source_sector="Tourism",normalized_sector="السياحة",source_activity=None,source_sub_activity=None)
    old=SimpleNamespace(payload={"classifications":[{"master_id":5,"sector":"صناعي",
        "classification_origin":"INFERRED_RULE"}]})
    class ScalarRows:
        def __init__(self,rows): self.rows=rows
        def all(self): return self.rows
    class FakeDB:
        def __init__(self): self.calls=0;self.added=[]
        def scalars(self,_statement):
            self.calls+=1
            return ScalarRows([linked] if self.calls==1 else [old])
        def scalar(self,_statement): return None
        def add(self,value): self.added.append(value)
    db=FakeDB();now=datetime.now(timezone.utc)
    apply_sector_phase2_after_ingestion(db,master,source=SimpleNamespace(id=1),
        source_record=linked,detected_at=now)
    assert master.sector=="السياحة"
    assert any(isinstance(x,ChangeHistory) and x.changed_field=="sector" for x in db.added)
    assert any(getattr(x,"event_type",None)=="SECTOR_INFERENCE_PHASE2_OFFICIAL_OVERRIDE" for x in db.added)


def test_future_official_other_is_not_treated_as_missing_or_ignored():
    from app.service import apply_sector_phase2_after_ingestion
    master=SimpleNamespace(id=6,sector="صناعي",updated_at=None,last_updated_at=None)
    linked=SimpleNamespace(source=SimpleNamespace(source_key="alahsa-opportunities"),source_id=1,
        id=12,source_sector="أخرى",normalized_sector="sector:other",source_activity=None,source_sub_activity=None)
    old=SimpleNamespace(payload={"classifications":[{"master_id":6,"sector":"صناعي",
        "classification_origin":"INFERRED_RULE"}]})
    class ScalarRows:
        def __init__(self,rows): self.rows=rows
        def all(self): return self.rows
    class FakeDB:
        def __init__(self): self.calls=0;self.added=[]
        def scalars(self,_statement):
            self.calls+=1
            return ScalarRows([linked] if self.calls==1 else [old])
        def scalar(self,_statement): return None
        def add(self,value): self.added.append(value)
    db=FakeDB();now=datetime.now(timezone.utc)
    apply_sector_phase2_after_ingestion(db,master,source=SimpleNamespace(id=1),
        source_record=linked,detected_at=now)
    assert canonical_id("sector",master.sector)=="sector:other"

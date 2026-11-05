import json
from pathlib import Path

from app.duplicate_review import compare_duplicate_masters, has_governance_blocker


def _compare(left_changes=None, right_changes=None, left_source=None, right_source=None, explanation=None):
    base = {"id": 1, "title_ar": "إنشاء مركز تجاري", "normalized_title": "انشاء مركز تجاري",
            "opportunity_owner": "أمانة الأحساء", "primary_publication_platform": "الفرص الاستثمارية",
            "sector": "تجاري", "activity": "تجاري", "sub_activity": None, "opportunity_type": None,
            "investment_model": None, "city": "الأحساء", "district": None,
            "location_description": "الهفوف، شارع 1", "latitude": None, "longitude": None,
            "land_area_sqm": 1000, "plot_number": "12", "investment_value": None,
            "currency": None, "contract_duration_years": 10, "publication_date": None,
            "submission_deadline": "2026-12-01", "status": "متاحة",
            "short_description": "إنشاء مركز تجاري", "full_description": "إنشاء مركز تجاري"}
    a, b = dict(base), dict(base)
    b["id"] = 2
    a.update(left_changes or {})
    b.update(right_changes or {})
    sa = {"source_key": "src-a", "publisher": "الجهة الناشرة", "official_source_id_original": "OFF-1",
          "source_opportunity_id": "123", "source_reference_number": "REF-1", "source_title": base["title_ar"],
          "source_owner": base["opportunity_owner"], "source_sector": "تجاري", "source_activity": "تجاري",
          "source_sub_activity": None, "raw_location": base["location_description"], "raw_area": "1000 م²",
          "raw_value": None, "raw_dates": {"deadline": "2026-12-01"}, "source_url": "https://a.test/123"}
    sb = dict(sa, source_key="src-a")
    sa.update(left_source or {})
    sb.update(right_source or {})
    if explanation is None:
        explanation = {"identity_review_decision": {"same_source": True,
            "review_reason": "same-source IDs require human confirmation"}}
    result = compare_duplicate_masters([a, b], {1: [sa], 2: [sb]}, explanation)
    return result


def test_same_source_same_official_id_remains_governed_review():
    r = _compare(right_source={"source_opportunity_id": "123", "source_url": "https://a.test/123"})
    assert r["classification"] == "SAME_SOURCE_AMBIGUOUS"
    assert r["auto_resolution_allowed"] is False


def test_cross_source_identical_records_are_not_auto_merged_by_display_match():
    r = _compare(right_source={"source_key": "src-b", "source_url": "https://b.test/123"},
                 explanation={"identity_review_decision": {"same_source": False, "basis": "official corroboration incomplete"}})
    assert r["classification"] == "CROSS_SOURCE_AMBIGUOUS"
    assert r["auto_resolution_allowed"] is False


def test_same_title_different_official_id_is_explained():
    r = _compare(right_source={"official_source_id_original": "OFF-2"})
    assert "official_source_id" in {x["field"] for x in r["different_fields"]}


def test_same_title_different_owner_is_explained():
    r = _compare(right_changes={"opportunity_owner": "بلدية أخرى"})
    assert "opportunity_owner" in {x["field"] for x in r["different_fields"]}


def test_same_title_different_location_is_explained():
    r = _compare(right_changes={"location_description": "المبرز، شارع 2"})
    assert "location_description" in {x["field"] for x in r["different_fields"]}


def test_same_title_different_investment_value_is_explained():
    r = _compare(right_changes={"investment_value": 1400000, "currency": "SAR"})
    assert {"investment_value", "currency"} <= {x["field"] for x in r["missing_on_left"]}


def test_asset_facility_type_difference_is_identity_evidence():
    r = _compare(left_changes={"asset_facility_type": [{"canonical_id": "gym", "label_ar": "نادي"}]},
                 right_changes={"asset_facility_type": [{"canonical_id": "kiosk", "label_ar": "كشك"}]})
    assert "asset_facility_type" in {x["field"] for x in r["different_fields"]}


def test_missing_and_present_are_not_collapsed():
    r = _compare(right_changes={"opportunity_owner": None})
    assert "opportunity_owner" in {x["field"] for x in r["missing_on_right"]}


def test_formatting_only_arabic_punctuation_and_digits_match():
    r = _compare(right_changes={"title_ar": "  إنشاء، مركز   تجاري! ", "city": "الأحساء"},
                 right_source={"source_title": " إنشاء، مركز   تجاري! ", "raw_area": "١٬٠٠٠ م²"})
    assert "title_ar" not in {x["field"] for x in r["different_fields"]}
    assert "raw_area" not in {x["field"] for x in r["different_fields"]}


def test_historical_provenance_conflict_is_a_blocker():
    r = _compare(explanation={"identity_review_decision": {"same_source": True,
        "historical_provenance_conflict": True, "review_reason": "conflicting historical provenance"}})
    assert has_governance_blocker(r)
    assert "historical" in r["blocking_reason"]


def test_identical_looking_review_has_specific_governance_reason():
    reason = "same-source records may be reissues; official history is missing"
    r = _compare(right_source={"source_opportunity_id": "123"},
                 explanation={"identity_review_decision": {"same_source": True, "review_reason": reason}})
    assert not r["different_fields"] and not r["missing_on_left"] and not r["missing_on_right"]
    assert r["blocking_reason"] == reason


def test_exact_looking_case_without_blocker_is_flagged():
    r = _compare(right_source={"source_opportunity_id": "123"}, explanation={})
    assert r["classification"] == "EXACT_LOOKING_WITHOUT_BLOCKER"
    assert not has_governance_blocker(r)


def test_ui_has_dedicated_difference_panel_and_blocker_copy():
    js = (Path(__file__).parents[1] / "app" / "static" / "app.js").read_text(encoding="utf-8")
    assert "الاختلافات بين الفرصتين" in js
    assert "لماذا تتطلب هذه الحالة مراجعة بشرية؟" in js
    assert "عرض الحقول المتطابقة" in js
    assert "غير محسوم / إبقاء للمراجعة" in js
    assert "data-review-keep-open" in js


def test_official_ids_block_auto_merge_without_claiming_distinct_opportunities():
    r = _compare(right_source={"official_source_id_original": "OFF-2"})
    assert "نفس المصدر" in r["human_review_reason"]
    assert "لا يثبت وحده أن الفرصتين مختلفتان" in r["human_review_reason"]
    assert r["auto_resolution_allowed"] is False


def test_cross_source_has_explicit_human_review_reason():
    r = _compare(right_source={"source_key": "src-b", "source_url": "https://b.test/123"},
                 explanation={"identity_review_decision": {"same_source": False}})
    assert "مصادر مختلفة" in r["human_review_reason"]
    assert "كافٍ للدمج الآلي" in r["human_review_reason"]


def test_keep_open_action_clears_selection_without_api_write():
    js = (Path(__file__).parents[1] / "app" / "static" / "app.js").read_text(encoding="utf-8")
    handler = js.split('[data-review-keep-open]', 1)[1].split('toast("ستبقى الحالة مفتوحة للمراجعة؛ لم يُرسل أي تغيير.")', 1)[0]
    assert "selectedAction = null" in handler
    assert 'toast("ستبقى الحالة مفتوحة للمراجعة؛ لم يُرسل أي تغيير.")' in js
    assert "api(" not in handler


def test_matching_fields_are_present_for_expandable_display():
    r = _compare()
    assert any(row["field"] == "sector" for row in r["matched_fields"])
    assert any(row["field"] == "source_opportunity_id" for row in r["matched_fields"])


def test_frozen_pilot_sample_is_not_regenerated_or_replaced():
    cohort = json.loads((Path(__file__).parents[1] / "app" / "human_review_pilot_cohort.json").read_text(encoding="utf-8"))
    duplicate_ids = [case["review_id"] for case in cohort["cases"] if case["type"] == "duplicate"]
    assert duplicate_ids == [32, 34, 37, 33, 35, 46]


def test_ambiguous_comparison_never_authorizes_auto_resolution():
    r = _compare(right_source={"source_opportunity_id": "124"})
    assert r["different_fields"]
    assert r["auto_resolution_allowed"] is False

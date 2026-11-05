from app.sector_inference import benchmark_prediction, classify_unspecified
from app.adapters import normalize_sector


def record(**values):
    return {
        "sector": "غير محدد", "title_ar": "فرصة استثمارية", "activity": None,
        "sub_activity": None, "short_description": None, "full_description": None,
        "subsector": None, "asset_facility_type": None, "sources": [], **values,
    }


def test_explicit_official_sector_wins_over_opposing_inference_signals():
    result = classify_unspecified(record(
        title_ar="تشغيل فندق سياحي", activity="الأنشطة المالية",
        sub_activity="خدمات الصرافة",
        sources=[{"source_key": "fixture", "source_record_id": 7, "source_sector": "Tourism"}],
    ))
    assert result["classification"] == "HIGH_CONFIDENCE"
    assert result["sector"] == "السياحة"
    assert result["origin"] == "SOURCE_EXPLICIT"


def test_reviewed_source_sector_alias_normalizes_to_real_estate():
    assert normalize_sector("Real Estate & Construction") == "العقارات والإنشاءات"


def test_existing_specified_canonical_sector_is_never_overwritten():
    result = classify_unspecified(record(sector="تجاري", title_ar="فندق منتجع سياحي"))
    assert result["classification"] == "EXISTING_CLASSIFIED"
    assert result["sector"] == "تجاري"


def test_deterministic_sub_activity_mapping_classifies_exchange_services():
    result = classify_unspecified(record(sub_activity="خدمات الصرافة"))
    assert result["classification"] == "HIGH_CONFIDENCE"
    assert result["sector"] == "الخدمات المالية"
    assert result["rule_key"] == "DETERMINISTIC_SUB_ACTIVITY"


def test_activity_and_title_agreement_classifies_financial_activity():
    result = classify_unspecified(record(
        activity="الأنشطة المالية", title_ar="تأجير موقع جهاز صراف آلي",
    ))
    assert result["classification"] == "HIGH_CONFIDENCE"
    assert result["sector"] == "الخدمات المالية"


def test_strong_tourism_evidence_requires_independent_support():
    result = classify_unspecified(record(
        title_ar="إنشاء فندق خمس نجوم", full_description="إنشاء فندق خمس نجوم ومرافق ضيافة فندقية.",
    ))
    assert result["classification"] == "HIGH_CONFIDENCE"
    assert result["sector"] == "السياحة"


def test_one_tourism_title_signal_is_review_required():
    result = classify_unspecified(record(title_ar="موقع لإنشاء فندق"))
    assert result["classification"] == "REVIEW_REQUIRED"


def test_agriculture_activity_and_title_agreement_classifies_primary_sector():
    result = classify_unspecified(record(
        activity="الأنشطة الزراعية والحيوانية", title_ar="إنشاء مزرعة نخيل وإنتاج التمور",
    ))
    assert result["classification"] == "HIGH_CONFIDENCE"
    assert result["sector"] == "الزراعة"


def test_generic_food_opportunity_does_not_become_agriculture():
    result = classify_unspecified(record(
        activity="الأنشطة التجارية", sub_activity="أنشطة تجارة المواد الغذائية",
        title_ar="تأجير وتشغيل نشاط تموينات",
    ))
    assert result["sector"] == "تجاري"


def test_generic_restaurant_does_not_become_tourism():
    result = classify_unspecified(record(title_ar="تأجير موقع مطعم"))
    assert result["classification"] == "INSUFFICIENT_EVIDENCE"


def test_conflicting_sector_signals_are_reviewed():
    result = classify_unspecified(record(
        activity="الأنشطة الزراعية والحيوانية", title_ar="مستشفى ومدرسة",
        short_description="مزرعة نخيل وإنتاج التمور",
    ))
    assert result["classification"] == "REVIEW_REQUIRED"
    assert result["rule_key"] == "CONFLICTING_SECTOR_SIGNALS"


def test_insufficient_evidence_stays_unspecified():
    result = classify_unspecified(record(title_ar="موقع استثماري"))
    assert result["classification"] == "INSUFFICIENT_EVIDENCE"
    assert result["sector"] == "غير محدد"


def test_repeated_classifier_run_is_idempotent():
    candidate = record(activity="الأنشطة التجارية", sub_activity="أنشطة تجارة المواد الغذائية")
    assert classify_unspecified(candidate) == classify_unspecified(candidate)


def test_inference_includes_traceable_rule_and_evidence():
    result = classify_unspecified(record(sub_activity="خدمات الصرافة"))
    assert result["rule_key"]
    assert result["confidence"] >= .90
    assert result["evidence"] == [{"field": "sub_activity", "signal": "خدمات الصرافة", "value": "خدمات الصرافة", "rule": "SUB_ACTIVITY_EXACT_EXCHANGE"}]


def test_source_sector_conflict_is_reviewed_before_inference():
    result = classify_unspecified(record(
        title_ar="إنشاء مزرعة نخيل", activity="الأنشطة الزراعية والحيوانية",
        sources=[
            {"source_key": "a", "source_record_id": 1, "source_sector": "Tourism"},
            {"source_key": "b", "source_record_id": 2, "source_sector": "Agriculture"},
        ],
    ))
    assert result["classification"] == "REVIEW_REQUIRED"
    assert result["rule_key"] == "CONFLICTING_OFFICIAL_SOURCE_SECTORS"


def test_benchmark_hides_canonical_and_source_sector_evidence():
    result = benchmark_prediction(record(
        sector="السياحة", sources=[{"source_key": "x", "source_sector": "Tourism"}],
    ))
    assert result["classification"] == "INSUFFICIENT_EVIDENCE"

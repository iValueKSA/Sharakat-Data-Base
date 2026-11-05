from app.standardization import (
    STANDARDIZATION_VERSION,
    canonical_id,
    canonical_identity,
    canonical_value,
    comparison_key,
    standardize_field,
    standardize_opportunity,
    standardize_text,
    parse_iso_date,
    parse_numeric,
    parse_area_sqm,
    parse_contract_duration_years,
    validate_url,
)
from app.normalization import normalize_arabic


def test_safe_arabic_text_normalization_and_idempotency():
    value = "  إِنْـشَاء\u200b\u00a0مُسْتَوْدَع   "
    normalized = standardize_text(value)
    assert normalized == "إنشاء مستودع"
    assert standardize_text(normalized) == normalized
    assert comparison_key("ألف") == comparison_key("آلف") == comparison_key("إلف") == comparison_key("الف")
    assert comparison_key("مدرسة") != comparison_key("مدرسه")
    assert comparison_key("هدى") != comparison_key("هدي")
    assert normalize_arabic("هدى") != normalize_arabic("هدي")


def test_confirmed_canonical_dimensions_and_unmapped_values():
    assert canonical_identity("sector", "اخرى") == {"id": "sector:other", "label": "أخرى"}
    assert canonical_identity("sector", "بقية القطاعات") == {"id": "sector:other", "label": "أخرى"}
    assert canonical_identity("sector", '"أخرى"') == {"id": "sector:other", "label": "أخرى"}
    assert canonical_identity("sector", None) == {"id": "sector:unspecified", "label": "غير محدد"}
    assert canonical_value("sector", "") == "غير محدد"
    assert canonical_value("sector", "قيمة مفقودة") == "غير محدد"
    assert canonical_value("sector", "أخرى") != canonical_value("sector", None)
    assert canonical_value("sector", "فرصة استثمارية") == "غير محدد"
    assert canonical_id("sector", "فرصة استثمارية") == "sector:unspecified"
    assert canonical_value("activity", "اخرى") == canonical_value("activity", "أخرى")
    assert canonical_identity("owner", "امانة الاحساء") == {"id": "al_ahsa_municipality", "label": "أمانة الأحساء"}
    assert canonical_value("owner", "هيئة تطوير الأحساء") != canonical_value("owner", "أمانة الأحساء")
    assert canonical_id("owner", "أمانة تجريبية") != canonical_id("owner", "امانة تجريبية")
    assert canonical_value("activity", "أخرى") != canonical_value("activity", "غير محدد")
    assert canonical_identity("activity", "الأنشطة الرياضية والترفيهية") == {
        "id": "activity:sports_recreation", "label": "الأنشطة الرياضية والترفيهية"
    }
    assert canonical_id("activity", "الأنشطة الرياضية و الترفيهية") == canonical_id(
        "activity", "الأنشطة الرياضية والترفيهية"
    ) == "activity:sports_recreation"
    assert canonical_identity("activity", None) == {
        "id": "activity:missing", "label": "غير محدد"
    }
    assert canonical_id("activity", "قيمة مفقودة") == "activity:missing"
    assert canonical_value("activity", None) == canonical_value("activity", "قيمة مفقودة") == "غير محدد"
    assert canonical_id("activity", "نشاط غير مسجل").startswith("unmapped:activity:")
    assert canonical_id("activity", "أخرى") == "activity:other"
    assert canonical_id("sub_activity", "أخرى") == "sub_activity:other"
    assert canonical_id("sector", "أخرى") == "sector:other"
    assert len({canonical_id(dimension, "أخرى") for dimension in ("activity", "sub_activity", "sector")}) == 3
    assert canonical_id("opportunity_type", "أخرى") == "opportunity_type:other"
    assert canonical_value("status", "UNKNOWN") == "Unknown"
    assert canonical_value("status", "غير متوفر") == "غير متوفر"
    assert canonical_value("status", "REMOVED_FROM_SOURCE") == "أزيلت من المصدر"
    assert canonical_id("status", "DELETED_FROM_SOURCE") != canonical_id("status", "CANCELLED")
    assert standardize_field("owner", "جهة غير مسجلة")["mapping_status"] == "UNMAPPED"


def test_standardize_opportunity_is_idempotent_and_retains_raw_provenance():
    raw = {
        "title": " فرصة\u00a0استثمارية ", "owner": "امانة الاحساء", "activity": "اخرى",
        "location": "الاحساء", "deadline": "01/02/2026", "reference": "01-٢٦-001",
        "url": " HTTPS://EXAMPLE.TEST:443/a ",
    }
    values = {"title_ar": " فرصة\u00a0استثمارية ", "normalized_title": "فرصة استثمارية",
              "opportunity_owner": "امانة الاحساء", "sector": "اخرى", "opportunity_type": "اخرى",
              "reference_number": "01-٢٦-001",
              "city": "الاحساء", "location_description": "الاحساء", "status": "UNKNOWN",
              "submission_deadline": "01/02/2026", "publication_date": None,
              "land_area_sqm": 1500.0, "investment_value": None, "contract_duration_years": None,
              "latitude": None, "longitude": None, "relevant": True}
    standardized = standardize_opportunity(values, source_key="fixture", source_record=raw)
    again = standardize_opportunity(standardized["values"], source_key="fixture", source_record=raw)
    assert standardized["values"] == again["values"]
    assert standardized["values"]["opportunity_owner"] == "أمانة الأحساء"
    assert standardized["values"]["sector"] == "أخرى"
    assert standardized["values"]["status"] == "Unknown"
    assert standardized["metadata"]["version"] == STANDARDIZATION_VERSION
    assert standardized["metadata"]["fields"]["opportunity_owner"]["raw"] == "امانة الاحساء"
    assert standardized["metadata"]["fields"]["opportunity_owner"]["canonical_id"] == "al_ahsa_municipality"
    assert standardized["metadata"]["fields"]["reference_number"]["normalized"] == "0126001"
    assert standardized["metadata"]["fields"]["submission_deadline"]["mapping_status"] == "VALID"
    assert "submission_deadline" not in [issue.get("field") for issue in standardized["issues"]]
    assert validate_url(raw["url"]) == ("https://example.test/a", None)
    assert validate_url("example.test/path")[1] == "invalid_absolute_http_url"
    assert validate_url("https://[broken")[1] == "invalid_absolute_http_url"


def test_business_date_parser_accepts_explicit_arabic_and_gregorian_formats():
    assert parse_iso_date("2026-10-21") == "2026-10-21"
    assert parse_iso_date("21/10/2026") == "2026-10-21"
    assert parse_iso_date("٢١/١٠/٢٠٢٦") == "2026-10-21"
    assert parse_iso_date("2026-10-21T00:30:00+03:00") == "2026-10-21T00:30:00+03:00"
    assert parse_iso_date("2026-10-21T00:30:00Z") == "2026-10-21T00:30:00+00:00"
    assert parse_iso_date("31/02/2026") is None
    assert parse_iso_date(None) is None


def test_submission_deadline_datetime_normalizes_to_saudi_local_date():
    values = {"submission_deadline": "2026-10-20T22:30:00Z", "publication_date": None}
    standardized = standardize_opportunity(values, source_key="fixture", source_record={"deadline": values["submission_deadline"]})
    assert standardized["values"]["submission_deadline"] == "2026-10-21"
    assert standardized["metadata"]["fields"]["submission_deadline"]["rule"] == "saudi_local_deadline_date_v2"

    naive_values = {"submission_deadline": "2026-10-21T00:30:00", "publication_date": None}
    naive = standardize_opportunity(naive_values, source_key="fixture", source_record={"deadline": naive_values["submission_deadline"]})
    assert naive["values"]["submission_deadline"] is None
    assert any(issue["code"] == "AMBIGUOUS_TIMEZONE_DATE_REVIEW" for issue in naive["issues"])


def test_missing_is_not_other_or_unknown():
    assert canonical_value("activity", None) == "غير محدد"
    assert canonical_value("activity", "Unknown") == "Unknown"
    assert canonical_value("activity", "أخرى") == "أخرى"


def test_sector_wrong_dimension_is_reviewed_and_raw_value_is_retained():
    raw = {"title": "عنوان", "activity": "فرصة استثمارية", "source_taxonomy": {"sector": "فرصة استثمارية"}}
    values = {"title_ar": "عنوان", "sector": None, "activity": "فرصة استثمارية", "opportunity_type": "INVESTMENT_OPPORTUNITY"}
    result = standardize_opportunity(values, source_key="fixture", source_record=raw)
    assert result["values"]["sector"] is None
    assert result["metadata"]["fields"]["sector"]["canonical_label"] == "غير محدد"
    assert result["metadata"]["fields"]["sector"]["mapping_status"] == "REVIEW_REQUIRED"
    assert "WRONG_DIMENSION_SECTOR_UNSPECIFIED" in {issue["code"] for issue in result["issues"]}
    assert raw["source_taxonomy"]["sector"] == "فرصة استثمارية"


def test_opportunity_type_values_fail_closed_and_keep_raw_review_evidence():
    for value in ("Investment", "INVESTMENT_OPPORTUNITY", "TemporaryRental", "LEASE_OPPORTUNITY",
                  "PPP_PROJECT", "COMMERCIAL_FACILITY_OPPORTUNITY", "الساحات الميادين", "أخرى"):
        expected_id = "opportunity_type:other" if value == "أخرى" else "opportunity_type:missing"
        expected_label = "أخرى" if value == "أخرى" else "غير محدد"
        assert canonical_id("opportunity_type", value) == expected_id
        assert canonical_value("opportunity_type", value) == expected_label
    assert canonical_value("opportunity_type", None) == "غير محدد"
    assert canonical_value("opportunity_type", "أخرى") != canonical_value("opportunity_type", None)

    raw = {"title": "عنوان", "opportunity_type": "COMMERCIAL_FACILITY_OPPORTUNITY"}
    result = standardize_opportunity(
        {"title_ar": "عنوان", "opportunity_type": "COMMERCIAL_FACILITY_OPPORTUNITY"},
        source_key="kfu", source_record=raw,
    )
    assert result["values"]["opportunity_type"] is None
    field = result["metadata"]["fields"]["opportunity_type"]
    assert field["raw"] == "COMMERCIAL_FACILITY_OPPORTUNITY"
    assert field["canonical_id"] == "opportunity_type:missing"
    assert field["canonical_label"] == "غير محدد"
    assert field["mapping_status"] == "REVIEW_REQUIRED"
    assert "OPPORTUNITY_TYPE_DIMENSION_REVIEW" in {issue["code"] for issue in result["issues"]}
    assert raw["opportunity_type"] == "COMMERCIAL_FACILITY_OPPORTUNITY"


def test_source_semantic_models_are_standardized_separately_from_type():
    from app.adapters import RawOpportunity, normalized_record
    raw = RawOpportunity(
        external_id="furas-test", title="تأجير مؤقت لموقع", url="https://example.test",
        owner="أمانة", raw={"attributes": {"OPPORTUNITYTYPE": "TemporaryRental"}},
        location_source_filtered=True,
    )
    values = normalized_record(raw)
    result = standardize_opportunity(values, source_key="furas", source_record=raw)
    assert result["values"]["opportunity_type"] == "تأجير مؤقت"
    assert result["metadata"]["fields"]["opportunity_type"]["canonical_id"] == "opportunity_type:temporary_rental"
    assert result["metadata"]["fields"]["opportunity_type"]["mapping_status"] == "MAPPED"
    assert result["values"]["investment_model"] is None


def test_temporary_rental_mapping_is_source_scoped_and_other_stays_distinct():
    from app.standardization import standardize_field
    furas = standardize_field("opportunity_type", "TemporaryRental", source_key="furas")
    other_source = standardize_field("opportunity_type", "TemporaryRental", source_key="other")
    assert (furas["canonical_id"], furas["canonical_label"], furas["mapping_status"]) == (
        "opportunity_type:temporary_rental", "تأجير مؤقت", "MAPPED")
    assert other_source["canonical_id"] == "opportunity_type:missing"
    assert other_source["mapping_status"] == "REVIEW_REQUIRED"
    approved_label = standardize_field("opportunity_type", "تأجير مؤقت")
    assert approved_label["canonical_id"] == "opportunity_type:temporary_rental"
    assert approved_label["mapping_status"] == "MAPPED"
    assert canonical_value("opportunity_type", "أخرى") == "أخرى"
    assert canonical_value("opportunity_type", "أخرى") != canonical_value("opportunity_type", None)


def test_kfu_commercial_facility_classifier_does_not_guess_investment_model():
    from app.adapters import RawOpportunity, normalized_record
    raw = RawOpportunity(
        external_id="kfu-facility-test", title="مزايدة تقديم الخدمات الغذائية والعامة",
        url="https://example.test/kfu", owner="جامعة الملك فيصل",
        raw={"opportunity_type": "COMMERCIAL_FACILITY_OPPORTUNITY",
             "raw_text": "مطاعم ومتاجر عامة بمباني كليات الجامعة؛ مدة العقد ثلاث سنوات"},
        location_source_filtered=True,
    )
    values = normalized_record(raw)
    result = standardize_opportunity(values, source_key="kfu", source_record=raw)
    assert result["values"]["opportunity_type"] is None
    assert result["values"].get("investment_model") is None


def test_numeric_parsing_preserves_raw_and_rejects_ambiguous_values():
    assert parse_numeric("١٬٥٠٠٬٠٠٠ ريال") == 1500000.0
    assert parse_numeric("1,500 sqm") == 1500.0
    assert parse_numeric("1,5") is None
    assert parse_numeric("$1,500") is None
    assert parse_numeric("unknown 100") is None


def test_area_normalization_requires_a_proven_square_metre_unit():
    assert parse_area_sqm("1,361.05 م²", source_key="alahsa-opportunities") == 1361.05
    assert parse_area_sqm("2 hectares", source_key="alahsa-opportunities") is None
    assert parse_area_sqm("64", source_key="invest-saudi") is None
    assert parse_area_sqm("64", source_key="furas", source_payload={"attributes":{"TOTALSPACEINMETERS":"64"}}) == 64
    assert parse_area_sqm("64", source_key="furas", source_payload={"attributes":{"TOTALSPACEINMETERS":"65"}}) is None


def test_contract_duration_requires_explicit_contract_unit():
    assert parse_contract_duration_years("15 سنة") == 15
    assert parse_contract_duration_years("24 months") == 2
    assert parse_contract_duration_years("5 Years") == 5
    assert parse_contract_duration_years("366 days") is None
    assert parse_contract_duration_years(15) is None


def test_standardization_does_not_relabel_unknown_area_or_duration_as_canonical():
    raw={"area_text":"64 hectares","contract_text":"366 days","raw":{}}
    values={"land_area_sqm":64,"contract_duration_years":366,"investment_value":None}
    result=standardize_opportunity(values,source_key="invest-saudi",source_record=raw)
    assert result["values"]["land_area_sqm"] is None
    assert result["values"]["contract_duration_years"] is None
    assert result["metadata"]["fields"]["land_area_sqm"]["mapping_status"]=="REVIEW_REQUIRED"
    assert result["metadata"]["fields"]["contract_duration_years"]["mapping_status"]=="REVIEW_REQUIRED"

from types import SimpleNamespace

from app.entity_resolution import compare_source_records, lifecycle_status, normalize_owner


def record(key, external_id, title, *, owner, location, area, duration, deadline,
           reference=None, city=None, district=None, street=None, plan=None, geometry=None):
    attrs = {"CITYNAME": city, "DISTRICT": district, "STREET": street,
             "DURATION": duration * 12, "CITY_ID": "005011001",
             "OPPORTUNITYID": reference or external_id}
    if plan:
        title += f" بالمخطط رقم {plan}"
    return SimpleNamespace(source_opportunity_id=external_id,
        source_reference_number=reference, source_title=title, source_owner=owner,
        raw_location=location, raw_area=str(area), raw_dates={"deadline": deadline},
        raw_status="Announced" if key == "furas" else "متاحة",
        raw_data_json={"attributes": attrs, "geometry": geometry or {},
                       "details": {"مدة العقد": str(duration), "نوع النشاط": "صناعي"}},
        source_url=f"https://{key}.example/{external_id}",
        source=SimpleNamespace(source_key=key))


def test_live_candidate_features_produce_strong_composite_not_title_only():
    ahsa = record("alahsa-opportunities", "441",
        "إنشاء وتشغيل وصيانة القطعة رقم 461 لنشاط صناعي بالمخطط رقم 14/16 بصناعية العيون",
        owner="أمانة الأحساء", location="العيون", area=752.34, duration=15,
        deadline="2026-10-21", plan="14/16")
    furas = record("furas", "01-26-017001-27001",
        "انشاء وتشغيل وصيانة القطعة رقم 461 لنشاط صناعي بالمخطط رقم 14/16 بصناعية العيون",
        owner="أمانة محافظة الأحساء", location="العيون الصناعية حارثة بن قيس",
        area=752.34, duration=15, deadline="2026-10-21", reference="01-26-017001-27001",
        city="العيون", district="الصناعية", street="حارثة بن قيس", plan="14/16",
        geometry={"x":49.543832,"y":25.635184})
    features = compare_source_records(ahsa, furas)
    assert features["owner_match"] is True
    assert features["area_difference_percentage"] == 0
    assert features["duration_match"] is True and features["deadline_match"] is True
    assert features["plot_match"] is True or features["plan_match"] is True
    assert features["auto_merge_safe"] is True


def test_title_alone_never_triggers_auto_merge_and_conflicting_plot_blocks_it():
    a = record("alahsa-opportunities", "1", "إنشاء وتشغيل وصيانة مستودع تجاري",
        owner="أمانة الأحساء", location="العيون", area=5000, duration=15, deadline="2026-10-21")
    b = record("furas", "r1", "إنشاء وتشغيل وصيانة مستودع تجاري",
        owner="أمانة محافظة الأحساء", location="العيون", area=5000, duration=15,
        deadline="2026-10-21", reference="r1")
    # The common words and all scalar fields do not supply an identity/site key.
    assert compare_source_records(a, b)["auto_merge_safe"] is False


def test_source_verified_official_reference_can_link_cross_source_records():
    reference = "06-26-189921-64005"
    furas = record("furas", "furas-listing", "Palm Processing Facility", owner=None,
        location="Al-Ahsa", area=5000, duration=15, deadline="2026-10-21", reference=reference)
    invest_saudi = record("invest-saudi", "investsaudi:10", "Palm Processing Project", owner=None,
        location="Eastern Province", area=5000, duration=15, deadline="2026-10-21", reference=reference)
    furas.raw_data_json = {"attributes": {"OPPORTUNITYID": reference}}
    invest_saudi.raw_data_json = {"source_record_family": "project", "modalData": {"opportunityNumber": reference}}
    features = compare_source_records(furas, invest_saudi)
    assert features["trusted_official_reference_match"] is True
    assert features["auto_merge_safe"] is True


def test_same_reference_text_without_verified_source_semantics_is_review_only():
    a = record("furas", "1", "Opportunity one", owner=None, location="Al-Ahsa", area=5000,
        duration=15, deadline="2026-10-21", reference="06-26-189921-64005")
    b = record("invest-saudi", "2", "Opportunity two", owner=None, location="Al-Ahsa", area=5000,
        duration=15, deadline="2026-10-21", reference="06-26-189921-64005")
    a.raw_data_json = {"attributes": {"OBJECTID": "06-26-189921-64005"}}
    b.raw_data_json = {"source_record_family": "opportunity", "id": "06-26-189921-64005"}
    features = compare_source_records(a, b)
    assert features["same_normalized_reference"] is True
    assert features["trusted_official_reference_match"] is False
    assert features["auto_merge_safe"] is False


def test_different_verified_references_block_same_site_fuzzy_auto_merge():
    a = record("furas", "1", "إنشاء وتشغيل وصيانة القطعة رقم 12 بالمخطط 14/16",
        owner="أمانة الأحساء", location="العيون", area=5000, duration=15,
        deadline="2026-10-21", reference="06-26-189921-64005", plan="14/16")
    b = record("invest-saudi", "2", "إنشاء وتشغيل وصيانة القطعة رقم 12 بالمخطط 14/16",
        owner="أمانة الأحساء", location="العيون", area=5000, duration=15,
        deadline="2026-10-21", reference="06-26-189921-64006", plan="14/16")
    a.raw_data_json = {"attributes": {"OPPORTUNITYID": "06-26-189921-64005"}}
    b.raw_data_json = {"source_record_family": "project", "modalData": {"opportunityNumber": "06-26-189921-64006"}}
    features = compare_source_records(a, b)
    assert features["official_reference_conflict"] is True
    assert features["strong_composite_match"] is True
    assert features["auto_merge_safe"] is False


def test_exact_official_reference_does_not_override_conflicting_parcels():
    reference = "06-26-189921-64005"
    a = record("furas", "1", "إنشاء وتشغيل مستودع قطعة رقم 12 بالمخطط 14/16",
        owner="أمانة الأحساء", location="العيون", area=5000, duration=15,
        deadline="2026-10-21", reference=reference, plan="14/16")
    b = record("invest-saudi", "2", "إنشاء وتشغيل مستودع قطعة رقم 13 بالمخطط 14/16",
        owner="أمانة الأحساء", location="العيون", area=5000, duration=15,
        deadline="2026-10-21", reference=reference, plan="14/16")
    a.raw_data_json = {"attributes": {"OPPORTUNITYID": reference}}
    b.raw_data_json = {"source_record_family": "project", "modalData": {"opportunityNumber": reference}}
    features = compare_source_records(a, b)
    assert features["trusted_official_reference_match"] is True
    assert features["plot_conflict"] is True
    assert features["auto_merge_safe"] is False


def test_same_source_composite_similarity_is_never_auto_merge_safe():
    a = record("furas", "1", "إنشاء وتشغيل القطعة رقم 12 بالمخطط 14/16",
        owner="أمانة الأحساء", location="العيون", area=5000, duration=15,
        deadline="2026-10-21", plan="14/16")
    b = record("furas", "2", "إنشاء وتشغيل القطعة رقم 12 بالمخطط 14/16",
        owner="أمانة الأحساء", location="العيون", area=5000, duration=15,
        deadline="2026-10-21", plan="14/16")
    features = compare_source_records(a, b)
    assert features["strong_composite_match"] is True
    assert features["auto_merge_safe"] is False

    a.source_title = "إنشاء وتشغيل وصيانة القطعة رقم 12 لنشاط صناعي بالمخطط رقم 14/16"
    b.source_title = "إنشاء وتشغيل وصيانة القطعة رقم 13 لنشاط صناعي بالمخطط رقم 14/16"
    assert compare_source_records(a, b)["plot_conflict"] is True
    assert compare_source_records(a, b)["auto_merge_safe"] is False


def test_incompatible_semantic_types_block_exact_reference_auto_merge():
    a = record("modon", "shared-id", "Al-Ahsa Development Destination",
        owner="MODON", location="Al-Ahsa", area=1000, duration=10, deadline="2026-10-21", reference="shared-id")
    b = record("furas", "shared-id", "Investment Opportunity for Development",
        owner="MODON", location="Al-Ahsa", area=1000, duration=10, deadline="2026-10-21", reference="shared-id")
    a.raw_data_json["record_semantic_type"] = "DESTINATION"
    b.raw_data_json["record_semantic_type"] = "INVESTMENT_OPPORTUNITY"
    features = compare_source_records(a, b)
    assert features["semantic_compatible"] is False
    assert features["current_duplicate_score"] == 0
    assert features["auto_merge_safe"] is False

def test_owner_alias_and_lifecycle_status_are_distinct_from_source_publisher():
    assert normalize_owner("أمانة الأحساء") == normalize_owner("أمانة محافظة الأحساء")
    assert lifecycle_status("Announced") == "ACTIVE"
    assert lifecycle_status("Deleted") == "REMOVED_FROM_SOURCE"
    assert lifecycle_status("ملغاة") == "CANCELLED"
    assert lifecycle_status("تم الترسية") == "AWARDED"
    assert lifecycle_status("مجهول") == "UNKNOWN"


def test_four_reviewed_live_pairs_keep_composite_identity_features():
    pairs = [
        ("إنشاء وتشغيل وصيانة القطعة رقم 461 1و 461 2 لنشاط صناعات خفيفة أو ورشة بالمخطط رقم 14-16 بصناعية العيون",
         "انشاء وتشغيل وصيانة القطعة رقم 461 1و 461 2 لنشاط صناعات خفيفة أو ورشة بالمخطط رقم 14 16 بصناعية العيون - الأنشطة الصناعية - مصنع", 752.34, 15, True, True),
        ("انشاء وتشغيل وصيانة مستودع غاز بالمخطط رقم (14/53) بمدينة الجرن بنشاط بيع وتوزيع أسطوانات الغاز",
         "انشاء وتشغيل وصيانة مستودع غاز بالمخطط رقم 14 53 بمدينة الجرن بنشاط بيع وتوزيع أسطوانات الغاز - الأنشطة التجارية - مستودع", 2734, 25, False, True),
        ("انشاء وتشغيل وصيانة القطعة رقم 471 لنشاط صناعات خفيفة أو ورشة بالمخطط رقم 14 16 بصناعية العيون",
         "انشاء وتشغيل وصيانة القطعة رقم 471 لنشاط صناعات خفيفة أو ورشة بالمخطط رقم 14/16 بصناعية العيون - الأنشطة الصناعية - مصنع", 708.45, 15, True, True),
        ("إنشاء وتشغيل وصيانة مواقف للمعدات والنقليات وورشة ومستودع ومكاتب إدارية وسكن للموظفين للقطع رقم 405/ت الى 409/ت بالمخطط رقم 14/154 الصناعية الشمالية بالعيون",
         "انشاء وتشغيل وصيانة مواقف للمعدات والنقليات وورشة ومستودع ومكاتب إدارية وسكن للموظفين للقطع رقم 405 ت الى 409 ت بالمخطط رقم 14 154 الصناعية الشمالية بالاحساء - الأنشطة التجارية - ورشة", 145000, 25, True, False),
    ]
    for index, (title_a, title_b, area, years, same_plot, auto_safe) in enumerate(pairs):
        a = record("alahsa-opportunities", str(index), title_a, owner="أمانة الأحساء",
            location="العيون", area=area, duration=years, deadline="2026-10-21")
        b = record("furas", f"01-26-{index}", title_b, owner="أمانة محافظة الأحساء",
            location="الاحساء الاحساء 173" if index == 3 else "العيون الصناعية",
            area=area, duration=years, deadline="2026-10-21",
            reference=f"01-26-{index}", city="الاحساء" if index == 3 else "العيون",
            district="الصناعية")
        features = compare_source_records(a, b)
        assert features["title_similarity"] >= .95
        assert features["owner_match"] and features["area_difference_percentage"] == 0
        assert features["duration_match"] and features["deadline_match"]
        assert features["plot_match"] is same_plot
        assert features["plan_match"] is True
        assert features["plot_conflict"] is False
        assert features["strong_composite_match"] is True
        assert features["auto_merge_safe"] is auto_safe

import json
from app.standardization import STANDARDIZATION_VERSION, canonical_identity, standardize_field, standardize_opportunity
from app.asset_facility_types import standardize_asset_facility_types
from app.database import SessionLocal
from app.models import AssetFacilityTypeAlias

assert STANDARDIZATION_VERSION == "16"
checks = {}
sector = standardize_field("sector", "healthcare")
assert sector["canonical_id"] == "sector:healthcare" and sector["mapping_status"] == "MAPPED"
checks["sector_alias"] = sector
activity = standardize_field("activity", "الأنشطة التجارية")
assert activity["canonical_id"] == "activity:commercial_activities" and activity["mapping_status"] == "MAPPED"
checks["activity_alias"] = activity
subactivity = standardize_field("sub_activity", "انشطة التجارة العامة")
assert subactivity["canonical_id"] == "sub_activity:general_trade" and subactivity["mapping_status"] == "MAPPED"
checks["sub_activity_alias"] = subactivity
missing_activity = standardize_field("activity", None)
assert missing_activity["canonical_id"] == "activity:missing" and missing_activity["mapping_status"] == "MISSING"
checks["missing_activity"] = missing_activity
unknown_activity = standardize_field("activity", "نشاط تجريبي غير مسجل")
assert unknown_activity["mapping_status"] == "UNMAPPED" and unknown_activity["raw"] == "نشاط تجريبي غير مسجل"
checks["unknown_activity_preserved_for_review"] = unknown_activity
type_result = standardize_field("opportunity_type", "TemporaryRental", source_key="furas")
assert type_result["canonical_id"] == "opportunity_type:temporary_rental" and type_result["mapping_status"] == "MAPPED"
checks["known_temporary_rental"] = type_result
unknown_type = standardize_field("opportunity_type", "NEW_TYPE", source_key="furas")
assert unknown_type["mapping_status"] == "REVIEW_REQUIRED" and unknown_type["raw"] == "NEW_TYPE"
checks["unknown_opportunity_type_review"] = unknown_type
lease = standardize_field("investment_model", "التأجير")
eomt = standardize_field("investment_model", "EOMT", source_key="ncp")
assert lease["canonical_id"] == "investment_model:lease" and eomt["canonical_id"] == "investment_model:eomt"
checks["investment_models"] = {"lease": lease, "eomt": eomt}
wrong_enum = standardize_opportunity({"activity": "PPP_PROJECT", "title_ar": "Fixture"}, source_key="ncp", source_record={"activity": "PPP_PROJECT"})
assert wrong_enum["values"]["activity"] is None
assert wrong_enum["metadata"]["fields"]["activity"]["mapping_status"] == "REVIEW_REQUIRED"
assert any(issue["code"] == "TECHNICAL_ENUM_EXCLUDED_FROM_ACTIVITY" for issue in wrong_enum["issues"])
checks["wrong_dimension_activity_enum"] = wrong_enum["metadata"]["fields"]["activity"]
asset_examples = {
 "العربات المتنقلة":"asset_facility_type:mobile_vending_site", "الحدائق":"asset_facility_type:public_park",
 "الشواطئ والواجهات":"asset_facility_type:waterfront", "الأراضي":"asset_facility_type:land",
 "الساحات الميادين":"asset_facility_type:public_square", "الطرق والأرصفة":"asset_facility_type:road_sidewalk",
 "المباني":"asset_facility_type:building", "أخرى":"asset_facility_type:other"}
with SessionLocal() as db:
    aliases = db.query(AssetFacilityTypeAlias).filter_by(source_key="furas", source_field="LOCATIONTYPE").all()
    assert len(aliases) >= 8
    for raw, expected in asset_examples.items():
        projected = standardize_asset_facility_types(db, "furas", {"attributes":{"LOCATIONTYPE":json.dumps([raw],ensure_ascii=False)}})
        assert [x["canonical_id"] for x in projected["assignments"]] == [expected], (raw,projected)
        assert not projected["unresolved"]
    multi = standardize_asset_facility_types(db, "furas", {"attributes":{"LOCATIONTYPE":json.dumps(["المباني","الساحات الميادين"],ensure_ascii=False)}})
    assert {x["canonical_id"] for x in multi["assignments"]} == {"asset_facility_type:building","asset_facility_type:public_square"}
    missing = standardize_asset_facility_types(db, "furas", {"attributes":{"LOCATIONTYPE":None}})
    assert not missing["assignments"] and not missing["unresolved"]
    unknown = standardize_asset_facility_types(db, "furas", {"attributes":{"LOCATIONTYPE":"نوع مستقبلي"}})
    assert not unknown["assignments"] and unknown["unresolved"][0]["raw_value"] == "نوع مستقبلي"
    wrong_source = standardize_asset_facility_types(db, "invest-saudi", {"activity":"برج مياه"})
    assert not wrong_source["assignments"] and not wrong_source["unresolved"]
    wrong_enum = standardize_asset_facility_types(db, "furas", {"attributes":{"LOCATIONTYPE":"PPP_PROJECT"}})
    assert not wrong_enum["assignments"] and wrong_enum["unresolved"][0]["raw_value"] == "PPP_PROJECT"
checks["asset_facility_examples"] = {"values_tested":list(asset_examples),"assignments":len(asset_examples),"multi_value_count":len(multi["assignments"]),"missing":missing,"unknown":unknown,"wrong_source_enum":wrong_source,"wrong_dimension_enum":wrong_enum}
print(json.dumps({"standardization_engine_version":STANDARDIZATION_VERSION,"future_rules_verified":True,"checks":checks},ensure_ascii=False,indent=2))

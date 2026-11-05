import json
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.asset_facility_types import (
    ASSET_FACILITY_TYPE_MISSING_ID,
    ASSET_FACILITY_TYPE_MISSING_LABEL,
    source_asset_type_candidates,
    standardize_asset_facility_types,
)
from app.entity_resolution import _source_facts
from app.models import AssetFacilityType, AssetFacilityTypeAlias, Base


def test_furas_locationtype_is_source_and_field_scoped_and_multivalued():
    raw = {"attributes": {"LOCATIONTYPE": json.dumps(["المباني", "الساحات الميادين"], ensure_ascii=False),
                           "SUBACTIVITYTYPE": "محلات تجارية"}}
    values, field = source_asset_type_candidates("furas", raw)
    assert field == "LOCATIONTYPE"
    assert values == ["المباني", "الساحات الميادين"]
    assert source_asset_type_candidates("invest-saudi", {"activity": "المباني"}) == ([], None)
    assert ASSET_FACILITY_TYPE_MISSING_LABEL == "غير محدد"


def test_known_alias_maps_unknown_stays_review_and_activity_is_not_asset_type():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine, tables=[AssetFacilityType.__table__, AssetFacilityTypeAlias.__table__])
    with Session(engine) as db:
        db.add(AssetFacilityType(canonical_id="asset_facility_type:building", label_ar="المباني", active=True))
        db.add(AssetFacilityType(canonical_id="asset_facility_type:other", label_ar="أخرى", active=True))
        db.add(AssetFacilityTypeAlias(source_key="furas", source_field="LOCATIONTYPE",
            source_value="المباني", canonical_id="asset_facility_type:building"))
        db.add(AssetFacilityTypeAlias(source_key="furas", source_field="LOCATIONTYPE",
            source_value="أخرى", canonical_id="asset_facility_type:other"))
        db.flush()
        mapped = standardize_asset_facility_types(db, "furas", {"attributes": {"LOCATIONTYPE": "\"المباني\""}})
        assert mapped["assignments"][0]["canonical_id"] == "asset_facility_type:building"
        assert mapped["unresolved"] == []
        other = standardize_asset_facility_types(db, "furas", {"attributes": {"LOCATIONTYPE": "\"أخرى\""}})
        assert other["assignments"][0]["canonical_id"] == "asset_facility_type:other"
        missing = standardize_asset_facility_types(db, "furas", {"attributes": {"LOCATIONTYPE": None}})
        assert missing["assignments"] == []
        assert "asset_facility_type:other" != ASSET_FACILITY_TYPE_MISSING_ID
        unknown = standardize_asset_facility_types(db, "furas", {"attributes": {"LOCATIONTYPE": "\"مرفق تجريبي\""}})
        assert unknown["assignments"] == []
        assert unknown["unresolved"][0]["raw_value"] == "مرفق تجريبي"
        wrong_dimension = standardize_asset_facility_types(db, "invest-saudi", {"activity": "برج مياه"})
        assert wrong_dimension["assignments"] == []
        assert wrong_dimension["unresolved"] == []


def test_entity_resolution_never_reuses_subactivity_as_asset_type():
    furas = SimpleNamespace(
        source_opportunity_id="furas-1", source_reference_number=None, source_title="عنوان",
        source_owner="بلدية", raw_location="الأحساء", raw_area=None, raw_dates={}, raw_status="",
        source_url="https://example.test", source=SimpleNamespace(source_key="furas"),
        raw_data_json={"attributes": {"LOCATIONTYPE": "\"المباني\"", "SUBACTIVITYTYPE": "محلات تجارية"}},
    )
    invest_saudi = SimpleNamespace(**{**furas.__dict__, "source": SimpleNamespace(source_key="invest-saudi"),
        "raw_data_json": {"activity": "برج مياه", "subActivity": "مبنى"}})
    assert _source_facts(furas)["asset_type"] == "المباني"
    assert _source_facts(invest_saudi)["asset_type"] == ""

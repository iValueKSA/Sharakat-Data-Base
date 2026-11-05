from __future__ import annotations
import asyncio, csv, io, os, json, logging, time, uuid
import hashlib
from urllib.parse import quote
from contextlib import asynccontextmanager
from datetime import datetime, timezone, date
from fastapi import FastAPI, Header, HTTPException, Query, Response, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field
from fastapi.responses import FileResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select, func, or_, and_, case, exists, text
from sqlalchemy.orm import selectinload
from .database import init_db, SessionLocal, engine
from .models import Source, Opportunity, SourceOpportunity, SourceObservation, OpportunityLocation, QualificationReview, ChangeHistory, SyncJob, SourceError, DuplicateCandidate, OpportunityConflict, FieldProvenance, SystemEvent, MergeAudit, LocationReview, TaxonomyMapping, SourceContentItem, SourceLimitation, ModonLocation, NcpProjectEvent, User, UserSession, AlertEvent, SystemSetting, AuditEvent, AssetFacilityType, OpportunityAssetFacilityType, SourceOpportunityDatasetMembership
from .service import seed_sources, sync_source, scheduler_loop
from .adapters import LOCATION_ACCEPTANCE_THRESHOLD
from .excel_export import build_opportunities_workbook, export_timestamp
from .merge import merge_candidate, undo_candidate
from .security import SESSION_COOKIE, SESSION_HOURS, allow_login_attempt, allow_rate, audit, hash_password, new_session, session_digest, user_for_session, utcnow, verify_password
from .filter_canonicalization import ACTIVITY_UNSPECIFIED_LABEL, MISSING_LABEL, SECTOR_UNSPECIFIED_LABEL, canonical_id, canonical_value, comparison_key, matching_values, option_labels, group_counts
from .standardization import OPPORTUNITY_TYPE_UNSPECIFIED_LABEL, INVESTMENT_MODEL_UNSPECIFIED_LABEL
from .geography import AL_AHSA_GOVERNORATE, EASTERN_REGION, canonical_geography_identity, geography_identity_by_id, resolve_master_geography
from .asset_facility_types import ASSET_FACILITY_TYPE_MISSING_ID, ASSET_FACILITY_TYPE_MISSING_LABEL
from .status_lifecycle import local_today
from .source_links import resolve_preferred_source_link, resolve_source_link
from .review_lifecycle import reevaluate_open_conflicts
from .data_quality import evaluate_data_quality, latest_data_quality_run, data_quality_history
from contextvars import ContextVar
from datetime import timedelta
from pathlib import Path

logger=logging.getLogger("app")
request_context: ContextVar[dict] = ContextVar("request_context", default={})
_request_count=0
_request_errors=0
_request_seconds=0.0

DATA_DIR=os.getenv("DATA_DIR","data")
PILOT_COHORT_PATH=Path(__file__).with_name("human_review_pilot_cohort.json")

def _load_human_review_pilot_cohort():
    try:
        payload=json.loads(PILOT_COHORT_PATH.read_text(encoding="utf-8"))
    except (OSError,ValueError) as exc:
        raise HTTPException(503,"تعذر تحميل عينة الطيار المجمدة.") from exc
    if not isinstance(payload,dict) or not isinstance(payload.get("cases"),list):
        raise HTTPException(503,"ملف عينة الطيار غير صالح.")
    return payload

def _raw_dimension_values(db, column, dimension: str):
    """Distinct stored labels for one Master dimension; source rows are not read or changed."""
    return list(db.scalars(select(column).where(Opportunity.merged_into_id.is_(None)).distinct()).all())

def _canonical_option_data(db, column, dimension: str):
    rows=db.execute(select(column,func.count(Opportunity.id)).where(Opportunity.merged_into_id.is_(None)).group_by(column)).all()
    raw_values=[value for value,_ in rows if value is not None and str(value).strip()]
    labels=option_labels(dimension,raw_values)
    count_by_id={};label_by_id={}
    for value,count in rows:
        identity=canonical_id(dimension,value);label=canonical_value(dimension,value)
        count_by_id[identity]=count_by_id.get(identity,0)+int(count);label_by_id[identity]=label
    counts={label_by_id[identity]:count for identity,count in count_by_id.items()}
    option_ids={label:identity for identity,label in label_by_id.items()}
    missing_label = (SECTOR_UNSPECIFIED_LABEL if dimension == "sector"
                     else ACTIVITY_UNSPECIFIED_LABEL if dimension == "activity"
                     else "غير محدد" if dimension in {"opportunity_type", "type", "investment_model", "owner", "opportunity_owner"}
                     else MISSING_LABEL)
    if counts.get(missing_label) and missing_label not in labels: labels.append(missing_label)
    return labels,counts,option_ids

def _canonical_filter_condition(db, column, dimension: str, selected: str):
    values=matching_values(dimension,selected,_raw_dimension_values(db,column,dimension))
    predicates=[]
    if any(value is None for value in values): predicates.append(column.is_(None))
    present=[value for value in values if value is not None]
    if present: predicates.append(column.in_(present))
    if len(predicates)==1: return predicates[0]
    if predicates: return or_(*predicates)
    return column.in_([])

def _sector_values_filter_condition(db, encoded_values: str):
    """Filter a presentation group by its explicit canonical sector members."""
    if len(encoded_values) > 4000:
        raise HTTPException(422,"قائمة القطاعات المجمعة طويلة جدًا")
    try:
        values=json.loads(encoded_values)
    except (TypeError,ValueError):
        raise HTTPException(422,"قائمة القطاعات المجمعة غير صالحة")
    if not isinstance(values,list) or not values or len(values)>32 or any(not isinstance(value,str) or not value.strip() for value in values):
        raise HTTPException(422,"قائمة القطاعات المجمعة غير صالحة")
    predicates=[_canonical_filter_condition(db,Opportunity.sector,"sector",value.strip()) for value in dict.fromkeys(values)]
    return or_(*predicates) if predicates else Opportunity.sector.in_([])

def _sector_values_display_labels(db, encoded_values: str):
    try:
        selected=json.loads(encoded_values)
    except (TypeError,ValueError):
        return []
    raw_values=_raw_dimension_values(db,Opportunity.sector,"sector")
    labels=[]
    for value in selected if isinstance(selected,list) else []:
        if not isinstance(value,str): continue
        for raw in matching_values("sector",value.strip(),raw_values):
            label=canonical_value("sector",raw)
            if label not in labels: labels.append(label)
    return labels


def _pending_location_reviews_by_master(db, master_ids=None):
    statement=(select(SourceOpportunity.master_opportunity_id,LocationReview.reason)
        .join(LocationReview,LocationReview.source_record_id==SourceOpportunity.id)
        .where(LocationReview.status=="PENDING",SourceOpportunity.master_opportunity_id.is_not(None),or_(
            LocationReview.reason.like("LOCATION_UNSPECIFIED:%"),
            LocationReview.reason.like("REGION_ONLY:%"),
            LocationReview.reason.like("COORDINATE_TEXT_CONFLICT:%"),
        )))
    if master_ids is not None:
        statement=statement.where(SourceOpportunity.master_opportunity_id.in_(master_ids or [-1]))
    pending={}
    for master_id,reason in db.execute(statement).all():
        pending.setdefault(master_id,reason or "")
    return pending


def _location_rows_for_hierarchy(db):
    rows=db.execute(select(Opportunity.id,Opportunity.city,Opportunity.district,Opportunity.location_confidence_score,Opportunity.manual_review_required)
        .where(Opportunity.merged_into_id.is_(None))).all()
    return rows,_pending_location_reviews_by_master(db,[row.id for row in rows])


def _source_location_values_by_master(db,master_ids=None):
    statement=(select(SourceOpportunity.master_opportunity_id,OpportunityLocation.location_name)
        .join(OpportunityLocation,OpportunityLocation.source_opportunity_id==SourceOpportunity.id)
        .where(SourceOpportunity.master_opportunity_id.is_not(None)))
    if master_ids is not None:
        statement=statement.where(SourceOpportunity.master_opportunity_id.in_(master_ids or [-1]))
    values={}
    for master_id,location_name in db.execute(statement).all():
        if location_name and location_name not in values.setdefault(master_id,[]):
            values[master_id].append(location_name)
    return values


def _location_identity_for_row(city, district):
    district_identity=canonical_geography_identity(district)
    if district_identity and district_identity["id"].startswith("al_ahsa_locality:"):
        return district_identity
    return canonical_geography_identity(city) or district_identity


def _location_filter_condition(db, selected):
    selected_geo=geography_identity_by_id(selected) if selected in {AL_AHSA_GOVERNORATE["id"],EASTERN_REGION["id"],"saudi_arabia"} or str(selected).startswith("al_ahsa_locality:") else canonical_geography_identity(selected)
    if not selected_geo:
        location_value=func.coalesce(func.nullif(Opportunity.district,""),func.nullif(Opportunity.city,""),"غير محدد")
        condition=_canonical_filter_condition(db,location_value,"location",selected)
        eligible=and_(Opportunity.location_confidence_score>=LOCATION_ACCEPTANCE_THRESHOLD,Opportunity.manual_review_required.is_(False),~Opportunity.id.in_(select(SourceOpportunity.master_opportunity_id).join(LocationReview,LocationReview.source_record_id==SourceOpportunity.id).where(LocationReview.status=="PENDING",SourceOpportunity.master_opportunity_id.is_not(None))))
        return and_(condition,eligible)

    rows,pending=_location_rows_for_hierarchy(db)
    source_locations=_source_location_values_by_master(db,[row.id for row in rows])
    selected_full=geography_identity_by_id(selected_geo["id"])
    if not selected_full:
        return Opportunity.id.in_([])
    matches=[]
    for row in rows:
        if row.id in pending or row.manual_review_required or float(row.location_confidence_score or 0)<LOCATION_ACCEPTANCE_THRESHOLD:
            continue
        identity=_location_identity_for_row(row.city,row.district)
        full=geography_identity_by_id(identity["id"]) if identity else None
        match=False
        if full:
            if selected_full.get("governorate_id"):
                match=full.get("governorate_id")==selected_full.get("governorate_id")
            elif selected_full.get("region_id") and selected_full.get("governorate_id") is None:
                match=full.get("region_id")==selected_full.get("region_id")
            elif selected_full.get("country_id") and selected_full.get("region_id") is None:
                match=full.get("country_id")==selected_full.get("country_id")
            else:
                match=identity["id"]==selected_geo["id"]
        if not match:
            for raw_location in source_locations.get(row.id,[]):
                source_identity=canonical_geography_identity(raw_location)
                source_full=geography_identity_by_id(source_identity["id"]) if source_identity else None
                if not source_full:
                    continue
                if selected_full.get("governorate_id"):
                    match=source_full.get("governorate_id")==selected_full.get("governorate_id")
                elif selected_full.get("region_id") and selected_full.get("governorate_id") is None:
                    match=source_full.get("region_id")==selected_full.get("region_id")
                elif selected_full.get("country_id") and selected_full.get("region_id") is None:
                    match=source_full.get("country_id")==selected_full.get("country_id")
                else:
                    match=source_identity["id"]==selected_geo["id"]
                if match:
                    break
        if match:
            matches.append(row.id)
    return Opportunity.id.in_(matches or [-1])


def _location_option_data(db):
    rows,pending=_location_rows_for_hierarchy(db)
    source_locations=_source_location_values_by_master(db,[row.id for row in rows])
    counts={};ids={};labels=set();hierarchy=[];governorate_masters=set();locality_masters={}
    for row in rows:
        if row.id in pending or row.manual_review_required or float(row.location_confidence_score or 0)<LOCATION_ACCEPTANCE_THRESHOLD:
            continue
        identity=_location_identity_for_row(row.city,row.district)
        full=geography_identity_by_id(identity["id"]) if identity else None
        if full and full.get("governorate_id"):
            governorate_masters.add(row.id)
            if full.get("locality_id"):
                label=identity["label"]
                labels.add(label);ids[label]=identity["id"];locality_masters.setdefault(label,set()).add(row.id)
        for raw_location in source_locations.get(row.id,[]):
            source_identity=canonical_geography_identity(raw_location)
            source_full=geography_identity_by_id(source_identity["id"]) if source_identity else None
            if source_full and source_full.get("governorate_id"):
                governorate_masters.add(row.id)
                if source_full.get("locality_id"):
                    label=source_identity["label"]
                    labels.add(label);ids[label]=source_identity["id"];locality_masters.setdefault(label,set()).add(row.id)
    counts.update({label:len(master_ids) for label,master_ids in locality_masters.items()})
    governorate_count=len(governorate_masters)
    parent_id=AL_AHSA_GOVERNORATE["id"];parent_label=AL_AHSA_GOVERNORATE["label"]
    counts[parent_label]=governorate_count;ids[parent_label]=parent_id;labels.add(parent_label)
    hierarchy.append({"id":"saudi_arabia","label":"المملكة العربية السعودية","parent_id":None,"level":"country"})
    hierarchy.append({"id":EASTERN_REGION["id"],"label":EASTERN_REGION["label"],"parent_id":"saudi_arabia","level":"region"})
    hierarchy.append({"id":parent_id,"label":parent_label,"parent_id":EASTERN_REGION["id"],"level":"governorate","count":governorate_count})
    for label in sorted(labels-{parent_label},key=comparison_key):
        identity=geography_identity_by_id(ids[label])
        if identity and identity.get("locality_id"):
            hierarchy.append({"id":identity["id"],"label":label,"parent_id":parent_id,"level":"locality","count":counts[label]})
    return sorted(labels,key=comparison_key),counts,ids,hierarchy


def _confirmed_location_master_ids(db):
    rows,pending=_location_rows_for_hierarchy(db)
    source_locations=_source_location_values_by_master(db,[row.id for row in rows])
    confirmed=[]
    for row in rows:
        if row.id in pending or row.manual_review_required or float(row.location_confidence_score or 0)<LOCATION_ACCEPTANCE_THRESHOLD:
            continue
        identity=_location_identity_for_row(row.city,row.district)
        full=geography_identity_by_id(identity["id"]) if identity else None
        source_in_governorate=any((identity:=canonical_geography_identity(place)) and (geography_identity_by_id(identity["id"]) or {}).get("governorate_id") for place in source_locations.get(row.id,[]))
        if (full and full.get("governorate_id")) or source_in_governorate:
            confirmed.append(row.id)
    return confirmed


def _opportunity_geography(db,o,pending=None,source_locations_by_master=None):
    pending=pending if pending is not None else _pending_location_reviews_by_master(db,[o.id])
    reason=pending.get(o.id)
    status=None
    if reason:
        status="REGION_ONLY" if reason.startswith("REGION_ONLY") else "LOCATION_UNSPECIFIED" if reason.startswith("LOCATION_UNSPECIFIED") else "LOCATION_REVIEW_REQUIRED"
    elif o.manual_review_required:
        status="LOCATION_REVIEW_REQUIRED";reason="الموقع محدد للمراجعة اليدوية في سجل الفرصة."
    elif float(o.location_confidence_score or 0)<LOCATION_ACCEPTANCE_THRESHOLD:
        status="LOCATION_REVIEW_REQUIRED";reason="درجة ثقة تحديد الموقع أقل من حد القبول الحالي."
    geo=resolve_master_geography(o.city,o.district,status=status,reason=reason)
    source_locations=(source_locations_by_master if source_locations_by_master is not None else _source_location_values_by_master(db,[o.id])).get(o.id,[])
    geo["source_locations"]=source_locations
    source_geographies=[]
    for raw_location in source_locations:
        identity=canonical_geography_identity(raw_location)
        full=geography_identity_by_id(identity["id"]) if identity else None
        if identity and full:
            source_geographies.append({"raw":raw_location,**identity,"country_id":full.get("country_id"),"country":full.get("country"),"region_id":full.get("region_id"),"region":full.get("region"),"governorate_id":full.get("governorate_id"),"governorate":full.get("governorate"),"locality_id":full.get("locality_id"),"locality":full.get("locality")})
    geo["source_geographies"]=source_geographies
    if (not reason and not o.manual_review_required and float(o.location_confidence_score or 0)>=LOCATION_ACCEPTANCE_THRESHOLD
            and not geo.get("confirmed") and any(item.get("governorate_id")==AL_AHSA_GOVERNORATE["id"] for item in source_geographies)):
        parent=geography_identity_by_id(AL_AHSA_GOVERNORATE["id"])
        geo.update({key:parent.get(key) for key in ("country_id","country","country_code","region_id","region","governorate_id","governorate")})
        geo["confirmed"]=True;geo["status"]="CONFIRMED";geo["reason"]="مصدر رسمي يذكر الأحساء ضمن مواقع الفرصة المتعددة."
        geo["multi_location_scope"]="MULTI_LOCATION"
    if geo["status"]=="REGION_ONLY":
        geo["status"]="LOCATION_REVIEW_REQUIRED";geo["confirmed"]=False
    geo["review_required"]=not geo["confirmed"]
    geo["status_ar"]={"CONFIRMED":"موقع مؤكد","LOCATION_UNSPECIFIED":"الموقع غير محدد","LOCATION_REVIEW_REQUIRED":"الموقع قيد المراجعة"}.get(geo["status"],"الموقع غير محدد")
    if geo["confirmed"]:
        geo["display_location"]=geo.get("locality") or canonical_value("location",o.city) or geo.get("governorate")
    else:
        geo["display_location"]="غير محدد" if geo["status"]=="LOCATION_UNSPECIFIED" else "قيد المراجعة"
    return geo


def _asset_facility_type_options(db):
    total = db.scalar(select(func.count(Opportunity.id)).where(Opportunity.merged_into_id.is_(None))) or 0
    rows = db.execute(
        select(AssetFacilityType.canonical_id, AssetFacilityType.label_ar, func.count(func.distinct(OpportunityAssetFacilityType.opportunity_id)))
        .join(OpportunityAssetFacilityType, OpportunityAssetFacilityType.canonical_id == AssetFacilityType.canonical_id)
        .join(Opportunity, Opportunity.id == OpportunityAssetFacilityType.opportunity_id)
        .where(AssetFacilityType.active.is_(True), Opportunity.merged_into_id.is_(None))
        .group_by(AssetFacilityType.canonical_id, AssetFacilityType.label_ar)
        .order_by(AssetFacilityType.label_ar)
    ).all()
    labels = [label for _, label, count in rows if count]
    counts = {label: int(count) for _, label, count in rows}
    ids = {label: canonical_id for canonical_id, label, _ in rows}
    assigned = db.scalar(select(func.count(func.distinct(OpportunityAssetFacilityType.opportunity_id))).join(Opportunity, Opportunity.id == OpportunityAssetFacilityType.opportunity_id).where(Opportunity.merged_into_id.is_(None))) or 0
    missing = max(0, int(total) - int(assigned))
    if missing:
        labels.append(ASSET_FACILITY_TYPE_MISSING_LABEL)
        counts[ASSET_FACILITY_TYPE_MISSING_LABEL] = missing
        ids[ASSET_FACILITY_TYPE_MISSING_LABEL] = ASSET_FACILITY_TYPE_MISSING_ID
    return labels, counts, ids


def _asset_facility_type_filter_condition(db, selected: str):
    rows = db.execute(select(AssetFacilityType.canonical_id, AssetFacilityType.label_ar).where(AssetFacilityType.active.is_(True))).all()
    by_id = {identifier: label for identifier, label in rows}
    by_label = {label: identifier for identifier, label in rows}
    if selected in {ASSET_FACILITY_TYPE_MISSING_ID, ASSET_FACILITY_TYPE_MISSING_LABEL}:
        return ~exists(select(1).where(OpportunityAssetFacilityType.opportunity_id == Opportunity.id))
    canonical_id = selected if selected in by_id else by_label.get(selected)
    if not canonical_id:
        return Opportunity.id.in_([])
    return exists(select(1).where(OpportunityAssetFacilityType.opportunity_id == Opportunity.id, OpportunityAssetFacilityType.canonical_id == canonical_id))


_TECHNICAL_TAXONOMY_HISTORY_VALUES = {
    comparison_key(value) for value in (
        "PPP_PROJECT", "PPP_PROJECT_ANNOUNCEMENT", "LEASE_OPPORTUNITY",
        "COMMERCIAL_FACILITY_OPPORTUNITY", "INVESTMENT_OPPORTUNITY",
        "GENERAL_ANNOUNCEMENT", "INVESTMENT_ANNOUNCEMENT",
        "INVESTMENT_SECTOR_INFORMATION", "STRATEGIC_PROJECT",
        "WASTE_SECTOR_INVESTMENT", "TemporaryRental", "TempRental",
    )
}


def _business_history_value(value):
    """Avoid exposing source enum tokens from legacy audit values in business UI."""
    if value is not None and comparison_key(value) in _TECHNICAL_TAXONOMY_HISTORY_VALUES:
        return "قيمة غير معتمدة"
    return value

ACTIVE_STATUSES = ["متاحة", "Announced", "ANNOUNCED", "PUBLISHED", "AVAILABLE", "ACTIVE", "منشورة"]
ACTIVE_EXCLUDED_STATUSES = ["ملغاة", "ملغي", "منتهية", "منتهي", "تم الترسية", "أزيلت من المصدر", "REMOVED_FROM_SOURCE", "EXPIRED", "CANCELLED", "AWARDED", "DELETED_FROM_SOURCE", "حالة غير معروفة", "غير محددة", "قيد مراجعة الحالة"]
HISTORICAL_STATUSES = ["منتهية", "منتهي", "ملغاة", "ملغي", "تمت الترسية", "تم الترسية", "أزيلت من المصدر", "REMOVED_FROM_SOURCE", "EXPIRED", "CANCELLED", "AWARDED", "DELETED_FROM_SOURCE"]


def _opportunity_filter_conditions(db, *, sector="", activity="", sub_activity="", status="", owner="", source="", location="", opportunity_type="", investment_model="", asset_facility_type="", subsector="", lifecycle=""):
    conditions=[Opportunity.merged_into_id.is_(None)]
    if sector: conditions.append(_canonical_filter_condition(db,Opportunity.sector,"sector",sector))
    if activity: conditions.append(_canonical_filter_condition(db,Opportunity.activity,"activity",activity))
    if sub_activity: conditions.append(_canonical_filter_condition(db,Opportunity.sub_activity,"sub_activity",sub_activity))
    if status: conditions.append(_canonical_filter_condition(db,Opportunity.status,"status",status))
    if source:
        conditions.append(Opportunity.id.in_(select(SourceOpportunity.master_opportunity_id).join(Source,Source.id==SourceOpportunity.source_id).where(Source.source_key==source,SourceOpportunity.master_opportunity_id.is_not(None))))
    if owner: conditions.append(_canonical_filter_condition(db,Opportunity.opportunity_owner,"owner",owner))
    if subsector: conditions.append(_canonical_filter_condition(db,Opportunity.subsector,"subsector",subsector))
    if location:
        conditions.append(_location_filter_condition(db,location))
    if opportunity_type: conditions.append(_canonical_filter_condition(db,Opportunity.opportunity_type,"opportunity_type",opportunity_type))
    if investment_model: conditions.append(_canonical_filter_condition(db,Opportunity.investment_model,"investment_model",investment_model))
    if asset_facility_type: conditions.append(_asset_facility_type_filter_condition(db,asset_facility_type))
    if lifecycle == "active": conditions.append(Opportunity.status.in_(ACTIVE_STATUSES))
    elif lifecycle == "historical": conditions.append(Opportunity.status.in_(HISTORICAL_STATUSES))
    elif lifecycle: raise HTTPException(422,"نطاق الحالة غير مدعوم")
    return conditions


def _period_start(period: str):
    if period not in {"", "all", "30d", "90d", "365d"}:
        raise HTTPException(422,"الفترة الزمنية غير مدعومة")
    return {"30d":datetime.now(timezone.utc)-timedelta(days=30),"90d":datetime.now(timezone.utc)-timedelta(days=90),"365d":datetime.now(timezone.utc)-timedelta(days=365)}.get(period)

def _geojson_contains(geometry: dict, longitude: float, latitude: float) -> bool:
    """Return whether a WGS84 point falls inside a GeoJSON Polygon or MultiPolygon."""
    if not isinstance(geometry, dict): return False
    polygons = [geometry.get("coordinates")] if geometry.get("type") == "Polygon" else geometry.get("coordinates", []) if geometry.get("type") == "MultiPolygon" else []
    def in_ring(ring):
        inside = False
        if not isinstance(ring, list) or len(ring) < 4: return False
        previous = ring[-1]
        for current in ring:
            try: x1, y1 = float(previous[0]), float(previous[1]); x2, y2 = float(current[0]), float(current[1])
            except (TypeError, ValueError, IndexError): previous = current; continue
            if ((y1 > latitude) != (y2 > latitude)) and longitude < (x2-x1)*(latitude-y1)/(y2-y1)+x1: inside = not inside
            previous = current
        return inside
    for polygon in polygons:
        if not polygon or not in_ring(polygon[0]): continue
        if not any(in_ring(hole) for hole in polygon[1:]): return True
    return False

def _alahsa_boundary_geometry():
    path=os.path.join(os.path.dirname(__file__),"static","geo","alahsa-governorate.geojson")
    try:
        with open(path,encoding="utf-8") as boundary_file: collection=json.load(boundary_file)
        return (collection.get("features") or [{}])[0].get("geometry") or {}
    except (OSError,ValueError,AttributeError):
        logger.exception("Unable to load the local Al-Ahsa boundary")
        return {}

def validate_forwarded_allow_ips(value: str) -> str:
    trusted=[item.strip() for item in value.split(",") if item.strip()]
    if not trusted or "*" in trusted:
        raise RuntimeError("Staging and production require explicit trusted proxy IPs or CIDRs in FORWARDED_ALLOW_IPS")
    return ",".join(trusted)

def spreadsheet_safe(value):
    if isinstance(value,str) and value.lstrip(" \t\r\n").startswith(("=","+","-","@")):
        return "'"+value
    return value
@asynccontextmanager
async def lifespan(app:FastAPI):
    environment=os.getenv("ENVIRONMENT",os.getenv("ENV","development")).lower()
    production=environment=="production"
    protected=environment in ("production","staging")
    database_url=os.getenv("DATABASE_URL","")
    if protected and (not database_url.startswith(("postgresql://","postgresql+psycopg://")) or "sqlite" in database_url.lower()):
        raise RuntimeError("Staging and production require PostgreSQL via DATABASE_URL")
    if protected and not os.getenv("SECRET_KEY"):
        raise RuntimeError("Staging and production require an externally supplied SECRET_KEY")
    if protected and not os.getenv("REDIS_URL"):
        raise RuntimeError("Staging and production require Redis for jobs and distributed locks")
    if protected:
        validate_forwarded_allow_ips(os.getenv("FORWARDED_ALLOW_IPS", ""))
    if protected and not os.getenv("PUBLIC_BASE_URL","").startswith("https://"):
        raise RuntimeError("Staging and production PUBLIC_BASE_URL must use HTTPS")
    if protected and (not os.getenv("CORS_ORIGINS") or "*" in os.getenv("CORS_ORIGINS","")):
        raise RuntimeError("Staging and production CORS_ORIGINS must contain explicit origins")
    if protected and os.getenv("BOOTSTRAP_ADMIN_PASSWORD") and len(os.getenv("BOOTSTRAP_ADMIN_PASSWORD",""))<12:
        raise RuntimeError("Initial administrator password must contain at least 12 characters")
    if not protected:init_db()
    with SessionLocal() as db: seed_sources(db)
    task=None
    if not protected and os.getenv("SYNC_ON_STARTUP","false").lower()=="true": task=asyncio.create_task(scheduler_loop())
    bootstrap_password=os.getenv("BOOTSTRAP_ADMIN_PASSWORD")
    bootstrap_email=os.getenv("BOOTSTRAP_ADMIN_EMAIL")
    if bootstrap_password and bootstrap_email:
        with SessionLocal() as db:
            if not db.scalar(select(User).where(User.email==bootstrap_email.lower())):
                db.add(User(email=bootstrap_email.lower(),display_name="Administrator",role="admin",password_hash=hash_password(bootstrap_password),is_active=True,created_at=utcnow()))
                db.commit()
    yield
    if task: task.cancel()

app=FastAPI(title="Al-Ahsa Investment Opportunities Intelligence Platform",version="0.1.0",lifespan=lifespan)
app.mount("/static",StaticFiles(directory="app/static"),name="static")
allowed_origins=[x.strip() for x in os.getenv("CORS_ORIGINS","").split(",") if x.strip()]
if allowed_origins: app.add_middleware(CORSMiddleware,allow_origins=allowed_origins,allow_credentials=True,allow_methods=["GET","POST","PATCH","PUT","DELETE"],allow_headers=["Content-Type","X-Request-ID"])

@app.exception_handler(Exception)
async def safe_unhandled_error(request:Request,exc:Exception):
    logger.exception("Unhandled API error",extra={"request_id":request_context.get().get("correlation_id"),"path":request.url.path})
    protected=os.getenv("ENVIRONMENT",os.getenv("ENV","development")).lower() in ("production","staging")
    detail="Internal server error" if protected else str(exc)
    return JSONResponse({"detail":detail,"request_id":request_context.get().get("correlation_id")},status_code=500)

@app.middleware("http")
async def security_and_correlation(request:Request,call_next):
    global _request_count,_request_errors,_request_seconds
    correlation_id=request.headers.get("X-Request-ID") or str(uuid.uuid4())
    identity=user_for_session(request.cookies.get(SESSION_COOKIE))
    context_token=request_context.set({"correlation_id":correlation_id,"user":identity,"path":request.url.path,"method":request.method})
    started=time.perf_counter();status=500
    try:
        protected=request.url.path.startswith("/api/admin/") and request.method in ("POST","PATCH","PUT","DELETE") or request.url.path.startswith("/api/export.")
        if protected:
            address=request.client.host if request.client else "unknown"
            if not allow_rate(f"{address}:{request.url.path}",20 if request.url.path.startswith("/api/export.") else 40,60):
                status=429
                return Response(content='{"detail":"Rate limit exceeded"}',media_type="application/json",status_code=429)
        response=await call_next(request);status=response.status_code
        response.headers["X-Request-ID"]=correlation_id
        response.headers["X-Content-Type-Options"]="nosniff"
        response.headers["Referrer-Policy"]="strict-origin-when-cross-origin"
        response.headers["X-Frame-Options"]="DENY"
        response.headers["Content-Security-Policy"]="default-src 'self'; img-src 'self' data: https:; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
        if os.getenv("ENVIRONMENT",os.getenv("ENV","development")).lower() in ("production","staging"): response.headers["Strict-Transport-Security"]="max-age=31536000; includeSubDomains"
        if request.url.path.startswith("/api/admin/") and request.method in ("POST","PATCH","PUT","DELETE") and status<400:
            try:
                with SessionLocal() as db:
                    user_id=(identity or {}).get("id")
                    audit(db,"ADMIN_ACTION",user_id,"http",request.url.path,after={"method":request.method,"status":status},metadata={"request_id":correlation_id,"ip":request.client.host if request.client else None})
                    db.commit()
            except Exception:
                logger.exception("Failed to persist administrative audit event")
        return response
    finally:
        elapsed=time.perf_counter()-started;_request_count+=1;_request_seconds+=elapsed
        if status>=400:_request_errors+=1
        logger.info(json.dumps({"timestamp":datetime.now(timezone.utc).isoformat(),"level":"INFO","service":"api","request_id":correlation_id,"user_id":(identity or {}).get("id"),"event":"http_request","method":request.method,"path":request.url.path,"status":status,"duration_seconds":round(elapsed,4)},ensure_ascii=False))
        request_context.reset(context_token)

def admin_auth(token:str|None):
    identity=request_context.get().get("user")
    protected=os.getenv("ENVIRONMENT",os.getenv("ENV","development")).lower() in ("production","staging")
    path=request_context.get().get("path","")
    if identity:
        if identity.get("role")=="admin": return identity
        review_path=(path.startswith("/api/admin/review-queue") or path.startswith("/api/admin/review-workbench")
                     or path=="/api/admin/validation-report"
                     or path in ("/api/admin/location-reviews","/api/admin/conflicts","/api/admin/duplicates")
                     or any(part in path for part in ("/location-reviews/","/conflicts/","/duplicates/")))
        if identity.get("role")=="analyst" and review_path: return identity
        if identity.get("role")=="viewer" and request_context.get().get("method")=="GET" and review_path: return identity
        raise HTTPException(403,"Insufficient permissions")
    if protected: raise HTTPException(401,"Authentication required")
    expected=os.getenv("ADMIN_TOKEN","")
    if expected and token!=expected: raise HTTPException(401,"رمز الإدارة غير صحيح")

def review_write_auth(token:str|None):
    """Require an authenticated reviewer or a configured admin token for decisions."""
    identity=admin_auth(token)
    if identity:
        if identity.get("role") not in ("admin","analyst"):
            raise HTTPException(403,"Insufficient permissions")
        return identity
    expected=os.getenv("ADMIN_TOKEN","")
    if not expected or token!=expected:
        raise HTTPException(401,"Authentication required for review decisions")
    return {"id":None,"role":"admin_token","display_name":"Configured admin token"}

def _review_audit(db, *, decision:str, entity_type:str, entity_id:int, note:str,
                  before:dict, after:dict, evidence:dict, identity:dict|None):
    actor=identity or {}
    audit_evidence=dict(evidence or {})
    source_record_ids=set(audit_evidence.get("source_record_ids") or [])
    if audit_evidence.get("source_record_id") is not None:source_record_ids.add(audit_evidence["source_record_id"])
    snapshots=[]
    for source_record_id in sorted(source_record_ids,key=lambda value:str(value)):
        try:source_record=db.get(SourceOpportunity,int(source_record_id))
        except (TypeError,ValueError):source_record=None
        if source_record:
            snapshots.append({"source_record_id":source_record.id,"content_hash":source_record.content_hash,
                "last_seen_at":dt(source_record.last_seen_at)})
    if snapshots:audit_evidence["source_snapshots"]=snapshots
    audit(db, f"REVIEW_{decision}", user_id=actor.get("id"), entity_type=entity_type,
          entity_id=str(entity_id), before=before,
          after={**after,"decision":decision,"reason":note,"evidence":audit_evidence},
          metadata={"actor":actor.get("display_name") or actor.get("role") or "configured_admin_token",
                    "actor_role":actor.get("role") or "admin_token",
                    "decision_kind":"HUMAN",
                    "request_id":request_context.get().get("correlation_id"),
                    "review_audit_version":"2"})

def _accept_inference_review(db, conflict:OpportunityConflict, master:Opportunity,
                             payload:"ReviewDecisionPayload", identity:dict|None):
    """Resolve a sector review only after a traceable medium inference was applied."""
    if conflict.field_name!="sector" or conflict.conflict_type!="TAXONOMY_CONFLICT":
        raise HTTPException(409,"لا يمكن قبول استدلال قطاعي لهذه المراجعة")
    if canonical_id("sector",master.sector)=="sector:unspecified":
        raise HTTPException(409,"لا يوجد قطاع مستنتج معتمد مرتبط بهذه المراجعة")
    events=db.scalars(select(SystemEvent).where(
        SystemEvent.event_type=="SECTOR_CONTROLLED_RELAXATION_APPLIED"
    ).order_by(SystemEvent.id.desc())).all()
    provenance=next((item for event in events for item in ((event.payload or {}).get("classifications") or [])
                     if item.get("master_id")==master.id and item.get("sector")==master.sector
                     and item.get("classification_origin")=="INFERRED_RULE_MEDIUM"
                     and item.get("rule_key") and item.get("positive_evidence")),None)
    if not provenance:
        raise HTTPException(409,"لا يوجد سجل استدلال متوسط الثقة موثق لهذه الفرصة")
    event=next(event for event in events if provenance in ((event.payload or {}).get("classifications") or []))
    before={"status":conflict.status,"master_id":master.id,"field":"sector","value":conflict.selected_value}
    conflict.status="RESOLVED_INFERENCE"
    db.flush()
    _review_audit(db,decision="SECTOR_INFERENCE_ACCEPTED",entity_type="opportunity_conflict",
        entity_id=conflict.id,note=payload.note.strip(),before=before,
        after={"status":conflict.status,"master_id":master.id,"field":"sector","value":master.sector},
        evidence={"system_event_id":event.id,"engine_version":provenance.get("engine_version"),
            "rule_key":provenance.get("rule_key"),"confidence":provenance.get("confidence"),
            "positive_evidence":provenance.get("positive_evidence"),"source_record_id":conflict.source_record_id},
        identity=identity)
    return {"ok":True,"status":conflict.status,"sector":master.sector}

class LoginPayload(BaseModel):
    model_config=ConfigDict(extra="forbid")
    email:str=Field(min_length=3,max_length=255)
    password:str=Field(min_length=1,max_length=256)

class ReviewDecisionPayload(BaseModel):
    model_config=ConfigDict(extra="forbid")
    note:str=Field(min_length=8,max_length=2000)
    version_token:str|None=Field(default=None,min_length=64,max_length=64)
    recommendation_override_reason:str|None=Field(default=None,max_length=300)
    recommendation_version:str|None=Field(default=None,min_length=64,max_length=64)
    analyst_note:str|None=Field(default=None,max_length=1800)

class ReviewReopenPayload(BaseModel):
    model_config=ConfigDict(extra="forbid")
    reason:str=Field(min_length=3,max_length=100)
    note:str|None=Field(default=None,max_length=1800)
    version_token:str=Field(min_length=64,max_length=64)

class ReviewBatchItem(BaseModel):
    model_config=ConfigDict(extra="forbid")
    domain:str=Field(pattern="^(field_conflict|taxonomy_conflict|duplicate|location|qualification)$")
    review_id:int=Field(gt=0)
    version_token:str=Field(min_length=64,max_length=64)
    recommendation_version:str|None=Field(default=None,min_length=64,max_length=64)

class ReviewBatchPayload(BaseModel):
    model_config=ConfigDict(extra="forbid")
    items:list[ReviewBatchItem]=Field(min_length=2,max_length=100)
    action:str=Field(pattern="^(keep|use_source|merge|reject|accept)$")
    reason:str=Field(min_length=8,max_length=300)
    batch_operation_id:str=Field(min_length=16,max_length=80)
    batch_signature:str|None=Field(default=None,min_length=64,max_length=64)
    override_reason:str|None=Field(default=None,max_length=300)
    confirm:bool=False

class HumanReviewPilotEventPayload(BaseModel):
    model_config=ConfigDict(extra="forbid")
    pilot_id:str=Field(min_length=1,max_length=80)
    event_kind:str=Field(pattern="^(PILOT_STARTED|PHASE_A_REVIEWED|CASE_OUTCOME|CASE_REOPENED)$")
    review_id_key:str|None=Field(default=None,max_length=120)
    phase:str|None=Field(default=None,pattern="^(A|B)$")
    outcome:str|None=Field(default=None,pattern="^(RESOLVED|KEPT_OPEN|SOURCE_RECHECK_REQUIRED|REOPENED_AFTER_DECISION)$")
    feedback:dict|None=None
    metrics:dict|None=None
    reason:str|None=Field(default=None,max_length=1000)

class UserCreatePayload(BaseModel):
    model_config=ConfigDict(extra="forbid")
    email:str=Field(min_length=5,max_length=255)
    display_name:str=Field(min_length=1,max_length=200)
    role:str=Field(pattern="^(admin|analyst|viewer)$")
    password:str=Field(min_length=12,max_length=256)

@app.get("/api/admin/users")
def list_users(x_admin_token:str|None=Header(default=None)):
    admin_auth(x_admin_token)
    with SessionLocal() as db:
        return [{"id":u.id,"email":u.email,"display_name":u.display_name,"role":u.role,"is_active":u.is_active,"last_login_at":dt(u.last_login_at)} for u in db.scalars(select(User).order_by(User.email)).all()]

@app.post("/api/admin/users")
def create_user(payload:UserCreatePayload,x_admin_token:str|None=Header(default=None)):
    identity=admin_auth(x_admin_token)
    with SessionLocal() as db:
        email=payload.email.strip().lower()
        if db.scalar(select(User.id).where(User.email==email)):raise HTTPException(409,"User already exists")
        user=User(email=email,display_name=payload.display_name.strip(),role=payload.role,password_hash=hash_password(payload.password),is_active=True,created_at=utcnow())
        db.add(user);db.flush();audit(db,"USER_CREATED",(identity or {}).get("id"),"user",str(user.id),after={"email":email,"role":payload.role});db.commit()
        return {"id":user.id,"email":user.email,"role":user.role}

@app.post("/api/admin/users/{user_id}/disable")
def disable_user(user_id:int,confirm:bool=Query(False),x_admin_token:str|None=Header(default=None)):
    identity=admin_auth(x_admin_token)
    with SessionLocal() as db:
        user=db.get(User,user_id)
        if not user:raise HTTPException(404,"User not found")
        if not confirm:raise HTTPException(409,"Explicit confirmation is required")
        if user.id==(identity or {}).get("id"):raise HTTPException(409,"Cannot disable the active account")
        user.is_active=False
        db.query(UserSession).filter(UserSession.user_id==user.id).delete(synchronize_session=False)
        audit(db,"USER_DISABLED",(identity or {}).get("id"),"user",str(user.id),before={"is_active":True},after={"is_active":False});db.commit()
        return {"ok":True,"is_active":False}

@app.post("/api/auth/login")
def login(payload:LoginPayload,request:Request,response:Response):
    address=request.client.host if request.client else "unknown"
    if not allow_login_attempt(f"{address}:{payload.email.lower()}"): raise HTTPException(429,"Too many login attempts")
    with SessionLocal() as db:
        user=db.scalar(select(User).where(User.email==payload.email.lower()))
        now=utcnow()
        locked_until=user.locked_until if user else None
        if locked_until and locked_until.tzinfo is None:locked_until=locked_until.replace(tzinfo=timezone.utc)
        if not user or not user.is_active or (locked_until and locked_until>now) or not verify_password(payload.password,user.password_hash):
            if user:
                user.failed_login_count=(user.failed_login_count or 0)+1
                if user.failed_login_count>=10:user.locked_until=now+timedelta(minutes=15)
                audit(db,"LOGIN_FAILED",user.id,"user",str(user.id),metadata={"request_id":request_context.get().get("correlation_id"),"ip":address})
                db.commit()
            raise HTTPException(401,"Invalid credentials")
        user.failed_login_count=0;user.locked_until=None;user.last_login_at=now
        session_token=new_session(db,user)
        audit(db,"LOGIN",user.id,"user",str(user.id),metadata={"request_id":request_context.get().get("correlation_id"),"ip":address})
        db.commit()
        response.set_cookie(SESSION_COOKIE,session_token,httponly=True,secure=os.getenv("ENVIRONMENT",os.getenv("ENV","development")).lower() in ("production","staging"),samesite="lax",max_age=SESSION_HOURS*3600,path="/")
        return {"user":{"id":user.id,"email":user.email,"display_name":user.display_name,"role":user.role}}

@app.post("/api/auth/logout")
def logout(request:Request,response:Response):
    value=request.cookies.get(SESSION_COOKIE)
    if value:
        with SessionLocal() as db:
            session=db.scalar(select(UserSession).where(UserSession.token_hash==session_digest(value)))
            if session:
                user_id=session.user_id;db.delete(session);audit(db,"LOGOUT",user_id,"user",str(user_id),metadata={"request_id":request_context.get().get("correlation_id")});db.commit()
    response.delete_cookie(SESSION_COOKIE,path="/")
    return {"ok":True}

@app.get("/api/auth/me")
def auth_me():
    identity=request_context.get().get("user")
    if not identity:raise HTTPException(401,"Authentication required")
    return {"user":identity}

@app.get("/")
def home(): return FileResponse("app/static/index.html")

@app.get("/api/health")
def health(): return {"status":"ok","time":datetime.now(timezone.utc).isoformat()}

@app.get("/health/live")
@app.get("/health")
def health_live(): return {"status":"ok","service":"api"}

@app.get("/health/ready")
def health_ready():
    checks={"database":"ok","redis":"not_configured","worker":"not_configured"}
    try:
        with SessionLocal() as db: db.execute(select(1))
    except Exception: checks["database"]="error"
    if os.getenv("REDIS_URL"):
        try:
            import redis
            client=redis.Redis.from_url(os.environ["REDIS_URL"],socket_connect_timeout=2,socket_timeout=2)
            client.ping()
            checks["redis"]="ok"
            checks["worker"]="ok" if next(client.scan_iter(match="worker:heartbeat:*",count=1),None) else "error"
        except Exception: checks["redis"]="error"
    ready=checks["database"]=="ok" and checks["redis"]!="error" and checks["worker"] not in ("error",)
    return Response(content=json.dumps({"status":"ready" if ready else "not_ready","checks":checks}),media_type="application/json",status_code=200 if ready else 503)

@app.get("/metrics")
def metrics():
    lines=["# HELP api_requests_total Requests served by this API process.","# TYPE api_requests_total counter",f"api_requests_total {_request_count}","# HELP api_errors_total Error responses served by this API process.","# TYPE api_errors_total counter",f"api_errors_total {_request_errors}","# HELP api_request_duration_seconds_sum Total request duration in seconds.","# TYPE api_request_duration_seconds_sum counter",f"api_request_duration_seconds_sum {_request_seconds:.6f}"]
    return Response("\n".join(lines)+"\n",media_type="text/plain; version=0.0.4")

@app.get("/api/admin/source-health")
def source_health(x_admin_token:str|None=Header(default=None)):
    admin_auth(x_admin_token)
    with SessionLocal() as db:
        return [{"key":s.source_key,"health":s.technical_health,"coverage":s.coverage_status,"last_attempt":dt(s.last_attempted_sync),"last_success":dt(s.last_successful_sync),"enabled":s.enabled} for s in db.scalars(select(Source).order_by(Source.priority)).all()]

@app.get("/api/admin/data-quality/latest")
def data_quality_latest(x_admin_token:str|None=Header(default=None)):
    admin_auth(x_admin_token)
    with SessionLocal() as db:
        return latest_data_quality_run(db) or {"status":"NOT_RUN","counts":{"pass":0,"warning":0,"fail":0},"gates":[]}

@app.get("/api/admin/data-quality/history")
def data_quality_runs(x_admin_token:str|None=Header(default=None),limit:int=Query(30,ge=1,le=100)):
    admin_auth(x_admin_token)
    with SessionLocal() as db:
        return data_quality_history(db,limit)

@app.post("/api/admin/data-quality/run")
def run_data_quality_now(scope:str="full",x_admin_token:str|None=Header(default=None)):
    admin_auth(x_admin_token)
    if scope not in {"fast","full","weekly"}: raise HTTPException(422,"Unsupported DQ scope")
    with SessionLocal() as db:
        result=evaluate_data_quality(db,scope=scope,trigger="admin_manual",persist=True)
        db.commit()
        return result

@app.get("/api/admin/system-status")
def system_status(x_admin_token:str|None=Header(default=None)):
    admin_auth(x_admin_token)
    result={"api":"ok","database":"ok","redis":"not_configured","workers":"unknown","scheduler":"unknown","queue_depth":None,"database_size_bytes":None,"raw_observations":0,"sync_jobs":0,"attachments_size_bytes":0,"pool":engine.pool.status()}
    with SessionLocal() as db:
        result["raw_observations"]=db.scalar(select(func.count()).select_from(__import__("app.models",fromlist=["SourceObservation"]).SourceObservation)) or 0
        result["sync_jobs"]=db.scalar(select(func.count()).select_from(SyncJob)) or 0
        if engine.dialect.name=="postgresql":
            result["database_size_bytes"]=db.scalar(select(func.pg_database_size(func.current_database())))
    if os.getenv("REDIS_URL"):
        try:
            import redis
            client=redis.Redis.from_url(os.environ["REDIS_URL"],socket_connect_timeout=2,socket_timeout=2)
            result["redis"]="ok";result["queue_depth"]=sum(client.llen(f"{name}") for name in ("source_sync","maintenance","exports","notifications","document_processing"))
            last_tick=client.get("scheduler:last_tick")
            result["scheduler"]="ok" if last_tick else "unknown"
            result["workers"]="ok" if next(client.scan_iter(match="worker:heartbeat:*",count=1),None) else "stale"
        except Exception:result["redis"]="error"
    backups=os.getenv("BACKUP_DIR","/backups")
    attachment_dir=__import__("pathlib").Path(os.getenv("ATTACHMENT_DIR","data/attachments"))
    if attachment_dir.exists():
        try:result["attachments_size_bytes"]=sum(item.stat().st_size for item in attachment_dir.rglob("*") if item.is_file())
        except OSError:result["attachments_size_bytes"]=None
    try:
        records=sorted(__import__("pathlib").Path(backups).glob("*.json"),key=lambda p:p.stat().st_mtime,reverse=True)
        result["last_backup"]=json.loads(records[0].read_text(encoding="utf-8")) if records else None
    except Exception:result["last_backup"]=None
    return result

@app.get("/api/admin/schedules")
def schedules(x_admin_token:str|None=Header(default=None)):
    admin_auth(x_admin_token)
    with SessionLocal() as db:
        result=[];now=datetime.now(timezone.utc)
        for source in db.scalars(select(Source).order_by(Source.priority)).all():
            interval=max(15,source.polling_frequency_minutes or 60)
            latest=db.scalar(select(SyncJob).where(SyncJob.source_id==source.id).order_by(SyncJob.id.desc()).limit(1))
            success=source.last_successful_sync
            next_run=(source.last_attempted_sync or now)+timedelta(minutes=interval)
            stale=bool(success and (now-success).total_seconds()>2*interval*60)
            result.append({"source_key":source.source_key,"enabled":source.enabled,"interval_minutes":interval,"last_run":dt(source.last_attempted_sync),"last_success":dt(success),"next_run":dt(next_run),"current_job":latest.id if latest and latest.job_state in ("QUEUED","RUNNING","RETRYING") else None,"last_job_state":latest.job_state if latest else None,"health":"STALE" if stale else source.technical_health})
        paused=db.scalar(select(SystemSetting).where(SystemSetting.key=="pause_all_scheduled_syncs"))
        maintenance=db.scalar(select(SystemSetting).where(SystemSetting.key=="maintenance_mode"))
        return {"paused":bool(paused and paused.value=="true"),"maintenance_mode":bool(maintenance and maintenance.value=="true"),"sources":result}

def set_system_setting(db,key,value):
    setting=db.scalar(select(SystemSetting).where(SystemSetting.key==key))
    if setting is None:db.add(SystemSetting(key=key,value=value))
    else:setting.value=value

@app.post("/api/admin/operations/{action}")
def operational_control(action:str,x_admin_token:str|None=Header(default=None)):
    admin_auth(x_admin_token)
    values={"pause-schedules":("pause_all_scheduled_syncs","true"),"resume-schedules":("pause_all_scheduled_syncs","false"),"maintenance-on":("maintenance_mode","true"),"maintenance-off":("maintenance_mode","false")}
    if action not in values:raise HTTPException(400,"Unsupported action")
    with SessionLocal() as db:
        key,value=values[action];before=db.scalar(select(SystemSetting).where(SystemSetting.key==key));old=before.value if before else None
        set_system_setting(db,key,value);audit(db,action.upper().replace("-","_"),entity_type="system_setting",entity_id=key,before={"value":old},after={"value":value},metadata={"request_id":request_context.get().get("correlation_id")});db.commit()
    return {"ok":True,"setting":key,"value":value}

@app.post("/api/admin/sources/{source_key}/pause")
def pause_source(source_key:str,confirm:bool=Query(False),x_admin_token:str|None=Header(default=None)):
    admin_auth(x_admin_token)
    if not confirm:raise HTTPException(409,"Explicit confirmation is required")
    with SessionLocal() as db:
        source=db.scalar(select(Source).where(Source.source_key==source_key))
        if not source:raise HTTPException(404,"Source not found")
        source.enabled=False;source.sync_status="DISABLED";audit(db,"SOURCE_DISABLED",entity_type="source",entity_id=source_key,after={"enabled":False});db.commit()
        return {"ok":True,"enabled":False}

@app.post("/api/admin/sources/{source_key}/resume")
def resume_source(source_key:str,confirm:bool=Query(False),x_admin_token:str|None=Header(default=None)):
    admin_auth(x_admin_token)
    if not confirm:raise HTTPException(409,"Explicit confirmation is required")
    with SessionLocal() as db:
        source=db.scalar(select(Source).where(Source.source_key==source_key))
        if not source:raise HTTPException(404,"Source not found")
        source.enabled=True;source.sync_status="READY";audit(db,"SOURCE_ENABLED",entity_type="source",entity_id=source_key,after={"enabled":True});db.commit()
        return {"ok":True,"enabled":True}

@app.post("/api/admin/jobs/{job_id}/cancel")
def cancel_queued_job(job_id:int,x_admin_token:str|None=Header(default=None)):
    admin_auth(x_admin_token)
    with SessionLocal() as db:
        job=db.scalar(select(SyncJob).where(SyncJob.id==job_id).with_for_update())
        if not job:raise HTTPException(404,"Job not found")
        if job.job_state!="QUEUED" or not job.celery_task_id:raise HTTPException(409,"Only queued jobs can be cancelled")
        from .celery_app import celery_app
        celery_app.control.revoke(job.celery_task_id,terminate=False)
        try:
            from .tasks import redis_client
            token=(job.metrics_json or {}).get("reservation_token")
            if token:
                client=redis_client()
                client.eval("if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) else return 0 end",1,f"source-sync-enqueued:{job.source_id}",token)
        except Exception:pass
        job.job_state="CANCELLED";job.status="CANCELLED";job.finished_at=utcnow();job.pagination_complete=False;db.commit()
        return {"ok":True,"status":job.job_state}

@app.post("/api/admin/jobs/{job_id}/retry")
def retry_failed_job(job_id:int,x_admin_token:str|None=Header(default=None)):
    admin_auth(x_admin_token)
    with SessionLocal() as db:
        job=db.get(SyncJob,job_id)
        if not job:raise HTTPException(404,"Job not found")
        if job.job_state not in ("FAILED","ABANDONED","COMPLETED_WITH_WARNINGS"):raise HTTPException(409,"Job is not retryable")
        source=db.get(Source,job.source_id)
        if not source:raise HTTPException(404,"Source not found")
        source_key=source.source_key
    from .tasks import enqueue_source
    return enqueue_source(source_key,"retry",request_context.get().get("correlation_id"))

@app.get("/api/admin/alerts")
def alerts(x_admin_token:str|None=Header(default=None),status_filter:str=Query("OPEN",alias="status")):
    admin_auth(x_admin_token)
    with SessionLocal() as db:
        return [{"id":a.id,"type":a.event_type,"severity":a.severity,"source_id":a.source_id,"payload":a.payload,"status":a.status,"created_at":dt(a.created_at),"acknowledged_by":a.acknowledged_by,"resolved_at":dt(a.resolved_at)} for a in db.scalars(select(AlertEvent).where(AlertEvent.status==status_filter).order_by(AlertEvent.created_at.desc()).limit(200)).all()]

@app.post("/api/admin/alerts/{alert_id}/{action}")
def update_alert(alert_id:int,action:str,x_admin_token:str|None=Header(default=None)):
    identity=admin_auth(x_admin_token)
    if action not in ("acknowledge","resolve"):raise HTTPException(400,"Unsupported action")
    with SessionLocal() as db:
        row=db.get(AlertEvent,alert_id)
        if not row:raise HTTPException(404,"Alert not found")
        now=utcnow()
        if action=="acknowledge":row.status="ACKNOWLEDGED";row.acknowledged_at=now;row.acknowledged_by=(identity or {}).get("id")
        else:row.status="RESOLVED";row.resolved_at=now
        db.commit();return {"ok":True,"status":row.status}

@app.get("/api/dashboard")
def dashboard():
    with SessionLocal() as db:
        total=db.scalar(select(func.count(Opportunity.id)).where(Opportunity.merged_into_id.is_(None))) or 0
        active=db.scalar(select(func.count(Opportunity.id)).where(Opportunity.merged_into_id.is_(None),Opportunity.status.in_(ACTIVE_STATUSES))) or 0
        recent=db.scalar(select(func.count(Opportunity.id)).where(Opportunity.merged_into_id.is_(None),Opportunity.first_seen_at>=datetime.now(timezone.utc).replace(hour=0,minute=0,second=0,microsecond=0))) or 0
        source_count=db.scalar(select(func.count(Source.id)).where(Source.enabled==True)) or 0
        pending=db.scalar(select(func.count(DuplicateCandidate.id)).where(DuplicateCandidate.status=="PENDING")) or 0
        pending_conflicts=db.scalar(select(func.count(OpportunityConflict.id)).where(OpportunityConflict.status=="OPEN")) or 0
        pending_qualifications=db.scalar(select(func.count(QualificationReview.id)).where(QualificationReview.status=="PENDING")) or 0
        source_listings=db.scalar(select(func.count(SourceOpportunity.id))) or 0
        multi_source_ids=select(SourceOpportunity.master_opportunity_id).where(SourceOpportunity.master_opportunity_id.is_not(None)).group_by(SourceOpportunity.master_opportunity_id).having(func.count(func.distinct(SourceOpportunity.source_id))>1).subquery()
        multi_source=db.scalar(select(func.count()).select_from(multi_source_ids)) or 0
        pending_locations=db.scalar(select(func.count(LocationReview.id)).where(LocationReview.status=="PENDING")) or 0
        pending_reviews=pending+pending_locations+pending_conflicts+pending_qualifications
        jobs=db.scalars(select(SyncJob).order_by(SyncJob.started_at.desc()).limit(5)).all()
        return {"total":total,"unique_master_opportunities":total,"source_listings_collected":source_listings,"multi_source_opportunities":multi_source,"active":active,"new_today":recent,"enabled_sources":source_count,"pending_duplicates":pending,"pending_location_reviews":pending_locations,"pending_conflicts":pending_conflicts,"pending_qualification_reviews":pending_qualifications,"pending_review_total":pending_reviews,
            "sectors":group_counts("sector",db.execute(select(Opportunity.sector,func.count()).where(Opportunity.merged_into_id.is_(None)).group_by(Opportunity.sector)).all())[:8],
            "recent_jobs":[job_json(j) for j in jobs]}

@app.get("/api/data-dashboard")
def data_dashboard(period:str="all",status:str="",sector:str="",activity:str="",sub_activity:str="",source:str="",owner:str="",location:str="",opportunity_type:str="",investment_model:str="",asset_facility_type:str="",subsector:str="",lifecycle:str=""):
    """Return SQL-aggregated executive analytics over non-merged Master Opportunities."""
    now=datetime.now(timezone.utc)
    period_start=_period_start(period)
    location_value=func.coalesce(func.nullif(Opportunity.district,""),func.nullif(Opportunity.city,""),"غير محدد")
    conditions=[Opportunity.merged_into_id.is_(None)]
    if period_start: conditions.append(Opportunity.first_seen_at>=period_start)
    today=local_today()
    today_iso=today.isoformat()
    with SessionLocal() as db:
        conditions.extend(_opportunity_filter_conditions(db,sector=sector,activity=activity,sub_activity=sub_activity,status=status,owner=owner,source=source,location=location,opportunity_type=opportunity_type,investment_model=investment_model,asset_facility_type=asset_facility_type,subsector=subsector,lifecycle=lifecycle)[1:])
        master_ids=select(Opportunity.id).where(*conditions)
        global_total=db.scalar(select(func.count(Opportunity.id)).where(Opportunity.merged_into_id.is_(None))) or 0
        total=db.scalar(select(func.count(Opportunity.id)).where(*conditions)) or 0
        active=db.scalar(select(func.count(Opportunity.id)).where(*conditions,Opportunity.status.in_(ACTIVE_STATUSES))) or 0
        historical=db.scalar(select(func.count(Opportunity.id)).where(*conditions,Opportunity.status.in_(HISTORICAL_STATUSES))) or 0
        recent_start=now-timedelta(days=30)
        new_30d=db.scalar(select(func.count(Opportunity.id)).where(*conditions,Opportunity.first_seen_at>=recent_start)) or 0
        source_count=db.scalar(select(func.count(func.distinct(SourceOpportunity.source_id))).join(Source,Source.id==SourceOpportunity.source_id).where(SourceOpportunity.master_opportunity_id.in_(master_ids))) or 0
        multis=select(SourceOpportunity.master_opportunity_id.label("master_id")).where(SourceOpportunity.master_opportunity_id.in_(master_ids)).group_by(SourceOpportunity.master_opportunity_id).having(func.count(func.distinct(SourceOpportunity.source_id))>1).subquery()
        multi_count=db.scalar(select(func.count()).select_from(multis)) or 0
        master_subquery=master_ids.subquery()
        by_sector=group_counts("sector",db.execute(select(Opportunity.sector,func.count(Opportunity.id)).where(Opportunity.id.in_(select(master_subquery.c.id))).group_by(Opportunity.sector)).all())
        by_status=group_counts("status",db.execute(select(Opportunity.status,func.count(Opportunity.id)).where(Opportunity.id.in_(select(master_subquery.c.id))).group_by(Opportunity.status)).all())
        by_activity=group_counts("activity",db.execute(select(Opportunity.activity,func.count(Opportunity.id)).where(Opportunity.id.in_(select(master_subquery.c.id))).group_by(Opportunity.activity)).all())
        by_sub_activity=group_counts("sub_activity",db.execute(select(Opportunity.sub_activity,func.count(Opportunity.id)).where(Opportunity.id.in_(select(master_subquery.c.id))).group_by(Opportunity.sub_activity)).all())
        by_type=group_counts("opportunity_type",db.execute(select(Opportunity.opportunity_type,func.count(Opportunity.id)).where(Opportunity.id.in_(select(master_subquery.c.id))).group_by(Opportunity.opportunity_type)).all())
        by_investment_model=group_counts("investment_model",db.execute(select(Opportunity.investment_model,func.count(Opportunity.id)).where(Opportunity.id.in_(select(master_subquery.c.id))).group_by(Opportunity.investment_model)).all())
        model_known=db.scalar(select(func.count(Opportunity.id)).where(Opportunity.id.in_(select(master_subquery.c.id)),Opportunity.investment_model.is_not(None),Opportunity.investment_model!="")) or 0
        model_review=db.scalar(select(func.count(func.distinct(OpportunityConflict.opportunity_id))).where(OpportunityConflict.field_name=="investment_model",OpportunityConflict.status=="OPEN",OpportunityConflict.opportunity_id.in_(select(master_subquery.c.id)))) or 0
        investment_model_coverage={"total":int(total),"canonical":int(model_known),"unspecified":int(total-model_known),"review":int(model_review),"canonical_percent":round(model_known*100/total,1) if total else 0}
        source_count_rows=db.execute(
            select(Source.source_key,Source.source_name_ar,func.count(func.distinct(SourceOpportunity.master_opportunity_id)))
            .select_from(Source)
            .outerjoin(SourceOpportunity,and_(SourceOpportunity.source_id==Source.id,SourceOpportunity.master_opportunity_id.in_(select(master_subquery.c.id))))
            .where(Source.enabled.is_(True)).group_by(Source.source_key,Source.source_name_ar,Source.priority)
            .order_by(func.count(func.distinct(SourceOpportunity.master_opportunity_id)).desc(),Source.priority)
        ).all()
        by_source=[{"key":key,"name":name,"count":int(count or 0),"share_percent":round((int(count or 0)*100/total),1) if total else 0} for key,name,count in source_count_rows]
        by_owner=group_counts("owner",db.execute(select(Opportunity.opportunity_owner,func.count(Opportunity.id)).where(Opportunity.id.in_(select(master_subquery.c.id))).group_by(Opportunity.opportunity_owner)).all())[:10]
        confirmed_geo_ids=_confirmed_location_master_ids(db)
        by_location=group_counts("location",db.execute(select(location_value,func.count(Opportunity.id)).where(Opportunity.id.in_(select(master_subquery.c.id)),Opportunity.id.in_(confirmed_geo_ids or [-1])).group_by(location_value)).all())[:12]
        dialect=engine.dialect.name
        month_expr=func.to_char(Opportunity.first_seen_at,"YYYY-MM") if dialect=="postgresql" else func.strftime("%Y-%m",Opportunity.first_seen_at)
        timeline_start=period_start or now-timedelta(days=365)
        timeline_conditions=[*conditions,Opportunity.first_seen_at>=timeline_start]
        timeline=[]
        for month,count in db.execute(select(month_expr,func.count(Opportunity.id)).where(*timeline_conditions).group_by(month_expr).order_by(month_expr)).all():
            if not month: continue
            year,month_number=map(int,month.split("-"))
            next_month=date(year+(month_number==12),1 if month_number==12 else month_number+1,1)
            timeline.append({"month":month,"start_date":f"{month}-01","end_date":(next_month-timedelta(days=1)).isoformat(),"count":int(count)})
        deadline_rows=db.execute(select(Opportunity.id,Opportunity.title_ar,Opportunity.opportunity_owner,Opportunity.submission_deadline,Opportunity.primary_publication_platform).where(*conditions,Opportunity.submission_deadline.is_not(None),Opportunity.submission_deadline.like("____-__-__"),Opportunity.submission_deadline>=today_iso,~Opportunity.status.in_(HISTORICAL_STATUSES)).order_by(Opportunity.submission_deadline,Opportunity.id).limit(8)).all()
        deadlines=[]
        for opportunity_id,title,organization,deadline,source_name in deadline_rows:
            try: days=(date.fromisoformat(deadline)-today).days
            except (TypeError,ValueError): continue
            deadlines.append({"id":opportunity_id,"title":title,"owner":organization,"deadline":deadline,"days_remaining":days,"source":source_name})
        deadline_base=[*conditions,Opportunity.submission_deadline.is_not(None),Opportunity.submission_deadline.like("____-__-__"),Opportunity.submission_deadline>=today_iso,~Opportunity.status.in_(HISTORICAL_STATUSES)]
        deadline_30d=db.scalar(select(func.count(Opportunity.id)).where(*deadline_base,Opportunity.submission_deadline<=(today+timedelta(days=30)).isoformat())) or 0
        deadline_buckets=[]
        for key,label,lower,upper in [("7d","خلال 7 أيام",0,7),("8_14d","8–14 يومًا",8,14),("15_30d","15–30 يومًا",15,30),("over_30d","أكثر من 30 يومًا",31,None)]:
            bucket_conditions=[*deadline_base,Opportunity.submission_deadline<= (today+timedelta(days=upper)).isoformat()] if upper is not None else [*deadline_base]
            if lower: bucket_conditions.append(Opportunity.submission_deadline>=(today+timedelta(days=lower)).isoformat())
            deadline_buckets.append({"key":key,"label":label,"count":db.scalar(select(func.count(Opportunity.id)).where(*bucket_conditions)) or 0})
        deadline_trend_counts={}
        trend_rows=db.scalars(select(Opportunity.submission_deadline).where(*deadline_base).order_by(Opportunity.submission_deadline)).all()
        for raw_deadline in trend_rows:
            try: parsed_deadline=date.fromisoformat(raw_deadline)
            except (TypeError,ValueError): continue
            month=parsed_deadline.strftime("%Y-%m")
            deadline_trend_counts[month]=deadline_trend_counts.get(month,0)+1
        deadline_trend=[]
        for month,count in sorted(deadline_trend_counts.items()):
            year,month_number=map(int,month.split("-"))
            next_month=date(year+(month_number==12),1 if month_number==12 else month_number+1,1)
            deadline_trend.append({"month":month,"start_date":f"{month}-01","end_date":(next_month-timedelta(days=1)).isoformat(),"count":count})
        completeness_fields={
            "owner":and_(Opportunity.opportunity_owner.is_not(None),Opportunity.opportunity_owner!=""),
            "sector":and_(Opportunity.sector.is_not(None),Opportunity.sector!=""),
            "location":or_(and_(Opportunity.location_description.is_not(None),Opportunity.location_description!=""),and_(Opportunity.district.is_not(None),Opportunity.district!="")),
            "deadline":and_(Opportunity.submission_deadline.is_not(None),Opportunity.submission_deadline!=""),
            "reference":and_(Opportunity.reference_number.is_not(None),Opportunity.reference_number!=""),
            "area":Opportunity.land_area_sqm.is_not(None),
        }
        complete_counts={key:db.scalar(select(func.sum(case((condition,1),else_=0))).where(*conditions)) or 0 for key,condition in completeness_fields.items()}
        completeness=[{"key":key,"label":label,"count":int(complete_counts[key]),"total":int(total),"percent":round((complete_counts[key]/total)*100,1) if total else 0} for key,label in [("owner","الجهة المالكة"),("sector","القطاع"),("location","تفاصيل الموقع"),("deadline","الموعد النهائي"),("reference","الرقم المرجعي"),("area","المساحة")]]
        area_totals={}
        for raw,area,count in db.execute(select(Opportunity.sector,func.sum(Opportunity.land_area_sqm),func.count(Opportunity.id)).where(Opportunity.id.in_(select(master_subquery.c.id)),Opportunity.land_area_sqm.is_not(None)).group_by(Opportunity.sector)).all():
            label=canonical_value("sector",raw);aggregate=area_totals.setdefault(label,{"name":label,"area_sqm":0.0,"count":0})
            aggregate["area_sqm"]+=float(area or 0);aggregate["count"]+=int(count)
        area_by_sector=sorted(({**row,"area_sqm":round(row["area_sqm"],2)} for row in area_totals.values()),key=lambda row:(-row["area_sqm"],comparison_key(row["name"])))[:8]
        source_health=[{"status":key or "UNKNOWN","count":int(count)} for key,count in db.execute(select(Source.technical_health,func.count(Source.id)).where(Source.enabled.is_(True)).group_by(Source.technical_health).order_by(func.count(Source.id).desc())).all()]
        source_coverage=[{"status":key or "UNKNOWN_COVERAGE","count":int(count)} for key,count in db.execute(select(Source.coverage_status,func.count(Source.id)).where(Source.enabled.is_(True)).group_by(Source.coverage_status).order_by(func.count(Source.id).desc())).all()]
        source_rows=db.execute(select(Source.source_key,Source.source_name_ar,Source.technical_health,Source.coverage_status,Source.last_successful_sync).where(Source.enabled.is_(True)).order_by(Source.priority,Source.source_name_ar)).all()
        source_list=[{"key":key,"name":name,"health":health,"coverage":coverage,"last_successful_sync":last.isoformat() if last else None} for key,name,health,coverage,last in source_rows]
        pending_duplicates=db.scalar(select(func.count(DuplicateCandidate.id)).where(DuplicateCandidate.status=="PENDING")) or 0
        pending_locations=db.scalar(select(func.count(LocationReview.id)).where(LocationReview.status=="PENDING")) or 0
        open_taxonomy=db.scalar(select(func.count(OpportunityConflict.id)).where(OpportunityConflict.status=="OPEN",OpportunityConflict.conflict_type=="TAXONOMY_CONFLICT")) or 0
        open_fields=db.scalar(select(func.count(OpportunityConflict.id)).where(OpportunityConflict.status=="OPEN",OpportunityConflict.conflict_type=="FIELD_VALUE_CONFLICT")) or 0
        multi_examples=db.execute(
            select(Opportunity.id,Opportunity.title_ar,Opportunity.opportunity_owner)
            .where(Opportunity.id.in_(select(multis.c.master_id)))
            .order_by(Opportunity.last_updated_at.desc())
            .limit(4)
        ).all()
        recent_opportunities=db.execute(
            select(Opportunity.id,Opportunity.title_ar,Opportunity.opportunity_owner,Opportunity.sector,Opportunity.status,Opportunity.submission_deadline)
            .where(*conditions).order_by(Opportunity.last_updated_at.desc(),Opportunity.id.desc()).limit(8)
        ).all()
        last_update=db.scalar(select(func.max(Source.last_successful_sync)))
        sectors,_,sector_ids=_canonical_option_data(db,Opportunity.sector,"sector")
        statuses,_,status_ids=_canonical_option_data(db,Opportunity.status,"status")
        owners,_,owner_ids=_canonical_option_data(db,Opportunity.opportunity_owner,"owner")
        locations,location_counts,location_ids,location_hierarchy=_location_option_data(db)
        types,_,type_ids=_canonical_option_data(db,Opportunity.opportunity_type,"opportunity_type")
        activities,_,activity_ids=_canonical_option_data(db,Opportunity.activity,"activity")
        sub_activities,_,sub_activity_ids=_canonical_option_data(db,Opportunity.sub_activity,"sub_activity")
        investment_models,_,investment_model_ids=_canonical_option_data(db,Opportunity.investment_model,"investment_model")
        asset_facility_types,_,asset_facility_type_ids=_asset_facility_type_options(db)
        subsectors,_,subsector_ids=_canonical_option_data(db,Opportunity.subsector,"subsector")
        sources=[{"key":key,"name":name} for key,name in db.execute(select(Source.source_key,Source.source_name_ar).order_by(Source.priority)).all()]
        options={"sectors":sectors,"statuses":statuses,"sources":sources,"owners":owners,"locations":locations,"location_hierarchy":location_hierarchy,"types":types,"activities":activities,"sub_activities":sub_activities,"investment_models":investment_models,"asset_facility_types":asset_facility_types,"subsectors":subsectors}
        option_ids={"sectors":sector_ids,"statuses":status_ids,"owners":owner_ids,"locations":location_ids,"types":type_ids,"activities":activity_ids,"sub_activities":sub_activity_ids,"investment_models":investment_model_ids,"asset_facility_types":asset_facility_type_ids,"subsectors":subsector_ids,"sources":{source["name"]:source["key"] for source in sources}}
        return {"generated_at":now.isoformat(),"as_of_date":today_iso,"global_total":int(global_total),"filters":{"period":period,"status":status,"sector":sector,"activity":activity,"sub_activity":sub_activity,"source":source,"owner":owner,"location":location,"opportunity_type":opportunity_type,"investment_model":investment_model,"asset_facility_type":asset_facility_type,"subsector":subsector,"lifecycle":lifecycle},"options":options,"option_ids":option_ids,
            "kpis":{"total":total,"active":active,"new_30d":new_30d,"historical":historical,"sources":source_count,"enabled_sources":len(source_list),"deadline_30d":int(deadline_30d),"multi_source":multi_count,"multi_source_percent":round(multi_count*100/total,1) if total else 0},
            "by_sector":by_sector,"by_status":by_status,"by_activity":by_activity,"by_sub_activity":by_sub_activity,"by_type":by_type,"by_investment_model":by_investment_model,"investment_model_coverage":investment_model_coverage,"by_source":by_source,"by_owner":by_owner,"by_location":by_location,"timeline":timeline,"deadlines":deadlines,"deadline_buckets":deadline_buckets,"deadline_trend":deadline_trend,
            "multi_source_examples":[{"id":item[0],"title":item[1],"owner":item[2]} for item in multi_examples],"recent_opportunities":[{"id":row[0],"title":row[1],"owner":row[2],"sector":canonical_value("sector",row[3]),"status":canonical_value("status",row[4]),"deadline":row[5]} for row in recent_opportunities],"source_health":source_health,"source_coverage":source_coverage,"sources":source_list,
            "data_quality":{"pending_duplicates":pending_duplicates,"pending_locations":pending_locations,"open_taxonomy_conflicts":open_taxonomy,"open_field_conflicts":open_fields},
            "completeness":completeness,"area_by_sector":area_by_sector,"latest_source_update":last_update.isoformat() if last_update else None}

@app.get("/api/opportunities")
def opportunities(q:str="",sector:str="",sector_values:str="",activity:str="",sub_activity:str="",status:str="",source:str="",owner:str="",location:str="",opportunity_type:str="",investment_model:str="",asset_facility_type:str="",subsector:str="",lifecycle:str="",period:str="all",created_after:str="",created_before:str="",deadline_after:str="",deadline_before:str="",map_ids:str="",limit:int=Query(50,ge=1,le=500),offset:int=Query(0,ge=0)):
    with SessionLocal() as db:
        query=select(Opportunity).where(Opportunity.merged_into_id.is_(None)).options(selectinload(Opportunity.source_records).selectinload(SourceOpportunity.source),selectinload(Opportunity.asset_facility_type_assignments).selectinload(OpportunityAssetFacilityType.asset_type))
        count_query=select(func.count(func.distinct(Opportunity.id))).select_from(Opportunity).where(Opportunity.merged_into_id.is_(None))
        filters=_opportunity_filter_conditions(db,sector=sector,activity=activity,sub_activity=sub_activity,status=status,owner=owner,source=source,location=location,opportunity_type=opportunity_type,investment_model=investment_model,asset_facility_type=asset_facility_type,subsector=subsector,lifecycle=lifecycle)
        if sector_values: filters.append(_sector_values_filter_condition(db,sector_values))
        period_start=_period_start(period)
        if period_start: filters.append(Opportunity.first_seen_at>=period_start)
        if map_ids:
            try: selected_map_ids=sorted({int(value) for value in map_ids.split(",") if value.strip()})
            except ValueError: raise HTTPException(422,"معرّفات الخريطة غير صالحة")
            if not selected_map_ids: raise HTTPException(422,"معرّفات الخريطة غير صالحة")
            filters.append(Opportunity.id.in_(selected_map_ids))
        for condition in filters[1:]: query=query.where(condition);count_query=count_query.where(condition)
        if q:
            like=f"%{q}%"
            search_filter=or_(Opportunity.title_ar.ilike(like),Opportunity.reference_number.ilike(like),Opportunity.location_description.ilike(like),Opportunity.opportunity_owner.ilike(like))
            query=query.where(search_filter);count_query=count_query.where(search_filter)
        if created_after:
            try: boundary=datetime.fromisoformat(created_after).replace(tzinfo=timezone.utc)
            except ValueError: raise HTTPException(422,"تاريخ البداية غير صالح")
            query=query.where(Opportunity.first_seen_at>=boundary);count_query=count_query.where(Opportunity.first_seen_at>=boundary)
        if created_before:
            try: boundary=datetime.fromisoformat(created_before).replace(tzinfo=timezone.utc)+timedelta(days=1)
            except ValueError: raise HTTPException(422,"تاريخ النهاية غير صالح")
            query=query.where(Opportunity.first_seen_at<boundary);count_query=count_query.where(Opportunity.first_seen_at<boundary)
        if deadline_after:
            query=query.where(Opportunity.submission_deadline>=deadline_after);count_query=count_query.where(Opportunity.submission_deadline>=deadline_after)
        if deadline_before:
            query=query.where(Opportunity.submission_deadline<=deadline_before);count_query=count_query.where(Opportunity.submission_deadline<=deadline_before)
        # last_updated_at is not unique (source synchronization can update many
        # Masters in the same transaction). The Master ID tie-breaker makes
        # offset pagination deterministic across adjacent requests.
        rows=db.scalars(query.order_by(Opportunity.last_updated_at.desc(),Opportunity.id.desc()).limit(limit).offset(offset)).unique().all()
        count=db.scalar(count_query) or 0
        row_ids=[row.id for row in rows]
        pending=_pending_location_reviews_by_master(db,row_ids)
        source_locations=_source_location_values_by_master(db,row_ids)
        return {"items":[opp_json(row,_opportunity_geography(db,row,pending,source_locations)) for row in rows],"total":count,"limit":limit,"offset":offset}

@app.get("/api/data-dashboard/geography")
def data_dashboard_geography(period:str="all",status:str="",sector:str="",activity:str="",sub_activity:str="",source:str="",owner:str="",location:str="",opportunity_type:str="",investment_model:str="",asset_facility_type:str="",subsector:str="",lifecycle:str=""):
    """Map only Furas master points whose stored coordinates match raw source geometry."""
    period_start=_period_start(period)
    geometry=_alahsa_boundary_geometry()
    with SessionLocal() as db:
        conditions=_opportunity_filter_conditions(db,sector=sector,activity=activity,sub_activity=sub_activity,status=status,owner=owner,source=source,location=location,opportunity_type=opportunity_type,investment_model=investment_model,asset_facility_type=asset_facility_type,subsector=subsector,lifecycle=lifecycle)
        if period_start: conditions.append(Opportunity.first_seen_at>=period_start)
        masters=db.scalars(select(Opportunity).where(*conditions).order_by(Opportunity.id)).all()
        total=len(masters)
        by_id={item.id:item for item in masters}
        coordinate_count=sum(1 for item in masters if item.latitude is not None and item.longitude is not None)
        missing_count=total-coordinate_count
        furas_rows=db.execute(
            select(SourceOpportunity.master_opportunity_id,SourceOpportunity.raw_data_json)
            .join(Source,Source.id==SourceOpportunity.source_id)
            .where(Source.source_key=="furas",SourceOpportunity.master_opportunity_id.in_(by_id or [-1]))
        ).all()
        source_geometry={}
        for master_id,raw in furas_rows:
            raw=raw or {}; point=raw.get("geometry") or {}
            try: x=float(point["x"]); y=float(point["y"])
            except (KeyError,TypeError,ValueError): continue
            item=by_id.get(master_id)
            if item and item.latitude is not None and item.longitude is not None and abs(item.longitude-x)<1e-8 and abs(item.latitude-y)<1e-8:
                source_geometry[master_id]=(x,y)
        boundary_excluded=0
        unverified=coordinate_count-len(source_geometry)
        grouped={}
        for master_id,(longitude,latitude) in source_geometry.items():
            if not (-180<=longitude<=180 and -90<=latitude<=90):
                unverified+=1;continue
            if not _geojson_contains(geometry,longitude,latitude):
                boundary_excluded+=1;continue
            key=(round(latitude,7),round(longitude,7))
            bucket=grouped.setdefault(key,[])
            bucket.append(by_id[master_id])
        points=[]
        for (latitude,longitude),items in grouped.items():
            points.append({
                "latitude":latitude,"longitude":longitude,"count":len(items),
                "active_count":sum(1 for item in items if item.status in ACTIVE_STATUSES),
                "ids":[item.id for item in items],
                "title":items[0].title_ar if len(items)==1 else f"{len(items)} فرص في الموقع نفسه",
                "location":canonical_value("location",items[0].district or items[0].city),
                "sector":canonical_value("sector",items[0].sector),
            })
        mapped_count=sum(len(point["ids"]) for point in points)
        return {"boundary":{"name":"محافظة الأحساء","source":"geoBoundaries / OpenStreetMap","license":"CC BY-SA 2.0"},
            "counts":{"total":total,"coordinate_records":coordinate_count,"exact_mapped":mapped_count,"locality_mapped":0,"missing_coordinates":missing_count,"outside_boundary":boundary_excluded,"unverified_coordinates":unverified,"unmapped":total-mapped_count},
            "points":points,"coordinate_precision":"مصدرية مباشرة WGS84؛ تطابق هندسة سجل Furas الخام، 7 منازل عشرية في العرض"}

@app.get("/api/opportunities/{opportunity_id}")
def opportunity_detail(opportunity_id:int):
    with SessionLocal() as db:
        item=db.scalar(select(Opportunity).where(Opportunity.id==opportunity_id).options(selectinload(Opportunity.source_records).selectinload(SourceOpportunity.source)))
        if not item: raise HTTPException(404,"الفرصة غير موجودة")
        changes=db.scalars(select(ChangeHistory).where(ChangeHistory.opportunity_id==item.id).order_by(ChangeHistory.detected_at.desc())).all()
        data=opp_json(item,_opportunity_geography(db,item))
        data["changes"]=[{
            "field": "نوع الفرصة" if c.changed_field == "opportunity_type" else "نموذج الاستثمار" if c.changed_field == "investment_model" else c.changed_field,
            "before": ("قيمة غير معتمدة" if c.previous_value is not None else OPPORTUNITY_TYPE_UNSPECIFIED_LABEL)
                if c.changed_field == "opportunity_type" else canonical_value("investment_model", c.previous_value) if c.changed_field in {"investment_model", "investment_model_source_projection"} else _business_history_value(c.previous_value),
            "after": ("قيمة غير معتمدة" if c.new_value is not None else OPPORTUNITY_TYPE_UNSPECIFIED_LABEL)
                if c.changed_field == "opportunity_type" else canonical_value("investment_model", c.new_value) if c.changed_field in {"investment_model", "investment_model_source_projection"} else _business_history_value(c.new_value),
            "date": dt(c.detected_at),
        } for c in changes if c.changed_field != "investment_model_source_projection"]
        return data

@app.get("/api/sources")
def sources():
    with SessionLocal() as db:
        multi_source_ids=select(SourceOpportunity.master_opportunity_id).where(SourceOpportunity.master_opportunity_id.is_not(None)).group_by(SourceOpportunity.master_opportunity_id).having(func.count(func.distinct(SourceOpportunity.source_id))>1).subquery()
        from .source_freshness import evaluate_source_jobs
        now=datetime.now(timezone.utc)
        all_jobs=db.scalars(select(SyncJob).order_by(SyncJob.started_at.desc())).all()
        jobs_by_source={}
        for job in all_jobs: jobs_by_source.setdefault(job.source_id,[]).append(job)
        result=[]
        for source in db.scalars(select(Source).order_by(Source.priority)).all():
            count=db.scalar(select(func.count(SourceOpportunity.id)).where(SourceOpportunity.source_id==source.id)) or 0
            latest=jobs_by_source.get(source.id,[None])[0]
            matches=db.scalar(select(func.count(func.distinct(SourceOpportunity.master_opportunity_id))).where(SourceOpportunity.source_id==source.id,SourceOpportunity.master_opportunity_id.in_(select(multi_source_ids.c.master_opportunity_id)))) or 0
            content_change=db.scalar(select(func.max(ChangeHistory.detected_at)).where(ChangeHistory.source_id==source.id))
            freshness=evaluate_source_jobs(source,jobs_by_source.get(source.id,[]),now=now,last_content_change=content_change)
            result.append(source_json(source,count,latest,matches,freshness))
        return result

@app.get("/api/source-coverage")
def source_coverage():
    """Read-only source coverage counters, separated from technical health and last-job counters."""
    removed_statuses=("أزيلت من المصدر","ازيلت من المصدر","REMOVED_FROM_SOURCE","DELETED_FROM_SOURCE")
    with SessionLocal() as db:
        result=[]
        for source in db.scalars(select(Source).where(Source.enabled.is_(True)).order_by(Source.priority)):
            records=db.scalars(select(SourceOpportunity).where(SourceOpportunity.source_id==source.id)).all()
            if source.source_key=="invest-saudi":
                current_ids=set(db.scalars(select(SourceOpportunityDatasetMembership.source_opportunity_id)
                    .join(SourceOpportunity,SourceOpportunity.id==SourceOpportunityDatasetMembership.source_opportunity_id)
                    .where(SourceOpportunity.source_id==source.id,SourceOpportunityDatasetMembership.is_current.is_(True)).distinct()).all())
                current_records=[row for row in records if row.id in current_ids]
                historical_records=[row for row in records if row.id not in current_ids]
                count_basis="unique source identities with at least one current official dataset membership"
            else:
                current_records=[row for row in records if row.canonical_status not in removed_statuses]
                historical_records=[row for row in records if row.canonical_status in removed_statuses]
                count_basis="source lifecycle status"
            location_reviews=db.scalar(select(func.count(LocationReview.id)).where(
                LocationReview.source_id==source.id,LocationReview.status=="PENDING")) or 0
            qualification_reviews=db.scalar(select(func.count(QualificationReview.id)).where(
                QualificationReview.source_id==source.id,QualificationReview.status=="PENDING")) or 0
            open_conflicts=db.scalar(select(func.count(OpportunityConflict.id)).where(
                OpportunityConflict.source_id==source.id,OpportunityConflict.status=="OPEN")) or 0
            latest_success=db.scalar(select(SyncJob).where(SyncJob.source_id==source.id,
                SyncJob.job_state=="COMPLETED",SyncJob.status=="SUCCESS")
                .order_by(SyncJob.finished_at.desc(),SyncJob.id.desc()).limit(1))
            if source.source_key=="invest-saudi":
                threshold=max(1,int(source.missing_confirmation_threshold or 3))
                pending_absence_ids=db.scalars(select(SourceOpportunityDatasetMembership.source_opportunity_id)
                    .join(SourceOpportunity,SourceOpportunity.id==SourceOpportunityDatasetMembership.source_opportunity_id)
                    .where(SourceOpportunity.source_id==source.id,SourceOpportunityDatasetMembership.is_current.is_(True),
                        SourceOpportunityDatasetMembership.missing_successful_checks>0,
                        SourceOpportunityDatasetMembership.missing_successful_checks<threshold)
                    .distinct()).all()
                pending_absence=len(pending_absence_ids)
            else:
                pending_absence=sum(1 for row in current_records if 0<(row.missing_successful_checks or 0)<max(1,int(source.missing_confirmation_threshold or 3)))
            result.append({
                "source_key":source.source_key,
                "technical_health":source.technical_health,
                "coverage_status":source.coverage_status,
                "source_record_total":len(records),
                "current_source_record_count":len(current_records),
                "historical_source_record_count":len(historical_records),
                "qualified_current_source_record_count":sum(1 for row in current_records if row.master_opportunity_id is not None),
                "unlinked_current_source_record_count":sum(1 for row in current_records if row.master_opportunity_id is None),
                "pending_location_review_count":location_reviews,
                "pending_qualification_review_count":qualification_reviews,
                "open_source_conflict_count":open_conflicts,
                "pending_review_count":location_reviews+qualification_reviews+open_conflicts,
                "pending_absence_confirmation_count":pending_absence,
                "count_basis":count_basis,
                "last_successful_scan":({
                    "job_id":latest_success.id,
                    "finished_at":dt(latest_success.finished_at),
                    "trigger_type":latest_success.trigger_type,
                    "pages_successful":latest_success.pages_successful,
                    "pages_requested":latest_success.pages_requested,
                    "enumerated_count":latest_success.unique_records,
                    "accepted_al_ahsa_count":latest_success.ahsa_count,
                    "active_count":latest_success.active_count,
                    "location_review_count":latest_success.location_review_count,
                } if latest_success else None),
            })
        return {"generated_at":datetime.now(timezone.utc).isoformat(),"sources":result}

@app.get("/api/source-limitations")
def source_limitations():
    with SessionLocal() as db:
        rows=db.scalars(select(SourceLimitation).order_by(SourceLimitation.source_id,SourceLimitation.limitation_type)).all()
        return [{"source_id":r.source_id,"source_key":db.get(Source,r.source_id).source_key,"type":r.limitation_type,"description":r.description,
            "evidence_url":r.evidence_url,"first_detected_at":dt(r.first_detected_at),"last_verified_at":dt(r.last_verified_at),
            "affects_completeness":r.affects_completeness,"resolution":r.resolution} for r in rows]

@app.get("/api/modon-locations")
def modon_locations():
    with SessionLocal() as db:
        return [{"official_name_ar":r.official_name_ar,"official_name_en":r.official_name_en,"location_type":r.location_type,
            "source_identifier":r.source_identifier,"region":r.region,"governorate":r.governorate,"latitude":r.latitude,
            "longitude":r.longitude,"active":r.active,"source_url":r.source_url,"verified_at":dt(r.verified_at)}
            for r in db.scalars(select(ModonLocation).order_by(ModonLocation.official_name_en)).all()]

@app.get("/api/ncp-project-events")
def ncp_project_events():
    with SessionLocal() as db:
        rows=db.scalars(select(NcpProjectEvent).order_by(NcpProjectEvent.event_date,NcpProjectEvent.id)).all()
        return [{"project_source_opportunity_id":r.project_source_opportunity_id,"event_type":r.event_type,"event_date":r.event_date,
            "source_url":r.source_url,"stage_before":r.stage_before,"stage_after":r.stage_after,"raw_title":r.raw_title,"raw_data":r.raw_data} for r in rows]

@app.post("/api/admin/sources/{source_key}/sync")
async def trigger_sync(source_key:str,x_admin_token:str|None=Header(default=None)):
    admin_auth(x_admin_token)
    if os.getenv("ENVIRONMENT",os.getenv("ENV","development")).lower() in ("production","staging"):
        with SessionLocal() as db:
            maintenance=db.scalar(select(SystemSetting).where(SystemSetting.key=="maintenance_mode"))
            if maintenance and maintenance.value.lower()=="true":raise HTTPException(503,"Source writes are paused for maintenance")
        from .tasks import enqueue_source
        return enqueue_source(source_key,"manual",request_context.get().get("correlation_id"))
    return await sync_source(source_key)

@app.patch("/api/admin/sources/{source_key}")
def update_source(source_key:str,enabled:bool|None=None,interval_minutes:int|None=Query(None,ge=15,le=10080),confirm:bool=Query(False),x_admin_token:str|None=Header(default=None)):
    admin_auth(x_admin_token)
    with SessionLocal() as db:
        source=db.scalar(select(Source).where(Source.source_key==source_key))
        if not source: raise HTTPException(404,"المصدر غير موجود")
        if enabled is not None and enabled!=source.enabled and not confirm:raise HTTPException(409,"Explicit confirmation is required to enable or disable a source")
        if interval_minutes is not None and not (max(15,source.polling_frequency_minutes)//4 <= interval_minutes <= max(15,source.polling_frequency_minutes)*4) and not confirm:raise HTTPException(409,"Explicit confirmation is required for a large schedule change")
        if enabled is not None: source.enabled=enabled
        if interval_minutes is not None: source.polling_frequency_minutes=interval_minutes
        db.commit(); return source_json(source,db.scalar(select(func.count(SourceOpportunity.id)).where(SourceOpportunity.source_id==source.id)),db.scalar(select(SyncJob).where(SyncJob.source_id==source.id).order_by(SyncJob.started_at.desc()).limit(1)))

@app.get("/api/admin/jobs")
def jobs(x_admin_token:str|None=Header(default=None)):
    admin_auth(x_admin_token)
    with SessionLocal() as db:
        rows=db.scalars(select(SyncJob).order_by(SyncJob.started_at.desc()).limit(100)).all()
        return [job_json(row) for row in rows]

@app.get("/api/admin/errors")
def errors(x_admin_token:str|None=Header(default=None)):
    admin_auth(x_admin_token)
    with SessionLocal() as db:
        return [{"id":e.id,"source_id":e.source_id,"date":dt(e.occurred_at),"category":e.category,"message":e.message} for e in db.scalars(select(SourceError).order_by(SourceError.occurred_at.desc()).limit(100)).all()]

@app.get("/api/admin/validation-report")
def validation_report(x_admin_token:str|None=Header(default=None)):
    admin_auth(x_admin_token)
    with SessionLocal() as db:
        masters=Opportunity.merged_into_id.is_(None)
        multi_source_ids=select(SourceOpportunity.master_opportunity_id).where(SourceOpportunity.master_opportunity_id.is_not(None)).group_by(SourceOpportunity.master_opportunity_id).having(func.count(func.distinct(SourceOpportunity.source_id))>1).subquery()
        today=local_today().isoformat()
        return {"generated_at":datetime.now(timezone.utc).isoformat(),"metrics":{
            "total_master_opportunities":db.scalar(select(func.count(Opportunity.id)).where(masters)) or 0,
            "total_source_records":db.scalar(select(func.count(SourceOpportunity.id))) or 0,
            "masters_with_multiple_sources":db.scalar(select(func.count()).select_from(multi_source_ids)) or 0,
            "duplicate_candidates_pending":db.scalar(select(func.count(DuplicateCandidate.id)).where(DuplicateCandidate.status=="PENDING")) or 0,
            "location_reviews_pending":db.scalar(select(func.count(LocationReview.id)).where(LocationReview.status=="PENDING")) or 0,
            "qualification_reviews_pending":db.scalar(select(func.count(QualificationReview.id)).where(QualificationReview.status=="PENDING")) or 0,
            "opportunity_locations":db.scalar(select(func.count(OpportunityLocation.id))) or 0,
            "missing_reference_number":db.scalar(select(func.count(Opportunity.id)).where(masters,or_(Opportunity.reference_number.is_(None),Opportunity.reference_number==""))) or 0,
            "missing_deadline":db.scalar(select(func.count(Opportunity.id)).where(masters,or_(Opportunity.submission_deadline.is_(None),Opportunity.submission_deadline==""))) or 0,
            "missing_area":db.scalar(select(func.count(Opportunity.id)).where(masters,Opportunity.land_area_sqm.is_(None))) or 0,
            "missing_owner":db.scalar(select(func.count(Opportunity.id)).where(masters,or_(Opportunity.opportunity_owner.is_(None),Opportunity.opportunity_owner==""))) or 0,
            "low_location_confidence":db.scalar(select(func.count(Opportunity.id)).where(masters,Opportunity.location_confidence_score<LOCATION_ACCEPTANCE_THRESHOLD)) or 0,
            "low_data_quality":db.scalar(select(func.count(Opportunity.id)).where(masters,Opportunity.data_quality_score<.60)) or 0,
            "open_conflicts":db.scalar(select(func.count(OpportunityConflict.id)).where(OpportunityConflict.status=="OPEN")) or 0,
            "taxonomy_conflicts":db.scalar(select(func.count(OpportunityConflict.id)).where(OpportunityConflict.status=="OPEN",OpportunityConflict.conflict_type=="TAXONOMY_CONFLICT")) or 0,
            "field_conflicts":db.scalar(select(func.count(OpportunityConflict.id)).where(OpportunityConflict.status=="OPEN",OpportunityConflict.conflict_type=="FIELD_VALUE_CONFLICT")) or 0,
            "taxonomy_mappings":db.scalar(select(func.count(TaxonomyMapping.id))) or 0,
            "discovered_content_items":db.scalar(select(func.count(SourceContentItem.id))) or 0,
            "expired_opportunities":db.scalar(select(func.count(Opportunity.id)).where(masters,Opportunity.status.in_(["منتهية","منتهي","expired","EXPIRED"]))) or 0,
            "cancelled_opportunities":db.scalar(select(func.count(Opportunity.id)).where(masters,Opportunity.status.in_(["ملغاة","ملغي","CANCELLED","CANCELED"]))) or 0,
            "possibly_removed_opportunities":db.scalar(select(func.count(Opportunity.id)).where(masters,Opportunity.status.in_(["أزيلت من المصدر","ازيلت من المصدر","REMOVED_FROM_SOURCE","DELETED_FROM_SOURCE"]))) or 0,
            "incomplete_sources":db.scalar(select(func.count(Source.id)).where(Source.enabled.is_(True),Source.technical_health!="HEALTHY")) or 0,
            "limited_coverage_sources":db.scalar(select(func.count(Source.id)).where(Source.enabled.is_(True),Source.coverage_status.in_(["PUBLIC_COVERAGE_LIMITED","PRIVATE_API_REQUIRED","AUTHENTICATED_SOURCE_REQUIRED","PARTIAL_OFFICIAL_COVERAGE"]))) or 0,
            "source_errors":db.scalar(select(func.count(SourceError.id))) or 0,
        }}

@app.get("/api/admin/raw-records")
def raw_records(x_admin_token:str|None=Header(default=None),limit:int=Query(100,ge=1,le=500)):
    admin_auth(x_admin_token)
    with SessionLocal() as db:
        rows=db.scalars(select(SourceOpportunity).options(selectinload(SourceOpportunity.source)).order_by(SourceOpportunity.last_seen_at.desc()).limit(limit)).all()
        return [{"id":r.id,"source":r.source.source_name_ar,"source_key":r.source.source_key,"title":r.source_title,"url":r.source_url,"hash":r.content_hash,"source_sector":r.source_sector,"source_activity":r.source_activity,"source_sub_activity":r.source_sub_activity,"source_subsector":r.source_subsector,"normalized_sector":r.normalized_sector,"normalized_subsector":r.normalized_subsector,"raw":r.raw_data_json,"last_seen":dt(r.last_seen_at)} for r in rows]

@app.get("/api/admin/source-content")
def source_content(source:str="ahda",x_admin_token:str|None=Header(default=None),limit:int=Query(300,ge=1,le=1000)):
    admin_auth(x_admin_token)
    with SessionLocal() as db:
        source_row=db.scalar(select(Source).where(Source.source_key==source))
        if not source_row:raise HTTPException(404,"المصدر غير موجود")
        from .models import SourceContentItem
        rows=db.scalars(select(SourceContentItem).where(SourceContentItem.source_id==source_row.id).order_by(SourceContentItem.extracted_at.desc()).limit(limit)).all()
        return [{"url":r.url,"title":r.title,"publication_date":r.publication_date,"content_type":r.content_type,"description":r.extracted_description,"attachments":r.attachments_json,"keywords":r.detected_keywords_json,"fingerprint":r.fingerprint,"extracted_at":dt(r.extracted_at),"material_change":r.material_change} for r in rows]

@app.get("/api/admin/duplicates")
def duplicates(x_admin_token:str|None=Header(default=None)):
    admin_auth(x_admin_token)
    with SessionLocal() as db:
        return [{"id":d.id,"left_id":d.left_opportunity_id,"right_id":d.right_opportunity_id,"left_title":db.get(Opportunity,d.left_opportunity_id).title_ar,"right_title":db.get(Opportunity,d.right_opportunity_id).title_ar,"score":d.confidence_score,"status":d.status,"explanation":d.explanation_json or {}} for d in db.scalars(select(DuplicateCandidate).where(DuplicateCandidate.status=="PENDING")).all()]

@app.get("/api/admin/location-reviews")
def location_reviews(x_admin_token:str|None=Header(default=None)):
    admin_auth(x_admin_token)
    with SessionLocal() as db:
        rows=db.scalars(select(LocationReview).where(LocationReview.status=="PENDING").order_by(LocationReview.confidence_score.desc())).all()
        return [{"id":r.id,"source":db.get(Source,r.source_id).source_name_ar,"title":r.title,"sector":r.sector,"location":r.source_location,"description":r.description,"latitude":r.latitude,"longitude":r.longitude,"evidence":r.evidence,"score":r.confidence_score,"reason":r.reason,"url":(db.get(SourceOpportunity,r.source_record_id).source_url if r.source_record_id else "")} for r in rows]

@app.get("/api/admin/qualification-reviews")
def qualification_reviews(x_admin_token:str|None=Header(default=None)):
    admin_auth(x_admin_token)
    with SessionLocal() as db:
        rows=db.scalars(select(QualificationReview).where(QualificationReview.status=="PENDING").order_by(QualificationReview.created_at.desc())).all()
        return [{"id":r.id,"source":db.get(Source,r.source_id).source_name_ar,"title":r.title,"url":r.source_url,
            "proposed_type":r.proposed_type,"reason":r.reason,"status":r.status} for r in rows]

@app.get("/api/admin/review-queue")
def review_queue(x_admin_token:str|None=Header(default=None),domain:str=Query("all"),status_filter:str=Query("OPEN",alias="status"),limit:int=Query(500,ge=1,le=1000),
                 priority:str|None=None,source_filter:str|None=None,disposition:str|None=None,min_age:int|None=None,max_age:int|None=None,
                 exclude_source_recheck:bool=False,master_status:str|None=None,evidence_status:str|None=None):
    """Unified logical review inventory; status is canonical OPEN or RESOLVED."""
    admin_auth(x_admin_token)
    domains={"duplicate","location","qualification","field_conflict","taxonomy_conflict"}
    field_labels={"opportunity_owner":"الجهة المالكة","location_description":"الموقع التفصيلي","title_ar":"العنوان العربي",
        "land_area_sqm":"المساحة","normalized_title":"العنوان المعياري","sector":"القطاع","short_description":"الوصف المختصر",
        "full_description":"الوصف الكامل","activity":"النشاط","sub_activity":"النشاط الفرعي","opportunity_type":"نوع الفرصة",
        "investment_model":"نموذج الاستثمار","status":"الحالة","submission_deadline":"موعد التقديم","contract_duration_years":"مدة العقد","investment_value":"القيمة الاستثمارية"}
    if domain!="all" and domain not in domains:raise HTTPException(422,"Unsupported review domain")
    if status_filter not in ("OPEN","RESOLVED","ALL"):raise HTTPException(422,"Unsupported review status")
    def wanted(raw):return status_filter=="ALL" or (status_filter=="OPEN" and raw in ("PENDING","OPEN")) or (status_filter=="RESOLVED" and raw not in ("PENDING","OPEN"))
    now=utcnow();items=[]
    with SessionLocal() as db:
        if domain in ("all","duplicate"):
            for row in db.scalars(select(DuplicateCandidate).order_by(DuplicateCandidate.created_at.desc()).limit(limit)).all():
                if not wanted(row.status):continue
                a=db.get(Opportunity,row.left_opportunity_id);b=db.get(Opportunity,row.right_opportunity_id);created=row.created_at
                items.append({"id":row.id,"domain":"duplicate","status":"OPEN" if row.status=="PENDING" else "RESOLVED","source_status":row.status,
                    "created_at":dt(created),"master_ids":[row.left_opportunity_id,row.right_opportunity_id],"title":f"{a.title_ar if a else 'سجل غير متاح'} ↔ {b.title_ar if b else 'سجل غير متاح'}",
                    "reason_key":"DUPLICATE_IDENTITY_AMBIGUITY","reason":"candidate_match","reason_label":"تشابه في هوية الفرصة يتطلب مراجعة",
                    "evidence":{"confidence_score":row.confidence_score,"explanation":row.explanation_json or {}},"url":None})
        if domain in ("all","location"):
            for row in db.scalars(select(LocationReview).order_by(LocationReview.created_at.desc()).limit(limit)).all():
                if not wanted(row.status):continue
                source=db.get(Source,row.source_id);record=db.get(SourceOpportunity,row.source_record_id) if row.source_record_id else None;created=row.created_at
                items.append({"id":row.id,"domain":"location","status":"OPEN" if row.status=="PENDING" else "RESOLVED","source_status":row.status,
                    "created_at":dt(created),"master_ids":[record.master_opportunity_id] if record and record.master_opportunity_id else [],"title":row.title,
                    "reason_key":"LOCATION_EVIDENCE_AMBIGUITY","reason":row.reason or "location_review","reason_label":"تحقق من دليل الموقع ونطاق الأحساء",
                    "source":source.source_name_ar if source else None,"source_record_id":row.source_record_id,
                    "evidence":{"location":row.source_location,"evidence":row.evidence,"description":row.description,"score":row.confidence_score},"url":record.source_url if record else None})
        if domain in ("all","qualification"):
            for row in db.scalars(select(QualificationReview).order_by(QualificationReview.created_at.desc()).limit(limit)).all():
                if not wanted(row.status):continue
                source=db.get(Source,row.source_id);record=db.get(SourceOpportunity,row.source_record_id) if row.source_record_id else None;created=row.created_at
                items.append({"id":row.id,"domain":"qualification","status":"OPEN" if row.status=="PENDING" else "RESOLVED","source_status":row.status,
                    "created_at":dt(created),"master_ids":[record.master_opportunity_id] if record and record.master_opportunity_id else [],"title":row.title,
                    "reason_key":"INVESTMENT_ELIGIBILITY_AMBIGUITY","reason":row.reason or "qualification_review","reason_label":"تحقق من أهلية الفرصة الاستثمارية",
                    "source":source.source_name_ar if source else None,"source_record_id":row.source_record_id,
                    "evidence":{"proposed_type":row.proposed_type},"url":row.source_url})
        if domain in ("all","field_conflict","taxonomy_conflict"):
            query=select(OpportunityConflict).order_by(OpportunityConflict.detected_at.desc()).limit(limit)
            for row in db.scalars(query).all():
                case_domain="taxonomy_conflict" if row.conflict_type=="TAXONOMY_CONFLICT" else "field_conflict"
                if domain not in ("all",case_domain) or not wanted(row.status):continue
                master=db.get(Opportunity,row.opportunity_id);source=db.get(Source,row.source_id);record=db.get(SourceOpportunity,row.source_record_id);created=row.detected_at
                reason_key={"contract_duration_years":"DURATION_UNIT_OR_SEMANTICS_UNVERIFIED","investment_value":"INVESTMENT_VALUE_ZERO_WITHOUT_UNIT_OR_MEANING"}.get(row.field_name,"STANDARDIZATION_EVIDENCE_REVIEW") if row.conflict_type=="STANDARDIZATION_REVIEW" else f"FIELD_CONFLICT:{row.field_name}"
                reason_label={"DURATION_UNIT_OR_SEMANTICS_UNVERIFIED":"وحدة أو دلالة مدة المصدر غير موثقة","INVESTMENT_VALUE_ZERO_WITHOUT_UNIT_OR_MEANING":"قيمة مصدر صفرية بلا عملة أو دلالة موثقة"}.get(reason_key,f"تعارض في {field_labels.get(row.field_name,row.field_name)}")
                items.append({"id":row.id,"domain":case_domain,"status":"OPEN" if row.status=="OPEN" else "RESOLVED","source_status":row.status,
                    "created_at":dt(created),"master_ids":[row.opportunity_id],"title":master.title_ar if master else "فرصة غير متاحة",
                    "reason_key":reason_key,"reason":reason_key,
                    "reason_label":reason_label,"field":row.field_name,"source":source.source_name_ar if source else None,"source_record_id":row.source_record_id,
                    "evidence":{"selected":row.selected_value,"conflicting":row.conflicting_value,"source_url":record.source_url if record else None,
                        "mapping_rule":((((record.standardized_data_json or {}).get("fields") or {}).get(row.field_name) or {}).get("rule") if record else None),
                        "review_flags":((((record.standardized_data_json or {}).get("fields") or {}).get(row.field_name) or {}).get("review_flags",[]) if record else []),
                        "guarded_standardization":row.conflict_type=="STANDARDIZATION_REVIEW"},"url":record.source_url if record else None})
        items.sort(key=lambda item:(item["created_at"] or ""),reverse=True)
        master_ids={mid for item in items for mid in item["master_ids"]}
        master_rows={mid:db.get(Opportunity,mid) for mid in master_ids}
        enrichment_events=db.scalars(select(AuditEvent).where(AuditEvent.event_type.in_(("REVIEW_EVIDENCE_ENRICHED","REVIEW_SOURCE_RECHECK_REQUESTED")))
            .order_by(AuditEvent.id.desc()).limit(2000)).all()
        dispositions={}
        for event in enrichment_events:
            payload=event.after_json or {}
            if isinstance(payload,dict) and payload.get("review_id") is not None:
                key=(payload.get("review_type"),int(payload["review_id"]))
                roles={str(evidence.get("evidence_role") or "") for evidence in payload.get("evidence",[]) if isinstance(evidence,dict)}
                classification=payload.get("classification") or payload.get("disposition")
                dispositions.setdefault(key,"SOURCE_RECHECK_REQUIRED" if classification=="SOURCE_RECHECK_REQUIRED"
                    or "SOURCE_SCOPE_ONLY_NO_PROJECT_SITE" in roles else payload.get("disposition"))
        for item in items:
            event_type={"field_conflict":"OPPORTUNITY_CONFLICT","taxonomy_conflict":"OPPORTUNITY_CONFLICT",
                "location":"LOCATION_REVIEW","qualification":"QUALIFICATION_REVIEW"}.get(item["domain"])
            item["disposition"]=dispositions.get((event_type,item["id"]),"HUMAN_REVIEW_REQUIRED")
            source_record=db.get(SourceOpportunity,item.get("source_record_id")) if item.get("source_record_id") else None
            source_entity=db.get(Source,source_record.source_id) if source_record else None
            if item["disposition"]!="SOURCE_RECHECK_REQUIRED" and item["domain"] in ("field_conflict","taxonomy_conflict") and item.get("field")=="investment_value" and str(item.get("evidence",{}).get("conflicting"))=="0" and source_entity and source_entity.source_key=="invest-saudi":
                source_record=db.get(SourceOpportunity,item.get("source_record_id"));master=db.get(Opportunity,(item.get("master_ids") or [None])[0])
                raw=source_record.raw_data_json if source_record and isinstance(source_record.raw_data_json,dict) else {}
                if str(raw.get("investmentSize")).strip() in ("0","0.0") and (not master or not master.currency): item["disposition"]="SOURCE_RECHECK_REQUIRED"
            if item["disposition"]!="SOURCE_RECHECK_REQUIRED" and item["domain"]=="location":
                source_record=db.get(SourceOpportunity,item.get("source_record_id"));raw=source_record.raw_data_json if source_record and isinstance(source_record.raw_data_json,dict) else {}
                if (raw.get("source_scope")=="SOURCE_SCOPE_AL_AHSA" and not (raw.get("project_location") or raw.get("location"))): item["disposition"]="SOURCE_RECHECK_REQUIRED"
            item["evidence_status"]="SOURCE_RECHECK_REQUIRED" if item["disposition"]=="SOURCE_RECHECK_REQUIRED" else "EVIDENCE_AVAILABLE" if item.get("source_record_id") or item.get("evidence",{}).get("explanation") else "EVIDENCE_LIMITED"
            created=datetime.fromisoformat(item["created_at"].replace("Z","+00:00")) if item["created_at"] else now
            if created.tzinfo is None:created=created.replace(tzinfo=timezone.utc)
            item["age_days"]=max(0,(now-created).days)
            masters=[master_rows.get(mid) for mid in item["master_ids"]]
            published=any(master and master.status in ACTIVE_STATUSES for master in masters)
            deadlines=[]
            for master in masters:
                if master and master.submission_deadline:
                    try:deadlines.append((date.fromisoformat(master.submission_deadline)-local_today()).days)
                    except (ValueError,TypeError):pass
            item["priority"]="P1" if published and any(0<=days<=7 for days in deadlines) else "P2" if published else "P3" if item["domain"] in ("duplicate","field_conflict","taxonomy_conflict") else "P4"
            item["entity_state"]=[{"id":mid,"merged_into_id":master_rows[mid].merged_into_id if master_rows.get(mid) else None,
                                   "status":master_rows[mid].status if master_rows.get(mid) else None} for mid in item["master_ids"]]
        if exclude_source_recheck: items=[item for item in items if item["disposition"]!="SOURCE_RECHECK_REQUIRED"]
        if priority: items=[item for item in items if item.get("priority")==priority]
        if disposition=="ACTIONABLE": items=[item for item in items if item.get("disposition")!="SOURCE_RECHECK_REQUIRED"]
        elif disposition and disposition!="ALL": items=[item for item in items if item.get("disposition")==disposition]
        if source_filter: items=[item for item in items if item.get("source")==source_filter or any(source_filter==entry.get("source_key") for entry in item.get("sources",[]))]
        if min_age is not None: items=[item for item in items if item.get("age_days",0)>=min_age]
        if max_age is not None: items=[item for item in items if item.get("age_days",0)<=max_age]
        if master_status: items=[item for item in items if any(str(entity.get("status") or "")==master_status for entity in item.get("entity_state",[]))]
        if evidence_status: items=[item for item in items if item.get("evidence_status")==evidence_status]
        rank={"P1":1,"P2":2,"P3":3,"P4":4}
        items.sort(key=lambda item:(rank.get(item.get("priority"),9),-item.get("age_days",0),item.get("created_at") or ""))
        return items[:limit]

def _review_version_token(db, domain:str, review_id:int) -> str:
    """Fingerprint the review, evidence and linked Master state for optimistic locking."""
    payload={"domain":domain,"id":int(review_id)}
    if domain in ("field_conflict","taxonomy_conflict"):
        row=db.get(OpportunityConflict,review_id)
        if not row: raise HTTPException(404,"المراجعة غير موجودة")
        master=db.get(Opportunity,row.opportunity_id);source=db.get(SourceOpportunity,row.source_record_id)
        payload.update(status=row.status,field=row.field_name,selected=row.selected_value,conflicting=row.conflicting_value,
            detected_at=dt(row.detected_at),master_updated=dt(master.updated_at) if master else None,
            source_hash=source.content_hash if source else None,source_seen=dt(source.last_seen_at) if source else None)
    elif domain=="duplicate":
        row=db.get(DuplicateCandidate,review_id)
        if not row: raise HTTPException(404,"المراجعة غير موجودة")
        left=db.get(Opportunity,row.left_opportunity_id);right=db.get(Opportunity,row.right_opportunity_id)
        payload.update(status=row.status,created_at=dt(row.created_at),score=row.confidence_score,
            left_updated=dt(left.updated_at) if left else None,left_merged=left.merged_into_id if left else None,
            right_updated=dt(right.updated_at) if right else None,right_merged=right.merged_into_id if right else None)
    elif domain=="location":
        row=db.get(LocationReview,review_id)
        if not row: raise HTTPException(404,"المراجعة غير موجودة")
        source=db.get(SourceOpportunity,row.source_record_id) if row.source_record_id else None
        master=db.get(Opportunity,source.master_opportunity_id) if source and source.master_opportunity_id else None
        payload.update(status=row.status,created_at=dt(row.created_at),source_hash=source.content_hash if source else None,
            source_seen=dt(source.last_seen_at) if source else None,master_updated=dt(master.updated_at) if master else None)
    elif domain=="qualification":
        row=db.get(QualificationReview,review_id)
        if not row: raise HTTPException(404,"المراجعة غير موجودة")
        source=db.get(SourceOpportunity,row.source_record_id) if row.source_record_id else None
        payload.update(status=row.status,created_at=dt(row.created_at),source_hash=source.content_hash if source else None,
            source_seen=dt(source.last_seen_at) if source else None)
    else: raise HTTPException(422,"نوع المراجعة غير مدعوم")
    evidence_entity_type={"field_conflict":"OPPORTUNITY_CONFLICT","taxonomy_conflict":"OPPORTUNITY_CONFLICT",
        "location":"LOCATION_REVIEW","qualification":"QUALIFICATION_REVIEW"}.get(domain)
    if evidence_entity_type:
        evidence_event=db.scalar(select(AuditEvent).where(AuditEvent.event_type=="REVIEW_EVIDENCE_ENRICHED",
            AuditEvent.entity_type=="review_evidence",AuditEvent.entity_id==f"{evidence_entity_type}:{review_id}")
            .order_by(AuditEvent.id.desc()).limit(1))
        if evidence_event:
            evidence_payload=evidence_event.after_json if isinstance(evidence_event.after_json,dict) else {}
            evidence_encoded=json.dumps(evidence_payload,ensure_ascii=False,sort_keys=True,separators=(",",":"),default=str)
            payload["evidence_event_id"]=evidence_event.id
            payload["evidence_fingerprint"]=hashlib.sha256(evidence_encoded.encode("utf-8")).hexdigest()
    encoded=json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(",",":"),default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

def _require_review_version(db, domain:str, review_id:int, token:str|None):
    if not token:
        raise HTTPException(409,"تعذر التحقق من نسخة المراجعة؛ أعد تحميل الحالة ثم عاين القرار مجددًا.")
    if token!=_review_version_token(db,domain,review_id):
        raise HTTPException(409,"تم تحديث هذه الحالة منذ فتحها، يرجى مراجعة البيانات المحدثة.")

def _workbench_allowed_actions(item:dict, role:str):
    if item.get("status")!="OPEN" or role not in ("admin","analyst","admin_token"): return []
    if item.get("disposition")=="SOURCE_RECHECK_REQUIRED": return []
    domain=item.get("domain")
    if domain in ("field_conflict","taxonomy_conflict"):
        actions=[{"key":"keep","label":"اعتماد القيمة الحالية"},{"key":"use_source","label":"اعتماد قيمة المصدر"}]
        if item.get("evidence",{}).get("guarded_standardization"):
            actions=[{"key":"keep","label":"تأكيد بقاء القيمة الحالية"}]
        if domain=="taxonomy_conflict" and item.get("field")=="sector" and not _valid_canonical_sector(item.get("evidence",{}).get("conflicting")):
            actions=[action for action in actions if action["key"]!="use_source"]
        return actions
    if domain=="duplicate": return [{"key":"reject","label":"ليستا نفس الفرصة"},{"key":"merge","label":"نفس الفرصة — معاينة الدمج"}]
    if domain=="location": return [{"key":"accept","label":"تأكيد ارتباط الأحساء"},{"key":"reject","label":"رفض المطابقة المحلية"}]
    if domain=="qualification": return ([{"key":"accept","label":"اعتماد الأهلية"},{"key":"reject","label":"رفض الأهلية"}] if role in ("admin","admin_token") else [])
    return []

def _valid_canonical_sector(value):
    from .standardization import canonical_id as standard_sector_id
    return bool(value and standard_sector_id("sector",value)!="sector:unspecified")

def _workbench_sources(db, master_ids:list[int], field:str|None, include_raw:bool=False, source_record_id:int|None=None):
    # Location and qualification reviews can be created before a SourceOpportunity
    # is attached to a Master. Keep that review's own record visible in the workbench.
    source_scope=SourceOpportunity.master_opportunity_id.in_(master_ids or [-1])
    if source_record_id is not None:
        source_scope=or_(source_scope,SourceOpportunity.id==int(source_record_id))
    records=db.scalars(select(SourceOpportunity).where(source_scope)
        .options(selectinload(SourceOpportunity.source)).order_by(SourceOpportunity.id)).all()
    result=[]
    for record in records:
        raw=record.raw_data_json if isinstance(record.raw_data_json,dict) else {}
        standardized=record.standardized_data_json if isinstance(record.standardized_data_json,dict) else {}
        fields=(standardized.get("fields") or {}) if isinstance(standardized,dict) else {}
        field_data=fields.get(field,{}) if field else {}
        excerpt={key:raw.get(key) for key in ("description","attributes","source_taxonomy","sector","activity","sub_activity","investmentSize","status") if key in raw}
        link=resolve_source_link(record,record.source)
        item={"source_id":record.source_id,"source":record.source.source_name_ar if record.source else "مصدر غير معروف",
            "publisher":record.source.organization_name if record.source else None,
            "source_key":record.source.source_key if record.source else None,"source_record_id":record.id,
            "master_id":record.master_opportunity_id,
            "source_opportunity_id":record.source_opportunity_id,"raw_title":record.source_title,
            "raw_field_value":(raw.get(field) if field and field in raw else getattr(record,{"opportunity_owner":"source_owner","status":"raw_status","location_description":"raw_location"}.get(field,"source_"+field),None) if field else None),
            "normalized_value":field_data.get("value") if isinstance(field_data,dict) else None,
            "mapping_rule":field_data.get("rule") if isinstance(field_data,dict) else None,
            "observed_at":dt(record.last_seen_at),"source_state":record.canonical_status,
            "source_url":link.get("url"),"source_link_status":link.get("link_health"),"evidence_note":field_data.get("review_flags",[]) if isinstance(field_data,dict) else [],
            "raw_excerpt":excerpt}
        if include_raw: item["raw_payload"]=raw
        result.append(item)
    return result

def _workbench_recommendation(db, item:dict) -> dict:
    """Small, deterministic recommendations only when source authority is provable."""
    none={"action":None,"confidence":"NONE","reason":"لا توجد توصية آلية موثوقة","supporting_evidence":[],
          "contradictory_evidence":[],"rule":None,"label":None,"confidence_levels_available":["HIGH","MEDIUM","NONE"]}
    if item.get("status")!="OPEN" or item.get("disposition")=="SOURCE_RECHECK_REQUIRED":
        return {**none,"reason":"لا توجد توصية آلية موثوقة قبل اكتمال تحقق المصدر."}
    domain=item.get("domain")
    if domain not in ("field_conflict","taxonomy_conflict") or not item.get("field"):
        return {**none,"reason":"هذه الحالة تحتاج حكمًا بشريًا ولا تنطبق عليها قاعدة توصية معتمدة."}
    field=item["field"]
    record=db.get(SourceOpportunity,item.get("source_record_id")) if item.get("source_record_id") else None
    conflict=db.get(OpportunityConflict,int(item["id"]))
    master=db.get(Opportunity,conflict.opportunity_id) if conflict else None
    if not record or not conflict or not master or master.merged_into_id is not None:
        return {**none,"reason":"لا تتوفر سلسلة أدلة مكتملة لإصدار توصية."}
    standardized=record.standardized_data_json if isinstance(record.standardized_data_json,dict) else {}
    field_data=((standardized.get("fields") or {}).get(field) or {})
    mapped=field_data.get("value")
    if mapped in (None,"") or str(mapped).strip()!=str(conflict.conflicting_value).strip():
        return {**none,"reason":"قيمة المصدر ليست مثبتة كقيمة معيارية مطابقة للتعارض."}
    source=db.get(Source,record.source_id)
    source_priority=source.priority if source else None
    current_provenance=db.scalars(select(FieldProvenance).where(
        FieldProvenance.opportunity_id==master.id,FieldProvenance.field_name==field
    ).order_by(FieldProvenance.captured_at.desc()).limit(20)).all()
    current_priorities=[]
    current_values=[]
    for provenance in current_provenance:
        provenance_source=db.get(Source,provenance.source_id)
        if provenance_source:
            current_priorities.append((provenance_source.priority,provenance.source_id,provenance.selected_value))
            current_values.append(str(provenance.selected_value).strip())
    # Source.priority is the platform's accepted authority ordering (lower wins).
    # If current-value authority is absent or tied, keep the decision with the analyst.
    if source_priority is None or not current_priorities:
        return {**none,"reason":"ترتيب موثوقية المصدر لا يحسم التعارض بوضوح؛ يلزم تقييم المحلل."}
    if field_data.get("mapping_status")!="MAPPED" or not field_data.get("rule"):
        return {**none,"reason":"حالة توحيد القيمة لا تسمح بتوصية حتمية."}
    canonical_best=min(priority for priority,_,_ in current_priorities)
    current_value=str(getattr(master,field,None)).strip()
    current_evidence=[{"source_id":source_id,"source_priority":priority,"value":value}
        for priority,source_id,value in current_priorities]
    source_evidence={"source_id":record.source_id,"source_record_id":record.id,"source_priority":source_priority,
        "field":field,"value":mapped,"mapping_rule":field_data.get("rule"),"mapping_status":field_data.get("mapping_status"),
        "content_hash":record.content_hash}
    if source_priority < canonical_best:
        action="use_source";confidence="HIGH"
        reason="قيمة المصدر موحدة صراحةً، ومصدرها أعلى موثوقية من جميع مصادر توثيق القيمة الحالية."
        rule="AUTHORITATIVE_SOURCE_OUTRANKS_CANONICAL_PROVENANCE_V1"
        supporting=[source_evidence];contradictory=current_evidence
    elif canonical_best < source_priority <= canonical_best+1 and set(current_values)=={current_value}:
        action="keep";confidence="MEDIUM"
        reason="القيمة الحالية مدعومة بمصدر أعلى موثوقية، بينما المصدر المتعارض مباشر لكنه أقل بدرجة واحدة."
        rule="CANONICAL_PROVENANCE_OUTRANKS_SOURCE_V1"
        supporting=current_evidence;contradictory=[source_evidence]
    else:
        return {**none,"reason":"ترتيب موثوقية المصدر لا يحسم التعارض بوضوح؛ يلزم تقييم المحلل."}
    return {"action":action,"confidence":confidence,"label":"اعتماد قيمة المصدر" if action=="use_source" else "الإبقاء على القيمة الحالية",
        "reason":reason,
        "supporting_evidence":supporting,"contradictory_evidence":contradictory,"rule":rule,
        "basis":{"source_priority":source_priority,"canonical_priorities":sorted({p for p,_,_ in current_priorities})},
        "confidence_levels_available":["HIGH","MEDIUM","NONE"]}

def _workbench_timeline(db,item,entity_type:str,entity_id:int):
    events=db.scalars(select(AuditEvent).where(AuditEvent.entity_type==entity_type,AuditEvent.entity_id==str(entity_id))
        .order_by(AuditEvent.created_at.asc(),AuditEvent.id.asc()).limit(300)).all()
    event_types={
        "REVIEW_ASSIGNED":("ASSIGNED","إسناد المراجعة"),
        "REVIEW_EVIDENCE_ENRICHED":("EVIDENCE_ENRICHED","إثراء الأدلة"),
        "REVIEW_RECOMMENDATION_SHOWN":("RECOMMENDATION_SHOWN","عرض توصية النظام"),
        "REVIEW_DECISION_PREVIEWED":("DECISION_PREVIEWED","معاينة القرار"),
        "REVIEW_REOPENED":("REOPENED","إعادة فتح المراجعة"),
        "REVIEW_FIELD_KEEP":("RESOLVED","حسم: الإبقاء على القيمة"),
        "REVIEW_FIELD_USE_SOURCE":("RESOLVED","حسم: اعتماد قيمة المصدر"),
        "REVIEW_DUPLICATE_REJECTED":("RESOLVED","حسم: فرصتان مختلفتان"),
        "REVIEW_DUPLICATE_MERGED":("RESOLVED","حسم: دمج التكرار"),
        "REVIEW_DUPLICATE_UNDONE":("MERGE_UNDONE","التراجع عن دمج التكرار"),
        "REVIEW_LOCATION_ACCEPTED":("RESOLVED","حسم مراجعة الموقع: اعتماد"),
        "REVIEW_LOCATION_REJECTED":("RESOLVED","حسم مراجعة الموقع: رفض"),
        "REVIEW_QUALIFICATION_ACCEPTED":("RESOLVED","حسم مراجعة الأهلية: اعتماد"),
        "REVIEW_QUALIFICATION_REJECTED":("RESOLVED","حسم مراجعة الأهلية: رفض"),
        "REVIEW_SECTOR_INFERENCE_ACCEPTED":("RESOLVED","اعتماد استدلال القطاع"),
    }
    timeline=[]
    evidence_events=db.scalars(select(AuditEvent).where(AuditEvent.entity_type=="review_evidence",
        AuditEvent.entity_id==f"{entity_type}:{entity_id}").order_by(AuditEvent.created_at.asc(),AuditEvent.id.asc()).limit(100)).all()
    for event in sorted([*events,*evidence_events],key=lambda e:(dt(e.created_at) or "",e.id)):
        after=event.after_json if isinstance(event.after_json,dict) else {}
        before=event.before_json if isinstance(event.before_json,dict) else {}
        kind,label=event_types.get(event.event_type,(after.get("decision") or event.event_type,event.event_type))
        actor=(event.request_metadata or {}).get("actor")
        if actor is None and event.user_id is None:
            actor="غير متوفر في السجل التاريخي" if event.event_type.startswith("REVIEW_") else "النظام"
        timeline.append({"event_type":kind,"label":label,"actor":actor,"timestamp":dt(event.created_at),
            "description":after.get("reason") or after.get("reopen_reason") or after.get("description") or label,
            "previous_value":before.get("value",before.get("status")),"new_value":after.get("value",after.get("status")),
            "evidence_reference":(after.get("evidence") or {}).get("source_record_id") if isinstance(after.get("evidence"),dict) else None,
            "legacy_incomplete":False,"event_id":f"audit:{event.id}","_sort_kind":1,"_sort_id":event.id,"_sort_part":0})
        recommendation=((after.get("evidence") or {}).get("recommendation") if isinstance(after.get("evidence"),dict) else after)
        if event.event_type=="REVIEW_EVIDENCE_ENRICHED":
            classification=after.get("classification") or after.get("disposition")
            timeline[-1]["event_type"]="SOURCE_RECHECK_STATUS_CHANGED" if classification else "EVIDENCE_ENRICHED"
            timeline[-1]["label"]="تغير حالة تحقق المصدر" if classification else "إثراء الأدلة"
            timeline[-1]["description"]=classification or timeline[-1]["description"]
        if isinstance(recommendation,dict) and recommendation.get("disposition") in ("FOLLOWED_RECOMMENDATION","OVERRIDDEN_RECOMMENDATION"):
            followed=recommendation.get("disposition")=="FOLLOWED_RECOMMENDATION"
            timeline.append({"event_type":"RECOMMENDATION_FOLLOWED" if followed else "RECOMMENDATION_OVERRIDDEN",
                "label":"اتباع توصية النظام" if followed else "تجاوز توصية النظام","actor":actor,"timestamp":dt(event.created_at),
                "description":recommendation.get("override_reason") or recommendation.get("reason") or "",
                "previous_value":recommendation.get("action"),"new_value":after.get("decision"),"evidence_reference":None,"legacy_incomplete":False,
                "event_id":f"audit:{event.id}:recommendation","_sort_kind":1,"_sort_id":event.id,"_sort_part":1})
    system_events=db.scalars(select(SystemEvent).where(SystemEvent.event_type.like("REVIEW%"))
        .order_by(SystemEvent.created_at.asc(),SystemEvent.id.asc()).limit(2000)).all()
    for event in system_events:
        payload=event.payload if isinstance(event.payload,dict) else {}
        matches=(payload.get("review_id")==entity_id or payload.get("prior_review_id")==entity_id)
        if not matches:continue
        timeline.append({"event_type":"SYSTEM_REEVALUATION" if "REOPENED" not in event.event_type else "REOPENED",
            "label":"إعادة تقييم آلية" if "REOPENED" not in event.event_type else "إعادة فتح بعد دليل مصدر جديد",
            "actor":"النظام","timestamp":dt(event.created_at),"description":payload.get("reason") or event.event_type,
            "previous_value":None,"new_value":None,"evidence_reference":payload.get("source_record_id"),"legacy_incomplete":False,
            "event_id":f"system:{event.id}","_sort_kind":2,"_sort_id":event.id,"_sort_part":0})
    created=item.get("created_at")
    if created:
        timeline.append({"event_type":"CREATED","label":"إنشاء المراجعة","actor":None,"timestamp":created,
            "description":"أُنشئت حالة المراجعة.","previous_value":None,"new_value":"OPEN","evidence_reference":None,"legacy_incomplete":False,
            "event_id":f"created:{entity_id}","_sort_kind":0,"_sort_id":int(entity_id),"_sort_part":0})
    # Existing domain tables do not consistently retain a resolution timestamp. Do not infer it.
    if item.get("status")!="OPEN" and not any(event.event_type not in ("REVIEW_RECOMMENDATION_SHOWN","REVIEW_EVIDENCE_ENRICHED") for event in events):
        timeline.append({"event_type":"LEGACY_DECISION_INCOMPLETE","label":"قرار تاريخي — بعض بيانات التدقيق غير متوفرة",
            "actor":"غير متوفر","timestamp":None,"description":"لا تتوفر هوية المنفذ أو وقت القرار في السجل التاريخي.",
            "previous_value":None,"new_value":item.get("source_status"),"evidence_reference":None,"legacy_incomplete":True,
            "event_id":None,"_sort_kind":9,"_sort_id":0,"_sort_part":0})
    timeline.sort(key=lambda event:(event.get("timestamp") is None,event.get("timestamp") or "",
        event.get("_sort_kind",9),event.get("_sort_id",0),event.get("_sort_part",0)))
    for event in timeline:
        event["historical_unknown_time"]=event.get("timestamp") is None
        event["timeline_group"]="HISTORICAL_UNKNOWN_TIME" if event["historical_unknown_time"] else "CHRONOLOGICAL"
        event.pop("_sort_kind",None);event.pop("_sort_id",None);event.pop("_sort_part",None)
    return timeline

def _workbench_detail(db, item:dict, *, include_raw:bool=False):
    domain=item["domain"];rid=int(item["id"]);field=item.get("field")
    master_ids=[int(value) for value in item.get("master_ids",[]) if value is not None]
    sources=_workbench_sources(db,master_ids,field,include_raw=include_raw,source_record_id=item.get("source_record_id"))
    item={**item,"linked_source_count":len(sources),"sources":sources}
    masters=[]
    for master_id in master_ids:
        master=db.get(Opportunity,master_id)
        if master:
            masters.append({"id":master.id,"canonical_id":master.canonical_id,"title":master.title_ar,"status":master.status,
                "owner":master.opportunity_owner,"publisher":None,"publication_platform":master.primary_publication_platform,"sector":master.sector,
                "activity":master.activity,"sub_activity":master.sub_activity,"location":master.location_description,
                "city":master.city,"district":master.district,"latitude":master.latitude,"longitude":master.longitude,
                "area":master.land_area_sqm,"area_unit":"m²" if master.land_area_sqm is not None else None,
                "investment_value":master.investment_value,"currency":master.currency,"duration":master.contract_duration_years,
                "duration_unit":"year" if master.contract_duration_years is not None else None,"deadline":master.submission_deadline,
                "updated_at":dt(master.updated_at)})
    item["masters"]=masters
    current=None;provenance=[];history=[]
    if domain in ("field_conflict","taxonomy_conflict"):
        conflict=db.get(OpportunityConflict,rid);master=db.get(Opportunity,conflict.opportunity_id) if conflict else None
        if conflict and master:
            current=getattr(master,conflict.field_name,None)
            p_rows=db.scalars(select(FieldProvenance).where(FieldProvenance.opportunity_id==master.id,FieldProvenance.field_name==field)
                .order_by(FieldProvenance.captured_at.desc()).limit(10).options(selectinload(FieldProvenance.source))).all()
            provenance=[{"value":p.selected_value,"source":p.source.source_name_ar if p.source else None,"source_id":p.source_id,
                "source_record_id":p.source_record_id,"captured_at":dt(p.captured_at),"confidence":p.confidence} for p in p_rows]
            changes=db.scalars(select(ChangeHistory).where(ChangeHistory.opportunity_id==master.id,ChangeHistory.changed_field==field)
                .order_by(ChangeHistory.detected_at.desc()).limit(20)).all()
            history=[{"value":c.new_value,"previous_value":c.previous_value,"source_id":c.source_id,"observed_at":dt(c.detected_at),"current":index==0 and getattr(master,field,None)==c.new_value} for index,c in enumerate(reversed(changes))]
            # Include source observation versions only for this source and field; they are ordered by time, never interpreted as authority.
            record=db.get(SourceOpportunity,conflict.source_record_id)
            if record:
                obs=db.scalars(select(SourceObservation).where(SourceObservation.source_opportunity_id==record.id)
                    .order_by(SourceObservation.last_seen_at.desc()).limit(20)).all()
                for observation in reversed(obs):
                    raw=observation.raw_data_json if isinstance(observation.raw_data_json,dict) else {}
                    raw_value=raw.get(field)
                    if raw_value is None and field=="opportunity_owner": raw_value=raw.get("owner")
                    if raw_value is None and field in ("sector","activity","sub_activity"): raw_value=(raw.get("source_taxonomy") or {}).get(field)
                    if raw_value is not None: history.append({"value":raw_value,"source_id":record.source_id,"source_record_id":record.id,"observed_at":dt(observation.last_seen_at),"observation_id":observation.id,"historical":True})
            history.sort(key=lambda row:row.get("observed_at") or "")
    competing=[]
    for source in sources:
        value=source.get("normalized_value")
        if value in (None,""): value=source.get("raw_field_value")
        competing.append({"value":value,"source":source.get("source"),"source_record_id":source.get("source_record_id"),"observed_at":source.get("observed_at")})
    present=[" ".join(str(row["value"]).split()).casefold() for row in competing if row.get("value") not in (None,"")]
    if len(present)>1: assessment="AGREEMENT" if len(set(present))==1 else "CONFLICT"
    elif present: assessment="MISSING_VALUE" if len(competing)>1 else "SINGLE_SOURCE"
    else: assessment="MISSING_VALUE"
    item["comparison"]={"current_value":current,"competing_values":competing,
        "assessment":assessment,"canonical_provenance":provenance}
    item["history"]=history
    entity_type={"duplicate":"duplicate_candidate","location":"location_review","qualification":"qualification_review","field_conflict":"opportunity_conflict","taxonomy_conflict":"opportunity_conflict"}.get(domain)
    item["timeline"]=_workbench_timeline(db,item,entity_type,rid) if entity_type else []
    item["version_token"]=_review_version_token(db,domain,rid)
    item["recommendation"]=_workbench_recommendation(db,item)
    item["recommendation_version"]=hashlib.sha256(json.dumps({"version_token":item["version_token"],
        "recommendation":item["recommendation"]},ensure_ascii=False,sort_keys=True,separators=(",",":"),default=str).encode("utf-8")).hexdigest()
    role=(request_context.get().get("user") or {}).get("role")
    item["allowed_actions"]=_workbench_allowed_actions(item,role or "admin_token")
    item["reopen_allowed"]=(item.get("status")=="RESOLVED" and (role or "admin_token") in ("admin","analyst","admin_token")
        and item.get("source_status") in _review_closed_statuses(domain))
    # Preserve the queue's evidence disposition, particularly SOURCE_RECHECK_REQUIRED.
    # The queue has already computed it from the latest enrichment and source scope.
    item["disposition"]=item.get("disposition") or ("HUMAN_REVIEW_REQUIRED" if item.get("status")=="OPEN" else "RESOLVED")
    return item

def _require_actionable_review(token:str|None, domain:str, review_id:int):
    """Keep source-recheck cases out of all direct human decision endpoints."""
    rows=review_queue(token,domain,"OPEN",1000)
    item=next((row for row in rows if int(row["id"])==int(review_id)),None)
    if not item:
        raise HTTPException(409,"الحالة لم تعد مفتوحة؛ أعد تحميل الطابور.")
    if item.get("disposition")=="SOURCE_RECHECK_REQUIRED":
        raise HTTPException(409,"هذه الحالة تتطلب تحققًا من المصدر ولا تسمح بقرار حسم حاليًا.")
    return item

def _current_recommendation_snapshot(db,token,domain,review_id):
    rows=review_queue(token,domain,"OPEN",1000)
    item=next((row for row in rows if int(row["id"])==int(review_id)),None)
    if not item: raise HTTPException(409,"الحالة لم تعد مفتوحة؛ أعد تحميل الطابور.")
    detail=_workbench_detail(db,item)
    recommendation=detail["recommendation"]
    snapshot={key:recommendation.get(key) for key in ("action","confidence","reason","supporting_evidence","contradictory_evidence","rule")}
    snapshot["version"]=detail["recommendation_version"]
    return snapshot

def _decision_recommendation(db,token,domain,review_id,action,payload):
    snapshot=_current_recommendation_snapshot(db,token,domain,review_id)
    if payload.recommendation_version and payload.recommendation_version!=snapshot["version"]:
        raise HTTPException(409,"تغيرت التوصية أو أدلتها منذ عرضها؛ أعد تحميل الحالة وراجع التوصية مجددًا.")
    has_recommendation=bool(snapshot.get("action"))
    if has_recommendation and not payload.recommendation_version:
        raise HTTPException(409,"أعد تحميل توصية النظام قبل حفظ القرار.")
    follows=has_recommendation and action==snapshot["action"]
    reason=(payload.recommendation_override_reason or "").strip()
    valid_override_reasons={"مصدر أحدث وأكثر موثوقية","السياق لا تدعمه التوصية","تحقق يدوي إضافي","تعارض في الأدلة","سبب آخر"}
    if has_recommendation and not follows and not reason:
        raise HTTPException(422,"أدخل سبب تجاوز توصية النظام قبل حفظ القرار.")
    if has_recommendation and not follows and reason not in valid_override_reasons:
        raise HTTPException(422,"اختر سببًا معتمدًا لتجاوز توصية النظام.")
    if follows:
        snapshot["disposition"]="FOLLOWED_RECOMMENDATION"
    elif has_recommendation:
        snapshot["disposition"]="OVERRIDDEN_RECOMMENDATION"
        snapshot["override_reason"]=reason
        snapshot["analyst_note"]=(payload.analyst_note or "").strip() or None
    else:
        snapshot["disposition"]="NO_RECOMMENDATION"
    return snapshot

def _review_model(domain):
    return {"duplicate":DuplicateCandidate,"location":LocationReview,"qualification":QualificationReview,
            "field_conflict":OpportunityConflict,"taxonomy_conflict":OpportunityConflict}.get(domain)

def _review_open_status(domain):
    return "PENDING" if domain in ("duplicate","location","qualification") else "OPEN"

def _review_closed_statuses(domain):
    return {"duplicate":{"MERGED","REJECTED"},"location":{"ACCEPTED","REJECTED"},
        "qualification":{"ACCEPTED","REJECTED"},"field_conflict":{"RESOLVED_SOURCE","RESOLVED_KEEP"},
        "taxonomy_conflict":{"RESOLVED_SOURCE","RESOLVED_KEEP","RESOLVED_INFERENCE"}}.get(domain,set())

def _review_audit_entity(domain):
    return {"duplicate":"duplicate_candidate","location":"location_review","qualification":"qualification_review",
        "field_conflict":"opportunity_conflict","taxonomy_conflict":"opportunity_conflict"}[domain]

@app.post("/api/admin/review-workbench/{domain}/{review_id}/recommendation-shown")
def review_workbench_recommendation_shown(domain:str,review_id:int,version_token:str=Query(...,min_length=64,max_length=64),x_admin_token:str|None=Header(default=None)):
    identity=request_context.get().get("user")
    if identity is None: identity=admin_auth(x_admin_token)
    if domain not in {"duplicate","location","qualification","field_conflict","taxonomy_conflict"}: raise HTTPException(422,"نوع المراجعة غير مدعوم")
    with SessionLocal() as db:
        _require_review_version(db,domain,review_id,version_token)
        rows=review_queue(x_admin_token,domain,"ALL",1000)
        item=next((row for row in rows if int(row["id"])==int(review_id)),None)
        if not item: raise HTTPException(404,"المراجعة غير موجودة")
        detail=_workbench_detail(db,item)
        recommendation=detail["recommendation"]
        sources=[{"source_record_id":s.get("source_record_id"),"observed_at":s.get("observed_at"),"content_hash":s.get("content_hash")} for s in detail.get("sources",[])]
        snapshot={**recommendation,"version":detail["recommendation_version"],"version_token":version_token}
        evidence_references=recommendation.get("supporting_evidence") or sources or [{"review_domain":domain,
            "review_id":review_id,"evidence_status":detail.get("evidence_status"),"basis":"NO_SUPPORTED_RULE"}]
        db.add(AuditEvent(user_id=(identity or {}).get("id"),event_type="REVIEW_RECOMMENDATION_SHOWN",
            entity_type=_review_audit_entity(domain),entity_id=str(review_id),before_json=None,
            after_json={**snapshot,"evidence_references":evidence_references,
                "review_domain":domain},request_metadata={"actor":(identity or {}).get("display_name") or (identity or {}).get("role") or "configured_admin_token",
                "actor_role":(identity or {}).get("role") or "admin_token","decision_kind":"SYSTEM_RECOMMENDATION"},created_at=utcnow()))
        db.commit()
        return {"ok":True,"recommendation_version":detail["recommendation_version"]}

@app.post("/api/admin/review-workbench/{domain}/{review_id}/reopen/preview")
def review_workbench_reopen_preview(domain:str,review_id:int,version_token:str=Query(...,min_length=64,max_length=64),x_admin_token:str|None=Header(default=None)):
    identity=review_write_auth(x_admin_token)
    if domain not in {"duplicate","location","qualification","field_conflict","taxonomy_conflict"}: raise HTTPException(422,"نوع المراجعة غير مدعوم")
    with SessionLocal() as db:
        _require_review_version(db,domain,review_id,version_token)
        model=_review_model(domain); row=db.scalar(select(model).where(model.id==review_id).with_for_update())
        if not row: raise HTTPException(404,"المراجعة غير موجودة")
        if row.status not in _review_closed_statuses(domain): raise HTTPException(409,"حالة هذه المراجعة لا تسمح بإعادة الفتح")
        entity_type=_review_audit_entity(domain)
        prior=db.scalars(select(AuditEvent).where(AuditEvent.entity_type==entity_type,AuditEvent.entity_id==str(review_id))
            .order_by(AuditEvent.created_at.desc())).first()
        last_decision=next((e for e in db.scalars(select(AuditEvent).where(AuditEvent.entity_type==entity_type,AuditEvent.entity_id==str(review_id)).order_by(AuditEvent.created_at.desc())).all()
            if (e.after_json or {}).get("decision")),None)
        decision_metadata_incomplete=not last_decision or not (last_decision.after_json or {}).get("decision") or not (last_decision.request_metadata or {}).get("actor") or not last_decision.created_at or not (last_decision.after_json or {}).get("reason")
        previous_evidence=((last_decision.after_json or {}).get("evidence") or {}) if last_decision else {}
        previous_sources=previous_evidence.get("source_snapshots") if isinstance(previous_evidence,dict) else None
        evidence_comparison_available=bool(previous_sources)
        current_evidence_changes=[]
        for previous_source in previous_sources or []:
            if not isinstance(previous_source,dict) or previous_source.get("source_record_id") is None:continue
            current_source=db.get(SourceOpportunity,int(previous_source["source_record_id"]))
            if current_source and previous_source.get("content_hash")!=current_source.content_hash:
                current_evidence_changes.append({"source_record_id":current_source.id,
                    "previous_content_hash":previous_source.get("content_hash"),"current_content_hash":current_source.content_hash,
                    "current_last_seen_at":dt(current_source.last_seen_at)})
        return {"review_id":review_id,"domain":domain,"current_status":row.status,
            "original_decision":(last_decision.after_json or {}).get("decision") if last_decision else None,
            "original_actor":(last_decision.request_metadata or {}).get("actor") if last_decision else None,
            "original_timestamp":dt(last_decision.created_at) if last_decision else None,
            "original_reason":(last_decision.after_json or {}).get("reason") if last_decision else None,
            "historical_decision_incomplete":decision_metadata_incomplete,
            "historical_notice":"قرار تاريخي — بعض بيانات التدقيق غير متوفرة" if decision_metadata_incomplete else None,
            "current_evidence_changes":current_evidence_changes,"evidence_change_comparison_available":evidence_comparison_available,
            "version_token":version_token,"allowed":identity.get("role") in ("admin","analyst","admin_token")}

@app.post("/api/admin/review-workbench/{domain}/{review_id}/reopen")
def review_workbench_reopen(domain:str,review_id:int,payload:ReviewReopenPayload,x_admin_token:str|None=Header(default=None)):
    identity=review_write_auth(x_admin_token)
    if domain not in {"duplicate","location","qualification","field_conflict","taxonomy_conflict"}: raise HTTPException(422,"نوع المراجعة غير مدعوم")
    if not payload.reason.strip(): raise HTTPException(422,"سبب إعادة الفتح مطلوب")
    valid_reopen_reasons={"ظهور دليل جديد","تغير بيانات المصدر","إعادة تقييم القرار السابق","تعارض جديد","سبب آخر"}
    if payload.reason.strip() not in valid_reopen_reasons: raise HTTPException(422,"اختر سببًا معتمدًا لإعادة الفتح.")
    with SessionLocal() as db:
        model=_review_model(domain); row=db.scalar(select(model).where(model.id==review_id).with_for_update())
        if not row: raise HTTPException(404,"المراجعة غير موجودة")
        _require_review_version(db,domain,review_id,payload.version_token)
        if row.status not in _review_closed_statuses(domain): raise HTTPException(409,"حالة هذه المراجعة لا تسمح بإعادة الفتح")
        previous_status=row.status; entity_type=_review_audit_entity(domain)
        previous_resolution=next((event for event in db.scalars(select(AuditEvent).where(
            AuditEvent.entity_type==entity_type,AuditEvent.entity_id==str(review_id)).order_by(AuditEvent.created_at.desc())).all()
            if (event.after_json or {}).get("decision")),None)
        source_rows=[]
        if domain in ("field_conflict","taxonomy_conflict"):
            source_rows=[db.get(SourceOpportunity,row.source_record_id)] if row.source_record_id else []
        elif domain in ("location","qualification"):
            source_rows=[db.get(SourceOpportunity,row.source_record_id)] if row.source_record_id else []
        evidence_version={"version_token":payload.version_token,"sources":[{"id":source.id,"content_hash":source.content_hash,
            "last_seen_at":dt(source.last_seen_at)} for source in source_rows if source]}
        row.status=_review_open_status(domain); db.flush();reopen_at=utcnow()
        db.add(AuditEvent(user_id=identity.get("id"),event_type="REVIEW_REOPENED",entity_type=entity_type,
            entity_id=str(review_id),before_json={"status":previous_status,"previous_resolution_event_id":previous_resolution.id if previous_resolution else None},
            after_json={"review_id":review_id,"previous_status":previous_status,"new_status":row.status,
                "status":row.status,"reopen_reason":payload.reason.strip(),"note":(payload.note or "").strip() or None,
                "review_version":payload.version_token,"evidence_version":evidence_version,
                "previous_resolution_reference":previous_resolution.id if previous_resolution else None,
                "previous_resolution_event_id":previous_resolution.id if previous_resolution else None,
                "actor":identity.get("display_name") or identity.get("role") or "configured_admin_token",
                "actor_role":identity.get("role") or "admin_token","timestamp":dt(reopen_at)},
            request_metadata={"actor":identity.get("display_name") or identity.get("role") or "configured_admin_token",
                "actor_role":identity.get("role") or "admin_token","decision_kind":"HUMAN_REOPEN","review_audit_version":"2"},created_at=reopen_at))
        db.commit()
        return {"ok":True,"review_id":review_id,"previous_status":previous_status,"status":row.status}

def _batch_item_state(db,token,item,action,*,lock=False,require_recommendation_version=False):
    if item.domain!="field_conflict" or action!="keep":
        return None,"تُتاح الدفعات حاليًا لقرار الإبقاء على القيمة في تعارضات الحقول فقط."
    conflict=None
    if lock:
        conflict=db.scalar(select(OpportunityConflict).where(OpportunityConflict.id==item.review_id).with_for_update().execution_options(populate_existing=True))
        if conflict:
            db.scalar(select(Opportunity).where(Opportunity.id==conflict.opportunity_id).with_for_update().execution_options(populate_existing=True))
            if conflict.source_record_id:
                db.scalar(select(SourceOpportunity).where(SourceOpportunity.id==conflict.source_record_id).with_for_update().execution_options(populate_existing=True))
    rows=review_queue(token,item.domain,"OPEN",1000)
    queued=next((row for row in rows if int(row["id"])==item.review_id),None)
    if not queued:return None,"الحالة ليست مفتوحة."
    if queued.get("disposition")=="SOURCE_RECHECK_REQUIRED":return None,"الحالة تتطلب تحققًا من المصدر."
    detail=_workbench_detail(db,queued)
    current_recommendation_version=detail.get("recommendation_version")
    if require_recommendation_version and not item.recommendation_version:return None,"نسخة توصية النظام غير موجودة؛ أعد معاينة الدفعة."
    if item.recommendation_version and item.recommendation_version!=current_recommendation_version:return None,"تغيرت التوصية أو أدلتها منذ معاينة الدفعة."
    if action not in {entry["key"] for entry in detail["allowed_actions"]}:return None,"الإجراء غير مسموح لهذا الدور أو الحالة."
    conflict=conflict or db.get(OpportunityConflict,item.review_id)
    master=db.get(Opportunity,conflict.opportunity_id) if conflict else None
    record=db.get(SourceOpportunity,conflict.source_record_id) if conflict else None
    source=db.get(Source,record.source_id) if record else None
    if not conflict or not master or not record or master.merged_into_id is not None:return None,"سلسلة الدليل أو الفرصة غير صالحة."
    _require_review_version(db,item.domain,item.review_id,item.version_token)
    standardized=record.standardized_data_json if isinstance(record.standardized_data_json,dict) else {}
    field_data=((standardized.get("fields") or {}).get(conflict.field_name) or {})
    canonical_sources=[]
    for p in db.scalars(select(FieldProvenance).where(FieldProvenance.opportunity_id==master.id,
            FieldProvenance.field_name==conflict.field_name).order_by(FieldProvenance.captured_at.desc()).limit(20)).all():
        authority=db.get(Source,p.source_id)
        canonical_sources.append({"source_id":p.source_id,"priority":authority.priority if authority else None,"value":p.selected_value})
    signature_data={"domain":item.domain,"review_type":conflict.conflict_type,"field":conflict.field_name,"action":action,
        "canonical_value":getattr(master,conflict.field_name,None),"selected_value":conflict.selected_value,
        "conflicting_value":conflict.conflicting_value,"evidence_pattern":{"mapping_status":field_data.get("mapping_status"),
        "mapping_rule":field_data.get("rule"),"source_priority":source.priority if source else None,
        "canonical_sources":sorted(canonical_sources,key=lambda row:(row["priority"] or 0,str(row["value"])))},
        "source_authority_condition":{"source_id":source.id if source else None,"source_priority":source.priority if source else None,
            "canonical_sources":sorted(canonical_sources,key=lambda row:(row["priority"] or 0,row["source_id"],str(row["value"])) )},
        "recommended_result":{"action":detail["recommendation"].get("action"),"confidence":detail["recommendation"].get("confidence"),
            "rule":detail["recommendation"].get("rule")},"business_data_impact":"STATUS_ONLY"}
    encoded=json.dumps(signature_data,ensure_ascii=False,sort_keys=True,separators=(",",":"),default=str)
    signature=hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    return {"item":item,"queued":queued,"conflict":conflict,"master":master,"record":record,
        "signature":signature,"signature_data":signature_data,"detail":detail,
        "recommendation_version":current_recommendation_version},None

@app.post("/api/admin/review-workbench/batch/preview")
def review_workbench_batch_preview(payload:ReviewBatchPayload,x_admin_token:str|None=Header(default=None)):
    identity=review_write_auth(x_admin_token)
    if not payload.reason.strip():raise HTTPException(422,"سبب الإجراء الجماعي مطلوب.")
    if payload.action=="merge":raise HTTPException(422,"لا يمكن تنفيذ دمج الفرص ضمن الدفعات.")
    with SessionLocal() as db:
        eligible=[];excluded=[]
        seen=set()
        for item in payload.items:
            key=(item.domain,item.review_id)
            if key in seen:excluded.append({"domain":item.domain,"review_id":item.review_id,"reason":"تكرار العنصر المحدد."});continue
            seen.add(key)
            state,error=_batch_item_state(db,x_admin_token,item,payload.action)
            if error:excluded.append({"domain":item.domain,"review_id":item.review_id,"reason":error})
            else:eligible.append(state)
        signatures={row["signature"] for row in eligible}
        override_required=any(row["detail"].get("recommendation",{}).get("action") not in (None,payload.action) for row in eligible)
        valid_override_reasons={"مصدر أحدث وأكثر موثوقية","السياق لا تدعمه التوصية","تحقق يدوي إضافي","تعارض في الأدلة","سبب آخر"}
        override_reason_valid=not override_required or payload.override_reason in valid_override_reasons
        if len(eligible)<2: return {"eligible":False,"signature":None,"signature_count":len(signatures),
            "items":[{"domain":row["item"].domain,"review_id":row["item"].review_id} for row in eligible],"excluded":excluded,
            "action":payload.action,"reason":payload.reason,"batch_operation_id":payload.batch_operation_id,"impact":"لا تغيير في بيانات الفرص؛ تحديث حالة المراجعة وسجل تدقيق مستقل لكل حالة.","actor_role":identity.get("role")}
        same=len(signatures)==1
        return {"eligible":same and override_reason_valid,"signature":next(iter(signatures)) if same else None,"signature_count":len(signatures),
            "items":[{"domain":row["item"].domain,"review_id":row["item"].review_id,"version_token":row["item"].version_token,
                "recommendation_version":row["recommendation_version"]} for row in eligible],
            "excluded":excluded,"action":payload.action,"reason":payload.reason,"batch_operation_id":payload.batch_operation_id,
            "override_required":override_required,"override_reason_valid":override_reason_valid,
            "recommendation_snapshots":[{"review_id":row["item"].review_id,**row["detail"].get("recommendation",{}),"version":row["recommendation_version"]} for row in eligible],
            "eligibility_reason":None if override_reason_valid else "يلزم اختيار سبب معتمد لتجاوز توصية النظام.",
            "impact":"لا تغيير في بيانات الفرص؛ تحديث حالة المراجعة وسجل تدقيق مستقل لكل حالة.","duplicate_merge_enabled":False,
            "actor_role":identity.get("role")}

@app.post("/api/admin/review-workbench/batch/commit")
def review_workbench_batch_commit(payload:ReviewBatchPayload,x_admin_token:str|None=Header(default=None)):
    identity=review_write_auth(x_admin_token)
    if not payload.reason.strip():raise HTTPException(422,"سبب الإجراء الجماعي مطلوب.")
    if not payload.confirm:raise HTTPException(422,"تأكيد تنفيذ الدفعة مطلوب.")
    if payload.action!="keep":raise HTTPException(422,"الإجراء الدفعي المسموح حاليًا هو الإبقاء على القيمة فقط.")
    if any(item.domain=="duplicate" for item in payload.items):raise HTTPException(422,"دمج الفرص مرفوض ضمن الدفعات.")
    if len({(item.domain,item.review_id) for item in payload.items})!=len(payload.items):raise HTTPException(422,"لا يجوز تكرار المراجعة ضمن الدفعة.")
    with SessionLocal() as db:
        if db.bind.dialect.name=="postgresql":
            lock_key=int.from_bytes(hashlib.sha256(payload.batch_operation_id.encode("utf-8")).digest()[:8],"big") & 0x7fffffffffffffff
            db.execute(text("SELECT pg_advisory_xact_lock(:lock_key)"),{"lock_key":lock_key})
        prior=db.scalar(select(AuditEvent).where(AuditEvent.event_type=="REVIEW_BATCH_DECISION",
            AuditEvent.entity_type=="review_batch",AuditEvent.entity_id==payload.batch_operation_id).with_for_update())
        if prior:raise HTTPException(409,"معرّف عملية الدفعة استُخدم من قبل.")
        states=[]
        for item in sorted(payload.items,key=lambda value:(value.domain,value.review_id)):
            state,error=_batch_item_state(db,x_admin_token,item,payload.action,lock=True,require_recommendation_version=True)
            if error:raise HTTPException(409,f"تعذر تنفيذ الدفعة بالكامل: المراجعة {item.review_id}: {error}")
            states.append(state)
        signatures={row["signature"] for row in states}
        if len(states)<2 or len(signatures)!=1:raise HTTPException(409,"توقيع الحالات غير متطابق؛ أُلغيت الدفعة بالكامل.")
        current_signature=next(iter(signatures))
        if not payload.batch_signature or payload.batch_signature!=current_signature:raise HTTPException(409,"توقيع الدفعة تغير منذ المعاينة؛ أعد معاينتها.")
        override_required=any(row["detail"].get("recommendation",{}).get("action") not in (None,payload.action) for row in states)
        valid_override_reasons={"مصدر أحدث وأكثر موثوقية","السياق لا تدعمه التوصية","تحقق يدوي إضافي","تعارض في الأدلة","سبب آخر"}
        if override_required and payload.override_reason not in valid_override_reasons:raise HTTPException(422,"اختر سببًا معتمدًا لتجاوز توصية النظام.")
        operation_id=payload.batch_operation_id
        for state in states:
            conflict=state["conflict"]
            recommendation=state["detail"].get("recommendation") or {}
            recommendation={key:recommendation.get(key) for key in ("action","confidence","reason","supporting_evidence","contradictory_evidence","rule")}
            recommendation["version"]=state["detail"].get("recommendation_version")
            if recommendation.get("action")=="keep":recommendation["disposition"]="FOLLOWED_RECOMMENDATION"
            elif recommendation.get("action"):
                recommendation["disposition"]="OVERRIDDEN_RECOMMENDATION";recommendation["override_reason"]=payload.override_reason
            else:recommendation["disposition"]="NO_RECOMMENDATION"
            before={"status":conflict.status,"master_id":conflict.opportunity_id,"field":conflict.field_name,
                "value":getattr(state["master"],conflict.field_name,None)}
            conflict.status="RESOLVED_KEEP";db.flush()
            _review_audit(db,decision="FIELD_KEEP",entity_type="opportunity_conflict",entity_id=conflict.id,
                note=payload.reason.strip(),before=before,after={"status":conflict.status,"master_id":conflict.opportunity_id,
                "field":conflict.field_name,"value":getattr(state["master"],conflict.field_name)},
                evidence={"source_id":conflict.source_id,"source_record_id":state["record"].id,
                    "batch_operation_id":operation_id,"deterministic_signature":state["signature"],
                    "recommendation":recommendation},identity=identity)
        db.add(AuditEvent(user_id=identity.get("id"),event_type="REVIEW_BATCH_DECISION",entity_type="review_batch",
            entity_id=operation_id,before_json=None,after_json={"batch_operation_id":operation_id,"action":payload.action,
                "deterministic_signature":current_signature,"batch_signature":payload.batch_signature,"eligible":True,
                "review_ids":[s["item"].review_id for s in states],"override_reason":payload.override_reason,
                "recommendation_versions":[s["recommendation_version"] for s in states],
                "individual_audit_count":len(states)},request_metadata={"actor":identity.get("display_name") or identity.get("role"),
                "actor_role":identity.get("role"),"decision_kind":"HUMAN_BATCH"},created_at=utcnow()))
        db.commit()
        return {"ok":True,"batch_operation_id":operation_id,"policy":"ATOMIC_ALL_OR_NONE",
            "resolved_review_ids":[s["item"].review_id for s in states],"individual_audit_count":len(states)}

@app.get("/api/admin/review-workbench/{domain}/{review_id}")
def review_workbench_detail(domain:str,review_id:int,include_raw:bool=False,x_admin_token:str|None=Header(default=None)):
    admin_auth(x_admin_token)
    if domain not in {"duplicate","location","qualification","field_conflict","taxonomy_conflict"}:raise HTTPException(422,"نوع المراجعة غير مدعوم")
    with SessionLocal() as db:
        rows=review_queue(x_admin_token,domain,"ALL",1000)
        item=next((row for row in rows if int(row["id"])==review_id),None)
        if not item:raise HTTPException(404,"المراجعة غير موجودة في الطابور")
        return _workbench_detail(db,item,include_raw=include_raw)

@app.post("/api/admin/review-workbench/{domain}/{review_id}/preview")
def review_workbench_preview(domain:str,review_id:int,action:str=Query(...),version_token:str=Query(...,min_length=64,max_length=64),x_admin_token:str|None=Header(default=None)):
    identity=review_write_auth(x_admin_token)
    with SessionLocal() as db:
        _require_review_version(db,domain,review_id,version_token)
        rows=review_queue(x_admin_token,domain,"OPEN",1000)
        item=next((row for row in rows if int(row["id"])==review_id),None)
        if not item:raise HTTPException(409,"الحالة لم تعد مفتوحة")
        detail=_workbench_detail(db,item)
        allowed={entry["key"] for entry in detail["allowed_actions"]}
        if action not in allowed:raise HTTPException(422,"الإجراء غير مسموح لهذا النوع أو الدور")
        impacts=[]
        if action in ("keep","use_source"):
            impacts.append({"entity":"canonical_value","before":detail.get("comparison",{}).get("current_value"),"after":detail.get("evidence",{}).get("conflicting") if action=="use_source" else detail.get("comparison",{}).get("current_value")})
        elif action=="merge":
            masters=detail.get("masters",[]);survivor=masters[0] if masters else {};merged=masters[1] if len(masters)>1 else {}
            impacts.append({"entity":"merge","surviving_master":{"id":survivor.get("id"),"title":survivor.get("title")},
                "merged_master":{"id":merged.get("id"),"title":merged.get("title")},
                "source_records_to_relink":[{"source":row.get("source"),"source_record_id":row.get("source_record_id"),"from_master":row.get("master_id")} for row in detail.get("sources",[]) if row.get("master_id")==merged.get("id")],
                "canonical_values":{"survivor":{key:survivor.get(key) for key in ("owner","publisher","sector","activity","location","investment_value","currency","duration")},
                    "merged":{key:merged.get(key) for key in ("owner","publisher","sector","activity","location","investment_value","currency","duration")}},
                "note":"سيُسجل مسار الدمج مع حفظ روابط المصادر والتدقيق وإمكانية التراجع."})
        else: impacts.append({"entity":"review_status","before":"OPEN","after":"RESOLVED"})
        return {"review_id":review_id,"domain":domain,"action":action,"impacts":impacts,"audit_event":"will be created",
            "version_token":version_token,"actor_role":identity.get("role")}

@app.get("/api/admin/review-workbench/pilot")
def review_workbench_pilot(x_admin_token:str|None=Header(default=None)):
    admin_auth(x_admin_token)
    cohort=_load_human_review_pilot_cohort()
    current=review_queue(x_admin_token,"all","ALL",1000,disposition="ALL")
    by_key={f"{item.get('domain')}:{item.get('id')}":item for item in current}
    with SessionLocal() as db:
        events=[event.payload for event in db.scalars(select(SystemEvent).where(
            SystemEvent.event_type=="HUMAN_REVIEW_PILOT_EVENT").order_by(SystemEvent.created_at.asc(),SystemEvent.id.asc())).all()
            if isinstance(event.payload,dict) and event.payload.get("pilot_id")==cohort["pilot_id"]]
        start_event=next((event for event in events if event.get("event_kind")=="PILOT_STARTED"),None)
        start_baseline=(start_event or {}).get("baseline")
        natural_jobs_after_start=[]
        if start_baseline:
            jobs=db.execute(select(SyncJob,Source.source_key).join(Source,Source.id==SyncJob.source_id)
                .where(SyncJob.id>start_baseline.get("sync_jobs_max_id",0)).order_by(SyncJob.id.asc())).all()
            natural_jobs_after_start=[{"job_id":job.id,"source":source_key,"status":job.status,
                "scan_complete":bool(job.pagination_complete) if job.pagination_complete is not None else "UNKNOWN","job_state":job.job_state,
                "master_delta":"UNKNOWN","source_delta":"UNKNOWN",
                "observation_delta":"UNKNOWN","review_delta":"UNKNOWN"} for job in jobs]
    started=any(event.get("event_kind")=="PILOT_STARTED" for event in events)
    phase_a_reviewed=any(event.get("event_kind")=="PHASE_A_REVIEWED" for event in events)
    cases=[]
    for frozen in cohort["cases"]:
        live=by_key.get(frozen["review_id_key"])
        cases.append({**frozen,"available":live is not None,"current":live})
    outcomes=[event for event in events if event.get("event_kind") in ("CASE_OUTCOME","CASE_REOPENED")]
    return {"pilot_id":cohort["pilot_id"],"metrics_purpose":cohort["metrics_purpose"],
        "phase_counts":cohort["phase_counts"],"started":started,"phase_a_reviewed":phase_a_reviewed,
        "active_phase":"B" if phase_a_reviewed else "A","cases":cases,"events":events,
        "start_baseline":start_baseline,"natural_jobs_after_start":natural_jobs_after_start,
        "outcomes":outcomes,"completed_case_keys":sorted({event.get("review_id_key") for event in outcomes
            if event.get("event_kind")=="CASE_OUTCOME" and event.get("review_id_key")})}

@app.post("/api/admin/review-workbench/pilot/events")
def review_workbench_pilot_event(payload:HumanReviewPilotEventPayload,x_admin_token:str|None=Header(default=None)):
    identity=review_write_auth(x_admin_token)
    cohort=_load_human_review_pilot_cohort()
    if payload.pilot_id!=cohort["pilot_id"]:raise HTTPException(404,"الطيار غير موجود.")
    with SessionLocal() as db:
        prior=[event.payload for event in db.scalars(select(SystemEvent).where(
            SystemEvent.event_type=="HUMAN_REVIEW_PILOT_EVENT").order_by(SystemEvent.created_at.asc(),SystemEvent.id.asc())).all()
            if isinstance(event.payload,dict) and event.payload.get("pilot_id")==cohort["pilot_id"]]
        if payload.event_kind=="PILOT_STARTED":
            if not any(event.get("event_kind")=="PILOT_STARTED" for event in prior):
                queue=review_queue(x_admin_token,"all","ALL",1000,disposition="ALL")
                open_rows=[item for item in queue if item.get("status")=="OPEN"]
                actionable=[item for item in open_rows if item.get("disposition")!="SOURCE_RECHECK_REQUIRED"]
                jobs=db.execute(select(SyncJob,Source.source_key).join(Source,Source.id==SyncJob.source_id).order_by(SyncJob.id.asc())).all()
                active_jobs=[job for job,source_key in jobs if str(job.job_state).upper() in {"QUEUED","RUNNING","RETRYING"}]
                latest_invest_saudi=next((job.id for job,source_key in reversed(jobs) if source_key=="invest-saudi"),None)
                master_ids={master_id for item in open_rows for master_id in (item.get("master_ids") or [])}
                master_sources={}
                if master_ids:
                    for master_id,source_name in db.execute(select(SourceOpportunity.master_opportunity_id,Source.source_name_ar)
                        .join(Source,Source.id==SourceOpportunity.source_id)
                        .where(SourceOpportunity.master_opportunity_id.in_(master_ids)).distinct()).all():
                        master_sources.setdefault(master_id,set()).add(source_name or "UNKNOWN")
                subtype_counts={};source_counts={}
                for item in open_rows:
                    subtype=item.get("field") or item.get("reason_key") or "UNSPECIFIED"
                    subtype_counts[subtype]=subtype_counts.get(subtype,0)+1
                    names={item.get("source")} if item.get("source") else set()
                    if not names:
                        names=set().union(*(master_sources.get(master_id,set()) for master_id in (item.get("master_ids") or [])))
                    if not names:names={"UNKNOWN_SOURCE"}
                    for name in names:source_counts[name]=source_counts.get(name,0)+1
                start_baseline={"captured_at":dt(utcnow()),"open_reviews_total":len(open_rows),
                    "human_review_required":len(actionable),"source_recheck_required":len(open_rows)-len(actionable),
                    "open_by_priority":{priority:sum(item.get("priority")==priority for item in open_rows) for priority in ("P1","P2","P3","P4")},
                    "open_by_type":{kind:sum(item.get("domain")==kind for item in open_rows) for kind in sorted({item.get("domain") for item in open_rows})},
                    "open_by_subtype":subtype_counts,"open_by_source":source_counts,
                    "sync_jobs_total":len(jobs),"sync_jobs_max_id":max((job.id for job,source_key in jobs),default=0),
                    "active_sync_jobs":len(active_jobs),"latest_invest_saudi_job_id":latest_invest_saudi}
                db.add(SystemEvent(event_type="HUMAN_REVIEW_PILOT_EVENT",payload={"pilot_id":cohort["pilot_id"],
                    "event_kind":"PILOT_STARTED","started_at":dt(utcnow()),"metrics_purpose":"WORKFLOW_CALIBRATION_ONLY",
                    "baseline":start_baseline},created_at=utcnow()))
                db.commit()
            return {"ok":True,"active_phase":"B" if any(event.get("event_kind")=="PHASE_A_REVIEWED" for event in prior) else "A"}
        if not any(event.get("event_kind")=="PILOT_STARTED" for event in prior):
            raise HTTPException(409,"ابدأ الطيار قبل تسجيل نتائجه.")
        phase_a_reviewed=any(event.get("event_kind")=="PHASE_A_REVIEWED" for event in prior)
        if payload.event_kind=="PHASE_A_REVIEWED":
            completed={event.get("review_id_key") for event in prior if event.get("event_kind")=="CASE_OUTCOME" and event.get("phase")=="A"}
            expected={case["review_id_key"] for case in cohort["cases"] if case.get("phase")=="A"}
            if completed!=expected:raise HTTPException(409,"أكمل نتائج حالات المرحلة أ العشرين قبل اعتماد مراجعتها.")
            if not payload.reason or len(payload.reason.strip())<8:raise HTTPException(422,"سجّل خلاصة مراجعة المرحلة أ قبل الانتقال إلى المرحلة ب.")
            if not phase_a_reviewed:
                db.add(SystemEvent(event_type="HUMAN_REVIEW_PILOT_EVENT",payload={"pilot_id":cohort["pilot_id"],
                    "event_kind":"PHASE_A_REVIEWED","metrics_purpose":"WORKFLOW_CALIBRATION_ONLY",
                    "summary":payload.reason.strip()},created_at=utcnow()))
                db.commit()
            return {"ok":True,"active_phase":"B"}
        if not payload.review_id_key or not payload.phase or not payload.outcome:
            raise HTTPException(422,"بيانات حالة الطيار غير مكتملة.")
        frozen=next((case for case in cohort["cases"] if case["review_id_key"]==payload.review_id_key),None)
        if not frozen or frozen.get("phase")!=payload.phase:raise HTTPException(409,"الحالة ليست جزءًا من هذه المرحلة المجمدة.")
        if payload.phase=="B" and not phase_a_reviewed:raise HTTPException(409,"تبدأ المرحلة ب بعد مراجعة نتائج المرحلة أ.")
        existing=[event for event in prior if event.get("event_kind")=="CASE_OUTCOME" and event.get("review_id_key")==payload.review_id_key]
        if payload.event_kind=="CASE_OUTCOME" and existing:raise HTTPException(409,"نتيجة هذه الحالة مسجلة بالفعل.")
        domain,raw_id=payload.review_id_key.split(":",1)
        if domain not in {"duplicate","location","qualification","field_conflict","taxonomy_conflict"} or not raw_id.isdigit():
            raise HTTPException(422,"معرّف المراجعة غير صالح.")
        review_model=_review_model(domain); review=db.get(review_model,int(raw_id))
        if not review:raise HTTPException(404,"المراجعة غير متاحة.")
        entity_type=_review_audit_entity(domain); started_event=next((event for event in prior if event.get("event_kind")=="PILOT_STARTED"),None)
        started_at=started_event.get("created_at") if started_event else None
        if payload.event_kind=="CASE_REOPENED":
            latest_reopen=db.scalar(select(AuditEvent).where(AuditEvent.event_type=="REVIEW_REOPENED",
                AuditEvent.entity_type==entity_type,AuditEvent.entity_id==raw_id).order_by(AuditEvent.created_at.desc()))
            if review.status!=_review_open_status(domain) or not latest_reopen or (started_at and dt(latest_reopen.created_at)<started_at):
                raise HTTPException(409,"لا يوجد حدث إعادة فتح حديث مرتبط بهذه الحالة.")
            if payload.outcome!="REOPENED_AFTER_DECISION":raise HTTPException(422,"نوع نتيجة إعادة الفتح غير صحيح.")
        elif payload.event_kind=="CASE_REOPENED":
            pass
        elif payload.outcome=="RESOLVED":
            decisions=db.scalars(select(AuditEvent).where(AuditEvent.entity_type==entity_type,AuditEvent.entity_id==raw_id)
                .order_by(AuditEvent.created_at.desc())).all()
            human_decision=next((event for event in decisions if (event.after_json or {}).get("decision")
                and (event.request_metadata or {}).get("decision_kind")=="HUMAN"),None)
            if review.status not in _review_closed_statuses(domain) or not human_decision or (started_at and dt(human_decision.created_at)<started_at):
                raise HTTPException(409,"يجب أن يسبق تسجيل الحسم قرار بشري مدقق داخل الطيار.")
        elif payload.outcome in {"KEPT_OPEN","SOURCE_RECHECK_REQUIRED"}:
            if review.status!=_review_open_status(domain):raise HTTPException(409,"هذه الحالة لم تعد مفتوحة.")
            if payload.outcome=="SOURCE_RECHECK_REQUIRED":
                if not payload.reason or len(payload.reason.strip())<8:raise HTTPException(422,"سبب الإحالة إلى تحقق المصدر مطلوب.")
                db.add(AuditEvent(user_id=identity.get("id"),event_type="REVIEW_SOURCE_RECHECK_REQUESTED",
                    entity_type=entity_type,entity_id=raw_id,before_json={"status":review.status},
                    after_json={"review_type":{"duplicate":"DUPLICATE_CANDIDATE","location":"LOCATION_REVIEW",
                        "qualification":"QUALIFICATION_REVIEW","field_conflict":"OPPORTUNITY_CONFLICT",
                        "taxonomy_conflict":"OPPORTUNITY_CONFLICT"}[domain],"review_id":int(raw_id),"classification":"SOURCE_RECHECK_REQUIRED",
                        "disposition":"SOURCE_RECHECK_REQUIRED","reason":payload.reason.strip(),"decision":"SOURCE_RECHECK_REQUIRED"},
                    request_metadata={"actor":identity.get("display_name") or identity.get("role") or "configured_admin_token",
                        "actor_role":identity.get("role") or "admin_token","decision_kind":"HUMAN","metrics_purpose":"WORKFLOW_CALIBRATION_ONLY"},
                    created_at=utcnow()))
        else:raise HTTPException(422,"نتيجة الطيار غير مدعومة.")
        feedback=payload.feedback or {}
        allowed_feedback={"evidence_sufficiency":{"YES","PARTIAL","NO"},"decision_clarity":{"YES","NO"},
            "recommendation_helpfulness":{"YES","PARTIAL","NO","NONE"},"actions_appropriate":{"YES","NO"}}
        if payload.event_kind=="CASE_OUTCOME":
            if set(feedback)!=(set(allowed_feedback)|{"missing_evidence_note"}):raise HTTPException(422,"أكمل أسئلة ملاحظات الطيار الأربعة.")
            if any(feedback.get(key) not in options for key,options in allowed_feedback.items()):raise HTTPException(422,"إجابات التغذية الراجعة غير صالحة.")
        metrics=payload.metrics or {}; allowed_metrics={"review_opened_at","first_evidence_interaction_at","decision_preview_opened_at",
            "decision_submitted_at","handling_time_seconds","time_to_first_evidence_seconds","time_from_preview_to_submit_seconds",
            "recommendation_available","recommendation_confidence","recommendation_followed","recommendation_overridden","override_reason",
            "evidence_panel_expanded","observation_history_opened","raw_data_opened","source_cards_viewed_count","reopen_used",
            "source_link_opened","decision_preview_used"}
        if set(metrics)-allowed_metrics:raise HTTPException(422,"حقول القياس تتجاوز نطاق معايرة سير العمل.")
        db.add(SystemEvent(event_type="HUMAN_REVIEW_PILOT_EVENT",payload={"pilot_id":cohort["pilot_id"],
            "event_kind":payload.event_kind,"review_id_key":payload.review_id_key,"phase":payload.phase,
            "outcome":payload.outcome,"feedback":feedback,"metrics":metrics,"metrics_purpose":"WORKFLOW_CALIBRATION_ONLY"},created_at=utcnow()))
        db.commit()
        return {"ok":True,"outcome":payload.outcome,"recorded":True}

@app.get("/api/admin/review-workbench/metrics")
def review_workbench_metrics(x_admin_token:str|None=Header(default=None)):
    admin_auth(x_admin_token)
    decisions={"FIELD_KEEP","FIELD_USE_SOURCE","SECTOR_INFERENCE_ACCEPTED","DUPLICATE_MERGED","DUPLICATE_REJECTED","DUPLICATE_UNDONE","LOCATION_ACCEPTED","LOCATION_REJECTED","QUALIFICATION_ACCEPTED","QUALIFICATION_REJECTED"}
    with SessionLocal() as db:
        events=db.scalars(select(AuditEvent).where(AuditEvent.event_type.like("REVIEW_%"))
            .order_by(AuditEvent.created_at.desc()).limit(5000)).all()
        decision_events=[event for event in events if (event.after_json or {}).get("decision") in decisions
            and (event.request_metadata or {}).get("actor")!="SYSTEM"]
        by_day={};handling=[];accepted=0;overrides=0;recommendations=0
        for event in decision_events:
            key=(event.created_at.date().isoformat() if event.created_at else "unknown")
            by_day[key]=by_day.get(key,0)+1
            entity=(event.after_json or {}).get("evidence") or {}
            recommendation=entity.get("recommendation") if isinstance(entity,dict) else None
            if recommendation:
                recommendations+=1
                if recommendation.get("action")==((event.after_json or {}).get("decision")): accepted+=1
                else: overrides+=1
            entity_id=event.entity_id
            model={"opportunity_conflict":OpportunityConflict,"duplicate_candidate":DuplicateCandidate,"location_review":LocationReview,"qualification_review":QualificationReview}.get(event.entity_type)
            row=db.get(model,int(entity_id)) if model and entity_id and str(entity_id).isdigit() else None
            created=(getattr(row,"detected_at",None) or getattr(row,"created_at",None)) if row else None
            if created and event.created_at:
                handling.append(max(0,(event.created_at-created).total_seconds()))
        sorted_handling=sorted(handling)
        median=(sorted_handling[len(sorted_handling)//2] if len(sorted_handling)%2 else sum(sorted_handling[len(sorted_handling)//2-1:len(sorted_handling)//2+1])/2) if sorted_handling else None
        open_items=review_queue(x_admin_token,"all","OPEN",1000,exclude_source_recheck=True)
        backlog={level:sum(item.get("priority")==level for item in open_items) for level in ("P1","P2","P3","P4")}
        reopen_count=db.scalar(select(func.count(SystemEvent.id)).where(SystemEvent.event_type=="REVIEW_REOPENED")) or 0
        cutoff=(datetime.now(timezone.utc)-timedelta(days=30)).date().isoformat()
        return {"resolved_last_30_days":sum(count for day,count in by_day.items() if day>=cutoff),
            "resolved_by_day":by_day,"average_handling_seconds":sum(handling)/len(handling) if handling else None,
            "median_handling_seconds":median,"recommendation_acceptance_rate":accepted/recommendations if recommendations else None,
            "recommendation_override_rate":overrides/recommendations if recommendations else None,
            "reopened_reviews":reopen_count,"backlog_by_priority":backlog,"purpose":"مؤشرات تشغيلية لتحسين سير العمل فقط"}

@app.post("/api/admin/location-reviews/{review_id}/{action}")
def resolve_location_review(review_id:int,action:str,payload:ReviewDecisionPayload,x_admin_token:str|None=Header(default=None)):
    identity=review_write_auth(x_admin_token)
    if action not in ("accept","reject"):raise HTTPException(400,"الإجراء غير مدعوم")
    with SessionLocal() as db:
        review=db.scalar(select(LocationReview).where(LocationReview.id==review_id).with_for_update())
        if not review:raise HTTPException(404,"طلب مراجعة الموقع غير موجود")
        if review.status!="PENDING":raise HTTPException(409,"حالة المراجعة تغيرت؛ أعد تحميل القائمة")
        _require_actionable_review(x_admin_token,"location",review_id)
        _require_review_version(db,"location",review_id,payload.version_token)
        recommendation_snapshot=_decision_recommendation(db,x_admin_token,"location",review_id,action,payload)
        source=db.get(Source,review.source_id);row=db.get(SourceOpportunity,review.source_record_id) if review.source_record_id else None
        if not source or not row:raise HTTPException(409,"سجل المصدر المرتبط بالمراجعة غير متاح")
        before={"status":review.status,"master_id":row.master_opportunity_id,"location":row.raw_location}
        evidence={"source_id":review.source_id,"source_record_id":row.id,"external_id":review.external_id,
                  "source_url":row.source_url,"evidence":review.evidence,"reason":review.reason,
                  "observations":db.scalar(select(func.count(SourceObservation.id)).where(SourceObservation.source_opportunity_id==row.id)) or 0,
                  "recommendation":recommendation_snapshot}
        if action=="accept":
            from .adapters import RawOpportunity
            raw_json=row.raw_data_json or {};raw_json_original=dict(raw_json);source_content_hash=row.content_hash;confidence=max(.85,review.confidence_score)
            raw=RawOpportunity(external_id=row.source_opportunity_id,title=row.source_title,url=row.source_url,owner=row.source_owner,location=row.raw_location,activity=(raw_json.get("normalized_taxonomy") or {}).get("sector") or review.sector,description=raw_json.get("description") or review.description,reference=row.source_reference_number,raw={**raw_json,"location_confidence_score":confidence,"location_detection_method":"ADMIN_LOCATION_REVIEW","location_evidence":review.evidence+" | Approved by reviewer","qualified_location":True},location_source_filtered=True)
            from .service import _safe_record
            counts={"raw_count":0,"ahsa_count":0,"new_count":0,"duplicate_count":0,"update_count":0,"rejected_count":0}
            _safe_record(db,source,raw,counts)
            # The review decision changes canonical qualification only. Restore the exact
            # source payload identity after projection; the derived review evidence stays
            # in standardized fields and the atomic audit event, never in raw provenance.
            row.raw_data_json=raw_json_original;row.content_hash=source_content_hash
        review.status="ACCEPTED" if action=="accept" else "REJECTED"
        db.flush()
        _review_audit(db,decision="LOCATION_ACCEPTED" if action=="accept" else "LOCATION_REJECTED",
            entity_type="location_review",entity_id=review.id,note=payload.note.strip(),before=before,
            after={"status":review.status,"master_id":row.master_opportunity_id},evidence=evidence,identity=identity)
        db.commit();return {"ok":True,"status":review.status}

@app.get("/api/admin/duplicates/merged")
def merged_duplicates(x_admin_token:str|None=Header(default=None)):
    admin_auth(x_admin_token)
    with SessionLocal() as db:
        rows=db.scalars(select(DuplicateCandidate).where(DuplicateCandidate.status=="MERGED")).all()
        return [{"id":d.id,"left_title":db.get(Opportunity,d.left_opportunity_id).title_ar,"right_title":db.get(Opportunity,d.right_opportunity_id).title_ar} for d in rows]

@app.get("/api/admin/conflicts")
def conflicts(x_admin_token:str|None=Header(default=None),conflict_type:str|None=None):
    admin_auth(x_admin_token)
    with SessionLocal() as db:
        query=select(OpportunityConflict).where(OpportunityConflict.status=="OPEN")
        if conflict_type=="FIELD_VALUE_CONFLICT": query=query.where(OpportunityConflict.conflict_type.in_(("FIELD_VALUE_CONFLICT","STANDARDIZATION_REVIEW")))
        elif conflict_type: query=query.where(OpportunityConflict.conflict_type==conflict_type)
        rows=db.scalars(query.order_by(OpportunityConflict.detected_at.desc()).limit(200)).all()
        return [{"id":c.id,"opportunity_id":c.opportunity_id,"title":db.get(Opportunity,c.opportunity_id).title_ar,"field":c.field_name,"conflict_type":c.conflict_type,"selected":c.selected_value,"conflicting":c.conflicting_value,"source":db.get(Source,c.source_id).source_name_ar,"date":dt(c.detected_at)} for c in rows]

@app.post("/api/admin/conflicts/{conflict_id}/{action}")
def resolve_conflict(conflict_id:int,action:str,payload:ReviewDecisionPayload,x_admin_token:str|None=Header(default=None)):
    identity=review_write_auth(x_admin_token)
    if action not in ("keep","use_source","accept_inference"): raise HTTPException(400,"الإجراء غير مدعوم")
    with SessionLocal() as db:
        conflict=db.scalar(select(OpportunityConflict).where(OpportunityConflict.id==conflict_id).with_for_update())
        if not conflict: raise HTTPException(404,"التعارض غير موجود")
        if conflict.status!="OPEN":raise HTTPException(409,"حالة المراجعة تغيرت؛ أعد تحميل القائمة")
        review_domain="taxonomy_conflict" if conflict.conflict_type=="TAXONOMY_CONFLICT" else "field_conflict"
        _require_actionable_review(x_admin_token,review_domain,conflict_id)
        _require_review_version(db,review_domain,conflict_id,payload.version_token)
        recommendation_snapshot=_decision_recommendation(db,x_admin_token,review_domain,conflict_id,action,payload)
        if conflict.conflict_type=="STANDARDIZATION_REVIEW" and action=="use_source":
            raise HTTPException(409,"لا يمكن اعتماد قيمة المصدر حتى تُوثق وحدتها أو دلالتها")
        if conflict.conflict_type=="TAXONOMY_CONFLICT" and conflict.field_name=="sector" and action=="use_source" and not _valid_canonical_sector(conflict.conflicting_value):
            raise HTTPException(422,"قيمة القطاع الواردة ليست ضمن القطاعات المعيارية المعتمدة")
        master=db.get(Opportunity,conflict.opportunity_id)
        source_record=db.get(SourceOpportunity,conflict.source_record_id)
        if not master or not source_record or master.merged_into_id is not None:raise HTTPException(409,"المراجعة لا تشير إلى فرصة حالية ومصدر صالح")
        if action=="accept_inference":
            result=_accept_inference_review(db,conflict,master,payload,identity)
            db.commit();return result
        previous=getattr(master,conflict.field_name,None)
        if not hasattr(master,conflict.field_name):raise HTTPException(409,"حقل التعارض غير صالح")
        evidence={"source_id":conflict.source_id,"source_record_id":source_record.id,"source_url":source_record.source_url,
                  "selected_value":conflict.selected_value,"conflicting_value":conflict.conflicting_value,
                  "observation_count":db.scalar(select(func.count(SourceObservation.id)).where(SourceObservation.source_opportunity_id==source_record.id)) or 0,
                  "recommendation":recommendation_snapshot}
        if action=="use_source" and master:
            setattr(master,conflict.field_name,conflict.conflicting_value)
            db.add(ChangeHistory(opportunity_id=master.id,changed_field=conflict.field_name,previous_value=str(previous or ""),new_value=conflict.conflicting_value,source_id=conflict.source_id,detected_at=datetime.now(timezone.utc)))
            master.updated_at=datetime.now(timezone.utc);master.last_updated_at=master.updated_at
        if master and source_record:
            db.add(FieldProvenance(opportunity_id=master.id,field_name=conflict.field_name,selected_value=str(getattr(master,conflict.field_name)),source_id=conflict.source_id,source_record_id=source_record.id,captured_at=datetime.now(timezone.utc),confidence=.9))
        conflict.status="RESOLVED_SOURCE" if action=="use_source" else "RESOLVED_KEEP"
        db.flush()
        _review_audit(db,decision="FIELD_USE_SOURCE" if action=="use_source" else "FIELD_KEEP",
            entity_type="opportunity_conflict",entity_id=conflict.id,note=payload.note.strip(),
            before={"status":"OPEN","master_id":master.id,"field":conflict.field_name,"value":previous},
            after={"status":conflict.status,"master_id":master.id,"field":conflict.field_name,"value":getattr(master,conflict.field_name)},
            evidence=evidence,identity=identity)
        reevaluate_open_conflicts(db,master_id=master.id,field_names={conflict.field_name})
        db.commit();return {"ok":True,"status":conflict.status}

@app.post("/api/admin/duplicates/{candidate_id}/{action}")
def duplicate_action(candidate_id:int,action:str,payload:ReviewDecisionPayload,x_admin_token:str|None=Header(default=None)):
    identity=review_write_auth(x_admin_token)
    if action not in ("merge","reject","undo"): raise HTTPException(400,"الإجراء غير مدعوم")
    with SessionLocal() as db:
        row=db.scalar(select(DuplicateCandidate).where(DuplicateCandidate.id==candidate_id).with_for_update())
        if not row: raise HTTPException(404,"حالة التكرار غير موجودة")
        expected="MERGED" if action=="undo" else "PENDING"
        if row.status!=expected:raise HTTPException(409,"حالة المراجعة تغيرت؛ أعد تحميل القائمة")
        if action in ("merge","reject"):_require_actionable_review(x_admin_token,"duplicate",candidate_id)
        _require_review_version(db,"duplicate",candidate_id,payload.version_token)
        recommendation_snapshot=_decision_recommendation(db,x_admin_token,"duplicate",candidate_id,action,payload) if action!="undo" else {"action":None,"confidence":"NONE","disposition":"NO_RECOMMENDATION"}
        left=db.get(Opportunity,row.left_opportunity_id);right=db.get(Opportunity,row.right_opportunity_id)
        before={"status":row.status,"left_master_id":row.left_opportunity_id,"right_master_id":row.right_opportunity_id,
                "left_merged_into_id":left.merged_into_id if left else None,"right_merged_into_id":right.merged_into_id if right else None}
        evidence={"explanation":row.explanation_json or {},"confidence_score":row.confidence_score,
                  "recommendation":recommendation_snapshot}
        try:
            if action=="undo":undo_candidate(db,row)
            elif action=="merge":merge_candidate(db,row,performed_by=identity.get("display_name") or identity.get("role") or "configured_admin_token")
            else:row.status="REJECTED"
        except ValueError as error: raise HTTPException(409,str(error)) from error
        db.flush()
        _review_audit(db,decision={"merge":"DUPLICATE_MERGED","reject":"DUPLICATE_REJECTED","undo":"DUPLICATE_UNDONE"}[action],
            entity_type="duplicate_candidate",entity_id=row.id,note=payload.note.strip(),before=before,
            after={"status":row.status,"left_merged_into_id":left.merged_into_id if left else None,
                   "right_merged_into_id":right.merged_into_id if right else None},evidence=evidence,identity=identity)
        db.commit(); return {"ok":True,"status":row.status}

@app.post("/api/admin/qualification-reviews/{review_id}/{action}")
def resolve_qualification_review(review_id:int,action:str,payload:ReviewDecisionPayload,x_admin_token:str|None=Header(default=None)):
    identity=review_write_auth(x_admin_token)
    if action not in ("accept","reject"):raise HTTPException(400,"الإجراء غير مدعوم")
    with SessionLocal() as db:
        review=db.scalar(select(QualificationReview).where(QualificationReview.id==review_id).with_for_update())
        if not review:raise HTTPException(404,"مراجعة التأهيل غير موجودة")
        if review.status!="PENDING":raise HTTPException(409,"حالة المراجعة تغيرت؛ أعد تحميل القائمة")
        _require_actionable_review(x_admin_token,"qualification",review_id)
        _require_review_version(db,"qualification",review_id,payload.version_token)
        recommendation_snapshot=_decision_recommendation(db,x_admin_token,"qualification",review_id,action,payload)
        record=db.get(SourceOpportunity,review.source_record_id) if review.source_record_id else None
        if not record:raise HTTPException(409,"سجل المصدر المرتبط بالمراجعة غير متاح")
        before={"status":review.status,"master_id":record.master_opportunity_id}
        evidence={"source_id":review.source_id,"source_record_id":record.id,"external_id":review.external_id,
                  "source_url":review.source_url,"reason":review.reason,
                  "observation_count":db.scalar(select(func.count(SourceObservation.id)).where(SourceObservation.source_opportunity_id==record.id)) or 0,
                  "recommendation":recommendation_snapshot}
        review.status="ACCEPTED" if action=="accept" else "REJECTED";db.flush()
        _review_audit(db,decision="QUALIFICATION_ACCEPTED" if action=="accept" else "QUALIFICATION_REJECTED",
            entity_type="qualification_review",entity_id=review.id,note=payload.note.strip(),before=before,
            after={"status":review.status,"master_id":record.master_opportunity_id},evidence=evidence,identity=identity)
        db.commit();return {"ok":True,"status":review.status}

@app.get("/api/export.csv")
def export_csv(q:str="",sector:str="",sector_values:str="",activity:str="",sub_activity:str="",status:str="",source:str="",owner:str="",location:str="",opportunity_type:str="",investment_model:str="",asset_facility_type:str="",subsector:str="",lifecycle:str="",period:str="all",created_after:str="",created_before:str="",deadline_after:str="",deadline_before:str="",map_ids:str=""):
    headers=["اسم الفرصة","الجهة المالكة","القطاع","النشاط","النشاط الفرعي","القطاع الفرعي","نوع الفرصة","المدينة","الحي / الموقع","المواقع التفصيلية","مرحلة المشروع","نموذج الاستثمار","نوع الأصل أو الموقع","المساحة (م²)","القيمة الاستثمارية","العملة","مدة العقد (سنة)","تاريخ النشر","آخر موعد للتقديم","الحالة","الرقم المرجعي الرسمي","معرّفات المصدر التقنية","المصدر الرئيسي","عدد المصادر","المصادر","رابط الفرصة","الدولة","المنطقة","المحافظة","المدينة / الموقع","الحي","حالة الموقع الجغرافي"]
    def generate():
        with SessionLocal() as db:
            conditions=_opportunity_filter_conditions(db,sector=sector,activity=activity,sub_activity=sub_activity,status=status,source=source,owner=owner,location=location,opportunity_type=opportunity_type,investment_model=investment_model,asset_facility_type=asset_facility_type,subsector=subsector,lifecycle=lifecycle)
            if sector_values: conditions.append(_sector_values_filter_condition(db,sector_values))
            if map_ids:
                try: selected_map_ids=sorted({int(value) for value in map_ids.split(",") if value.strip()})
                except ValueError: raise HTTPException(422,"معرّفات الخريطة غير صالحة")
                if not selected_map_ids: raise HTTPException(422,"معرّفات الخريطة غير صالحة")
                conditions.append(Opportunity.id.in_(selected_map_ids))
            period_start=_period_start(period)
            if period_start: conditions.append(Opportunity.first_seen_at>=period_start)
            if q:
                like=f"%{q}%"; conditions.append(or_(Opportunity.title_ar.ilike(like),Opportunity.reference_number.ilike(like),Opportunity.location_description.ilike(like),Opportunity.opportunity_owner.ilike(like)))
            if created_after:
                try: conditions.append(Opportunity.first_seen_at>=datetime.fromisoformat(created_after).replace(tzinfo=timezone.utc))
                except ValueError: raise HTTPException(422,"تاريخ البداية غير صالح")
            if created_before:
                try: conditions.append(Opportunity.first_seen_at<datetime.fromisoformat(created_before).replace(tzinfo=timezone.utc)+timedelta(days=1))
                except ValueError: raise HTTPException(422,"تاريخ النهاية غير صالح")
            if deadline_after: conditions.append(Opportunity.submission_deadline>=deadline_after)
            if deadline_before: conditions.append(Opportunity.submission_deadline<=deadline_before)
            export_ids=db.scalars(select(Opportunity.id).where(*conditions)).all()
            pending=_pending_location_reviews_by_master(db,export_ids)
            source_locations=_source_location_values_by_master(db,export_ids)
            query=select(Opportunity).where(*conditions).options(selectinload(Opportunity.source_records).selectinload(SourceOpportunity.source)).order_by(Opportunity.id).execution_options(yield_per=500)
            rows=db.scalars(query)
            first=io.StringIO();csv.writer(first).writerow(headers);yield "\ufeff"+first.getvalue()
            for o in rows:
                details=source_fact_summary(o);geo=_opportunity_geography(db,o,pending,source_locations)
                safe_city=geo.get("display_location") or (canonical_value("location",o.city) if geo.get("confirmed") else "غير محدد")
                safe_location=o.location_description if geo.get("confirmed") else None
                source_link=resolve_preferred_source_link(o.source_records)
                source_external_ids=" | ".join(r.source_opportunity_id if ":" in r.source_opportunity_id else f"{r.source.source_key}:{r.source_opportunity_id}" for r in o.source_records)
                values=[o.title_ar,canonical_value("owner",o.opportunity_owner),canonical_value("sector",o.sector),canonical_value("activity",o.activity),canonical_value("sub_activity",o.sub_activity),o.subsector,canonical_value("opportunity_type",o.opportunity_type),safe_city,safe_location,details["locations"],details["stages"],canonical_value("investment_model",o.investment_model),asset_facility_type_display(o),o.land_area_sqm,o.investment_value,o.currency if o.investment_value is not None else None,o.contract_duration_years,o.publication_date,o.submission_deadline,canonical_value("status",o.status),o.reference_number,source_external_ids,canonical_value("publication_platform",o.primary_publication_platform),len(o.source_records)," | ".join(r.source.source_name_ar for r in o.source_records),source_link.get("url") or "",geo.get("country"),geo.get("region"),geo.get("governorate"),geo.get("display_location"),geo.get("district"),geo.get("status_ar")]
                chunk=io.StringIO();csv.writer(chunk).writerow([spreadsheet_safe(v) for v in values]);yield chunk.getvalue()
    return StreamingResponse(generate(),media_type="text/csv; charset=utf-8",headers={"Content-Disposition":"attachment; filename=al-ahsa-opportunities.csv"})

@app.get("/api/export.xlsx")
def export_xlsx(q:str="",sector:str="",sector_values:str="",activity:str="",sub_activity:str="",status:str="",source:str="",owner:str="",location:str="",opportunity_type:str="",investment_model:str="",asset_facility_type:str="",subsector:str="",lifecycle:str="",period:str="all",created_after:str="",created_before:str="",deadline_after:str="",deadline_before:str="",map_ids:str=""):
    with SessionLocal() as db:
        conditions=_opportunity_filter_conditions(db,sector=sector,activity=activity,sub_activity=sub_activity,status=status,source=source,owner=owner,location=location,opportunity_type=opportunity_type,investment_model=investment_model,asset_facility_type=asset_facility_type,subsector=subsector,lifecycle=lifecycle)
        if sector_values: conditions.append(_sector_values_filter_condition(db,sector_values))
        if map_ids:
            try: selected_map_ids=sorted({int(value) for value in map_ids.split(",") if value.strip()})
            except ValueError: raise HTTPException(422,"معرّفات الخريطة غير صالحة")
            if not selected_map_ids: raise HTTPException(422,"معرّفات الخريطة غير صالحة")
            conditions.append(Opportunity.id.in_(selected_map_ids))
        period_start=_period_start(period)
        if period_start: conditions.append(Opportunity.first_seen_at>=period_start)
        if q:
            like=f"%{q}%"; conditions.append(or_(Opportunity.title_ar.ilike(like),Opportunity.reference_number.ilike(like),Opportunity.location_description.ilike(like),Opportunity.opportunity_owner.ilike(like)))
        if created_after:
            try: conditions.append(Opportunity.first_seen_at>=datetime.fromisoformat(created_after).replace(tzinfo=timezone.utc))
            except ValueError: raise HTTPException(422,"تاريخ البداية غير صالح")
        if created_before:
            try: conditions.append(Opportunity.first_seen_at<datetime.fromisoformat(created_before).replace(tzinfo=timezone.utc)+timedelta(days=1))
            except ValueError: raise HTTPException(422,"تاريخ النهاية غير صالح")
        if deadline_after: conditions.append(Opportunity.submission_deadline>=deadline_after)
        if deadline_before: conditions.append(Opportunity.submission_deadline<=deadline_before)
        rows=db.scalars(select(Opportunity).where(*conditions).options(selectinload(Opportunity.source_records).selectinload(SourceOpportunity.source),selectinload(Opportunity.asset_facility_type_assignments).selectinload(OpportunityAssetFacilityType.asset_type)).order_by(Opportunity.id)).unique().all()
        row_ids=[row.id for row in rows]
        pending=_pending_location_reviews_by_master(db,row_ids)
        source_locations=_source_location_values_by_master(db,row_ids)
        geography_by_id={row.id:_opportunity_geography(db,row,pending,source_locations) for row in rows}
        generated_at=export_timestamp()
        workbook=build_opportunities_workbook(rows,source_fact_summary,spreadsheet_safe,generated_at,canonicalize=canonical_value,geography_for=lambda opportunity:geography_by_id.get(opportunity.id,{}))
        applied=[("عبارة البحث",q),("الفترة",period if period not in {"", "all"} else ""),("نطاق الحالة", {"active":"نشطة","historical":"تاريخية"}.get(lifecycle,"")),("القطاع",sector),("القطاعات المجمعة","، ".join(_sector_values_display_labels(db,sector_values)) if sector_values else ""),("النشاط",activity),("النشاط الفرعي",sub_activity),("القطاع الفرعي",subsector),("الحالة",status),("المصدر",source),("الجهة المالكة",owner),("الموقع",location),("نوع الفرصة",opportunity_type),("نموذج الاستثمار",investment_model),("نوع الأصل أو الموقع",asset_facility_type),("الموعد من",deadline_after),("الموعد حتى",deadline_before)]
        applied_text="؛ ".join(f"{label}: {value}" for label,value in applied if value)
        metadata=workbook["معلومات التقرير"]
        metadata["B11"]="جميع الفرص الرئيسية غير المدمجة" if not applied_text else "الفرص المطابقة للمرشحات المحددة"
        metadata["B12"]="لا توجد مرشحات" if not applied_text else applied_text
        output=io.BytesIO(); workbook.save(output); output.seek(0)
        filename=f"فرص_الأحساء_{generated_at.date().isoformat()}.xlsx"
        disposition=f"attachment; filename=al-ahsa-opportunities-{generated_at.date().isoformat()}.xlsx; filename*=UTF-8''{quote(filename)}"
        return Response(output.getvalue(),media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",headers={"Content-Disposition":disposition})

@app.get("/api/filters")
def filters():
    with SessionLocal() as db:
        sectors,sector_counts,sector_ids=_canonical_option_data(db,Opportunity.sector,"sector")
        statuses,status_counts,status_ids=_canonical_option_data(db,Opportunity.status,"status")
        owners,owner_counts,owner_ids=_canonical_option_data(db,Opportunity.opportunity_owner,"owner")
        locations,location_counts,location_ids,location_hierarchy=_location_option_data(db)
        types,type_counts,type_ids=_canonical_option_data(db,Opportunity.opportunity_type,"opportunity_type")
        activities,activity_counts,activity_ids=_canonical_option_data(db,Opportunity.activity,"activity")
        sub_activities,sub_activity_counts,sub_activity_ids=_canonical_option_data(db,Opportunity.sub_activity,"sub_activity")
        investment_models,investment_model_counts,investment_model_ids=_canonical_option_data(db,Opportunity.investment_model,"investment_model")
        asset_facility_types,asset_facility_type_counts,asset_facility_type_ids=_asset_facility_type_options(db)
        subsectors,subsector_counts,subsector_ids=_canonical_option_data(db,Opportunity.subsector,"subsector")
        sources=[{"key":key,"name":name} for key,name in db.execute(select(Source.source_key,Source.source_name_ar).order_by(Source.priority)).all()]
        source_counts={key:(db.scalar(select(func.count(func.distinct(SourceOpportunity.master_opportunity_id))).join(Source,Source.id==SourceOpportunity.source_id).where(Source.source_key==key,SourceOpportunity.master_opportunity_id.is_not(None),SourceOpportunity.master_opportunity_id.in_(select(Opportunity.id).where(Opportunity.merged_into_id.is_(None))))) or 0) for key,_ in db.execute(select(Source.source_key,Source.source_name_ar).order_by(Source.priority)).all()}
        return {
            "sectors":sectors,"statuses":statuses,"owners":owners,"sources":sources,"locations":locations,"location_hierarchy":location_hierarchy,"types":types,"activities":activities,"sub_activities":sub_activities,"investment_models":investment_models,"asset_facility_types":asset_facility_types,"subsectors":subsectors,
            "option_counts":{"sectors":sector_counts,"statuses":status_counts,"owners":owner_counts,"sources":source_counts,"locations":location_counts,"types":type_counts,"activities":activity_counts,"sub_activities":sub_activity_counts,"investment_models":investment_model_counts,"asset_facility_types":asset_facility_type_counts,"subsectors":subsector_counts},
            "option_ids":{
                "sectors":sector_ids,
                "statuses":status_ids,
                "owners":owner_ids,
                "locations":location_ids,
                "types":type_ids,
                "activities":activity_ids,
                "sub_activities":sub_activity_ids,
                "investment_models":investment_model_ids,
                "asset_facility_types":asset_facility_type_ids,
                "subsectors":subsector_ids,
                "sources":{source["name"]:source["key"] for source in sources},
            },
        }

def dt(value): return value.isoformat() if value else None
def asset_facility_type_display(opportunity):
    labels={assignment.asset_type.label_ar for assignment in getattr(opportunity,"asset_facility_type_assignments",[]) if assignment.asset_type and assignment.asset_type.active}
    return " | ".join(sorted(labels,key=comparison_key)) if labels else ASSET_FACILITY_TYPE_MISSING_LABEL

def source_fact_summary(o):
    locations=set();stages=set();models=set();scopes=set()
    for record in o.source_records:
        raw=record.raw_data_json or {}
        locations.update(str(x) for x in (raw.get("opportunity_locations") or []) if x)
        stages.add(str(raw.get("project_stage"))) if raw.get("project_stage") else None
        derived_model=((getattr(record, "standardized_data_json", None) or {}).get("fields") or {}).get("investment_model") or {}
        model_label=derived_model.get("canonical_label") if derived_model.get("mapping_status") == "MAPPED" else None
        models.add(canonical_value("investment_model", model_label)) if model_label else None
        scopes.add(str(raw.get("location_scope"))) if raw.get("location_scope") else None
        locations.update(place.location_name for place in record.opportunity_locations)
    return {"locations":" | ".join(sorted(locations)),"stages":" | ".join(sorted(stages)),
        "investment_models":" | ".join(sorted(models)),"location_scopes":" | ".join(sorted(scopes))}
def source_json(s,count,last_job=None,multi_source_matches=0,freshness=None):
    freshness=freshness or {}
    expected=(s.last_attempted_sync+timedelta(minutes=max(15,s.polling_frequency_minutes or 60))) if s.last_attempted_sync else None
    return {"id":s.id,"key":s.source_key,"name":s.source_name_ar,"publication_platform":s.source_name_ar,"source_operator":s.organization_name,"url":s.opportunities_url,"source_type":s.source_type,"priority":s.priority,"enabled":s.enabled,"interval":s.polling_frequency_minutes,"status":s.sync_status,"technical_health":s.technical_health,"coverage_status":s.coverage_status,"coverage_notes":s.coverage_notes,"method":s.extraction_method,"last_attempt":dt(s.last_attempted_sync),"last_success":dt(s.last_successful_sync),"freshness_status":freshness.get("status","UNKNOWN"),"freshness_age_minutes":freshness.get("age_minutes"),"freshness_basis":freshness.get("freshness_basis"),"freshness_reason":freshness.get("reason"),"operational_type":freshness.get("operational_type"),"warning_threshold_minutes":freshness.get("warning_threshold_minutes"),"fail_threshold_minutes":freshness.get("fail_threshold_minutes"),"last_complete_scan":freshness.get("last_complete_scan"),"last_scope_verification":freshness.get("last_scope_verification"),"last_failure":freshness.get("last_failure"),"last_failure_reason":freshness.get("last_failure_reason"),"consecutive_failures":freshness.get("consecutive_failures",0),"next_expected_check":dt(expected),"record_count":last_job.unique_records if last_job and last_job.unique_records is not None else (s.last_record_count if s.last_attempted_sync else count),"retained_source_record_count":count,"source_total_reported":last_job.source_total_reported if last_job else s.last_source_total_reported,"collection_completeness_percent":last_job.collection_completeness_percent if last_job else s.last_collection_completeness_percent,"pagination_complete":last_job.pagination_complete if last_job else s.last_pagination_complete,"pages_requested":last_job.pages_requested if last_job else 0,"pages_successful":last_job.pages_successful if last_job else 0,"records_received":last_job.records_received if last_job else 0,"records_parsed":last_job.records_parsed if last_job else 0,"unique_records":last_job.unique_records if last_job else count,"ahsa_records":last_job.ahsa_count if last_job else 0,"active_count":last_job.active_count if last_job else 0,"new_records":last_job.new_count if last_job else 0,"updated_records":last_job.update_count if last_job else 0,"unchanged_records":last_job.unchanged_count if last_job else 0,"duplicate_candidates":last_job.duplicate_candidates_count if last_job else 0,"merged_records":last_job.merged_records_count if last_job else 0,"multi_source_matches":multi_source_matches,"rejected_records":last_job.rejected_count if last_job else 0,"removed_records":last_job.removed_records_count if last_job else 0,"location_review_count":last_job.location_review_count if last_job else 0,"metrics":last_job.metrics_json if last_job else {},"errors":((last_job.metrics_json or {}).get("error_pages",0)+(1 if last_job and last_job.error_message else 0)) if last_job else 0,"expired_count":last_job.expired_count if last_job else 0,"duplicate_items_between_pages":last_job.duplicate_items_between_pages if last_job else 0,"notes":s.notes}

def source_publishing_entity(record):
    """Return an item-level publisher only when the source payload names one."""
    raw=record.raw_data_json or {}
    direct=raw.get("publishing_entity") or raw.get("publisher")
    if record.source.source_key=="furas":
        direct=(raw.get("attributes") or {}).get("ENTITIESNAME") or direct
    return str(direct).strip() if direct not in (None,"") else None
def job_json(j): return {"id":j.id,"source_id":j.source_id,"started_at":dt(j.started_at),"queued_at":dt(j.queued_at),"finished_at":dt(j.finished_at),"status":j.status,"job_state":j.job_state,"trigger_type":j.trigger_type,"worker_id":j.worker_id,"correlation_id":j.correlation_id,"attempt_number":j.attempt_number,"heartbeat_at":dt(j.heartbeat_at),"pages_scanned":j.pages_scanned,"pages_requested":j.pages_requested,"pages_successful":j.pages_successful,"source_total_reported":j.source_total_reported,"records_received":j.records_received,"records_parsed":j.records_parsed,"unique_records":j.unique_records,"collection_completeness_percent":j.collection_completeness_percent,"pagination_complete":j.pagination_complete,"active_count":j.active_count,"expired_count":j.expired_count,"duplicate_items_between_pages":j.duplicate_items_between_pages,"raw_count":j.raw_count,"ahsa_count":j.ahsa_count,"new_count":j.new_count,"duplicate_count":j.duplicate_count,"duplicate_candidates_count":j.duplicate_candidates_count,"merged_records_count":j.merged_records_count,"update_count":j.update_count,"unchanged_count":j.unchanged_count,"rejected_count":j.rejected_count,"location_review_count":j.location_review_count,"removed_records_count":j.removed_records_count,"metrics":j.metrics_json or {},"error":j.error_message}
def opp_json(o, geography=None):
    from .entity_resolution import lifecycle_status
    canonical_status=canonical_value("status",o.status)
    geography=geography or resolve_master_geography(o.city,o.district)
    asset_types=[{"id":item.asset_type.canonical_id,"label":item.asset_type.label_ar} for item in getattr(o,"asset_facility_type_assignments",[]) if item.asset_type and item.asset_type.active]
    unique_asset_types={item["id"]:item for item in asset_types}
    asset_types=sorted(unique_asset_types.values(),key=lambda item:(comparison_key(item["label"]),item["id"]))
    confirmed=bool(geography.get("confirmed"))
    location_status_ar={"CONFIRMED":"موقع مؤكد","LOCATION_UNSPECIFIED":"الموقع غير محدد","LOCATION_REVIEW_REQUIRED":"الموقع قيد المراجعة"}.get(geography.get("status"),"الموقع غير محدد")
    display_city=geography.get("display_location") or ((geography.get("locality") or geography.get("governorate")) if confirmed else "غير محدد")
    sources=[]
    for r in o.source_records:
        link=resolve_source_link(r,r.source)
        sources.append({"name":r.source.source_name_ar,"publication_platform":r.source.source_name_ar,"publishing_entity":source_publishing_entity(r),"source_operator":r.source.organization_name,"url":link["url"],"historical_url":link["historical_url"],"checked_url":link["checked_url"],"link_health":link["link_health"],"link_checked_at":link["checked_at"],"url_repaired":link["url_repaired"],"key":r.source.source_key,"source_external_id":r.source_opportunity_id,"title":r.source_title,"raw_location":r.raw_location,"raw_status":r.raw_status,"canonical_status":canonical_value("status",r.canonical_status),"status_review_flags":((((r.standardized_data_json or {}).get("fields") or {}).get("status") or {}).get("review_flags") or []),"project_stage":(r.raw_data_json or {}).get("project_stage"),"investment_model":((((r.standardized_data_json or {}).get("fields") or {}).get("investment_model") or {}).get("canonical_label") if (((r.standardized_data_json or {}).get("fields") or {}).get("investment_model") or {}).get("mapping_status") == "MAPPED" else None),"qualification_reason":(r.raw_data_json or {}).get("qualification_reason"),"location_scope":(r.raw_data_json or {}).get("location_scope"),"opportunity_locations":[x.location_name for x in r.opportunity_locations] or (r.raw_data_json or {}).get("opportunity_locations",[])})
    return {"id":o.id,"canonical_id":o.canonical_id,"title":o.title_ar,"owner":canonical_value("owner",o.opportunity_owner),"sector":canonical_value("sector",o.sector),"activity":canonical_value("activity",o.activity),"sub_activity":canonical_value("sub_activity",o.sub_activity) if o.sub_activity else None,"subsector":canonical_value("subsector",o.subsector) if o.subsector else None,"type":canonical_value("opportunity_type",o.opportunity_type),"investment_model":canonical_value("investment_model",o.investment_model),"asset_facility_types":asset_types,"asset_facility_type":(" | ".join(item["label"] for item in asset_types) if asset_types else ASSET_FACILITY_TYPE_MISSING_LABEL),"city":display_city,"location":o.location_description if confirmed else None,"geography":{**geography,"status_ar":location_status_ar},"area":o.land_area_sqm,"area_unit":"m²" if o.land_area_sqm is not None else None,"investment_value":o.investment_value,"currency":o.currency if o.investment_value is not None else None,"duration":o.contract_duration_years,"duration_unit":"year" if o.contract_duration_years is not None else None,"deadline":o.submission_deadline,"status":canonical_status,"lifecycle_status":lifecycle_status(o.status),"reference":o.reference_number,"source_facts":source_fact_summary(o),"sources":sources,"source_count":len(o.source_records),"confidence":o.location_confidence_score,"first_seen":dt(o.first_seen_at),"updated_at":dt(o.last_updated_at)}

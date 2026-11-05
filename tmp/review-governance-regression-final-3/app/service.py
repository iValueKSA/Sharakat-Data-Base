from __future__ import annotations
import asyncio, difflib, os, hashlib, json
from types import SimpleNamespace
from datetime import datetime, timezone
from sqlalchemy import select, func, or_, and_, delete
from sqlalchemy.orm import Session
import httpx
from .adapters import ADAPTERS, PARSER_VERSION, LOCATION_ACCEPTANCE_THRESHOLD, normalized_record, SourceBlocked, normalize_sector
from .database import SessionLocal
from .models import Source, Opportunity, SourceOpportunity, SourceOpportunityDatasetMembership, SourceObservation, SourceOpportunityTaxonomy, OpportunityLocation, QualificationReview, SyncJob, SourceError, ChangeHistory, SystemEvent, FieldProvenance, DuplicateCandidate, OpportunityConflict, SourceContentItem, LocationReview, TaxonomyMapping, OrganizationAlias, SourceLimitation, ModonLocation, NcpProjectEvent, AlertEvent, OpportunityAssetFacilityType
from .filter_canonicalization import canonical_value, comparison_key
from .standardization import STANDARDIZATION_VERSION, canonical_identity, standardize_opportunity
from .normalization import normalize_arabic, comparison_title, normalize_reference
from .asset_facility_types import standardize_asset_facility_types
from .entity_resolution import compare_source_records, values_equivalent
from .status_lifecycle import canonical_source_status, aggregate_master_status
from .source_links import source_url_history_observation

NOW=lambda: datetime.now(timezone.utc)
def classify_http_health(status_code):
    # A failed fetch without an HTTP response (DNS, TLS, connect, or parser
    # transport errors) is not a successful health check. Keep it at WARNING.
    if status_code is None:return "WARNING"
    if status_code==429:return "RATE_LIMITED"
    if status_code is not None and int(status_code)>=500:return "WARNING"
    if status_code is not None and int(status_code)>=400:return "FAILED"
    return "HEALTHY"

def source_authority(source_key:str) -> int:
    return {"alahsa-opportunities":3,"furas":2}.get(source_key,1)

def _alert(db,event_type,severity,master,source,raw,value_hash=None):
    payload={"opportunity_id":master.id,"title":master.title_ar,"owner":master.opportunity_owner,"sector":master.sector,"location":master.location_description or master.city,"deadline":master.submission_deadline,"primary_source":source.source_name_ar,"official_url":raw.url,"value_hash":value_hash}
    fingerprint=hashlib.sha256(json.dumps({"type":event_type,"id":master.id,"value":value_hash},ensure_ascii=False,sort_keys=True,default=str).encode()).hexdigest()
    if not db.scalar(select(AlertEvent.id).where(AlertEvent.fingerprint==fingerprint)):
        db.add(AlertEvent(fingerprint=fingerprint,event_type=event_type,severity=severity,source_id=source.id,payload=payload,status="OPEN",created_at=NOW()))

def store_source_taxonomy(record,raw,source_key=""):
    payload=raw.raw or {};source_taxonomy=payload.get("source_taxonomy") or {}
    normalized_taxonomy=payload.get("normalized_taxonomy") or {}
    attrs=payload.get("attributes") or {}
    family=payload.get("source_record_family")
    source_key=source_key or (record.source.source_key if record.source else "")
    if source_key=="furas":
        source_activity=attrs.get("ACTIVITYTYPE") or raw.activity
        source_sub_activity=attrs.get("SUBACTIVITYTYPE") or raw.sub_activity
        if comparison_key(str(source_activity or "").strip().strip('"')) in {comparison_key(x) for x in ("الساحات الميادين","العربات المتنقلة","المباني")}:
            source_activity=None
    elif source_key=="invest-saudi" and family=="project":
        source_activity=payload.get("activity")
        source_sub_activity=payload.get("subActivity")
    elif source_key=="alahsa-opportunities":
        source_activity=(payload.get("details") or {}).get("نوع النشاط")
        source_sub_activity=None
    else:
        source_activity=raw.activity
        source_sub_activity=raw.sub_activity
    record.source_sector=source_taxonomy.get("sector")
    record.source_activity=str(source_activity).strip() if source_activity not in (None,"") else None
    record.source_sub_activity=str(source_sub_activity).strip() if source_sub_activity not in (None,"") else None
    record.source_sub_activity=raw.sub_activity
    record.source_subsector=source_taxonomy.get("subsector")
    record.normalized_sector=(normalize_sector(record.source_sector) if record.source_sector else normalize_sector(normalized_taxonomy.get("sector")))
    record.normalized_subsector=normalized_taxonomy.get("subsector")
    payload=raw.raw or {}
    record.official_source_id_original=payload.get("official_source_id_original")
    record.official_source_id_normalized=payload.get("official_source_id_normalized")

def store_investsaudi_observations(db,source,record,raw):
    payload=raw.raw or {};now=NOW();new_observation=False
    for membership in payload.get("dataset_memberships",[]):
        dataset=membership["dataset_name"];endpoint=membership["endpoint"]
        row=db.scalar(select(SourceOpportunityDatasetMembership).where(
            SourceOpportunityDatasetMembership.source_opportunity_id==record.id,
            SourceOpportunityDatasetMembership.dataset_name==dataset))
        if not row:
            row=SourceOpportunityDatasetMembership(source_opportunity_id=record.id,dataset_name=dataset,endpoint=endpoint,first_seen_at=now,last_seen_at=now)
            db.add(row)
        row.endpoint=endpoint;row.last_seen_at=now;row.missing_successful_checks=0;row.is_current=True
        row.dataset_specific_metadata=membership.get("dataset_specific_metadata") or {}
        for obs in payload.get("source_observations",[]):
            if obs["dataset_name"]!=dataset or obs["endpoint"]!=endpoint:continue
            raw_observation=obs.get("raw_data_json") or {}
            content_hash=hashlib.sha256(json.dumps(raw_observation,sort_keys=True,ensure_ascii=False,default=str).encode()).hexdigest()
            observation=db.scalar(select(SourceObservation).where(
                SourceObservation.source_opportunity_id==record.id,SourceObservation.endpoint==endpoint,
                SourceObservation.content_hash==content_hash))
            if not observation:
                new_observation=True
                observation=SourceObservation(source_opportunity_id=record.id,dataset_name=dataset,endpoint=endpoint,
                    official_source_id_original=obs["official_source_id_original"],official_source_id_normalized=obs["official_source_id_normalized"],
                    raw_data_json=raw_observation,source_updated_at=(raw_observation.get("updated_at") or raw_observation.get("updatedAt") or raw_observation.get("lastModified") or raw_observation.get("modifiedAt")),
                    content_hash=content_hash,first_seen_at=now,last_seen_at=now)
                db.add(observation)
            else:observation.last_seen_at=now
            taxonomy=obs.get("source_taxonomy") or {};normalized=obs.get("normalized_taxonomy") or {}
            source_value=taxonomy.get("sector")
            if source_value:
                tax=db.scalar(select(SourceOpportunityTaxonomy).where(
                    SourceOpportunityTaxonomy.source_opportunity_id==record.id,
                    SourceOpportunityTaxonomy.dataset_name==dataset,
                    SourceOpportunityTaxonomy.source_taxonomy_value==str(source_value)))
                normalized_value=str(normalized.get("sector") or normalize_sector(source_value) or "REVIEW_REQUIRED")
                rule=f"broad-sector mapping v1: {source_value} → {normalized_value}"
                if not tax:
                    db.add(SourceOpportunityTaxonomy(source_opportunity_id=record.id,dataset_name=dataset,
                        source_taxonomy_value=str(source_value),normalized_taxonomy_value=normalized_value,mapping_rule=rule,mapping_version="1"))
                else:tax.normalized_taxonomy_value=normalized_value;tax.mapping_rule=rule
    return new_observation

def store_pif_route_observations(db,record,raw):
    """Persist every public route representation under one PIF source identity."""
    payload=raw.raw or {};now=NOW();new_observation=False
    for membership in payload.get("route_memberships",[]):
        endpoint=membership.get("route_url")
        if not endpoint:continue
        route_key="PIF_ROUTE:"+hashlib.sha256(endpoint.encode()).hexdigest()[:24]
        row=db.scalar(select(SourceOpportunityDatasetMembership).where(
            SourceOpportunityDatasetMembership.source_opportunity_id==record.id,
            SourceOpportunityDatasetMembership.dataset_name==route_key))
        if not row:
            row=SourceOpportunityDatasetMembership(source_opportunity_id=record.id,dataset_name=route_key,
                endpoint=endpoint,first_seen_at=now,last_seen_at=now)
            db.add(row)
        row.endpoint=endpoint;row.last_seen_at=now;row.missing_successful_checks=0;row.is_current=True
        row.dataset_specific_metadata={k:v for k,v in membership.items() if k!="route_url"}
    for observation_data in payload.get("source_observations",[]):
        endpoint=observation_data.get("route_url")
        if not endpoint:continue
        raw_observation=dict(observation_data)
        content_hash=hashlib.sha256(json.dumps(raw_observation,sort_keys=True,ensure_ascii=False,default=str).encode()).hexdigest()
        observation=db.scalar(select(SourceObservation).where(
            SourceObservation.source_opportunity_id==record.id,SourceObservation.endpoint==endpoint,
            SourceObservation.content_hash==content_hash))
        if not observation:
            official_id=str(payload.get("pif_opportunity_id") or raw.external_id)[:200]
            observation=SourceObservation(source_opportunity_id=record.id,dataset_name="pif-route-observation",
                endpoint=endpoint,official_source_id_original=official_id,official_source_id_normalized=official_id,
                raw_data_json=raw_observation,source_updated_at=None,content_hash=content_hash,first_seen_at=now,last_seen_at=now)
            db.add(observation);new_observation=True
        else:observation.last_seen_at=now
    return new_observation

def reconcile_investsaudi_memberships(db,source,seen_by_dataset,checked_at):
    rows=db.scalars(select(SourceOpportunityDatasetMembership).join(SourceOpportunity).where(
        SourceOpportunity.source_id==source.id,SourceOpportunityDatasetMembership.is_current.is_(True))).all()
    newly_removed=set()
    for membership in rows:
        seen=seen_by_dataset.get(membership.dataset_name,set())
        if membership.source_opportunity_id in seen:
            membership.missing_successful_checks=0;membership.last_seen_at=checked_at;continue
        membership.missing_successful_checks=(membership.missing_successful_checks or 0)+1
        if membership.missing_successful_checks>=max(1,int(source.missing_confirmation_threshold or 3)):
            membership.is_current=False
            newly_removed.add(membership.source_opportunity_id)
    return len(newly_removed)

def investsaudi_reconciliation_metrics(endpoint_complete,endpoint_rows,unique_ids,duplicate_memberships,dataset_count=4):
    endpoint_status="PAGINATION_COMPLETE" if endpoint_complete else "INCOMPLETE_COLLECTION"
    is_reconciled=(endpoint_complete and endpoint_rows is not None and unique_ids is not None and
        duplicate_memberships is not None and unique_ids+duplicate_memberships==endpoint_rows)
    datasets_complete=endpoint_complete and dataset_count==4
    return {"endpoint_completeness":endpoint_status,"dataset_count":dataset_count,"datasets_complete":datasets_complete,
        "unique_dataset_reconciliation":"DATASET_RECONCILED" if is_reconciled and datasets_complete else "DATASET_RECONCILIATION_WARNING",
        "ui_counter_observed":2197,"ui_counter_type":"STATIC_FRONTEND_VALUE","ui_counter_authoritative":False,
        "ui_counter_semantics":"UNKNOWN","ui_counter_observed_at":"2026-10-12"}
DEFAULT_SOURCES=[
 {"source_key":"furas","source_name_ar":"فرص – البوابة الموحدة للاستثمار","organization_name":"وزارة البلديات والإسكان والجهات الحكومية المشاركة","base_url":"https://furas.momah.gov.sa/ar","opportunities_url":"https://furas.momah.gov.sa/ar/list-opportunities","source_type":"structured_opportunity_platform","priority":1,"polling_frequency_minutes":60,"extraction_method":"Public ArcGIS REST query via official catalogue proxy","notes":"CITY_ID values for Al-Ahsa cities are verified from the public investment layer; booklet price is not investment value."},
 {"source_key":"alahsa-opportunities","source_name_ar":"منصة الفرص الاستثمارية بالأحساء","organization_name":"أمانة الأحساء","base_url":"https://alahsa-opportunities.com/","opportunities_url":"https://alahsa-opportunities.com/","source_type":"local_opportunity_platform","priority":2,"polling_frequency_minutes":60,"extraction_method":"Server-rendered HTML cards","notes":"منصة مخصصة جغرافياً للأحساء؛ يجري مسح الصفحات المتاحة."},
 {"source_key":"ahda","source_name_ar":"هيئة تطوير الأحساء","organization_name":"هيئة تطوير الأحساء","base_url":"https://www.ahda.gov.sa/","opportunities_url":"https://www.ahda.gov.sa/","source_type":"unstructured_opportunity_publisher","priority":3,"polling_frequency_minutes":360,"extraction_method":"Sitemap discovery + server-rendered HTML","notes":"يفصل الرصد الصفحي عن تأهيل الفرص؛ نطاق المصدر لا يثبت مدينة/حي محدد."},
 {"source_key":"invest-saudi","source_name_ar":"استثمر في السعودية","organization_name":"وزارة الاستثمار","base_url":"https://investsaudi.sa/","opportunities_url":"https://investsaudi.sa/investment-opportunities","source_type":"national_opportunity_platform","priority":4,"polling_frequency_minutes":360,"extraction_method":"Public paginated JSON API","notes":"المنطقة الشرقية وحدها لا تكفي للتصنيف؛ تحفظ كل السجلات الوطنية خاماً وتقبل الأدلة المحلية فقط."},
 {"source_key":"kfu","source_name_ar":"جامعة الملك فيصل","organization_name":"جامعة الملك فيصل","base_url":"https://www.kfu.edu.sa/","opportunities_url":"https://www.kfu.edu.sa/ar/Departments/Investment/Documents/Newdesign/اعلانات-الإدارة.html","source_type":"announcement_driven_local_source","priority":5,"polling_frequency_minutes":720,"extraction_method":"Official investment announcement page; Arabic asset qualification","notes":"يفصل تأجير وتشغيل الأصول الجامعية عن المناقصات الشرائية العامة؛ الملفات تحفظ كرابط وبيانات وصفية ولا تُنزّل."},
 {"source_key":"modon","source_name_ar":"مدن","organization_name":"الهيئة السعودية للمدن الصناعية ومناطق التقنية","base_url":"https://modon.gov.sa/","opportunities_url":"https://modon.gov.sa/en/InvestmentOpportunities","source_type":"industrial_spatial_opportunity_source","priority":6,"polling_frequency_minutes":720,"extraction_method":"Official public catalog/product/news surfaces + public GIS schema; no private API access","notes":"طبقات GIS مرجعية فقط ولا تدخل الفرص دون دليل توافر حالي. حالة التغطية العامة منفصلة عن الصحة التقنية."},
 {"source_key":"ncp","source_name_ar":"المركز الوطني للتخصيص","organization_name":"المركز الوطني للتخصيص","base_url":"https://ncp.gov.sa/","opportunities_url":"https://ncp.gov.sa/en/MediaCenter/News/Pages/default.aspx","source_type":"ppp_privatisation_pipeline_source","priority":7,"polling_frequency_minutes":720,"extraction_method":"Paginated official English/Arabic SharePoint public News archives and linked articles","notes":"التغطية المكتملة للنطاق العام تعني أرشيف الإعلانات العامة فقط؛ واجهة المشروعات الاستثمارية الخاصة لا تُستعلم."},
 {"source_key":"nhc","source_name_ar":"NHC الاستثمار","organization_name":"الشركة الوطنية للإسكان","base_url":"https://www.nhc.sa/","opportunities_url":"https://www.nhc.sa/en/investment-opportunities/","source_type":"real_estate_investment_and_partnership_source","priority":8,"polling_frequency_minutes":720,"extraction_method":"Public NHC investment, qualification, and stimulation pages; no authenticated e-services","notes":"يُفصل محتوى الوجهات والمبيعات السكنية عن دعوات الشركاء والمشغلين؛ الخدمات العقارية المسجلة لا تُستعلم."},
 {"source_key":"pif","source_name_ar":"بوابة القطاع الخاص لصندوق الاستثمارات العامة","organization_name":"صندوق الاستثمارات العامة","base_url":"https://www.pif.gov.sa/","opportunities_url":"https://www.pif.gov.sa/en/private-sector-hub/explore-opportunities/","source_type":"national_value_chain_investment_source","priority":9,"polling_frequency_minutes":720,"extraction_method":"Public PIF ecosystem and portfolio-company opportunity pages; item-level company/location validation","notes":"الفرص الوطنية تحفظ كسجلات مصدرية فقط؛ تقبل بالأحساء عند وجود دليل مشروع أو أصل محدد."},
 {"source_key":"mwan","source_name_ar":"موان","organization_name":"المركز الوطني لإدارة النفايات","base_url":"https://mwan.gov.sa/","opportunities_url":"https://mwan.gov.sa/en/investment-opportunities","source_type":"waste_sector_investment_source","priority":10,"polling_frequency_minutes":1440,"extraction_method":"Public opportunity listing, linked project details, and public investor opportunity cards","notes":"تُستبعد قوائم الجهات المرخصة وإحصاءات القطاع من الفرص؛ لا تُقبل إلا المواقع المحددة بالأحساء."},
]
locks: dict[str,asyncio.Lock]={}

def seed_sources(db:Session):
    coverage_defaults={"furas":"COMPLETE_PUBLIC_SOURCE","alahsa-opportunities":"COMPLETE_PUBLIC_SOURCE","ahda":"COMPLETE_FOR_DEFINED_SCOPE",
        "invest-saudi":"COMPLETE_PUBLIC_SOURCE","kfu":"COMPLETE_FOR_DEFINED_SCOPE","modon":"PUBLIC_COVERAGE_LIMITED","ncp":"COMPLETE_FOR_DEFINED_SCOPE",
        "nhc":"PUBLIC_COVERAGE_LIMITED","pif":"PUBLIC_COVERAGE_LIMITED","mwan":"COMPLETE_FOR_DEFINED_SCOPE"}
    for item in DEFAULT_SOURCES:
        source=db.scalar(select(Source).where(Source.source_key==item["source_key"]))
        if not source:
            source=Source(**item,enabled=item["source_key"] in ADAPTERS)
            db.add(source)
        else:
            for key,value in item.items():
                if key not in ("notes","polling_frequency_minutes"): setattr(source,key,value)
        if source.source_key in coverage_defaults and source.coverage_status in (None,"UNKNOWN_COVERAGE"):
            source.coverage_status=coverage_defaults[source.source_key]
    aliases=[
        ("al-ahsa-municipality","أمانة الأحساء","Al-Ahsa Municipality","أمانة الأحساء","alahsa-opportunities"),
        ("al-ahsa-municipality","أمانة الأحساء","Al-Ahsa Municipality","أمانة محافظة الأحساء","furas"),
        ("al-ahsa-municipality","أمانة الأحساء","Al-Ahsa Municipality","Al Ahsa Municipality","furas"),
        ("ahda","هيئة تطوير الأحساء","Al-Ahsa Development Authority","هيئة تطوير الأحساء","ahda"),
        ("ahda","هيئة تطوير الأحساء","Al-Ahsa Development Authority","Al-Ahsa Development Authority","ahda"),
        ("misa","وزارة الاستثمار","Ministry of Investment","وزارة الاستثمار","invest-saudi"),
        ("misa","وزارة الاستثمار","Ministry of Investment","Ministry of Investment of Saudi Arabia","invest-saudi"),
        ("kfu","جامعة الملك فيصل","King Faisal University","جامعة الملك فيصل","kfu"),
        ("kfu","جامعة الملك فيصل","King Faisal University","King Faisal University","kfu"),
        ("modon","الهيئة السعودية للمدن الصناعية ومناطق التقنية","Saudi Authority for Industrial Cities and Technology Zones","مدن","modon"),
        ("modon","الهيئة السعودية للمدن الصناعية ومناطق التقنية","Saudi Authority for Industrial Cities and Technology Zones","MODON","modon"),
        ("ncp","المركز الوطني للتخصيص","National Center for Privatization & PPP","المركز الوطني للتخصيص","ncp"),
        ("ncp","المركز الوطني للتخصيص","National Center for Privatization & PPP","National Center for Privatization & PPP","ncp"),
    ]
    for organization_id,ar,en,alias,key in aliases:
        row=db.scalar(select(OrganizationAlias).where(OrganizationAlias.alias==alias))
        if not row: db.add(OrganizationAlias(organization_id=organization_id,canonical_name_ar=ar,canonical_name_en=en,alias=alias,source_key=key))
    db.commit()

def store_status_observation(db,source,record,raw,observed_at=None):
    """Append immutable current source evidence so raw status transitions remain auditable."""
    observed_at=observed_at or NOW()
    payload={"raw_payload":raw.raw or {},"raw_status":raw.status,"raw_deadline":raw.deadline,
        "canonical_status":record.canonical_status}
    content_hash=hashlib.sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False,default=str).encode()).hexdigest()
    exists=db.scalar(select(SourceObservation.id).where(SourceObservation.source_opportunity_id==record.id,
        SourceObservation.endpoint==record.source_url,SourceObservation.content_hash==content_hash))
    if exists:
        return False
    official_id=str(record.official_source_id_original or record.source_opportunity_id)[:200]
    normalized_id=str(record.official_source_id_normalized or official_id)[:200]
    db.add(SourceObservation(source_opportunity_id=record.id,dataset_name="source-record-status-snapshot",
        endpoint=record.source_url,official_source_id_original=official_id,official_source_id_normalized=normalized_id,
        raw_data_json=payload,source_updated_at=None,content_hash=content_hash,first_seen_at=observed_at,last_seen_at=observed_at))
    return True

def store_canonical_status_observation(db,record,observed_at=None):
    """Snapshot a lifecycle-only transition such as confirmed disappearance."""
    observed_at=observed_at or NOW()
    raw_dates=record.raw_dates if isinstance(record.raw_dates,dict) else {}
    payload={"raw_payload":record.raw_data_json or {},"raw_status":record.raw_status,
        "raw_deadline":raw_dates.get("deadline"),"canonical_status":record.canonical_status,
        "missing_successful_checks":record.missing_successful_checks,
        "observation_reason":"confirmed_source_disappearance" if record.missing_successful_checks else "derived_status_transition"}
    content_hash=hashlib.sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False,default=str).encode()).hexdigest()
    exists=db.scalar(select(SourceObservation.id).where(SourceObservation.source_opportunity_id==record.id,
        SourceObservation.endpoint==record.source_url,SourceObservation.content_hash==content_hash))
    if exists:return False
    official_id=str(record.official_source_id_original or record.source_opportunity_id)[:200]
    normalized_id=str(record.official_source_id_normalized or official_id)[:200]
    db.add(SourceObservation(source_opportunity_id=record.id,dataset_name="source-record-status-snapshot",
        endpoint=record.source_url,official_source_id_original=official_id,official_source_id_normalized=normalized_id,
        raw_data_json=payload,source_updated_at=None,content_hash=content_hash,first_seen_at=observed_at,last_seen_at=observed_at))
    return True

def canonical_duplicate_pair(left_id:int,right_id:int)->tuple[int,int]:
    if left_id==right_id:raise ValueError("duplicate candidate requires two distinct Masters")
    return (left_id,right_id) if left_id<right_id else (right_id,left_id)

def queue_conflict_idempotently(db, *, opportunity_id:int, field_name:str, conflict_type:str,
                                selected_value:str, conflicting_value:str, source_id:int,
                                source_record_id:int, detected_at:datetime):
    """Keep one OPEN logical field conflict; link a recurrence to its prior decision."""
    key=(OpportunityConflict.opportunity_id==opportunity_id,
         OpportunityConflict.field_name==field_name,
         OpportunityConflict.selected_value==selected_value,
         OpportunityConflict.conflicting_value==conflicting_value,
         OpportunityConflict.source_id==source_id,
         OpportunityConflict.source_record_id==source_record_id)
    if db.scalar(select(OpportunityConflict.id).where(*key,OpportunityConflict.status=="OPEN")):
        return None
    prior=db.scalar(select(OpportunityConflict.id).where(*key).order_by(OpportunityConflict.id.desc()).limit(1))
    row=OpportunityConflict(opportunity_id=opportunity_id,field_name=field_name,conflict_type=conflict_type,
        selected_value=selected_value,conflicting_value=conflicting_value,source_id=source_id,
        source_record_id=source_record_id,detected_at=detected_at,status="OPEN")
    db.add(row)
    if prior:
        db.add(SystemEvent(event_type="REVIEW_REOPENED",created_at=detected_at,payload={
            "review_type":"opportunity_conflict","prior_review_id":prior,"master_id":opportunity_id,
            "field":field_name,"source_record_id":source_record_id}))
    return row

def _safe_record(db,source,raw,counts,owner_alias_registry=None):
    master_owner=raw.owner
    owner_alias=None
    if raw.owner:
        owner_norm=comparison_key(raw.owner)
        if owner_alias_registry is None:
            aliases=db.scalars(select(OrganizationAlias).where(or_(OrganizationAlias.source_key.is_(None),OrganizationAlias.source_key==source.source_key))).all()
            owner_alias_registry={comparison_key(row.alias):row for row in aliases}
        alias=owner_alias_registry.get(owner_norm)
        if alias:
            owner_alias=alias
            master_owner=alias.canonical_name_ar
    values=normalized_record(raw)
    # Canonical Master projection only. Keep RawOpportunity and SourceOpportunity
    # owner/status/location evidence exactly as received from the source.
    values["opportunity_owner"]=master_owner
    values["primary_publication_platform"]=source.source_name_ar
    result=standardize_opportunity(values,source_key=source.source_key,source_record=raw)
    values=result["values"]
    standardization=result["metadata"]
    if source.source_key=="furas":
        # Furas exposes date keys whose business meanings are not documented
        # well enough to promote them to publication or bid-submission dates.
        # Keep the attributes in raw_data_json and mark both projections as
        # explicitly unverified on every future ingestion.
        attributes=(raw.raw or {}).get("attributes") or {}
        fields=standardization.setdefault("fields",{})
        raw_deadline_fields={key:attributes.get(key) for key in ("STARTDATE","ENDDATE","LASTRFPSELLDATE","LASTBIDATE")}
        fields["submission_deadline"]={"raw":raw_deadline_fields,"canonical_id":None,"canonical_label":None,
            "mapping_status":"UNVERIFIED","rule":"furas_dates_raw_only_v1",
            "review_flags":["UNVERIFIED_DATE_FIELD_SEMANTICS"]}
        fields["publication_date"]={"raw":attributes.get("STARTDATE"),"canonical_id":None,"canonical_label":None,
            "mapping_status":"UNVERIFIED","rule":"furas_dates_raw_only_v1",
            "review_flags":["UNVERIFIED_DATE_FIELD_SEMANTICS"]}
        if attributes.get("DURATION") not in (None, ""):
            fields["contract_duration_years"]={"raw":attributes.get("DURATION"),"normalized":None,
                "canonical_id":None,"canonical_label":None,"mapping_status":"REVIEW_REQUIRED",
                "rule":"furas_duration_unit_and_semantics_unverified_v1",
                "review_flags":["UNVERIFIED_DURATION_UNIT_OR_SEMANTICS"]}
            standardization.setdefault("issues",[]).append({"field":"contract_duration_years",
                "code":"UNVERIFIED_DURATION_UNIT_OR_SEMANTICS","source_key":"furas"})
    canonical_status,status_flags=canonical_source_status(source.source_key,raw.status,raw.deadline)
    values["status"]=canonical_status
    standardization.setdefault("fields",{})["status"]={"raw":raw.status,"canonical_id":canonical_status,
        "canonical_label":canonical_status,"mapping_status":"MAPPED" if canonical_status not in ("حالة غير معروفة","غير محددة") else "REVIEW_REQUIRED",
        "rule":"source_aware_lifecycle_v1","review_flags":status_flags}
    asset_type_projection=standardize_asset_facility_types(db,source.source_key,raw.raw or {})
    standardization["asset_facility_types"]=asset_type_projection
    if owner_alias:
        owner_identity=canonical_identity("owner",owner_alias.canonical_name_ar)
        standardization["fields"]["opportunity_owner"].update({
            "canonical_id":owner_identity["id"] if owner_identity else owner_alias.organization_id,
            "canonical_label":owner_alias.canonical_name_ar,"mapping_status":"MAPPED",
            "rule":"organization_alias_registry_v1"})
    counts["standardization_records_processed"]=counts.get("standardization_records_processed",0)+1
    field_rules=[field.get("rule") for field in standardization.get("fields",{}).values()]
    counts["standardization_fields_changed"]=counts.get("standardization_fields_changed",0)+sum(rule not in ("unchanged","preserve_missing") for rule in field_rules)
    counts["standardization_aliases_matched"]=counts.get("standardization_aliases_matched",0)+sum(rule in ("approved_alias_v1","organization_alias_registry_v1") for rule in field_rules)
    counts["standardization_unmapped_values"]=counts.get("standardization_unmapped_values",0)+sum(field.get("mapping_status")=="UNMAPPED" for field in standardization.get("fields",{}).values())
    counts["standardization_issues"]=counts.get("standardization_issues",0)+len(standardization.get("issues",[]))
    updates_before=counts.get("update_count",0)
    normalized_ref=normalize_reference(raw.reference)
    old=db.scalar(select(SourceOpportunity).where(SourceOpportunity.source_id==source.id,SourceOpportunity.source_opportunity_id==raw.external_id))
    counts["raw_count"]+=1
    if not values["relevant"]:
        counts["rejected_count"]+=1
        if old:
            old.last_seen_at=NOW(); old.content_hash=raw.content_hash; old.raw_data_json=raw.raw or {};old.raw_status=raw.status;old.raw_dates={"deadline":raw.deadline};old.canonical_status=canonical_status
            old.standardized_data_json=standardization;old.standardization_version=STANDARDIZATION_VERSION
            store_source_taxonomy(old,raw,source.source_key)
            store_status_observation(db,source,old,raw)
        else:
            now=NOW()
            record=SourceOpportunity(source_id=source.id,master_opportunity_id=None,source_opportunity_id=raw.external_id,source_reference_number=raw.reference,
                source_reference_number_normalized=normalize_reference(raw.reference),
                source_title=raw.title,normalized_source_title=normalize_arabic(raw.title),source_url=raw.url,source_owner=raw.owner,raw_location=raw.location,raw_area=raw.area_text,
                raw_dates={"deadline":raw.deadline},raw_status=raw.status,canonical_status=canonical_status,raw_data_json=raw.raw or {},standardized_data_json=standardization,
                standardization_version=STANDARDIZATION_VERSION,first_seen_at=now,last_seen_at=now,content_hash=raw.content_hash,parser_version=PARSER_VERSION)
            store_source_taxonomy(record,raw,source.source_key);db.add(record);db.flush();store_status_observation(db,source,record,raw)
        return

    counts["ahsa_count"]+=1
    master=old.master if old else None
    possible_candidate=None
    incoming=SimpleNamespace(source_opportunity_id=raw.external_id,source_reference_number=raw.reference,
        source_title=raw.title,source_owner=raw.owner,raw_location=raw.location,raw_area=raw.area_text,
        raw_dates={"deadline":raw.deadline},raw_status=raw.status,raw_data_json=raw.raw or {},
        source_url=raw.url,source=source)
    # A normalized reference is a lookup candidate, not by itself authorization
    # to attach a record. Require a source-verified official reference on both
    # sides and let the shared identity resolver reject contradictory evidence.
    if not master and normalized_ref:
        ref_masters=db.scalars(select(Opportunity).where(
            Opportunity.merged_into_id.is_(None),
            Opportunity.reference_number_normalized==normalized_ref).order_by(Opportunity.id)).all()
        safe_reference_matches=[]
        reference_review_matches=[]
        for candidate in ref_masters:
            existing_records=db.scalars(select(SourceOpportunity).where(
                SourceOpportunity.master_opportunity_id==candidate.id,
                SourceOpportunity.source_reference_number_normalized==normalized_ref)).all()
            for prior in existing_records:
                if not prior.source:
                    continue
                features=compare_source_records(prior,incoming)
                if features["auto_merge_safe"] and features["trusted_official_reference_match"]:
                    safe_reference_matches.append((candidate,features))
                elif features["same_normalized_reference"]:
                    reference_review_matches.append((candidate,features))
        # A collision, contradiction, same-source alias, or multiple equally
        # strong references must go to review rather than selecting the first row.
        if not reference_review_matches and len(safe_reference_matches)==1:
            master=safe_reference_matches[0][0]
        elif reference_review_matches or len(safe_reference_matches)>1:
            candidates_for_review=reference_review_matches or safe_reference_matches
            candidate,features=max(candidates_for_review,key=lambda item:item[1]["current_duplicate_score"])
            possible_candidate=(candidate,features["current_duplicate_score"],features)
    if not master:
        candidates=db.scalars(select(Opportunity).where(Opportunity.merged_into_id.is_(None)).order_by(Opportunity.last_seen_at.desc()).limit(1000)).all()
        for candidate in candidates:
            existing_records=db.scalars(select(SourceOpportunity).where(SourceOpportunity.master_opportunity_id==candidate.id)).all()
            # Do not use a different source attached to the Master to bypass the
            # same-source fuzzy-merge prohibition. A same-source reference alias
            # is retained separately and queued for explicit review above.
            if any(record.source_id==source.id for record in existing_records):
                continue
            comparisons=[]
            for prior in existing_records:
                if not prior.source or prior.source.source_key==source.source_key:
                    continue  # same-source fuzzy resolution is prohibited
                features=compare_source_records(prior,incoming)
                comparisons.append((prior,features))
            if not comparisons: continue
            prior,features=max(comparisons,key=lambda item:item[1]["current_duplicate_score"])
            score=features["current_duplicate_score"]
            if features["auto_merge_safe"] and score>=.90:
                master=candidate
                break
            # Candidate generation is intentionally broader than the score bands:
            # exact plan/parcel + owner + compatible area can surface a low-score
            # review case when GIS locality coverage is weak (the reviewed Pair 4).
            candidate_signal = score >= .75 or features["strong_composite_match"] or features["exact_identifier_match"]
            if candidate_signal and (possible_candidate is None or score>possible_candidate[1]):
                possible_candidate=(candidate,score,features)
    now=NOW()
    conflicts=[]
    for flag in status_flags:
        if flag in {"AMBIGUOUS_RAW_STATUS","AMBIGUOUS_BOOLEAN_STATUS","INVALID_DEADLINE","STATUS_DEADLINE_CONFLICT"}:
            field="submission_deadline" if flag=="INVALID_DEADLINE" else "status"
            evidence=(raw.deadline if field=="submission_deadline" else f"{raw.status!r}; deadline={raw.deadline!r}")
            conflicts.append((field,str(canonical_status),str(evidence or "قيمة حالة غير قابلة للتفسير")))
    wrong_dimension=next((issue for issue in standardization.get("issues",[]) if issue.get("code")=="WRONG_DIMENSION_SECTOR_UNSPECIFIED"),None)
    if wrong_dimension:
        raw_sector=((raw.raw or {}).get("source_taxonomy") or {}).get("sector") or raw.activity
        if raw_sector:
            conflicts.append(("sector",str(master.sector if master and master.sector else "غير محدد"),str(raw_sector)))
    model_review=next((issue for issue in standardization.get("issues",[]) if issue.get("field")=="investment_model" and issue.get("code")=="INVESTMENT_MODEL_REVIEW_REQUIRED"),None)
    if model_review:
        evidence=(standardization.get("fields",{}).get("investment_model_evidence") or {}).get("raw")
        conflicts.append(("investment_model",str(master.investment_model if master and master.investment_model else "غير محدد"),str(evidence or "يتطلب تحديد نموذج الاستثمار")))
    if master is None:
        master=Opportunity(canonical_id=f"AH-{now:%Y%m%d%H%M%S}-{raw.content_hash[:8]}",title_ar=raw.title,normalized_title=values["normalized_title"],
            reference_number=raw.reference,reference_number_normalized=normalized_ref,opportunity_owner=values["opportunity_owner"],primary_publication_platform=source.source_name_ar,city=values["city"],
            land_area_sqm=values["land_area_sqm"],sector=values["sector"],activity=values["activity"],sub_activity=values["sub_activity"],opportunity_type=values["opportunity_type"],investment_model=values["investment_model"],contract_duration_years=values["contract_duration_years"],
            submission_deadline=values["submission_deadline"],status=values["status"],location_description=values["location_description"],short_description=values["short_description"],full_description=values["full_description"],
            latitude=values["latitude"],longitude=values["longitude"],publication_date=values["publication_date"],location_confidence_score=values["location_confidence_score"],location_detection_method=values["location_detection_method"],location_evidence=values["location_evidence"],data_quality_score=values["data_quality_score"],
            manual_review_required=values["location_confidence_score"]<LOCATION_ACCEPTANCE_THRESHOLD,first_seen_at=now,last_seen_at=now,last_updated_at=now,created_at=now,updated_at=now)
        db.add(master); db.flush(); counts["new_count"]+=1
        _alert(db,"OPPORTUNITY_CREATED","INFO",master,source,raw,master.canonical_id)
        if possible_candidate:
            candidate,score,features=possible_candidate
            pair=canonical_duplicate_pair(candidate.id,master.id)
            pair_match=or_(and_(DuplicateCandidate.left_opportunity_id==pair[0],DuplicateCandidate.right_opportunity_id==pair[1]),
                           and_(DuplicateCandidate.left_opportunity_id==pair[1],DuplicateCandidate.right_opportunity_id==pair[0]))
            open_pair=db.scalar(select(DuplicateCandidate.id).where(DuplicateCandidate.status=="PENDING",pair_match))
            prior_pair=db.scalar(select(DuplicateCandidate.id).where(pair_match).order_by(DuplicateCandidate.id.desc()).limit(1))
            if not open_pair: db.add(DuplicateCandidate(left_opportunity_id=pair[0],right_opportunity_id=pair[1],confidence_score=score,status="PENDING",created_at=now,
                explanation_json={"positive_evidence":features["positive_evidence"],"contradicting_evidence":features["contradicting_evidence"],
                    "features":{k:features[k] for k in ("title_similarity","location_similarity","area_similarity","area_difference_percentage","description_similarity","exact_identifier_match","plot_match","plan_match","duration_match","deadline_match")},"auto_merge_safe":features["auto_merge_safe"],"recurrence_of":prior_pair}))
            if prior_pair and not open_pair: db.add(SystemEvent(event_type="REVIEW_REOPENED",created_at=now,payload={"review_type":"duplicate_candidate","prior_review_id":prior_pair,"master_ids":list(pair)}))
            counts["duplicate_candidates_count"]=counts.get("duplicate_candidates_count",0)+1
    else:
        if old is None:
            counts["duplicate_count"]+=1
            counts["merged_records_count"]=counts.get("merged_records_count",0)+1
        master.last_seen_at=now
        # Source city fields can name a governorate, an urban locality, or a
        # municipality-level area. The master city is intentionally normalized
        # to Al-Ahsa, so comparing those labels as competing city values creates
        # false conflict rows. Detailed source locations remain in provenance.
        for key in ("title_ar","reference_number","opportunity_owner","land_area_sqm","sector","activity","sub_activity","opportunity_type","investment_model","contract_duration_years","submission_deadline","location_description","short_description","latitude","longitude","publication_date"):
            new=values.get(key)
            if new is not None and getattr(master,key)!=new:
                previous=getattr(master,key)
                same_source_value = not old or old.source_title == raw.title
                if same_source_value and values_equivalent(key,previous,new):
                    continue
                if not previous:
                    setattr(master,key,new)
                    if key=="reference_number": master.reference_number_normalized=normalize_reference(new)
                else:
                    provenance=db.scalars(select(FieldProvenance).where(FieldProvenance.opportunity_id==master.id,FieldProvenance.field_name==key)).all()
                    matching_provenance=[p for p in provenance if p.selected_value==str(previous)]
                    fallback_keys=db.scalars(select(Source.source_key).join(SourceOpportunity,SourceOpportunity.source_id==Source.id).where(SourceOpportunity.master_opportunity_id==master.id)).all()
                    fallback_rank=max([source_authority(key) for key in fallback_keys] or [0])
                    selected_rank=max([source_authority(p.source.source_key) for p in matching_provenance if p.source] or [fallback_rank])
                    current_source_was_selected=bool(old and any(p.source_record_id==old.id for p in matching_provenance))
                    source_value_changed=bool(old and old.content_hash!=raw.content_hash)
                    may_select=(source_authority(source.source_key)>selected_rank or (current_source_was_selected and source_value_changed))
                    if not may_select:
                        conflicts.append((key,str(previous),str(new)))
                        continue
                    db.add(ChangeHistory(opportunity_id=master.id,changed_field=key,previous_value=str(previous),new_value=str(new),source_id=source.id,detected_at=now))
                    if key=="reference_number": master.reference_number_normalized=normalize_reference(new)
                    counts["update_count"]+=1; setattr(master,key,new)
            if key in ("submission_deadline","status","investment_value","location_description","latitude","longitude"):
                event="DEADLINE_CHANGED" if key=="submission_deadline" else "OPPORTUNITY_UPDATED"
                _alert(db,event,"INFO",master,source,raw,hashlib.sha256(f"{key}:{new}".encode()).hexdigest())
        master.last_updated_at=now; master.updated_at=now
    if old:
        previous_source_status=old.canonical_status
        old.master_opportunity_id=master.id; old.last_seen_at=now;old.missing_successful_checks=0;old.last_missing_at=None
        old.source_reference_number=raw.reference
        old.source_reference_number_normalized=normalized_ref
        url_history=source_url_history_observation(old,raw.url,now)
        if url_history:db.add(SourceObservation(**url_history))
        old.source_title=raw.title;old.normalized_source_title=values["normalized_title"];old.source_url=raw.url
        old.source_owner=raw.owner;old.raw_location=raw.location;old.raw_area=raw.area_text;old.raw_status=raw.status;old.canonical_status=canonical_status
        old.standardized_data_json=standardization;old.standardization_version=STANDARDIZATION_VERSION
        if previous_source_status!=canonical_status:
            db.add(ChangeHistory(opportunity_id=master.id,changed_field="source_status",previous_value=previous_source_status,
                new_value=canonical_status,source_id=source.id,detected_at=now))
        if old.content_hash!=raw.content_hash:
            old_documents=(old.raw_data_json or {}).get("documents",[])
            new_documents=(raw.raw or {}).get("documents",[])
            if old_documents!=new_documents:
                db.add(ChangeHistory(opportunity_id=master.id,changed_field="documents",previous_value=str(old_documents),new_value=str(new_documents),source_id=source.id,detected_at=now))
            old.content_hash=raw.content_hash; old.raw_data_json=raw.raw or {}; old.raw_dates={"deadline":raw.deadline}
            counts["update_count"]+=1
        record=old
        store_source_taxonomy(record,raw,source.source_key)
        for field in ("title_ar","reference_number","opportunity_owner","land_area_sqm","sector","activity","sub_activity","investment_model","contract_duration_years","submission_deadline","status","location_description","short_description","latitude","longitude","publication_date"):
            incoming=values.get(field); selected=getattr(master,field,None)
            if selected is None or incoming is None or str(selected)!=str(incoming): continue
            existing=db.scalar(select(FieldProvenance.id).where(FieldProvenance.opportunity_id==master.id,FieldProvenance.field_name==field,
                FieldProvenance.source_record_id==old.id,FieldProvenance.selected_value==str(selected)))
            if not existing: db.add(FieldProvenance(opportunity_id=master.id,field_name=field,selected_value=str(selected),source_id=source.id,source_record_id=old.id,captured_at=now,confidence=values["location_confidence_score"]))
    else:
        record=SourceOpportunity(source_id=source.id,master_opportunity_id=master.id,source_opportunity_id=raw.external_id,source_reference_number=raw.reference,source_reference_number_normalized=normalized_ref,
            source_title=raw.title,normalized_source_title=values["normalized_title"],source_url=raw.url,source_owner=raw.owner,raw_location=raw.location,raw_area=raw.area_text,
            raw_dates={"deadline":raw.deadline},raw_status=raw.status,canonical_status=canonical_status,raw_data_json=raw.raw or {},standardized_data_json=standardization,
            standardization_version=STANDARDIZATION_VERSION,first_seen_at=now,last_seen_at=now,content_hash=raw.content_hash,parser_version=PARSER_VERSION)
        store_source_taxonomy(record,raw,source.source_key)
        db.add(record); db.flush()
        for field in ("title_ar","reference_number","opportunity_owner","land_area_sqm","sector","activity","sub_activity","investment_model","contract_duration_years","submission_deadline","status","location_description","short_description","latitude","longitude","publication_date"):
            incoming=values.get(field); selected=getattr(master,field,None)
            if selected is not None and incoming is not None and str(selected)==str(incoming):
                db.add(FieldProvenance(opportunity_id=master.id,field_name=field,selected_value=str(selected),source_id=source.id,source_record_id=record.id,captured_at=now,confidence=values["location_confidence_score"]))
    if old and counts.get("update_count",0)==updates_before:
        counts["unchanged_count"]=counts.get("unchanged_count",0)+1
    db.flush()
    store_status_observation(db,source,record,raw,now)
    linked_states=db.scalars(select(SourceOpportunity.canonical_status).where(
        SourceOpportunity.master_opportunity_id==master.id)).all()
    projected_status,projection_flags=aggregate_master_status(linked_states)
    if projected_status!=master.status:
        previous_status=master.status
        master.status=projected_status
        master.last_updated_at=now;master.updated_at=now
        db.add(ChangeHistory(opportunity_id=master.id,changed_field="status",previous_value=previous_status,
            new_value=projected_status,source_id=source.id,detected_at=now))
    if projection_flags:
        conflicting=" | ".join(sorted(set(linked_states)))
        exists=db.scalar(select(OpportunityConflict.id).where(OpportunityConflict.opportunity_id==master.id,
            OpportunityConflict.field_name=="status",OpportunityConflict.conflicting_value==conflicting,
            OpportunityConflict.source_record_id==record.id,OpportunityConflict.status=="OPEN"))
        if not exists:
            db.add(OpportunityConflict(opportunity_id=master.id,field_name="status",conflict_type="FIELD_VALUE_CONFLICT",
                selected_value=projected_status,conflicting_value=conflicting,source_id=source.id,
                source_record_id=record.id,detected_at=now,status="OPEN"))
    # A source-level standardization flag is actionable review evidence, not a
    # canonical duration. Keep it in the governed queue without promoting the
    # raw Furas number to years. The idempotent key is scoped to the Master and
    # source record, so repeated observations do not multiply open cases.
    duration_field=(standardization.get("fields") or {}).get("contract_duration_years") or {}
    if source.source_key=="furas" and master.contract_duration_years is None and duration_field.get("mapping_status")=="REVIEW_REQUIRED":
        raw_duration=duration_field.get("raw")
        if raw_duration not in (None, ""):
            queue_conflict_idempotently(db,opportunity_id=master.id,field_name="contract_duration_years",
                conflict_type="STANDARDIZATION_REVIEW",selected_value=str(master.contract_duration_years or ""),
                conflicting_value=str(raw_duration),source_id=source.id,source_record_id=record.id,detected_at=now)
    # Invest Saudi's literal zero investmentSize values have no currency or
    # documented meaning. Preserve them as raw evidence and keep the canonical
    # investment value unspecified until a reviewer has evidence to decide.
    investment_size=(raw.raw or {}).get("investmentSize")
    if source.source_key=="invest-saudi" and master.investment_value is None and str(investment_size).strip() in ("0","0.0"):
        queue_conflict_idempotently(db,opportunity_id=master.id,field_name="investment_value",
            conflict_type="STANDARDIZATION_REVIEW",selected_value=str(master.investment_value or ""),
            conflicting_value=str(investment_size),source_id=source.id,source_record_id=record.id,detected_at=now)
    prior_asset_assignments=db.scalars(select(OpportunityAssetFacilityType).where(OpportunityAssetFacilityType.source_record_id==record.id)).all()
    prior_asset_ids={item.canonical_id for item in prior_asset_assignments}
    incoming_asset_assignments=asset_type_projection.get("assignments",[])
    incoming_asset_ids={item["canonical_id"] for item in incoming_asset_assignments}
    if prior_asset_ids!=incoming_asset_ids:
        def labels(ids):
            from .asset_facility_types import ASSET_FACILITY_TYPE_LABELS
            return " | ".join(sorted((ASSET_FACILITY_TYPE_LABELS.get(value,value) for value in ids),key=comparison_key)) or "غير محدد"
        db.add(ChangeHistory(opportunity_id=master.id,changed_field="asset_facility_type",previous_value=labels(prior_asset_ids),new_value=labels(incoming_asset_ids),source_id=source.id,detected_at=now))
    db.execute(delete(OpportunityAssetFacilityType).where(OpportunityAssetFacilityType.source_record_id==record.id))
    for assignment in incoming_asset_assignments:
        db.add(OpportunityAssetFacilityType(opportunity_id=master.id,canonical_id=assignment["canonical_id"],source_record_id=record.id,raw_value=assignment["raw_value"]))
    for item in asset_type_projection.get("unresolved",[]):
        conflicts.append(("asset_facility_type","غير محدد",str(item["raw_value"])))
    for field,selected,conflicting in conflicts:
        row=queue_conflict_idempotently(db,opportunity_id=master.id,field_name=field,
            conflict_type="TAXONOMY_CONFLICT" if field in ("sector","subsector","sub_activity","opportunity_type","activity","investment_model","asset_facility_type") else "FIELD_VALUE_CONFLICT",
            selected_value=selected,conflicting_value=conflicting,source_id=source.id,source_record_id=record.id,detected_at=now)

def re_search_plot(title:str):
    import re
    match=re.search(r"(?:قطعة|plot)\s*(?:رقم)?\s*([\w/-]+)",title,re.I)
    return match.group(1) if match else None

def reconcile_missing_records(db:Session,source:Source,seen_external_ids:set[str],checked_at:datetime):
    """Count misses only after complete successful snapshots; a single miss never removes a master."""
    # Reconcile every source identity, including national/unqualified rows that
    # intentionally have no Master.  Master lifecycle projection below remains
    # conditional on a Master link; SourceOpportunity history is not.
    existing=db.scalars(select(SourceOpportunity).where(SourceOpportunity.source_id==source.id)).all()
    threshold=max(1,int(source.missing_confirmation_threshold or 3))
    removed=[]
    for row in existing:
        if row.source_opportunity_id in seen_external_ids:
            row.missing_successful_checks=0;row.last_missing_at=None
            continue
        row.missing_successful_checks=(row.missing_successful_checks or 0)+1;row.last_missing_at=checked_at
        if row.missing_successful_checks<threshold:continue
        previous_source_status=row.canonical_status
        row.canonical_status="أزيلت من المصدر"
        store_canonical_status_observation(db,row,checked_at)
        # An unlinked SourceOpportunity has no Master to project into, but its
        # source-level lifecycle and immutable observation must still advance.
        if row.master_opportunity_id is None:
            if previous_source_status!="أزيلت من المصدر":
                removed.append({"source_opportunity_id":row.source_opportunity_id,"master_opportunity_id":None,
                    "missing_successful_checks":row.missing_successful_checks})
            continue
        master=db.get(Opportunity,row.master_opportunity_id)
        if not master:continue
        linked_states=db.scalars(select(SourceOpportunity.canonical_status).where(
            SourceOpportunity.master_opportunity_id==master.id)).all()
        projected_status,projection_flags=aggregate_master_status(linked_states)
        if projected_status!=master.status:
            previous=master.status;master.status=projected_status;master.last_updated_at=checked_at;master.updated_at=checked_at
            db.add(ChangeHistory(opportunity_id=master.id,changed_field="status",previous_value=previous,new_value=projected_status,source_id=source.id,detected_at=checked_at))
        if previous_source_status!="أزيلت من المصدر":
            db.add(ChangeHistory(opportunity_id=master.id,changed_field="source_status",previous_value=previous_source_status,new_value="أزيلت من المصدر",source_id=source.id,detected_at=checked_at))
        removed.append({"source_opportunity_id":row.source_opportunity_id,"master_opportunity_id":master.id,"missing_successful_checks":row.missing_successful_checks})
    return removed

def reconcile_status_lifecycle(db:Session,checked_at=None):
    """Refresh date-derived source states and deterministic Master projections."""
    from .status_lifecycle import canonical_source_status
    checked_at=checked_at or NOW();updated_sources=0;updated_masters=0;reviews=0
    rows=db.scalars(select(SourceOpportunity)).all()
    affected_masters=set()
    for row in rows:
        source=row.source
        threshold=max(1,int(source.missing_confirmation_threshold or 3))
        if (row.missing_successful_checks or 0)>=threshold:
            projected_source="أزيلت من المصدر";flags=[]
        else:
            dates=row.raw_dates if isinstance(row.raw_dates,dict) else {}
            projected_source,flags=canonical_source_status(source.source_key,row.raw_status,dates.get("deadline"),now=checked_at)
        if row.canonical_status!=projected_source:
            previous=row.canonical_status;row.canonical_status=projected_source;updated_sources+=1
            if row.master_opportunity_id is not None:
                db.add(ChangeHistory(opportunity_id=row.master_opportunity_id,changed_field="source_status",previous_value=previous,
                    new_value=projected_source,source_id=row.source_id,detected_at=checked_at))
            store_canonical_status_observation(db,row,checked_at)
        status_field=(row.standardized_data_json or {}).get("fields",{}).get("status",{})
        if status_field.get("review_flags")!=flags or status_field.get("canonical_id")!=projected_source or status_field.get("raw")!=row.raw_status:
            standardized=dict(row.standardized_data_json or {});fields=dict(standardized.get("fields") or {})
            fields["status"]={**status_field,"raw":row.raw_status,"canonical_id":projected_source,
                "canonical_label":projected_source,"mapping_status":"MAPPED" if projected_source not in ("حالة غير معروفة","غير محددة") else "REVIEW_REQUIRED",
                "rule":"source_aware_lifecycle_v1","review_flags":flags}
            standardized["fields"]=fields;row.standardized_data_json=standardized
        if row.master_opportunity_id is not None:
            affected_masters.add(row.master_opportunity_id)
        for flag in flags:
            if flag not in {"AMBIGUOUS_RAW_STATUS","AMBIGUOUS_BOOLEAN_STATUS","INVALID_DEADLINE","STATUS_DEADLINE_CONFLICT"}:continue
            if row.master_opportunity_id is None:continue
            field="submission_deadline" if flag=="INVALID_DEADLINE" else "status"
            evidence=(row.raw_dates or {}).get("deadline") if field=="submission_deadline" else f"{row.raw_status!r}; deadline={(row.raw_dates or {}).get('deadline')!r}"
            created=queue_conflict_idempotently(db,opportunity_id=row.master_opportunity_id,field_name=field,
                conflict_type="FIELD_VALUE_CONFLICT",selected_value=projected_source,
                conflicting_value=str(evidence or "قيمة حالة غير قابلة للتفسير"),source_id=row.source_id,
                source_record_id=row.id,detected_at=checked_at)
            if created:reviews+=1
    for master_id in affected_masters:
        master=db.get(Opportunity,master_id)
        if not master:continue
        states=db.scalars(select(SourceOpportunity.canonical_status).where(SourceOpportunity.master_opportunity_id==master_id)).all()
        projected,flags=aggregate_master_status(states)
        if master.status!=projected:
            previous=master.status;master.status=projected;master.updated_at=checked_at;master.last_updated_at=checked_at;updated_masters+=1
            db.add(ChangeHistory(opportunity_id=master.id,changed_field="status",previous_value=previous,new_value=projected,
                source_id=None,detected_at=checked_at))
        if flags:
            record=db.scalar(select(SourceOpportunity).where(SourceOpportunity.master_opportunity_id==master_id).order_by(SourceOpportunity.id).limit(1))
            if record:
                evidence=" | ".join(sorted(set(states)))
                created=queue_conflict_idempotently(db,opportunity_id=master_id,field_name="status",
                    conflict_type="FIELD_VALUE_CONFLICT",selected_value=projected,conflicting_value=evidence,
                    source_id=record.source_id,source_record_id=record.id,detected_at=checked_at)
                if created:reviews+=1
    db.flush()
    return {"updated_source_statuses":updated_sources,"updated_master_statuses":updated_masters,"reviews_created":reviews}

async def sync_source(source_key:str,queued_job_id:int|None=None):
    lock=locks.setdefault(source_key,asyncio.Lock())
    if lock.locked(): return {"status":"ALREADY_RUNNING","source_key":source_key}
    async with lock:
        db=SessionLocal()
        source=db.scalar(select(Source).where(Source.source_key==source_key))
        if not source or not source.enabled:
            db.close(); return {"status":"DISABLED_OR_UNKNOWN","source_key":source_key}
        adapter_cls=ADAPTERS.get(source_key)
        if not adapter_cls:
            db.close(); return {"status":"NOT_IMPLEMENTED","source_key":source_key}
        job=db.get(SyncJob,queued_job_id) if queued_job_id else None
        if job is None:
            job=SyncJob(source_id=source.id,started_at=NOW(),status="RUNNING",job_state="RUNNING",heartbeat_at=NOW())
            db.add(job)
        else:
            job.started_at=NOW();job.status="RUNNING";job.job_state="RUNNING";job.heartbeat_at=NOW()
        source.sync_status="RUNNING"; source.last_attempted_sync=NOW(); db.commit()
        counts={"pages_scanned":0,"raw_count":0,"ahsa_count":0,"new_count":0,"duplicate_count":0,"update_count":0,"unchanged_count":0,"rejected_count":0,"duplicate_candidates_count":0,"merged_records_count":0,"removed_records_count":0,"location_review_count":0,
            "standardization_records_processed":0,"standardization_fields_changed":0,"standardization_aliases_matched":0,"standardization_unmapped_values":0,"standardization_issues":0}
        try:
            timeout=httpx.Timeout(35,connect=15)
            adapter=adapter_cls()
            async with httpx.AsyncClient(timeout=timeout,verify=__import__("ssl").create_default_context(),follow_redirects=True,limits=httpx.Limits(max_connections=4)) as client:
                records,pages=await adapter.fetch(client)
            if source_key=="invest-saudi":
                # A published Furas opportunity number is a verified source linkage because
                # Furas itself was collected through the Al-Ahsa municipality filters.
                furas_source=db.scalar(select(Source).where(Source.source_key=="furas"))
                accepted_ids={raw.external_id for raw in records}
                linked_count=0;link_enrichments=[]
                if furas_source:
                    for raw in getattr(adapter,"raw_candidates",[]):
                        ref=normalize_reference(raw.reference)
                        if not ref or raw.external_id in accepted_ids:continue
                        linked=db.scalar(select(SourceOpportunity).where(SourceOpportunity.source_id==furas_source.id,
                            SourceOpportunity.source_reference_number_normalized==ref,SourceOpportunity.master_opportunity_id.is_not(None)).limit(1))
                        if not linked:continue
                        existing_invest=db.scalar(select(SourceOpportunity).where(SourceOpportunity.source_id==source.id,
                            SourceOpportunity.source_opportunity_id==raw.external_id))
                        previous_raw=(existing_invest.raw_data_json or {}) if existing_invest else {}
                        previous_link=previous_raw.get("linked_furas_source_record_id")
                        raw.raw=dict(raw.raw or {});raw.raw.update({"location_confidence_score":.95,"location_detection_method":"LINKED_FURAS_REFERENCE","location_evidence":f"Exact opportunity number links to Al-Ahsa-filtered Furas record {linked.source_opportunity_id}.","qualified_location":True,"linked_furas_source_record_id":linked.id})
                        if previous_link!=linked.id:
                            link_enrichments.append({"source_opportunity_id":raw.external_id,"furas_source_record_id":linked.id,
                                "reference":ref,"previous":{"location_confidence_score":previous_raw.get("location_confidence_score"),
                                    "location_detection_method":previous_raw.get("location_detection_method"),
                                    "qualified_location":previous_raw.get("qualified_location"),
                                    "linked_furas_source_record_id":previous_link},
                                "current":{"location_confidence_score":.95,"location_detection_method":"LINKED_FURAS_REFERENCE",
                                    "qualified_location":True,"linked_furas_source_record_id":linked.id}})
                        raw.location_source_filtered=True;records.append(raw);accepted_ids.add(raw.external_id);linked_count+=1
                if linked_count:
                    adapter.location_reviews=[r for r in adapter.location_reviews if r["external_id"] not in accepted_ids]
                    adapter.metrics["known_furas_link_matches"]=linked_count
                    adapter.metrics["accepted_records"]+=linked_count
                    adapter.metrics["active_count"]=adapter.metrics.get("active_count",0)+linked_count
                    adapter.metrics["location_review_count"]=len(adapter.location_reviews)
                    adapter.metrics["rejected_records"]=adapter.metrics["unique_records"]-adapter.metrics["accepted_records"]-len(adapter.location_reviews)
                    if link_enrichments:
                        db.add(SystemEvent(event_type="SOURCE_RECORD_CROSS_SOURCE_ENRICHED",created_at=NOW(),payload={
                            "source_key":"invest-saudi","job_id":job.id,"classification":"VALID_CROSS_SOURCE_ENRICHMENT",
                            "enrichments":link_enrichments,"reason":"An exact published Furas opportunity reference links the Invest Saudi source row to an Al-Ahsa-filtered record; no Master identity or source API value is replaced."}))
            counts["pages_scanned"]=pages
            adapter_metrics=getattr(adapter,"metrics",{})
            if source_key=="nhc" and adapter_metrics.get("route_inventory"):
                # Route state is retained as a compact snapshot on each sync job.
                # This makes failures explicit without treating a blocked supporting
                # page as an empty inventory or deleting its last successful content.
                previous_job=db.scalar(select(SyncJob).where(SyncJob.source_id==source.id,SyncJob.id!=job.id)
                    .order_by(SyncJob.id.desc()).limit(1))
                previous_routes={r.get("route_url"):r for r in ((previous_job.metrics_json or {}).get("route_inventory",[]) if previous_job else [])}
                current_time=NOW().isoformat()
                for route in adapter_metrics["route_inventory"]:
                    url=route["route_url"]
                    previous=previous_routes.get(url,{})
                    old_content=db.scalar(select(SourceContentItem).where(SourceContentItem.source_id==source.id,SourceContentItem.external_key==url))
                    was_successful=previous.get("route_state")=="SUCCESS"
                    last_success=previous.get("last_success_at") or (old_content.extracted_at.isoformat() if old_content else None)
                    last_failure=previous.get("last_failure_at")
                    if not last_failure:
                        historical_failure=db.scalar(select(SourceError).where(SourceError.source_id==source.id,SourceError.message.like(f"{url}%"))
                            .order_by(SourceError.id.desc()).limit(1))
                        if historical_failure:
                            last_failure=historical_failure.occurred_at.isoformat()
                    previous_failures=int(previous.get("consecutive_failures",0) or 0)
                    if route["route_state"]=="SUCCESS":
                        last_success=current_time
                        consecutive_failures=0
                    else:
                        last_failure=current_time
                        consecutive_failures=previous_failures+1 if previous.get("route_state") in ("ACCESS_RESTRICTED","FETCH_FAILED","PARSER_FAILED") else 1
                    route.update({"last_success_at":last_success,"last_failure_at":last_failure,
                        "consecutive_failures":consecutive_failures,
                        "previous_successful_content_preserved":bool(old_content and route["route_state"]=="ACCESS_RESTRICTED"),
                        "last_success_was_recorded":bool(was_successful or old_content)})
            for page_error in adapter_metrics.get("page_errors",[]):
                db.add(SourceError(source_id=source.id,occurred_at=NOW(),category="PAGE_FETCH",message=f"{page_error.get('url')}: {page_error.get('error')}"))
            for surface_error in adapter_metrics.get("public_surface_errors",[]):
                db.add(SourceError(source_id=source.id,occurred_at=NOW(),category=str(surface_error.get("status") or "PUBLIC_SURFACE"),message=f"{surface_error.get('url')}: public surface check failed"))
            source_total=adapter_metrics.get("source_total_reported")
            unique_records=adapter_metrics.get("unique_records",len(records))
            endpoint_rows_received=adapter_metrics.get("endpoint_rows_received",adapter_metrics.get("records_received",unique_records))
            completeness=(100.0*endpoint_rows_received/source_total if source_total else
                (100.0 if adapter_metrics.get("pagination_complete") is True and adapter_metrics.get("source_collection_complete",True) is True and unique_records else 0.0))
            pagination_complete=adapter_metrics.get("pagination_complete")
            collected_total=endpoint_rows_received if source_key=="invest-saudi" else unique_records
            complete=(pagination_complete is True and adapter_metrics.get("source_collection_complete",True) is True and adapter_metrics.get("pages_successful",pages)>0 and (source_total is None or collected_total==source_total))
            public_scope_complete=bool(adapter_metrics.get("public_scope_complete",complete))
            source.coverage_status=adapter_metrics.get("coverage_status",source.coverage_status or "UNKNOWN_COVERAGE")
            source.technical_health=adapter_metrics.get("technical_health") or ("HEALTHY" if complete else "WARNING")
            if source_key=="invest-saudi":
                adapter_metrics.update(investsaudi_reconciliation_metrics(
                    complete,endpoint_rows_received,adapter_metrics.get("unique_official_ids",unique_records),
                    adapter_metrics.get("duplicate_endpoint_memberships"),len(adapter_metrics.get("endpoints",[]))))
            counts.update({"source_total_reported":source_total,"pages_requested":adapter_metrics.get("pages_requested",pages),
                "pages_successful":adapter_metrics.get("pages_successful",pages),"records_received":adapter_metrics.get("records_received",len(records)),
                "records_parsed":adapter_metrics.get("records_parsed",len(records)),"unique_records":unique_records,
                "collection_completeness_percent":round(completeness,2),"pagination_complete":pagination_complete,
                "active_count":adapter_metrics.get("active_count",0),"expired_count":adapter_metrics.get("expired_count",0),
                "duplicate_items_between_pages":adapter_metrics.get("duplicate_items_between_pages",0)})
            # Preserve content publishers independently; an empty qualified set is healthy only
            # when the sitemap/pages were fully discovered and parsed.
            content_items=getattr(adapter,"content_items",[])
            for item in content_items:
                old_content=db.scalar(select(SourceContentItem).where(SourceContentItem.source_id==source.id,SourceContentItem.external_key==item["url"]))
                now=NOW(); changed=bool(old_content and old_content.fingerprint!=item.get("fingerprint"))
                if old_content:
                    old_content.title=item.get("title","");old_content.publication_date=item.get("publication_date");old_content.content_type=item.get("content_type","NON_INVESTMENT_CONTENT")
                    old_content.raw_text=item.get("raw_text","");old_content.extracted_description=item.get("extracted_description","");old_content.attachments_json=item.get("attachments",[])
                    old_content.detected_keywords_json=item.get("detected_keywords",[]);old_content.fingerprint=item.get("fingerprint","");old_content.extracted_at=now;old_content.parser_version=item.get("parser_version",PARSER_VERSION);old_content.material_change=changed
                else:
                    db.add(SourceContentItem(source_id=source.id,external_key=item["url"],url=item["url"],title=item.get("title",""),publication_date=item.get("publication_date"),content_type=item.get("content_type","NON_INVESTMENT_CONTENT"),raw_text=item.get("raw_text",""),extracted_description=item.get("extracted_description",""),attachments_json=item.get("attachments",[]),detected_keywords_json=item.get("detected_keywords",[]),fingerprint=item.get("fingerprint",""),extracted_at=now,parser_version=item.get("parser_version",PARSER_VERSION)))
            db.flush()
            # Invest Saudi stores its complete national snapshot as source records, even when a
            # record is rejected geographically. Only qualified records reach Master Opportunity.
            records_to_store=getattr(adapter,"raw_candidates",None) or records
            invest_seen_by_dataset={};invest_created=0;invest_updated=0
            owner_alias_registry={comparison_key(row.alias):row for row in db.scalars(select(OrganizationAlias).where(
                or_(OrganizationAlias.source_key.is_(None),OrganizationAlias.source_key==source_key))).all()}
            if source_key=="modon":
                # Geography is evidence from the official catalog filters, even when
                # the public catalog has no currently verifiable opportunity rows.
                for location in ({"source_identifier":"public-filter:first-industrial-city-al-ahsa","official_name_en":"First Industrial City in Al-Ahsa","official_name_ar":"المدينة الصناعية الأولى بالأحساء","location_type":"INDUSTRIAL_CITY"},
                                 {"source_identifier":"public-filter:modon-oasis-al-ahsa","official_name_en":"Modon Oasis in Al-Ahsa","official_name_ar":"واحة مدن بالأحساء","location_type":"INDUSTRIAL_OASIS"}):
                    existing_location=db.scalar(select(ModonLocation).where(ModonLocation.source_identifier==location["source_identifier"]))
                    if not existing_location:
                        db.add(ModonLocation(**location,region="Eastern Province",governorate=None,latitude=None,longitude=None,active=True,
                            source_url="https://modon.gov.sa/en/InvestmentOpportunities",verified_at=NOW()))
                    else:
                        existing_location.official_name_ar=location["official_name_ar"];existing_location.region="Eastern Province";existing_location.active=True;existing_location.verified_at=NOW()
            for raw in records_to_store:
                previous=db.scalar(select(SourceOpportunity).where(SourceOpportunity.source_id==source.id,SourceOpportunity.source_opportunity_id==raw.external_id)) if source_key=="invest-saudi" else None
                if source_key=="invest-saudi":
                    if previous is None:invest_created+=1
                _safe_record(db,source,raw,counts,owner_alias_registry=owner_alias_registry)
                record=db.scalar(select(SourceOpportunity).where(SourceOpportunity.source_id==source.id,SourceOpportunity.source_opportunity_id==raw.external_id))
                if record:
                    payload=raw.raw or {}
                    places=payload.get("opportunity_locations") or []
                    for place_name in places:
                        if not place_name:continue
                        place=db.scalar(select(OpportunityLocation).where(OpportunityLocation.source_opportunity_id==record.id,OpportunityLocation.location_name==str(place_name)))
                        if not place:
                            place=OpportunityLocation(source_opportunity_id=record.id,location_name=str(place_name));db.add(place)
                        place.location_scope=payload.get("location_scope","SINGLE_LOCATION")
                        place.is_al_ahsa=bool(payload.get("qualified") and str(place_name) in {"Al-Ahsa","Al-Hofuf","Al-Mubarraz","الأحساء","الهفوف","المبرز"})
                        place.source_location_text=raw.location
                    if payload.get("qualification_review_required"):
                        review=db.scalar(select(QualificationReview).where(QualificationReview.source_id==source.id,QualificationReview.external_id==raw.external_id))
                        if not review:
                            review=QualificationReview(source_id=source.id,external_id=raw.external_id,created_at=NOW());db.add(review)
                        old_evidence=(review.source_record_id,review.title,review.source_url,review.proposed_type,review.reason)
                        prior_status=review.status
                        review.source_record_id=record.id;review.title=raw.title;review.source_url=raw.url
                        review.proposed_type=payload.get("opportunity_type");review.reason=payload.get("qualification_reason","")
                        new_evidence=(review.source_record_id,review.title,review.source_url,review.proposed_type,review.reason)
                        if prior_status not in (None,"PENDING") and old_evidence!=new_evidence:
                            review.status="PENDING"
                            db.add(SystemEvent(event_type="REVIEW_REOPENED",created_at=NOW(),payload={"review_type":"qualification_review","review_id":review.id,"source_record_id":record.id,"reason":"new source evidence"}))
                if source_key=="invest-saudi":
                    record=db.scalar(select(SourceOpportunity).where(SourceOpportunity.source_id==source.id,SourceOpportunity.source_opportunity_id==raw.external_id))
                    observation_changed=store_investsaudi_observations(db,source,record,raw) if record else False
                    if previous is not None and observation_changed:invest_updated+=1
                    for membership in (raw.raw or {}).get("dataset_memberships",[]):
                        invest_seen_by_dataset.setdefault(membership["dataset_name"],set()).add(record.id)
                elif source_key=="pif" and record:
                    store_pif_route_observations(db,record,raw)
            if source_key=="ncp" and record and (raw.raw or {}).get("project_stage"):
                    payload=raw.raw or {};stage=payload.get("project_stage") or "PIPELINE"
                    event_type={"EOI":"EOI_PUBLISHED","EOI_RESULTS":"EOI_RESULTS","RFQ":"RFQ_PUBLISHED","RFP":"RFP_PUBLISHED","AWARDED":"AWARDED","CANCELLED":"CANCELLED","PIPELINE":"PROJECT_ANNOUNCED"}.get(stage,stage)
                    previous_event=db.scalar(select(NcpProjectEvent).where(NcpProjectEvent.project_source_opportunity_id==record.id).order_by(NcpProjectEvent.id.desc()).limit(1))
                    event=db.scalar(select(NcpProjectEvent).where(NcpProjectEvent.project_source_opportunity_id==record.id,NcpProjectEvent.source_url==raw.url,NcpProjectEvent.event_type==event_type))
                    if not event:
                        db.add(NcpProjectEvent(project_source_opportunity_id=record.id,event_type=event_type,event_date=payload.get("publication_date"),
                            source_url=raw.url,stage_before=previous_event.stage_after if previous_event else None,stage_after=stage,raw_title=raw.title,raw_data=payload))
            if source_key=="ahda": counts["raw_count"]=len(content_items)
            for row in getattr(adapter,"location_reviews",[]):
                source_record=db.scalar(select(SourceOpportunity).where(SourceOpportunity.source_id==source.id,SourceOpportunity.source_opportunity_id==row["external_id"]))
                review=db.scalar(select(LocationReview).where(LocationReview.source_id==source.id,LocationReview.external_id==row["external_id"]))
                if not review:
                    review=LocationReview(source_id=source.id,external_id=row["external_id"],created_at=NOW());db.add(review)
                old_evidence=(review.source_record_id,review.title,review.source_location,review.description,review.latitude,review.longitude,review.evidence,review.reason,review.confidence_score)
                prior_status=review.status
                review.source_record_id=source_record.id if source_record else None;review.title=row["title"];review.sector=row.get("sector");review.source_location=row.get("location")
                review.description=row.get("description");review.latitude=row.get("latitude");review.longitude=row.get("longitude");review.evidence=row.get("evidence","")
                review.confidence_score=row["confidence_score"];review.reason=row.get("reason","")
                new_evidence=(review.source_record_id,review.title,review.source_location,review.description,review.latitude,review.longitude,review.evidence,review.reason,review.confidence_score)
                if prior_status not in (None,"PENDING") and old_evidence!=new_evidence:
                    review.status="PENDING"
                    db.add(SystemEvent(event_type="REVIEW_REOPENED",created_at=NOW(),payload={"review_type":"location_review","review_id":review.id,"source_record_id":review.source_record_id,"reason":"new source evidence"}))
            counts["location_review_count"]=len(getattr(adapter,"location_reviews",[]))
            if source_key=="invest-saudi": counts["rejected_count"]=int(adapter_metrics.get("rejected_records",counts["rejected_count"]))
            if source_key=="ahda": counts["rejected_count"]=int(adapter_metrics.get("rejected_content",counts["rejected_count"]))
            for item in getattr(adapter,"raw_records",[]):
                source_value=(item.get("source_taxonomy") or {}).get("sector")
                normalized=(item.get("normalized_taxonomy") or {}).get("sector")
                if source_value:
                    mapping=db.scalar(select(TaxonomyMapping).where(TaxonomyMapping.source_key==source_key,TaxonomyMapping.source_value==source_value))
                    rule=f"broad-sector mapping v1: {source_value} → {normalized or 'Other'}"
                    if not mapping: db.add(TaxonomyMapping(source_key=source_key,source_value=source_value,normalized_value=normalized or "Other",mapping_rule=rule,mapping_version="1"))
                    else: mapping.normalized_value=normalized or "Other";mapping.mapping_rule=rule;mapping.mapping_version="1"
            if source_key=="invest-saudi" and complete:
                removed_from_current=reconcile_investsaudi_memberships(db,source,invest_seen_by_dataset,NOW())
                adapter_metrics["source_opportunities_created"]=invest_created
                adapter_metrics["source_opportunities_updated"]=invest_updated
                adapter_metrics["dataset_memberships"]=sum(len((raw.raw or {}).get("dataset_memberships",[])) for raw in records_to_store)
                all_source_ids=set(db.scalars(select(SourceOpportunity.id).where(SourceOpportunity.source_id==source.id)).all())
                current_membership_ids=set(db.scalars(select(SourceOpportunityDatasetMembership.source_opportunity_id)
                    .join(SourceOpportunity).where(SourceOpportunity.source_id==source.id,SourceOpportunityDatasetMembership.is_current.is_(True))).all())
                historical_source_only=len(all_source_ids-current_membership_ids)
                adapter_metrics.update({"api_endpoint_rows_received":endpoint_rows_received,
                    "current_unique_official_ids":adapter_metrics.get("unique_official_ids",unique_records),
                    "current_unique_source_records":adapter_metrics.get("unique_official_ids",unique_records),
                    "historical_source_only_ids":historical_source_only,
                    "historical_missing_from_current_snapshot":historical_source_only,
                    "removed_from_current_source_snapshot":historical_source_only,
                    "newly_removed_from_current_source_snapshot":removed_from_current,
                    "alahsa_accepted":adapter_metrics.get("accepted_records",0),
                    "new_source_opportunities":invest_created,"updated_source_opportunities":invest_updated,
                    "error_count":len(adapter_metrics.get("page_errors",[]))})
            for limitation in adapter_metrics.get("source_limitations",[]):
                row=db.scalar(select(SourceLimitation).where(SourceLimitation.source_id==source.id,
                    SourceLimitation.limitation_type==limitation["limitation_type"],SourceLimitation.evidence_url==limitation["evidence_url"]))
                if not row:
                    row=SourceLimitation(source_id=source.id,limitation_type=limitation["limitation_type"],evidence_url=limitation["evidence_url"],first_detected_at=NOW())
                    db.add(row)
                row.description=limitation["description"];row.last_verified_at=NOW();row.affects_completeness=limitation.get("affects_completeness",True);row.resolution=limitation.get("resolution")
            if adapter_metrics.get("collection_incomplete"):
                job.status="INCOMPLETE_COLLECTION_WARNING";source.sync_status="INCOMPLETE_COLLECTION_WARNING"
                db.add(SystemEvent(event_type="INCOMPLETE_COLLECTION_WARNING",payload={"source":source_key,"source_total_reported":source_total,
                    "unique_records":unique_records,"pages_requested":counts["pages_requested"],"pages_successful":counts["pages_successful"],
                    "pagination_complete":pagination_complete,"collection_completeness_percent":counts["collection_completeness_percent"]},created_at=NOW()))
            elif not records_to_store and not content_items:
                job.status="WARNING"; source.sync_status="PARSER_WARNING"
                detail="؛ ".join(getattr(adapter,"diagnostics",[]))
                source.notes=(source.notes+"\nآخر فحص لم ينتج سجلات؛ لم تُحذف البيانات. "+detail).strip()
            elif adapter_metrics.get("parser_warning"):
                job.status="PARSER_WARNING";source.sync_status="PARSER_WARNING"
                db.add(SystemEvent(event_type="PARSER_WARNING",payload={"source":source_key,"diagnostics":getattr(adapter,"diagnostics",[])},created_at=NOW()))
            else:
                if complete and adapter_metrics.get("reconciliation_safe",True):
                    seen_ids={raw.external_id for raw in records}
                    removed=reconcile_missing_records(db,source,seen_ids,NOW())
                    counts["removed_records_count"]=len(removed)
                    job.status="SUCCESS"
                    if source_key=="invest-saudi" and adapter_metrics.get("unique_dataset_reconciliation")!="DATASET_RECONCILED":
                        source.sync_status="DATASET_RECONCILIATION_WARNING"
                    else:source.sync_status="HEALTHY"
                    source.last_successful_sync=NOW()
                elif public_scope_complete:
                    job.status="SUCCESS";source.sync_status="HEALTHY";source.last_successful_sync=NOW()
                else:
                    job.status="INCOMPLETE_COLLECTION_WARNING";source.sync_status="INCOMPLETE_COLLECTION_WARNING"
                    db.add(SystemEvent(event_type="INCOMPLETE_COLLECTION_WARNING",payload={"source":source_key,"source_total_reported":source_total,
                        "unique_records":unique_records,"pages_requested":counts["pages_requested"],"pages_successful":counts["pages_successful"],
                        "pagination_complete":pagination_complete,"collection_completeness_percent":counts["collection_completeness_percent"]},created_at=NOW()))
            source.last_record_count=counts["raw_count"]
            source.last_source_total_reported=source_total
            source.last_collection_completeness_percent=counts["collection_completeness_percent"]
            source.last_pagination_complete=pagination_complete
            if job.status in ("BLOCKED",):source.technical_health="BLOCKED"
            elif job.status in ("FAILED",):source.technical_health="FAILED"
            elif job.status in ("PARSER_WARNING",):source.technical_health="PARSER_BROKEN"
            elif job.status not in ("SUCCESS",):source.technical_health="WARNING"
            source.coverage_notes=adapter_metrics.get("coverage_notes",source.coverage_notes or "")
            job.job_state="COMPLETED" if job.status=="SUCCESS" else "FAILED" if job.status=="FAILED" else "COMPLETED_WITH_WARNINGS"
            job.finished_at=NOW()
            job.heartbeat_at=NOW()
            for key,val in counts.items():
                if hasattr(job,key): setattr(job,key,val)
            job.location_review_count=counts["location_review_count"]
            adapter_metrics["standardization"]={"version":STANDARDIZATION_VERSION,"records_processed":counts["standardization_records_processed"],
                "fields_standardized":counts["standardization_fields_changed"],"approved_alias_matches":counts["standardization_aliases_matched"],
                "unmapped_values":counts["standardization_unmapped_values"],"validation_issues":counts["standardization_issues"]}
            job.metrics_json=adapter_metrics
            db.add(SystemEvent(event_type="SYNC_COMPLETED",payload={"source":source_key,**counts,"status":job.status},created_at=NOW()))
            db.commit()
            return {"status":job.status,"source_key":source_key,**counts,"source_metrics":adapter_metrics}
        except SourceBlocked as exc:
            db.rollback()
            source=db.scalar(select(Source).where(Source.source_key==source_key));job=db.get(SyncJob,job.id)
            if source:source.sync_status="BLOCKED";source.technical_health="BLOCKED"
            if job:job.status="BLOCKED";job.job_state="COMPLETED_WITH_WARNINGS";job.finished_at=NOW();job.heartbeat_at=NOW();job.error_message=str(exc)
            if source:db.add(SourceError(source_id=source.id,occurred_at=NOW(),category="BLOCKED",message=str(exc)))
            db.add(SystemEvent(event_type="SYNC_BLOCKED",payload={"source":source_key,"error":str(exc)},created_at=NOW()));db.commit()
            return {"status":"BLOCKED","source_key":source_key,"error":str(exc),**counts}
        except Exception as exc:
            db.rollback()
            source=db.scalar(select(Source).where(Source.source_key==source_key)); job=db.get(SyncJob,job.id)
            http_status=getattr(getattr(exc,"response",None),"status_code",None)
            health=classify_http_health(http_status)
            if source: source.sync_status="FAILED";source.technical_health=health
            if job: job.status="FAILED"; job.job_state="FAILED"; job.finished_at=NOW(); job.heartbeat_at=NOW(); job.error_message=str(exc)
            if source: db.add(SourceError(source_id=source.id,occurred_at=NOW(),category="HTTP_5XX" if http_status and http_status>=500 else type(exc).__name__,message=str(exc)))
            db.add(SystemEvent(event_type="SYNC_FAILED",payload={"source":source_key,"error":str(exc)},created_at=NOW())); db.commit()
            return {"status":"FAILED","source_key":source_key,"error":str(exc),**counts}
        finally: db.close()

async def scheduler_loop():
    while True:
        db=SessionLocal()
        try:
            now=NOW(); sources=db.scalars(select(Source).where(Source.enabled==True)).all()
            due=[s.source_key for s in sources if s.source_key in ADAPTERS and (s.last_attempted_sync is None or (now-s.last_attempted_sync).total_seconds()>=s.polling_frequency_minutes*60)]
        finally: db.close()
        for key in due:
            try: await sync_source(key)
            except Exception: pass
        await asyncio.sleep(60)


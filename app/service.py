from __future__ import annotations
import asyncio, difflib, os, hashlib, json
from collections import defaultdict
from statistics import median
from types import SimpleNamespace
from datetime import datetime, timezone
from sqlalchemy import select, func, or_, and_, delete, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, selectinload
import httpx
from .adapters import ADAPTERS, FurasAdapter, InvestSaudiAdapter, PARSER_VERSION, LOCATION_ACCEPTANCE_THRESHOLD, normalized_record, SourceBlocked, normalize_sector
from .database import SessionLocal
from .models import Source, Opportunity, SourceOpportunity, SourceOpportunityDatasetMembership, SourceObservation, SourceOpportunityTaxonomy, OpportunityLocation, QualificationReview, SyncJob, SourceError, ChangeHistory, SystemEvent, AuditEvent, FieldProvenance, DuplicateCandidate, OpportunityConflict, SourceContentItem, LocationReview, TaxonomyMapping, OrganizationAlias, SourceLimitation, ModonLocation, NcpProjectEvent, AlertEvent, OpportunityAssetFacilityType, GeographicReferenceDataset, GeographicReferenceUnit
from .filter_canonicalization import canonical_value, comparison_key
from .standardization import STANDARDIZATION_VERSION, canonical_identity, standardize_opportunity
from .normalization import normalize_arabic, comparison_title, normalize_reference
from .asset_facility_types import standardize_asset_facility_types
from .entity_resolution import compare_source_records, values_equivalent
from .status_lifecycle import canonical_source_status, aggregate_master_status
from .sync_lifecycle import SyncJobFinalizationConflict, terminal_sync_job_state, transition_sync_job
from .furas_checkpoint import StaleFurasCheckpoint
from .source_links import source_url_history_observation
from .review_lifecycle import reevaluate_open_conflicts
from .review_evidence import re_evaluate_review_evidence
from .sector_inference_phase2 import SECTOR_LABELS_BY_ID
from .sector_inference_relaxed import ENGINE_VERSION as SECTOR_P2_ENGINE_VERSION
from .sector_classification import ENGINE_VERSION as GOVERNED_SECTOR_ENGINE_VERSION, classify_governed, evidence_fingerprint
from .sector_inference import GENERIC_OR_WRONG_DIMENSION
from .standardization import canonical_id as sector_canonical_id

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

def resolve_official_geography(db:Session, label:str):
    """Resolve a source-published place only through one exact current reference name/alias."""
    dataset=db.scalar(select(GeographicReferenceDataset).where(GeographicReferenceDataset.is_current.is_(True)))
    if not dataset or not label:
        return None
    target=normalize_arabic(label)
    matches=[]
    for unit in db.scalars(select(GeographicReferenceUnit).where(
            GeographicReferenceUnit.dataset_id==dataset.id,
            GeographicReferenceUnit.level.in_(("city","governorate")))):
        labels=[unit.name_ar,unit.name_en,*((unit.aliases_json or []))]
        if any(value and normalize_arabic(str(value))==target for value in labels):
            matches.append(unit)
    return matches[0] if len(matches)==1 else None

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

def store_ncp_portal_observations(db,record,raw):
    """Persist the portal as a second NCP dataset without creating another source identity."""
    payload=raw.raw or {};now=NOW();new_observation=False
    for observation_data in payload.get("source_observations",[]):
        if observation_data.get("dataset_name")!="ncp-investors-portal":continue
        endpoint=observation_data.get("endpoint")
        raw_observation=observation_data.get("raw_data_json") or {}
        if not endpoint:continue
        content_hash=hashlib.sha256(json.dumps(raw_observation,sort_keys=True,ensure_ascii=False,default=str).encode()).hexdigest()
        observation=db.scalar(select(SourceObservation).where(
            SourceObservation.source_opportunity_id==record.id,SourceObservation.endpoint==endpoint,
            SourceObservation.content_hash==content_hash))
        if not observation:
            observation=SourceObservation(source_opportunity_id=record.id,dataset_name="ncp-investors-portal",
                endpoint=endpoint,official_source_id_original=str(observation_data.get("official_source_id_original") or "")[:200],
                official_source_id_normalized=str(observation_data.get("official_source_id_normalized") or "")[:200],
                raw_data_json=raw_observation,source_updated_at=observation_data.get("source_updated_at"),
                content_hash=content_hash,first_seen_at=now,last_seen_at=now)
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

def assess_investsaudi_reconciliation_scope(db, source, metrics, *, current_job_id=None, seen_by_dataset=None):
    """Block lifecycle reconciliation unless all four stable Invest Saudi datasets are comparable."""
    adapter=InvestSaudiAdapter
    expected={adapter.api:"Opportunities",adapter.projects_api:"Investment projects",
        adapter.pif_api:"PIF opportunities",adapter.regional_api:"Regional opportunities"}
    endpoints=metrics.get("endpoints") or []
    by_url={row.get("endpoint"):row for row in endpoints if isinstance(row,dict)}
    reasons=[]
    if set(by_url)!=set(expected) or len(endpoints)!=4:
        reasons.append("EXPECTED_DATASET_SET_MISMATCH")
    for url,dataset in expected.items():
        row=by_url.get(url)
        if not row or row.get("dataset_name")!=dataset or row.get("method")!="GET":
            reasons.append(f"DATASET_SCOPE_MISMATCH:{dataset}")
        elif row.get("page_size")!=adapter.page_size or not row.get("request_params"):
            reasons.append(f"REQUEST_SCOPE_MISMATCH:{dataset}")
        elif (row.get("complete") is not True or row.get("pages") is None
              or row.get("pages_succeeded")!=row.get("pages") or row.get("failed_pages",0)!=0
              or row.get("empty_unexpected_pages",0)!=0):
            reasons.append(f"DATASET_PAGINATION_INCOMPLETE:{dataset}")
    if metrics.get("pagination_complete") is not True or metrics.get("source_collection_complete") is not True:
        reasons.append("INCOMPLETE_MULTI_DATASET_SCAN")

    prior_query=select(SyncJob).where(SyncJob.source_id==source.id,SyncJob.status=="SUCCESS",
        SyncJob.job_state=="COMPLETED",SyncJob.pagination_complete.is_(True))
    if current_job_id is not None:
        prior_query=prior_query.where(SyncJob.id<current_job_id)
    prior_jobs=db.scalars(prior_query.order_by(SyncJob.finished_at.desc(),SyncJob.id.desc()).limit(5)).all()
    prior_endpoint_rows=[]
    for job in prior_jobs:
        job_endpoints=(job.metrics_json or {}).get("endpoints") or []
        prior_map={r.get("endpoint"):r for r in job_endpoints if isinstance(r,dict)}
        if set(prior_map)==set(expected) and len(job_endpoints)==4:
            prior_endpoint_rows.append((job,prior_map))
    if not prior_endpoint_rows and db.scalar(select(func.count(SourceOpportunity.id)).where(SourceOpportunity.source_id==source.id)):
        reasons.append("NO_COMPARABLE_SUCCESSFUL_BASELINE")
    latest_id=prior_endpoint_rows[0][0].id if prior_endpoint_rows else None
    per_dataset={}
    for url,dataset in expected.items():
        current=by_url.get(url) or {}
        current_count=current.get("total")
        historical=[int(m[url].get("total") or 0) for _,m in prior_endpoint_rows if url in m]
        baseline=median(historical) if historical else None
        mad=median([abs(value-baseline) for value in historical]) if historical else None
        allowance=max(float(adapter.page_size),3*mad) if mad is not None else 0
        if current_count is None:
            reasons.append(f"MISSING_DATASET_TOTAL:{dataset}")
        elif current_count==0 and any(value>0 for value in historical):
            reasons.append(f"UNEXPECTED_EMPTY_DATASET:{dataset}")
        elif baseline is not None and baseline-current_count>allowance:
            reasons.append(f"DATASET_POPULATION_DROP_OUTSIDE_HISTORY:{dataset}")
        latest=prior_endpoint_rows[0][1].get(url) if prior_endpoint_rows else None
        if latest and (latest.get("method")!=current.get("method") or latest.get("page_size")!=current.get("page_size")):
            reasons.append(f"DATASET_SCOPE_CHANGED:{dataset}")
        per_dataset[dataset]={"current_total":current_count,"recent_success_totals":historical,
            "median_baseline":baseline,"median_absolute_deviation":mad,"allowed_drop_from_history":allowance,
            "population_drop_guard_passed":current_count is not None and (baseline is None or baseline-current_count<=allowance),
            "scope_signature":{"endpoint":url,"method":current.get("method"),"page_size":current.get("page_size"),
                "request_params":current.get("request_params")}}
    seen_by_dataset=seen_by_dataset or {}
    threshold=max(1,int(source.missing_confirmation_threshold or 3))
    recent_events=db.scalars(select(SystemEvent).where(SystemEvent.event_type=="SOURCE_RECONCILIATION_GUARD_BLOCKED")
        .order_by(SystemEvent.id.desc()).limit(20)).all()
    recent_guard_payloads=[event.payload for event in recent_events if isinstance(event.payload,dict)
        and event.payload.get("source")=="invest-saudi"]
    scope_signatures={name:detail["scope_signature"] for name,detail in per_dataset.items()}
    removal_history=[]
    for previous_job,_ in prior_endpoint_rows:
        value=(previous_job.metrics_json or {}).get("newly_removed_from_current_source_snapshot")
        if value is not None:removal_history.append(int(value))
    removal_baseline=median(removal_history) if removal_history else 0
    removal_mad=median([abs(value-removal_baseline) for value in removal_history]) if removal_history else 0
    removal_allowance=max(float(adapter.page_size),3*removal_mad)
    dataset_candidates={}
    for dataset in expected.values():
        memberships=db.scalars(select(SourceOpportunityDatasetMembership).join(SourceOpportunity).where(
            SourceOpportunity.source_id==source.id,SourceOpportunityDatasetMembership.dataset_name==dataset,
            SourceOpportunityDatasetMembership.is_current.is_(True))).all()
        current_ids=seen_by_dataset.get(dataset,set())
        candidates=sorted(m.source_opportunity_id for m in memberships if m.source_opportunity_id not in current_ids
            and (m.missing_successful_checks or 0)+1>=threshold)
        dataset_candidates[dataset]=candidates
        detail=per_dataset[dataset]
        detail.update({"active_memberships":len(memberships),"third_miss_removal_candidates":len(candidates),
            "candidate_ratio":len(candidates)/max(1,len(memberships)),"historical_membership_removals":removal_history,
            "membership_removal_allowance":removal_allowance})
    for dataset,candidates in dataset_candidates.items():
        detail=per_dataset[dataset]
        if len(candidates)>removal_allowance:
            confirmed=any((event.get("guard") or {}).get("scope_signatures")==scope_signatures
                and (event.get("guard") or {}).get("dataset_candidates")==dataset_candidates
                and (event.get("guard") or {}).get("mass_removal_candidate_count",0)>removal_allowance
                for event in recent_guard_payloads)
            if confirmed:
                detail["mass_removal_confirmation"]="CONFIRMED_SECOND_COMPARABLE_SCAN"
            else:
                reasons.append(f"MASS_REMOVAL_CANDIDATE_ANOMALY:{dataset}")
                detail["mass_removal_confirmation"]="HELD_PENDING_COMPARABLE_SCAN"
    mass_candidate_count=sum(len(ids) for ids in dataset_candidates.values())
    return {"safe":not reasons,"reasons":sorted(set(reasons)),"prior_success_job_id":latest_id,
        "dataset_count":len(by_url),"datasets":per_dataset,
        "removal_policy":"all four datasets must be complete and scope-comparable; an unexpected empty or out-of-history drop blocks all lifecycle reconciliation for this scan",
        "statistical_allowance":"max(one API page, three times the median absolute deviation of up to five comparable complete successful scans)",
        "mass_removal_candidate_count":mass_candidate_count,"dataset_candidates":dataset_candidates,
        "scope_signatures":scope_signatures,"membership_removal_allowance":removal_allowance,
        "membership_removal_baseline":removal_history}

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
        {"source_key":"ncp","source_name_ar":"المركز الوطني للتخصيص","organization_name":"المركز الوطني للتخصيص","base_url":"https://ncp.gov.sa/","opportunities_url":"https://ncp.gov.sa/en/MediaCenter/News/Pages/default.aspx","source_type":"ppp_privatisation_pipeline_source","priority":7,"polling_frequency_minutes":720,"extraction_method":"Paginated NCP public News archives plus anonymous UUID-keyed Investors Portal JSON list/detail API","notes":"تُحفظ أخبار التخصيص ومشروعات بوابة المستثمرين ضمن هوية مصدر NCP واحدة؛ يُثبّت التكرار المؤكد عبر بيانات المشروع دون إنشاء مصدر NCP ثانٍ."},
 {"source_key":"nhc","source_name_ar":"NHC الاستثمار","organization_name":"الشركة الوطنية للإسكان","base_url":"https://www.nhc.sa/","opportunities_url":"https://www.nhc.sa/en/investment-opportunities/","source_type":"real_estate_investment_and_partnership_source","priority":8,"polling_frequency_minutes":720,"extraction_method":"Public NHC investment, qualification, and stimulation pages; no authenticated e-services","notes":"يُفصل محتوى الوجهات والمبيعات السكنية عن دعوات الشركاء والمشغلين؛ الخدمات العقارية المسجلة لا تُستعلم."},
 {"source_key":"pif","source_name_ar":"بوابة القطاع الخاص لصندوق الاستثمارات العامة","organization_name":"صندوق الاستثمارات العامة","base_url":"https://www.pif.gov.sa/","opportunities_url":"https://www.pif.gov.sa/en/private-sector-hub/explore-opportunities/","source_type":"national_value_chain_investment_source","priority":9,"polling_frequency_minutes":720,"extraction_method":"Public PIF ecosystem and portfolio-company opportunity pages; item-level company/location validation","notes":"الفرص الوطنية تحفظ كسجلات مصدرية فقط؛ تقبل بالأحساء عند وجود دليل مشروع أو أصل محدد."},
 {"source_key":"mwan","source_name_ar":"موان","organization_name":"المركز الوطني لإدارة النفايات","base_url":"https://mwan.gov.sa/","opportunities_url":"https://mwan.gov.sa/en/investment-opportunities","source_type":"waste_sector_investment_source","priority":10,"polling_frequency_minutes":1440,"extraction_method":"Public opportunity listing, linked project details, and public investor opportunity cards","notes":"تُستبعد قوائم الجهات المرخصة وإحصاءات القطاع من الفرص؛ لا تُقبل إلا المواقع المحددة بالأحساء."},
 {"source_key":"waha-development","source_name_ar":"شركة واحة للتنمية والتطوير","organization_name":"شركة واحة للتنمية والتطوير","base_url":"https://waha.sa/","opportunities_url":"https://waha.sa/opportunities.html","source_type":"official_company_site_and_location_reference","priority":11,"polling_frequency_minutes":1440,"extraction_method":"Official public pages and publicly referenced investment-location GeoJSON; catalogue-only, no opportunity adapter","notes":"المصدر مستقل عن فرص. صفحة الفرص العامة خالية حاليًا من الفرص المفصلة، ومسار تدفق الصفقات يتطلب التسجيل/الدخول. صفحة الخريطة تعرض قريبًا، لكن واجهة المواقع العامة التي تستدعيها ملفات الموقع تعيد 58 موقعًا مكانيًا (49 قطعة أرض و9 مواقع مشروعات). حالات المصدر: 48 شاغرًا، و9 مستثمرة، وواحدة بلا حالة؛ معرّف الفرصة غير موجود لكل المواقع. ملف Waha_clean.json القديم يعيد 84 ميزة متعارضة ويُعامل كنسخة قديمة. لا تتضمن المواقع طرحًا وشروطًا استثمارية أو روابط تفاصيل فرص، لذلك لا تُحوّل إلى سجلات فرص. سجل واحة المعروض عبر فرص يبقى سجل مصدر مستقلًا دون تغيير هوية المالك أو دمج مبني على تشابه العنوان.","coverage_notes":"تغطية عامة محدودة: صفحة opportunities.html تعرض حاليًا حالة عدم توفر فرص عامة؛ invest.html يعرض مجالات عامة ومسار تسجيل يتيح تدفق الفرص بعد التسجيل/الدخول. صفحة map.html تعرض قريبًا، وواجهة المواقع العامة تعيد 58 مضلعًا (49 قطعة أرض و9 مواقع مشروعات) مع الاسم والإحداثيات والمساحة والحالة؛ الحالة الخام هي 48 شاغرًا و9 مستثمرة وواحدة فارغة. لا تحتوي الميزات على معرّف فرصة أو رابط تفاصيل، ولا تنشر شروط طرح أو تقديم. ملف Waha_clean.json القديم يعرض 84 ميزة متعارضة، لذا لا يُستخدم كجرد حالي. تُوثق الـ58 موقعًا كمرجع مكاني فقط ولا تُدرج كفرص استثمارية."},
 {"source_key":"rcjy-investment-opportunities","source_name_ar":"فرص الهيئة الملكية للجبيل وينبع (RCJY)","organization_name":"الهيئة الملكية للجبيل وينبع","base_url":"https://www.rcjy.gov.sa/","opportunities_url":"https://invest.rcjy.gov.sa/InvestmentPortal/InvestmentOpportunities","source_type":"official_public_investment_opportunity_platform","priority":12,"polling_frequency_minutes":1440,"extraction_method":"Public OutSystems screen-services JSON/XHR with runtime manifest and paginated search endpoint","notes":"كتالوج رسمي مستقل للهيئة الملكية للجبيل وينبع. تُحفظ سجلات المصدر منفصلة عن فرص ومدن واستثمر في السعودية؛ معرّف مزود المصدر هو InvestmentOpportunity.Id. الحقول غير المنشورة تبقى غير محددة، ولا تُستنتج حالة الإتاحة من قيم OutSystems الافتراضية أو من زر البدء. لا يُدمج المصدر مع هوية المالك؛ هو ناشر منصة الفرص."},
 {"source_key":"rcu-investment-opportunities","source_name_ar":"فرص الهيئة الملكية لمحافظة العلا","organization_name":"الهيئة الملكية لمحافظة العلا","base_url":"https://eservices.rcu.gov.sa/","opportunities_url":"https://eservices.rcu.gov.sa/opportunities","source_type":"official_public_investment_opportunity_platform","priority":13,"polling_frequency_minutes":1440,"extraction_method":"Public JSON XHR POST; paginated investment-opportunities/list","notes":"كتالوج عام مستقل للهيئة الملكية لمحافظة العلا. تُحفظ السجلات الخام بهوية UUID الرسمية ومعرّف العرض، ولا يُستنتج المالك أو الموقع من الناشر وحده. الالتقاط الأولي لا ينشئ Masters تلقائياً، والإزالة من المصدر مؤجلة حتى تثبيت خط أساس مستقر."},
 {"source_key":"taadeen-mining-bids","source_name_ar":"منصة تعدين – مزايدات التعدين","organization_name":"منصة تعدين (ناشر الكتالوج العام)؛ الجهة المالكة/المرخصة تُترك غير محددة ما لم يذكرها سجل العطاء صراحة","base_url":"https://cms.taadeen.sa/","opportunities_url":"https://cms.taadeen.sa/en/mining-bids","source_type":"official_public_mining_bid_catalog","priority":14,"polling_frequency_minutes":1440,"extraction_method":"Public paginated HTML catalog plus public round and site/belt bid detail pages","notes":"يُحفظ كل عرض موقع/حزام كمصدر مستقل مع سياق الجولة والمراحل والوثائق. معرّف المصدر هو مسار صفحة التفاصيل الرسمي مع سياق الجولة. لا تُنشأ Masters تلقائياً؛ فحص الهوية ودورة الحياة منفصل. خطة الجولات الأولية التي لا تعرض سجلات تفصيلية لا تُحوّل إلى فرص مواقع."},
]
locks: dict[str,asyncio.Lock]={}

def seed_sources(db:Session):
    coverage_defaults={"furas":"COMPLETE_PUBLIC_SOURCE","alahsa-opportunities":"COMPLETE_PUBLIC_SOURCE","ahda":"COMPLETE_FOR_DEFINED_SCOPE",
        "invest-saudi":"COMPLETE_PUBLIC_SOURCE","kfu":"COMPLETE_FOR_DEFINED_SCOPE","modon":"PUBLIC_COVERAGE_LIMITED","ncp":"COMPLETE_FOR_DEFINED_SCOPE",
        "nhc":"PUBLIC_COVERAGE_LIMITED","pif":"PUBLIC_COVERAGE_LIMITED","mwan":"COMPLETE_FOR_DEFINED_SCOPE","waha-development":"PUBLIC_COVERAGE_LIMITED","rcjy-investment-opportunities":"COMPLETE_FOR_DEFINED_SCOPE","rcu-investment-opportunities":"COMPLETE_FOR_DEFINED_SCOPE","taadeen-mining-bids":"COMPLETE_FOR_DEFINED_SCOPE"}
    for item in DEFAULT_SOURCES:
        source=db.scalar(select(Source).where(Source.source_key==item["source_key"]))
        if not source:
            # Ta'adeen is added disabled so the scheduler cannot race the
            # one controlled bootstrap capture. It is enabled after capture.
            source=Source(**item,enabled=item["source_key"] in ADAPTERS and item["source_key"]!="taadeen-mining-bids")
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

def _review_value_key(field_name:str, value):
    """Stable semantic value key for review identity (timestamps are excluded)."""
    if value is None or not str(value).strip() or str(value).strip() in {"غير محدد", "غير محددة"}:
        return "__MISSING__"
    if field_name in {"sector", "subsector", "sub_activity", "activity", "opportunity_type", "investment_model", "asset_facility_type"}:
        from .standardization import canonical_id
        return canonical_id(field_name, value)
    if field_name in {"reference_number", "official_source_id", "source_opportunity_id"}:
        from .normalization import normalize_reference
        return normalize_reference(value) or "__MISSING__"
    if field_name in {"status", "canonical_status"}:
        from .entity_resolution import lifecycle_status
        status = lifecycle_status(str(value))
        if status != "UNKNOWN":
            return f"status:{status}"
    if field_name in {"land_area_sqm", "investment_value", "contract_duration_years", "latitude", "longitude"}:
        try:
            number = float(str(value).replace(",", ""))
            return f"number:{number:.9g}"
        except (TypeError, ValueError):
            pass
    return comparison_key(value)

def _review_logical_fingerprint(db, *, opportunity_id:int, field_name:str, conflict_type:str,
                                selected_value, conflicting_value, source_id:int, source_record_id:int):
    record=db.get(SourceOpportunity,source_record_id)
    standardized=(record.standardized_data_json or {}) if record and isinstance(record.standardized_data_json,dict) else {}
    field_evidence=(standardized.get("fields") or {}).get(field_name) or {}
    identity={"master_id":opportunity_id,"field":field_name,"review_type":conflict_type,
        "source_id":source_id,"source_record_id":source_record_id,
        "selected":_review_value_key(field_name,selected_value),
        "competing":_review_value_key(field_name,conflicting_value),
        "evidence_version":{"mapping_status":field_evidence.get("mapping_status"),
            "rule":field_evidence.get("rule"),"canonical_id":field_evidence.get("canonical_id"),
            "review_flags":sorted(field_evidence.get("review_flags") or [])}}
    encoded=json.dumps(identity,ensure_ascii=False,sort_keys=True,separators=(",",":"),default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest(),identity

def _stored_review_fingerprint(db, review_id:int):
    for event in db.scalars(select(SystemEvent).where(SystemEvent.event_type=="REVIEW_FINGERPRINT_CAPTURED")
                            .order_by(SystemEvent.id.desc()).limit(5000)).all():
        payload=event.payload or {}
        if int(payload.get("review_id") or 0)==int(review_id):
            return payload.get("fingerprint"),payload.get("identity")
    return None,None

def queue_conflict_idempotently(db, *, opportunity_id:int, field_name:str, conflict_type:str,
                                selected_value:str, conflicting_value:str, source_id:int,
                                source_record_id:int, detected_at:datetime):
    """Reuse an open or settled logical conflict until substantive evidence changes."""
    fingerprint,identity=_review_logical_fingerprint(db,opportunity_id=opportunity_id,field_name=field_name,
        conflict_type=conflict_type,selected_value=selected_value,conflicting_value=conflicting_value,
        source_id=source_id,source_record_id=source_record_id)
    candidates=db.scalars(select(OpportunityConflict).where(
        OpportunityConflict.opportunity_id==opportunity_id,
        OpportunityConflict.field_name==field_name,
        OpportunityConflict.source_id==source_id,
        OpportunityConflict.source_record_id==source_record_id).order_by(OpportunityConflict.id.desc()).limit(100)).all()
    for prior_row in candidates:
        legacy_fingerprint,_=_review_logical_fingerprint(db,opportunity_id=prior_row.opportunity_id,
            field_name=prior_row.field_name,conflict_type=prior_row.conflict_type,
            selected_value=prior_row.selected_value,conflicting_value=prior_row.conflicting_value,
            source_id=prior_row.source_id,source_record_id=prior_row.source_record_id)
        stored_fingerprint,_=_stored_review_fingerprint(db,prior_row.id)
        prior_fingerprint=stored_fingerprint or legacy_fingerprint
        if prior_fingerprint!=fingerprint:
            continue
        reevaluation_exists=False
        for event in db.scalars(select(SystemEvent).where(SystemEvent.event_type=="SYSTEM_REEVALUATION")
                                .order_by(SystemEvent.id.desc()).limit(2000)).all():
            payload=event.payload or {}
            if (payload.get("review_fingerprint")==fingerprint
                    and payload.get("job_id")==db.info.get("sync_job_id")):
                reevaluation_exists=True
                break
        if not reevaluation_exists:
            observation=db.scalar(select(SourceObservation).where(
                SourceObservation.source_opportunity_id==source_record_id).order_by(SourceObservation.id.desc()).limit(1))
            previous_event=db.scalar(select(AuditEvent).where(
                AuditEvent.entity_type=="opportunity_conflict",AuditEvent.entity_id==str(prior_row.id)
            ).order_by(AuditEvent.id.desc()).limit(1))
            db.add(SystemEvent(event_type="SYSTEM_REEVALUATION",created_at=detected_at,payload={
                "review_fingerprint":fingerprint,"identity":identity,"source_id":source_id,
                "source_record_id":source_record_id,"observation_id":observation.id if observation else None,
                "prior_review_id":prior_row.id,"previous_status":prior_row.status,
                "previous_decision_event_type":previous_event.event_type if previous_event else None,
                "job_id":db.info.get("sync_job_id"),"actor":"SYSTEM","result":"NO_MATERIAL_CHANGE",
                "rule":"RESOLVED_CONFLICT_MATERIALITY_V1"}))
        if prior_row.status in {"OPEN", "PENDING"}:
            return None
        return None
    prior=next((item for item in candidates if item.status not in {"OPEN","PENDING"}),None)
    row=OpportunityConflict(opportunity_id=opportunity_id,field_name=field_name,conflict_type=conflict_type,
        selected_value=selected_value,conflicting_value=conflicting_value,source_id=source_id,
        source_record_id=source_record_id,detected_at=detected_at,status="OPEN")
    db.add(row);db.flush()
    db.add(SystemEvent(event_type="REVIEW_FINGERPRINT_CAPTURED",created_at=detected_at,payload={
        "review_id":row.id,"review_type":"opportunity_conflict","fingerprint":fingerprint,
        "identity":identity,"job_id":db.info.get("sync_job_id"),"actor":"SYSTEM",
        "rule":"SEMANTIC_REVIEW_FINGERPRINT_V1"}))
    if prior:
        calculated_prior_fingerprint,prior_identity=_review_logical_fingerprint(db,opportunity_id=prior.opportunity_id,
            field_name=prior.field_name,conflict_type=prior.conflict_type,
            selected_value=prior.selected_value,conflicting_value=prior.conflicting_value,
            source_id=prior.source_id,source_record_id=prior.source_record_id)
        stored_prior_fingerprint,_=_stored_review_fingerprint(db,prior.id)
        prior_fingerprint=stored_prior_fingerprint or calculated_prior_fingerprint
        db.add(SystemEvent(event_type="REVIEW_REEVALUATED_MATERIAL_CHANGE",created_at=detected_at,payload={
            "review_type":"opportunity_conflict","prior_review_id":prior.id,"master_id":opportunity_id,
            "field":field_name,"source_record_id":source_record_id,"prior_fingerprint":prior_fingerprint,
            "new_fingerprint":fingerprint,"prior_identity":prior_identity,"new_identity":identity,
            "result":"MATERIAL_CHANGE_REEVALUATED","rule":"RESOLVED_CONFLICT_MATERIALITY_V1"}))
    return row

def apply_sector_phase2_after_ingestion(db:Session, master:Opportunity, *, source:Source,
                                        source_record:SourceOpportunity, detected_at:datetime):
    """Apply the single governed sector classifier inside source ingestion."""
    linked=db.scalars(select(SourceOpportunity).where(
        SourceOpportunity.master_opportunity_id==master.id).options(
            selectinload(SourceOpportunity.source)).order_by(SourceOpportunity.id)).all()
    observations_by_source_record={}
    linked_ids=[row.id for row in linked if hasattr(row,"source_opportunity_id")]
    observation_rows=db.scalars(select(SourceObservation).where(
        SourceObservation.source_opportunity_id.in_(linked_ids)
    ).order_by(SourceObservation.last_seen_at.desc(),SourceObservation.id.desc())).all() if linked_ids else []
    for observation in observation_rows:
        observations_by_source_record.setdefault(observation.source_opportunity_id,[])
        if len(observations_by_source_record[observation.source_opportunity_id])<3:
            observations_by_source_record[observation.source_opportunity_id].append({
                "last_seen_at":observation.last_seen_at.isoformat() if observation.last_seen_at else None,
                "raw_data_json":observation.raw_data_json})
    source_facts=[{"source_key":row.source.source_key if row.source else "",
                   "source_record_id":row.id,"source_sector":row.source_sector,
                   "normalized_sector":row.normalized_sector,
                   "source_activity":row.source_activity,"source_sub_activity":row.source_sub_activity,
                   "source_title":getattr(row,"source_title",None),"source_subsector":getattr(row,"source_subsector",None),
                   "raw_data_json":getattr(row,"raw_data_json",{}),"standardized_data_json":getattr(row,"standardized_data_json",{}),
                   "observations":observations_by_source_record.get(row.id,[])}
                  for row in linked]
    current_id=sector_canonical_id("sector",master.sector)
    phase2_events=db.scalars(select(SystemEvent).where(
        SystemEvent.event_type.in_(("SECTOR_INFERENCE_PHASE2_APPLIED", "SECTOR_CONTROLLED_RELAXATION_APPLIED",
                                    "SECTOR_INFERENCE_PHASE2_OFFICIAL_OVERRIDE", "SECTOR_GOVERNED_CLASSIFICATION_APPLIED",
                                    "SECTOR_GOVERNED_RECLASSIFIED"))
    ).order_by(SystemEvent.id.desc())).all()
    prior_inferred=next((item for event in phase2_events
                         for item in (event.payload or {}).get("classifications", [])
                         if item.get("master_id")==master.id
                         and item.get("classification_origin") in {"INFERRED_RULE", "INFERRED_RULE_MEDIUM",
                             "INFERRED_RULE_FORCED_BEST_FIT"}
                         and sector_canonical_id("sector",item.get("sector"))==current_id),None)
    explicit=defaultdict(list)
    for fact in source_facts:
        raw=fact.get("source_sector")
        mapped=normalize_sector(raw) if raw and comparison_key(raw) not in GENERIC_OR_WRONG_DIMENSION else None
        mapped_id=sector_canonical_id("sector",mapped) if mapped else "sector:unspecified"
        if mapped_id!="sector:unspecified":
            explicit[mapped_id].append({"source_key":fact["source_key"],"source_record_id":fact["source_record_id"],"raw_value":raw})
    if prior_inferred and explicit:
        if len(explicit)==1:
            official_id, official_evidence=next(iter(explicit.items()))
            if official_id!=current_id:
                previous=master.sector
                target=SECTOR_LABELS_BY_ID[official_id]
                master.sector=target
                master.updated_at=detected_at; master.last_updated_at=detected_at
                db.add(ChangeHistory(opportunity_id=master.id,changed_field="sector",previous_value=previous,
                    new_value=target,source_id=source.id,detected_at=detected_at))
                db.add(SystemEvent(event_type="SECTOR_INFERENCE_PHASE2_OFFICIAL_OVERRIDE",created_at=detected_at,
                    payload={"engine_version":SECTOR_P2_ENGINE_VERSION,"classifications":[{
                        "master_id":master.id,"sector":target,"classification_origin":"SOURCE_EXPLICIT",
                        "rule_key":"P2_OFFICIAL_SOURCE_SUPERSEDES_INFERENCE","evidence_fields":official_evidence,
                        "superseded_sector":previous,"inference_timestamp":detected_at.isoformat()}]}))
        elif len(explicit)>1 and not db.scalar(select(OpportunityConflict.id).where(
                OpportunityConflict.opportunity_id==master.id,OpportunityConflict.field_name=="sector",
                OpportunityConflict.status=="OPEN")):
            values=" | ".join(sorted({item["raw_value"] for group in explicit.values() for item in group if item["raw_value"]}))
            queue_conflict_idempotently(db,opportunity_id=master.id,field_name="sector",
                conflict_type="TAXONOMY_CONFLICT",selected_value=str(master.sector or "غير محدد"),
                conflicting_value=values,source_id=source.id,source_record_id=source_record.id,detected_at=detected_at)
        return
    assets=db.execute(select(OpportunityAssetFacilityType.raw_value).where(
        OpportunityAssetFacilityType.opportunity_id==master.id)).scalars().all()
    record_payload={"id":master.id,"sector":master.sector,"activity":master.activity,
        "sub_activity":master.sub_activity,"subsector":master.subsector,"title_ar":master.title_ar,
        "normalized_title":master.normalized_title,"short_description":master.short_description,
        "full_description":master.full_description,"asset_facility_type":" | ".join(sorted(set(assets))),
        "opportunity_type":master.opportunity_type,"investment_model":master.investment_model,
        "opportunity_owner":master.opportunity_owner,"primary_publication_platform":master.primary_publication_platform,
        "location_description":master.location_description,"sources":source_facts}
    if current_id!="sector:unspecified":
        # Preserve pre-existing specified values. Only a value created by this
        # governed service is eligible for material-evidence reclassification.
        governed_prior=next((item for event in phase2_events
                             for item in (event.payload or {}).get("classifications", [])
                             if item.get("master_id")==master.id
                             and item.get("classification_origin") in {"INFERRED_RULE","INFERRED_RULE_MEDIUM",
                                 "INFERRED_RULE_FORCED_BEST_FIT"}
                             and item.get("sector")==master.sector
                             and item.get("evidence_fingerprint")),None)
        if not governed_prior:
            return
        candidate=classify_governed({**record_payload,"sector":"غير محدد"})
        fingerprint=evidence_fingerprint(record_payload,candidate)
        if fingerprint==governed_prior.get("evidence_fingerprint"):
            return
        result=candidate
    else:
        result=classify_governed(record_payload)
    if result["classification"] in {"HIGH_CONFIDENCE", "MEDIUM_CONFIDENCE", "FORCED_BEST_FIT"}:
        previous=master.sector
        changed=sector_canonical_id("sector",previous)!=sector_canonical_id("sector",result["sector"])
        if changed:
            master.sector=result["sector"]
            master.updated_at=detected_at;master.last_updated_at=detected_at
            db.add(ChangeHistory(opportunity_id=master.id,changed_field="sector",previous_value=previous,
                new_value=master.sector,source_id=source.id,detected_at=detected_at))
        fingerprint=evidence_fingerprint(record_payload,result)
        event_type="SECTOR_GOVERNED_RECLASSIFIED" if current_id!="sector:unspecified" else "SECTOR_GOVERNED_CLASSIFICATION_APPLIED"
        db.add(SystemEvent(event_type=event_type,created_at=detected_at,
            payload={"engine_version":result.get("engine_version", GOVERNED_SECTOR_ENGINE_VERSION),"classifications":[{
                "master_id":master.id,"sector":master.sector,"classification_origin":result.get("classification_origin"),
                "classification_method":result.get("method",result["classification"]),
                "engine_version":result.get("engine_version", GOVERNED_SECTOR_ENGINE_VERSION),
                "confidence":result["confidence"],"confidence_label":result.get("confidence_label"),
                "total_score":result.get("total_score",result.get("top_score")),
                "confidence_score":result.get("confidence_score"),"confidence_margin":result.get("confidence_margin"),
                "confidence_margin_applicability":result.get("confidence_margin_applicability", "UNKNOWN"),
                "top_sector_id":result.get("top_sector_id",result.get("sector_id")),"top_score":result.get("top_score"),
                "second_sector_id":result.get("second_sector_id"),"second_score":result.get("second_score"),
                "rule_key":result["rule_key"],"rule_keys":result.get("rule_keys",[result["rule_key"]]),
                "positive_evidence":result.get("positive_evidence",[]),"negative_evidence":result.get("negative_evidence",[]),
                "evidence_fields":result.get("evidence_fields",sorted({item.get("field","") for item in result["positive_evidence"]})),
                "reason":result.get("reason"),"top_score":result.get("top_score"),
                "previous_sector":previous,"sector_changed":changed,"evidence_fingerprint":fingerprint,
                "raw_source_sector_values_preserved":True,
                "inference_timestamp":detected_at.isoformat()}]}))

def _safe_record(db,source,raw,counts,owner_alias_registry=None,allow_master_creation=True):
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
            selected=(values.get("submission_deadline") if field=="submission_deadline" else canonical_status)
            selected_value=str(selected) if selected not in (None, "") else "غير محدد"
            conflicts.append((field,selected_value,str(evidence or "قيمة حالة غير قابلة للتفسير")))
    wrong_dimension=next((issue for issue in standardization.get("issues",[]) if issue.get("code")=="WRONG_DIMENSION_SECTOR_UNSPECIFIED"),None)
    if wrong_dimension:
        raw_sector=((raw.raw or {}).get("source_taxonomy") or {}).get("sector") or raw.activity
        if raw_sector:
            conflicts.append(("sector",str(master.sector if master and master.sector else "غير محدد"),str(raw_sector)))
    model_review=next((issue for issue in standardization.get("issues",[]) if issue.get("field")=="investment_model" and issue.get("code")=="INVESTMENT_MODEL_REVIEW_REQUIRED"),None)
    if model_review:
        evidence=(standardization.get("fields",{}).get("investment_model_evidence") or {}).get("raw")
        conflicts.append(("investment_model",str(master.investment_model if master and master.investment_model else "غير محدد"),str(evidence or "يتطلب تحديد نموذج الاستثمار")))
    if source.source_key=="furas" and not allow_master_creation and master is None:
        # National checkpoint capture stores every source row while deferring
        # Master creation to a later governed promotion phase. Exact safe
        # matches to an existing Master are still allowed above.
        if old:
            changed=old.content_hash!=raw.content_hash
            old.source_title=raw.title;old.normalized_source_title=values["normalized_title"]
            old.source_reference_number=raw.reference;old.source_reference_number_normalized=normalized_ref
            old.source_url=raw.url;old.source_owner=raw.owner;old.raw_location=raw.location;old.raw_area=raw.area_text
            old.raw_dates={"deadline":raw.deadline};old.raw_status=raw.status;old.canonical_status=canonical_status
            old.raw_data_json=raw.raw or {};old.standardized_data_json=standardization
            old.standardization_version=STANDARDIZATION_VERSION;old.content_hash=raw.content_hash
            old.last_seen_at=now;old.missing_successful_checks=0;old.last_missing_at=None
            store_source_taxonomy(old,raw,source.source_key)
            counts["update_count" if changed else "unchanged_count"]+=1
            record=old
        else:
            record=SourceOpportunity(source_id=source.id,master_opportunity_id=None,
                source_opportunity_id=raw.external_id,source_reference_number=raw.reference,
                source_reference_number_normalized=normalized_ref,source_title=raw.title,
                normalized_source_title=values["normalized_title"],source_url=raw.url,
                source_owner=raw.owner,raw_location=raw.location,raw_area=raw.area_text,
                raw_dates={"deadline":raw.deadline},raw_status=raw.status,canonical_status=canonical_status,
                raw_data_json=raw.raw or {},standardized_data_json=standardization,
                standardization_version=STANDARDIZATION_VERSION,first_seen_at=now,last_seen_at=now,
                content_hash=raw.content_hash,parser_version=PARSER_VERSION)
            store_source_taxonomy(record,raw,source.source_key);db.add(record);db.flush()
        store_status_observation(db,source,record,raw,now)
        return
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
    db.flush()
    apply_sector_phase2_after_ingestion(db,master,source=source,source_record=record,detected_at=now)
    for field,selected,conflicting in conflicts:
        row=queue_conflict_idempotently(db,opportunity_id=master.id,field_name=field,
            conflict_type="TAXONOMY_CONFLICT" if field in ("sector","subsector","sub_activity","opportunity_type","activity","investment_model","asset_facility_type") else "FIELD_VALUE_CONFLICT",
            selected_value=selected,conflicting_value=conflicting,source_id=source.id,source_record_id=record.id,detected_at=now)
    # Re-evaluate only reviews attached to this source record after its current
    # standardized evidence has been persisted. No backlog-wide scan occurs.
    reevaluate_open_conflicts(db,source_record_id=record.id,master_id=master.id,now=now)
    # Attach new provenance only to reviews related to this source record or
    # Master. This also covers new observations, source reappearance, and a
    # source record newly linked to an existing Master.
    if (raw.raw or {}).get("location_detection_method") != "ADMIN_LOCATION_REVIEW":
        re_evaluate_review_evidence(db,source_record_id=record.id,master_id=master.id,
                                    trigger="source_observation_or_link",now=now)

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
        if previous_source_status!="أزيلت من المصدر":
            removed.append({"source_opportunity_id":row.source_opportunity_id,"master_opportunity_id":master.id,"missing_successful_checks":row.missing_successful_checks})
    return removed

def source_presence_ids(source_key,qualified_records,raw_candidates=None):
    """Return IDs present in the enumerated source scope, independent of geography qualification."""
    population=(raw_candidates or qualified_records) if source_key in {"invest-saudi","furas"} else qualified_records
    return {raw.external_id for raw in population}


FURAS_LOCAL_SCOPE="AL_AHSA_SUBSET_V1"
FURAS_NATIONAL_SCOPE="SAUDI_NATIONAL_V1"


def assess_furas_reconciliation_scope(db:Session,source:Source,job:SyncJob,metrics:dict,collection_complete:bool)->dict:
    """Allow absence reconciliation only for a complete scan covering prior scope."""
    scope=metrics.get("enumeration_scope")
    if not collection_complete or metrics.get("pagination_complete") is not True or metrics.get("reconciliation_scope_complete") is not True:
        return {"safe":False,"reason":"SCAN_NOT_COMPLETE_AND_VERIFIED","enumeration_scope":scope}
    if scope not in {FURAS_LOCAL_SCOPE,FURAS_NATIONAL_SCOPE}:
        return {"safe":False,"reason":"UNKNOWN_ENUMERATION_SCOPE","enumeration_scope":scope}
    prior=db.scalar(select(SyncJob).where(SyncJob.source_id==source.id,SyncJob.id!=job.id,
        SyncJob.status=="SUCCESS",SyncJob.pagination_complete.is_(True)).order_by(SyncJob.id.desc()).limit(1))
    if prior is None:
        # The existing installed collector was fixed to reviewed Al-Ahsa CITY_IDs.
        prior_scope=FURAS_LOCAL_SCOPE
    else:
        prior_scope=(prior.metrics_json or {}).get("enumeration_scope") or FURAS_LOCAL_SCOPE
    covers_prior=(scope==prior_scope or (scope==FURAS_NATIONAL_SCOPE and prior_scope==FURAS_LOCAL_SCOPE))
    return {"safe":covers_prior,"reason":"CURRENT_SCOPE_COVERS_PRIOR_SCOPE" if covers_prior else "CURRENT_SCOPE_IS_NARROWER_THAN_PRIOR_SCOPE",
        "enumeration_scope":scope,"previous_complete_scope":prior_scope,"previous_complete_job_id":prior.id if prior else None}


def reconcile_furas_missing_records(db:Session,source:Source,seen_ids:set[str],checked_at,job:SyncJob,metrics:dict,collection_complete:bool):
    """Fail closed: a partial, empty/unverified, or narrower Furas scan cannot age records."""
    guard=assess_furas_reconciliation_scope(db,source,job,metrics,collection_complete)
    if not guard["safe"]:
        return [],guard
    if not seen_ids:
        return [],{**guard,"safe":False,"reason":"EMPTY_ENUMERATION_NEVER_RECONCILES"}
    return reconcile_missing_records(db,source,seen_ids,checked_at),guard


def acquire_sync_ingestion_lock(db:Session)->bool:
    """Serialize source ingestion transactions across worker processes on PostgreSQL.

    Network discovery remains concurrent. The transaction advisory lock is taken
    before any post-fetch writes so overlapping sources cannot deadlock while
    touching the same canonical Master rows in opposite orders.
    """
    if db.bind is None or db.bind.dialect.name!="postgresql":
        return False
    db.execute(text("SELECT pg_advisory_xact_lock(:namespace, :lock_key)"),
        {"namespace":0x41485341,"lock_key":1})
    return True


async def _sync_furas_checkpointed(db:Session,source:Source,job:SyncJob,counts:dict,*,stop_after_batches=None):
    """Fetch and commit Furas pages with a durable per-page resume cursor."""
    from .furas_checkpoint import (StaleFurasCheckpoint, acquire_resume_lock,
        release_resume_lock, validate_checkpoint_lifecycle, checkpoint_is_resumable)
    from .geography_flags import flag_enabled
    scope="SAUDI_NATIONAL_V1" if flag_enabled("FURAS_NATIONAL_ENUMERATION_ENABLED") else "AL_AHSA_SUBSET_V1"
    lock_conn=acquire_resume_lock(db,f"furas:{scope}")
    if lock_conn is False:
        raise RuntimeError("A Furas run already owns this enumeration-scope checkpoint")
    adapter=FurasAdapter();resume_checkpoint=None
    current_metrics=job.metrics_json if isinstance(job.metrics_json,dict) else {}
    candidate=current_metrics.get("furas_checkpoint")
    if candidate is not None and not isinstance(candidate,dict):candidate=None
    unusable_current_checkpoint=False
    if candidate and candidate.get("enumeration_complete") is not True:
        if checkpoint_is_resumable(candidate):resume_checkpoint=candidate
        else:unusable_current_checkpoint=True
    ignored_previous_checkpoint=None
    if not candidate or candidate.get("enumeration_complete") is True:
        previous=db.scalar(select(SyncJob).where(SyncJob.source_id==source.id,SyncJob.id!=job.id,
            SyncJob.job_state.in_(("FAILED","ABANDONED","COMPLETED_WITH_WARNINGS")))
            .order_by(SyncJob.id.desc()).limit(1))
        previous_checkpoint=(previous.metrics_json or {}).get("furas_checkpoint") if previous else None
        if previous_checkpoint and (not isinstance(previous_checkpoint,dict)
                or previous_checkpoint.get("enumeration_complete") is not True):
            if checkpoint_is_resumable(previous_checkpoint):resume_checkpoint=previous_checkpoint
            else:ignored_previous_checkpoint=previous.id
    if ignored_previous_checkpoint is not None:
        current=dict(job.metrics_json or {})
        current.update({"checkpoint_resume_rejected":True,
            "checkpoint_resume_rejection_reason":"Previous job checkpoint is not resumable; new membership snapshot started",
            "checkpoint_resume_source_job_id":ignored_previous_checkpoint})
        job.metrics_json=current;db.commit()
    owner_alias_registry={comparison_key(row.alias):row for row in db.scalars(select(OrganizationAlias).where(
        or_(OrganizationAlias.source_key.is_(None),OrganizationAlias.source_key=="furas"))).all()}
    try:
        from .tls import create_source_ssl_context
        async with httpx.AsyncClient(timeout=httpx.Timeout(35,connect=15),verify=create_source_ssl_context("furas"),
                follow_redirects=True,limits=httpx.Limits(max_connections=4)) as client:
            if unusable_current_checkpoint:
                raise StaleFurasCheckpoint("Current job checkpoint lacks a verifiable immutable membership snapshot")
            async def commit_batch(batch_records,checkpoint):
                acquire_sync_ingestion_lock(db)
                inserted=int(checkpoint.get("source_rows_inserted_total",0))
                updated=int(checkpoint.get("source_rows_updated_total",0))
                for raw in batch_records:
                    raw.raw=dict(raw.raw or {})
                    raw.raw["checkpoint_provenance"]={"scan_run_id":checkpoint["scan_run_id"],
                        "enumeration_scope":checkpoint["enumeration_scope"],
                        "scope_fingerprint":checkpoint["scope_fingerprint"],
                        "source_object_id":(raw.raw.get("attributes") or {}).get("OBJECTID")}
                    previous_row=db.scalar(select(SourceOpportunity).where(SourceOpportunity.source_id==source.id,
                        SourceOpportunity.source_opportunity_id==raw.external_id))
                    previous_hash=previous_row.content_hash if previous_row else None
                    _safe_record(db,source,raw,counts,owner_alias_registry=owner_alias_registry,
                        allow_master_creation=False)
                    if previous_row is None:inserted+=1
                    elif previous_hash!=raw.content_hash:updated+=1
                if checkpoint.get("last_error"):
                    history=list(checkpoint.get("resume_history",[]))
                    history.append({"error":checkpoint.pop("last_error"),"resumed_at":NOW().isoformat()})
                    checkpoint["resume_history"]=history
                checkpoint["job_id"]=job.id
                checkpoint["source_rows_inserted_total"]=inserted
                checkpoint["source_rows_updated_total"]=updated
                checkpoint["master_rows_created_total"]=0
                checkpoint["terminal_status"]="RUNNING"
                checkpoint["removal_reconciliation_allowed"]=False
                if not validate_checkpoint_lifecycle(checkpoint,"RUNNING"):
                    raise RuntimeError("Furas checkpoint failed lifecycle integrity validation")
                current=dict(job.metrics_json or {})
                current.update({"furas_checkpoint":checkpoint,"enumeration_scope":checkpoint["enumeration_scope"],
                    "scope_fingerprint":checkpoint["scope_fingerprint"],"checkpoint_batch_commit":"DATA_AND_CURSOR_ATOMIC"})
                if ignored_previous_checkpoint is not None:
                    current.update({"checkpoint_resume_rejected":True,
                        "checkpoint_resume_rejection_reason":"Previous job checkpoint is not resumable; new membership snapshot started",
                        "checkpoint_resume_source_job_id":ignored_previous_checkpoint})
                job.metrics_json=current;job.heartbeat_at=NOW();job.pages_scanned=checkpoint["pages_completed"]
                job.pages_successful=checkpoint["pages_completed"];job.pages_requested=checkpoint["pages_completed"]
                job.records_received=checkpoint["records_seen_total"];job.records_parsed=checkpoint["records_seen_total"]
                job.unique_records=checkpoint["unique_source_ids_seen"];job.raw_count=counts["raw_count"]
                job.new_count=inserted;job.update_count=updated;job.removed_records_count=0
                counts["pages_scanned"]=checkpoint["pages_completed"]
                source.sync_status="RUNNING";db.commit()
            async def commit_completion(checkpoint):
                checkpoint["job_id"]=job.id
                checkpoint["terminal_status"]="COMPLETE" if checkpoint.get("enumeration_complete") else "INCOMPLETE"
                checkpoint["removal_reconciliation_allowed"]=False
                current=dict(job.metrics_json or {});current["furas_checkpoint"]=checkpoint
                current["checkpoint_batch_commit"]="DATA_AND_CURSOR_ATOMIC"
                job.metrics_json=current;job.heartbeat_at=NOW();db.commit()
            records,pages=await adapter.fetch(client,checkpoint=resume_checkpoint,on_batch=commit_batch,
                on_complete=commit_completion,stop_after_batches=stop_after_batches)
        metrics=dict(adapter.metrics);checkpoint=metrics.get("checkpoint") or {}
        metrics["checkpoint_resume_source_job_id"]=(resume_checkpoint or {}).get("job_id")
        metrics["checkpoint_resume_offset"]=(resume_checkpoint or {}).get("last_committed_offset",0)
        metrics["checkpoint_terminal_integrity"]=validate_checkpoint_lifecycle(checkpoint,"RUNNING")
        source_total=metrics.get("source_total_reported");unique=metrics.get("unique_records",0)
        missing_members=len(checkpoint.get("missing_object_ids",[]))
        complete=(checkpoint.get("enumeration_complete") is True and metrics.get("pagination_complete") is True
            and checkpoint.get("snapshot_membership_complete") is True
            and unique+missing_members==source_total)
        metrics["enumeration_complete"]=complete;metrics["reconciliation_scope_complete"]=complete
        metrics["reconciliation_safe"]=False
        metrics["pages_requested"]=metrics.get("pages_requested",pages);metrics["pages_successful"]=metrics.get("pages_successful",pages)
        metrics["records_received"]=checkpoint.get("source_features_received",unique)
        metrics["records_parsed"]=checkpoint.get("source_features_received",unique)
        metrics["snapshot_members_processed"]=checkpoint.get("records_seen_total",0)
        metrics["active_count"]=unique;metrics["expired_count"]=0
        counts.update({"pages_scanned":checkpoint.get("pages_completed",0),"source_total_reported":source_total,
            "pages_requested":metrics["pages_requested"],"pages_successful":metrics["pages_successful"],
            "records_received":metrics["records_received"],"records_parsed":metrics["records_parsed"],
            "unique_records":unique,"pagination_complete":complete,"active_count":unique,
            "collection_completeness_percent":100.0 if complete else (round(100*unique/source_total,2) if source_total else 0.0),
            "duplicate_items_between_pages":metrics.get("duplicate_source_ids",0)})
        job.source_total_reported=source_total;job.collection_completeness_percent=counts["collection_completeness_percent"]
        job.pagination_complete=complete;job.active_count=unique
        outcome="SUCCESS" if complete else "INCOMPLETE_COLLECTION_WARNING"
        if complete:
            guard=assess_furas_reconciliation_scope(db,source,job,metrics,True)
            from .geography_flags import flag_enabled
            removals_enabled=flag_enabled("FURAS_NATIONAL_REMOVAL_RECONCILIATION_ENABLED")
            metrics["reconciliation_guard"]=guard;metrics["reconciliation_safe"]=guard["safe"]
            metrics["removal_reconciliation_enabled"]=removals_enabled
            prior_national_jobs=db.scalars(select(SyncJob).where(SyncJob.source_id==source.id,
                SyncJob.id!=job.id,SyncJob.status=="SUCCESS",SyncJob.pagination_complete.is_(True))
                .order_by(SyncJob.id.desc()).limit(25)).all()
            has_prior_national=any(((prior.metrics_json or {}).get("enumeration_scope")==FURAS_NATIONAL_SCOPE)
                for prior in prior_national_jobs)
            first_national_bootstrap=(metrics.get("enumeration_scope")==FURAS_NATIONAL_SCOPE and not has_prior_national)
            metrics["first_national_bootstrap"]=first_national_bootstrap
            metrics["bootstrap_removal_guard"]={"withheld":first_national_bootstrap,
                "reason":"FIRST_NATIONAL_CAPTURE_PRESERVES_EXISTING_LOCAL_ABSENCE_SEMANTICS"
                    if first_national_bootstrap else "NOT_FIRST_NATIONAL_CAPTURE"}
            removal_allowed=bool(complete and removals_enabled and not first_national_bootstrap)
            checkpoint["removal_reconciliation_allowed"]=removal_allowed
            if first_national_bootstrap:
                # The first complete national snapshot is a baseline capture.
                # It covers the old local scope, but old local absence counters
                # are not treated as national removal evidence on this run.
                metrics["reconciliation_executed"]=False
                source.sync_status="HEALTHY";source.last_successful_sync=NOW()
            elif removal_allowed and guard["safe"]:
                removed,guard=reconcile_furas_missing_records(db,source,set(checkpoint.get("processed_source_ids",[])),NOW(),job,metrics,True)
                metrics["reconciliation_guard"]=guard;metrics["reconciliation_safe"]=guard["safe"]
                counts["removed_records_count"]=len(removed)
                metrics["reconciliation_executed"]=bool(removed)
            elif not guard["safe"]:outcome="RECONCILIATION_SCOPE_WARNING"
            else:metrics["reconciliation_executed"]=False
            if not first_national_bootstrap:
                source.sync_status="HEALTHY" if outcome=="SUCCESS" else "RECONCILIATION_SCOPE_WARNING"
                source.last_successful_sync=NOW()
        else:
            source.sync_status="INCOMPLETE_COLLECTION_WARNING";source.technical_health="WARNING"
        source.last_record_count=counts["raw_count"];source.last_source_total_reported=source_total
        source.last_collection_completeness_percent=counts["collection_completeness_percent"]
        source.last_pagination_complete=complete
        checkpoint=dict(checkpoint);checkpoint["terminal_status"]=outcome
        checkpoint["removal_reconciliation_allowed"]=bool(complete
            and metrics.get("removal_reconciliation_enabled")
            and metrics.get("reconciliation_safe")
            and not metrics.get("first_national_bootstrap"))
        metrics["checkpoint"]=checkpoint;metrics["furas_checkpoint"]=checkpoint
        metrics["checkpoint_batch_commit"]="DATA_AND_CURSOR_ATOMIC"
        current=dict(job.metrics_json or {});current.update(metrics);current["furas_checkpoint"]=checkpoint
        job.metrics_json=current;job.new_count=checkpoint.get("source_rows_inserted_total",0)
        job.update_count=checkpoint.get("source_rows_updated_total",0);job.removed_records_count=counts["removed_records_count"]
        finished=NOW();db.flush()
        if not transition_sync_job(db,job,target_state=terminal_sync_job_state(outcome),target_status=outcome,
                finished_at=finished,allowed_from={"RUNNING"},values={"heartbeat_at":finished}):
            raise SyncJobFinalizationConflict(f"Sync job {job.id} was finalized by another writer")
        if outcome=="SUCCESS":
            from .data_quality import evaluate_data_quality
            dq=evaluate_data_quality(db,scope="fast",trigger="post_sync",source_id=source.id,job_id=job.id,persist=True)
            metrics["POST_SYNC_DQ_RUN_ID"]=dq["run_id"];metrics["POST_SYNC_DQ_COUNTS"]=dq["counts"]
            metrics["POST_SYNC_DQ_FAILING_GATES"]=[gate["gate_key"] for gate in dq["failed_gates"]]
        metrics={**(job.metrics_json or {}),**metrics}
        job.metrics_json=metrics
        db.add(SystemEvent(event_type="SYNC_COMPLETED",payload={"source":"furas","job_id":job.id,**counts,"status":outcome},created_at=NOW()))
        db.commit()
        return {"status":outcome,"source_key":"furas","job_id":job.id,**counts,"source_metrics":metrics}
    except StaleFurasCheckpoint:
        raise
    finally:
        release_resume_lock(lock_conn)

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

async def sync_source(source_key:str,queued_job_id:int|None=None,*,defer_failure_finalization:bool=False,
                      furas_stop_after_batches:int|None=None):
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
            if job.job_state!="RUNNING" or job.status!="RUNNING" or job.finished_at is not None:
                db.close();return {"status":"JOB_NOT_ACTIVE","source_key":source_key,"job_id":job.id}
            retry_checkpoint=(job.metrics_json or {}).get("furas_checkpoint") if source_key=="furas" else None
            job.heartbeat_at=NOW()
            job.pagination_complete=False;job.collection_completeness_percent=0.0;job.source_total_reported=None
            job.error_message=None
            job.metrics_json=({**(job.metrics_json or {})} if source_key=="furas" and adapter_cls is FurasAdapter else {})
            if retry_checkpoint and retry_checkpoint.get("enumeration_complete") is not True:
                job.metrics_json["furas_checkpoint"]=retry_checkpoint
            for field in ("pages_scanned","pages_requested","pages_successful","records_received","records_parsed","unique_records",
                          "raw_count","ahsa_count","new_count","duplicate_count","update_count","rejected_count","unchanged_count",
                          "duplicate_candidates_count","merged_records_count","removed_records_count","active_count","expired_count",
                          "duplicate_items_between_pages","location_review_count"):
                setattr(job,field,0)
        source.sync_status="RUNNING"; source.last_attempted_sync=NOW(); db.info["sync_job_id"]=job.id; db.commit()
        counts={"pages_scanned":0,"raw_count":0,"ahsa_count":0,"new_count":0,"duplicate_count":0,"update_count":0,"unchanged_count":0,"rejected_count":0,"duplicate_candidates_count":0,"merged_records_count":0,"removed_records_count":0,"location_review_count":0,
            "standardization_records_processed":0,"standardization_fields_changed":0,"standardization_aliases_matched":0,"standardization_unmapped_values":0,"standardization_issues":0}
        try:
            if source_key=="furas" and adapter_cls is FurasAdapter:
                return await _sync_furas_checkpointed(db,source,job,counts,stop_after_batches=furas_stop_after_batches)
            timeout=httpx.Timeout(35,connect=15)
            adapter=adapter_cls()
            if source_key=="ncp":
                # Reuse already captured portal details while the public list
                # fingerprint is stable. Detail payloads refresh on their own
                # cadence and do not force 159 image-heavy detail responses on
                # every 12-hour News archive scan.
                portal_cache={}
                for existing in db.scalars(select(SourceOpportunity).where(SourceOpportunity.source_id==source.id)).all():
                    raw_payload=existing.raw_data_json or {}
                    items=[]
                    if raw_payload.get("provider")=="NCP_INVESTORS_PORTAL":
                        item=raw_payload.get("ncp_portal_record")
                        if item:items.append(item)
                    items.extend(raw_payload.get("ncp_investors_portal_enrichments") or [])
                    for item in items:
                        provider_id=item.get("provider_id")
                        if provider_id:portal_cache[str(provider_id)]=item
                adapter.portal_detail_cache=portal_cache
            from .tls import create_source_ssl_context
            async with httpx.AsyncClient(timeout=timeout,verify=create_source_ssl_context(source_key),follow_redirects=True,limits=httpx.Limits(max_connections=4)) as client:
                records,pages=await adapter.fetch(client)
            ingestion_lock_acquired=acquire_sync_ingestion_lock(db)
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
            if source_key=="furas":
                reconciliation_guard=assess_furas_reconciliation_scope(db,source,job,adapter_metrics,complete)
                adapter_metrics["reconciliation_guard"]=reconciliation_guard
                adapter_metrics["reconciliation_safe"]=reconciliation_guard["safe"]
                adapter_metrics["ingestion_lock"]="POSTGRES_ADVISORY_TRANSACTION_LOCK" if ingestion_lock_acquired else "NOT_REQUIRED_FOR_DIALECT"
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
                        if source_key in {"rcjy-investment-opportunities","rcu-investment-opportunities"}:
                            geography=resolve_official_geography(db,str(place_name))
                            place.geography_reference_unit_id=geography.id if geography else None
                            place.source_evidence_json={
                                "verification_method":"EXACT_CURRENT_REFERENCE_NAME_OR_ALIAS" if geography else "UNMAPPED_OR_AMBIGUOUS_EXACT_REFERENCE",
                                "dataset_id":geography.dataset_id if geography else None,
                                "reference_unit_id":geography.id if geography else None,
                                "reference_level":geography.level if geography else None,
                                "reference_external_id":geography.external_id if geography else None,
                                "source_location":raw.location or place_name,
                                "source_url":payload.get("source_url") or raw.url,
                            }
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
                elif source_key=="ncp" and record:
                    store_ncp_portal_observations(db,record,raw)
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
            changed_taxonomy_values=set()
            for item in getattr(adapter,"raw_records",[]):
                source_value=(item.get("source_taxonomy") or {}).get("sector")
                normalized=(item.get("normalized_taxonomy") or {}).get("sector")
                if source_value:
                    mapping=db.scalar(select(TaxonomyMapping).where(TaxonomyMapping.source_key==source_key,TaxonomyMapping.source_value==source_value))
                    rule=f"broad-sector mapping v1: {source_value} → {normalized or 'Other'}"
                    if not mapping:
                        db.add(TaxonomyMapping(source_key=source_key,source_value=source_value,normalized_value=normalized or "Other",mapping_rule=rule,mapping_version="1"))
                        changed_taxonomy_values.add(source_value)
                    elif (mapping.normalized_value!= (normalized or "Other") or mapping.mapping_rule!=rule or mapping.mapping_version!="1"):
                        mapping.normalized_value=normalized or "Other";mapping.mapping_rule=rule;mapping.mapping_version="1"
                        changed_taxonomy_values.add(source_value)
            # A changed canonical mapping only revisits records carrying that
            # source/value; it never scans the full review backlog.
            for source_value in changed_taxonomy_values:
                affected_records=db.scalars(select(SourceOpportunity).where(
                    SourceOpportunity.source_id==source.id,
                    SourceOpportunity.source_sector==source_value,
                    SourceOpportunity.master_opportunity_id.is_not(None)).order_by(SourceOpportunity.id)).all()
                for affected in affected_records:
                    re_evaluate_review_evidence(db,source_record_id=affected.id,
                        master_id=affected.master_opportunity_id,trigger="canonical_mapping_update")
            if source_key=="invest-saudi" and complete:
                reconciliation_guard=assess_investsaudi_reconciliation_scope(db,source,adapter_metrics,
                    current_job_id=job.id,seen_by_dataset=invest_seen_by_dataset)
                adapter_metrics["reconciliation_guard"]=reconciliation_guard
                adapter_metrics["reconciliation_safe"]=reconciliation_guard["safe"]
                removed_from_current=(reconcile_investsaudi_memberships(db,source,invest_seen_by_dataset,NOW())
                    if reconciliation_guard["safe"] else 0)
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
            outcome_status="RUNNING"
            if adapter_metrics.get("collection_incomplete"):
                outcome_status="INCOMPLETE_COLLECTION_WARNING";source.sync_status="INCOMPLETE_COLLECTION_WARNING"
                db.add(SystemEvent(event_type="INCOMPLETE_COLLECTION_WARNING",payload={"source":source_key,"source_total_reported":source_total,
                    "unique_records":unique_records,"pages_requested":counts["pages_requested"],"pages_successful":counts["pages_successful"],
                    "pagination_complete":pagination_complete,"collection_completeness_percent":counts["collection_completeness_percent"]},created_at=NOW()))
            elif not records_to_store and not content_items:
                outcome_status="WARNING"; source.sync_status="PARSER_WARNING"
                detail="؛ ".join(getattr(adapter,"diagnostics",[]))
                source.notes=(source.notes+"\nآخر فحص لم ينتج سجلات؛ لم تُحذف البيانات. "+detail).strip()
            elif adapter_metrics.get("parser_warning"):
                outcome_status="PARSER_WARNING";source.sync_status="PARSER_WARNING"
                db.add(SystemEvent(event_type="PARSER_WARNING",payload={"source":source_key,"diagnostics":getattr(adapter,"diagnostics",[])},created_at=NOW()))
            else:
                if complete and adapter_metrics.get("reconciliation_safe",True):
                    # Presence is source scope, not Al-Ahsa qualification. Invest Saudi
                    # retains all national candidates, so all of them must reset misses.
                    seen_ids=source_presence_ids(source_key,records,records_to_store)
                    if source_key=="furas":
                        removed,guard=reconcile_furas_missing_records(db,source,seen_ids,NOW(),job,adapter_metrics,complete)
                        adapter_metrics["reconciliation_guard"]=guard
                        adapter_metrics["reconciliation_safe"]=guard["safe"]
                    else:
                        removed=reconcile_missing_records(db,source,seen_ids,NOW())
                    counts["removed_records_count"]=len(removed)
                    if source_key=="invest-saudi":
                        adapter_metrics["source_lifecycle_newly_removed_count"]=len(removed)
                    outcome_status="SUCCESS"
                    if source_key=="invest-saudi" and adapter_metrics.get("unique_dataset_reconciliation")!="DATASET_RECONCILED":
                        source.sync_status="DATASET_RECONCILIATION_WARNING"
                    else:source.sync_status="HEALTHY"
                    source.last_successful_sync=NOW()
                elif source_key=="invest-saudi" and complete:
                    outcome_status="SUCCESS"
                    source.sync_status="RECONCILIATION_GUARD_WARNING"
                    source.last_successful_sync=NOW()
                    db.add(SystemEvent(event_type="SOURCE_RECONCILIATION_GUARD_BLOCKED",created_at=NOW(),
                        payload={"source":source_key,"job_id":job.id,
                            "guard":adapter_metrics.get("reconciliation_guard"),
                            "reason":"Complete collection retained as evidence; lifecycle removals withheld until a comparable safe scan."}))
                elif source_key=="furas" and complete:
                    outcome_status="RECONCILIATION_SCOPE_WARNING"
                    source.sync_status="RECONCILIATION_SCOPE_WARNING"
                    source.technical_health="WARNING"
                    source.last_successful_sync=NOW()
                    db.add(SystemEvent(event_type="SOURCE_RECONCILIATION_SCOPE_BLOCKED",created_at=NOW(),payload={
                        "source":source_key,"job_id":job.id,"guard":adapter_metrics.get("reconciliation_guard"),
                        "reason":"Complete feature collection was retained; removals were withheld because its verified enumeration scope did not cover the previous completed scope."}))
                elif public_scope_complete:
                    outcome_status="SUCCESS";source.sync_status="HEALTHY";source.last_successful_sync=NOW()
                else:
                    outcome_status="INCOMPLETE_COLLECTION_WARNING";source.sync_status="INCOMPLETE_COLLECTION_WARNING"
                    db.add(SystemEvent(event_type="INCOMPLETE_COLLECTION_WARNING",payload={"source":source_key,"source_total_reported":source_total,
                        "unique_records":unique_records,"pages_requested":counts["pages_requested"],"pages_successful":counts["pages_successful"],
                        "pagination_complete":pagination_complete,"collection_completeness_percent":counts["collection_completeness_percent"]},created_at=NOW()))
            source.last_record_count=counts["raw_count"]
            source.last_source_total_reported=source_total
            source.last_collection_completeness_percent=counts["collection_completeness_percent"]
            source.last_pagination_complete=pagination_complete
            if outcome_status in ("BLOCKED",):source.technical_health="BLOCKED"
            elif outcome_status in ("FAILED",):source.technical_health="FAILED"
            elif outcome_status in ("PARSER_WARNING",):source.technical_health="PARSER_BROKEN"
            elif outcome_status not in ("SUCCESS",):source.technical_health="WARNING"
            source.coverage_notes=adapter_metrics.get("coverage_notes",source.coverage_notes or "")
            if outcome_status=="SUCCESS":
                from .autonomous_review_resolution import resolve_post_sync_reviews
                review_metrics=resolve_post_sync_reviews(db,source_id=source.id,job_id=job.id)
                adapter_metrics.update({key.upper():value for key,value in review_metrics.items()})
            finished_at=NOW()
            job_counts={key:value for key,value in counts.items() if hasattr(job,key)}
            job_counts["location_review_count"]=counts["location_review_count"]
            terminal_state=terminal_sync_job_state(outcome_status)
            # Finish the source/Master writes first. The lifecycle row CAS is
            # deliberately late so its row lock is not held across ingestion
            # updates; both remain invisible until this transaction commits.
            db.flush()
            if not transition_sync_job(db,job,target_state=terminal_state,target_status=outcome_status,
                    finished_at=finished_at,allowed_from={"RUNNING"},
                    values={**job_counts,"heartbeat_at":finished_at}):
                raise SyncJobFinalizationConflict(f"Sync job {job.id} was finalized by another writer")
            if outcome_status=="SUCCESS":
                from .data_quality import evaluate_data_quality
                dq=evaluate_data_quality(db,scope="fast",trigger="post_sync",source_id=source.id,
                                         job_id=job.id,persist=True)
                adapter_metrics["POST_SYNC_DQ_RUN_ID"]=dq["run_id"]
                adapter_metrics["POST_SYNC_DQ_COUNTS"]=dq["counts"]
                adapter_metrics["POST_SYNC_DQ_FAILING_GATES"]=[gate["gate_key"] for gate in dq["failed_gates"]]
            adapter_metrics["standardization"]={"version":STANDARDIZATION_VERSION,"records_processed":counts["standardization_records_processed"],
                "fields_standardized":counts["standardization_fields_changed"],"approved_alias_matches":counts["standardization_aliases_matched"],
                "unmapped_values":counts["standardization_unmapped_values"],"validation_issues":counts["standardization_issues"]}
            job.metrics_json=adapter_metrics
            db.add(SystemEvent(event_type="SYNC_COMPLETED",payload={"source":source_key,**counts,"status":outcome_status},created_at=NOW()))
            db.commit()
            return {"status":outcome_status,"source_key":source_key,"job_id":job.id,**counts,"source_metrics":adapter_metrics}
        except SyncJobFinalizationConflict:
            db.rollback();db.close()
            return {"status":"STALE_FINALIZER_IGNORED","source_key":source_key,"job_id":queued_job_id}
        except SourceBlocked as exc:
            db.rollback()
            source=db.scalar(select(Source).where(Source.source_key==source_key));job=db.get(SyncJob,job.id)
            if source:source.sync_status="BLOCKED";source.technical_health="BLOCKED"
            finished_at=NOW()
            finalized=bool(job and transition_sync_job(db,job,target_state="COMPLETED_WITH_WARNINGS",target_status="BLOCKED",
                finished_at=finished_at,allowed_from={"RUNNING"},values={"heartbeat_at":finished_at,"error_message":str(exc)}))
            if not finalized:
                db.rollback();db.close()
                return {"status":"STALE_FINALIZER_IGNORED","source_key":source_key,"job_id":queued_job_id}
            if source:db.add(SourceError(source_id=source.id,occurred_at=NOW(),category="BLOCKED",message=str(exc)))
            db.add(SystemEvent(event_type="SYNC_BLOCKED",payload={"source":source_key,"error":str(exc)},created_at=NOW()));db.commit()
            return {"status":"BLOCKED","source_key":source_key,"job_id":job.id if job else queued_job_id,"error":str(exc),**counts}
        except asyncio.CancelledError as exc:
            db.rollback()
            source=db.scalar(select(Source).where(Source.source_key==source_key));job=db.get(SyncJob,job.id)
            if source_key=="furas" and adapter_cls is FurasAdapter and job:
                from .furas_checkpoint import append_failure_diagnostic
                job.metrics_json=append_failure_diagnostic(job.metrics_json or {},exc,
                    failure_stage="WORKER_SHUTDOWN",retryable=True)
                job.error_message=str(exc);job.heartbeat_at=NOW();db.commit()
            raise
        except Exception as exc:
            db.rollback()
            source=db.scalar(select(Source).where(Source.source_key==source_key)); job=db.get(SyncJob,job.id)
            http_status=getattr(getattr(exc,"response",None),"status_code",None)
            health=classify_http_health(http_status)
            if source: source.sync_status="FAILED";source.technical_health=health
            if job:
                if source_key=="furas" and adapter_cls is FurasAdapter:
                    from .furas_checkpoint import append_failure_diagnostic
                    if isinstance(exc,StaleFurasCheckpoint):failure_stage="CHECKPOINT_OR_MEMBERSHIP_VALIDATION"
                    elif isinstance(exc,SQLAlchemyError):failure_stage="DATABASE_COMMIT_OR_RECONCILIATION"
                    elif isinstance(exc,httpx.HTTPError):failure_stage="HTTP_REQUEST"
                    elif getattr(exc,"failure_stage",None):failure_stage=str(exc.failure_stage)
                    elif isinstance(exc,asyncio.CancelledError):failure_stage="WORKER_SHUTDOWN"
                    else:failure_stage="SOURCE_CAPTURE_OR_FINALIZATION"
                    retryable=bool(getattr(exc,"retryable",not isinstance(exc,StaleFurasCheckpoint)))
                    metrics=append_failure_diagnostic(job.metrics_json or {},exc,
                        failure_stage=failure_stage,retryable=retryable)
                    if isinstance(exc,StaleFurasCheckpoint):
                        metrics["checkpoint_resume_rejected"]=True
                        metrics["checkpoint_resume_rejection_reason"]=str(exc)
                    job.metrics_json=metrics
                if defer_failure_finalization:
                    if job.job_state not in {"RUNNING","RETRYING"}:
                        db.rollback();db.close()
                        return {"status":"STALE_FINALIZER_IGNORED","source_key":source_key,"job_id":job.id}
                    job.error_message=str(exc);job.heartbeat_at=NOW()
                elif not transition_sync_job(db,job,target_state="FAILED",target_status="FAILED",finished_at=NOW(),
                        allowed_from={"RUNNING","RETRYING"},values={"heartbeat_at":NOW(),"error_message":str(exc)}):
                    db.rollback();db.close()
                    return {"status":"STALE_FINALIZER_IGNORED","source_key":source_key,"job_id":job.id}
            if source: db.add(SourceError(source_id=source.id,occurred_at=NOW(),category="HTTP_5XX" if http_status and http_status>=500 else type(exc).__name__,message=str(exc)))
            db.add(SystemEvent(event_type="SYNC_FAILED",payload={"source":source_key,"error":str(exc)},created_at=NOW())); db.commit()
            return {"status":"FAILED","source_key":source_key,"job_id":job.id if job else queued_job_id,"error":str(exc),**counts}
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


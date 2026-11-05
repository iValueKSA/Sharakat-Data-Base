import sys,json,hashlib
sys.path.insert(0,"/app")
from datetime import datetime,timezone
from collections import Counter,defaultdict
from sqlalchemy import select,func,text
from app.database import SessionLocal
from app.models import Opportunity,SourceOpportunity,Source,SourceObservation,SyncJob,FieldProvenance,ChangeHistory,AlertEvent
from app.standardization import STANDARDIZATION_VERSION

def iso_epoch(v):
 try:
  if v in (None,""): return None
  return datetime.fromtimestamp(float(v)/1000,timezone.utc).date().isoformat()
 except Exception:return None
with SessionLocal() as db:
 db.connection().execute(text("SET TRANSACTION READ ONLY"))
 now=db.execute(select(func.now())).scalar()
 masters=db.scalars(select(Opportunity).order_by(Opportunity.id)).all()
 nonmerged=[m for m in masters if m.merged_into_id is None]
 sources={s.id:s for s in db.scalars(select(Source)).all()}
 links=db.scalars(select(SourceOpportunity).order_by(SourceOpportunity.id)).all()
 linked=defaultdict(list)
 for r in links:
  if r.master_opportunity_id: linked[r.master_opportunity_id].append(r)
 furas=[r for r in links if r.source and r.source.source_key=="furas"]
 furas_linked=[r for r in furas if r.master_opportunity_id]
 classes={"deadline":[],"publication":[]}; rows=[]; stats=Counter(); fstatus=Counter(); types=Counter(); datepatterns=Counter(); same_end_sell=0
 for r in furas_linked:
  m=next((x for x in masters if x.id==r.master_opportunity_id),None)
  if not m: continue
  a=(r.raw_data_json or {}).get("attributes") or {}
  pat=tuple(a.get(k) not in (None,"") for k in ("STARTDATE","ENDDATE","LASTRFPSELLDATE","LASTBIDATE","ENVELOPESOPENDATE"));datepatterns[pat]+=1
  if a.get("ENDDATE")==a.get("LASTRFPSELLDATE"):same_end_sell+=1
  fstatus[(m.status,r.canonical_status)]+=1;types[str(a.get("OPPORTUNITYTYPE"))]+=1
  others=[s for s in linked[m.id] if s.source and s.source.source_key!="furas"]
  other_deadlines=[(s.raw_dates or {}).get("deadline") for s in others if (s.raw_dates or {}).get("deadline")]
  other_pubs=[(s.raw_data_json or {}).get("publication_date") for s in others if (s.raw_data_json or {}).get("publication_date")]
  raw_end=iso_epoch(a.get("ENDDATE")); raw_sell=iso_epoch(a.get("LASTRFPSELLDATE")); raw_start=iso_epoch(a.get("STARTDATE"))
  if m.submission_deadline and (m.submission_deadline in {raw_end,raw_sell}) and not any(str(x)==m.submission_deadline for x in other_deadlines):
   classes["deadline"].append(m.id)
  if m.publication_date and m.publication_date==raw_start and not any(str(x)==m.publication_date for x in other_pubs):
   classes["publication"].append(m.id)
  rows.append({"master_id":m.id,"source_opportunity_id":r.id,"ref":r.source_reference_number,"status":m.status,"merged":bool(m.merged_into_id),"source_status":r.canonical_status,"type":a.get("OPPORTUNITYTYPE"),"raw_start":a.get("STARTDATE"),"raw_end":a.get("ENDDATE"),"raw_sell":a.get("LASTRFPSELLDATE"),"raw_bid":a.get("LASTBIDATE"),"raw_open":a.get("ENVELOPESOPENDATE"),"canonical_deadline":m.submission_deadline,"canonical_publication":m.publication_date,"other_sources":[s.source.source_key for s in others if s.source],"other_deadlines":other_deadlines,"other_publications":other_pubs})
 obs=db.execute(select(func.count(SourceObservation.id),func.max(SourceObservation.id))).one()
 jobs=db.scalars(select(SyncJob).order_by(SyncJob.id.desc()).limit(20)).all()
 fingerprints={"master_identity":hashlib.sha256("|".join(f"{m.id}:{m.canonical_id}:{m.merged_into_id}" for m in masters).encode()).hexdigest(),"source_links":hashlib.sha256("|".join(f"{r.id}:{r.source_id}:{r.master_opportunity_id}:{r.source_opportunity_id}:{r.source_url}" for r in links).encode()).hexdigest(),"furas_raw_payloads":hashlib.sha256("|".join(f"{r.id}:{hashlib.sha256(json.dumps(r.raw_data_json or {},sort_keys=True,ensure_ascii=False,default=str).encode()).hexdigest()}" for r in furas).encode()).hexdigest(),"furas_observations":hashlib.sha256("|".join(str(x) for x in db.scalars(select(SourceObservation.id,SourceObservation.source_opportunity_id,SourceObservation.content_hash).join(SourceOpportunity,SourceOpportunity.id==SourceObservation.source_opportunity_id).where(SourceOpportunity.source_id==next((s.id for s in sources.values() if s.source_key=="furas"),-1)).order_by(SourceObservation.id)).all()).encode()).hexdigest()}
 data={"snapshot_utc":now.isoformat(),"standardization_version":STANDARDIZATION_VERSION,"total_master_rows":len(masters),"nonmerged_masters":len(nonmerged),"source_opportunities":len(links),"observations":obs[0],"observation_max_id":obs[1],"furas_source_opportunities":len(furas),"furas_linked":len(furas_linked),"furas_deadline_correction_ids":sorted(set(classes["deadline"])),"furas_publication_correction_ids":sorted(set(classes["publication"])),"furas_deadline_correction_count":len(set(classes["deadline"])),"furas_publication_correction_count":len(set(classes["publication"])),"date_presence_patterns":{str(k):v for k,v in datepatterns.items()},"equal_ENDDATE_LASTRFPSELLDATE":same_end_sell,"furas_types":dict(types),"furas_lifecycle_counts":dict(Counter(m.status for m in nonmerged if any(x.source and x.source.source_key=="furas" for x in linked[m.id]))),"furas_source_lifecycle_counts":dict(Counter(r.canonical_status for r in furas_linked)),"expired_masters_with_furas_only_date":sorted(m.id for m in nonmerged if m.status=="منتهية" and any(x.source and x.source.source_key=="furas" for x in linked[m.id]) and not any((x.source and x.source.source_key!="furas" and (x.raw_dates or {}).get("deadline")) for x in linked[m.id])),"status_counts":dict(Counter(m.status for m in nonmerged)),"deadlines_populated":sum(bool(m.submission_deadline) for m in nonmerged),"publication_populated":sum(bool(m.publication_date) for m in nonmerged),"fingerprints":fingerprints,"jobs_after_pre_correction_snapshot":[{"id":j.id,"source_id":j.source_id,"status":j.status,"job_state":j.job_state,"trigger_type":j.trigger_type,"queued_at":j.queued_at.isoformat() if j.queued_at else None,"started_at":j.started_at.isoformat() if j.started_at else None,"finished_at":j.finished_at.isoformat() if j.finished_at else None,"raw_count":j.raw_count,"update_count":j.update_count,"new_count":j.new_count} for j in reversed(jobs) if j.queued_at and j.queued_at>=datetime(2026,10,20,6,54,58,383590,tzinfo=timezone.utc)],"sample_furas_rows":[r for r in rows if r["master_id"] in {10,102,109,195,324,325}],"all_furas_rows":rows}
 print(json.dumps(data,ensure_ascii=False,default=str))

import json
from collections import Counter
from datetime import datetime, timezone
from sqlalchemy import event, select
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models import Opportunity, Source, SourceOpportunity, SyncJob
import app.main as main
@event.listens_for(Session,"after_begin")
def ro(session,transaction,connection):
 if connection.dialect.name=="postgresql": connection.exec_driver_sql("SET TRANSACTION READ ONLY")
t=main.request_context.set({"user":{"id":0,"role":"admin"},"path":"/api/admin/review-queue","method":"GET"})
try: all_rows=main.review_queue(None,"all","OPEN",1000)
finally: main.request_context.reset(t)
open_rows=[r for r in all_rows if r.get("status")=="OPEN"]
actionable=[r for r in open_rows if r.get("disposition")!="SOURCE_RECHECK_REQUIRED"]
with SessionLocal() as db:
 total_jobs,max_job=db.execute(select(__import__('sqlalchemy').func.count(SyncJob.id),__import__('sqlalchemy').func.max(SyncJob.id))).one()
 candidates=[]
 for r in actionable:
  ids=r.get("master_ids") or []
  masters=[db.get(Opportunity,mid) for mid in ids]
  refs=[(m.reference_number or m.canonical_id) for m in masters if m]
  src_ids=set()
  if r.get("source_record_id"):
   rec=db.get(SourceOpportunity,r['source_record_id'])
   if rec: src_ids.add(rec.source_id)
  if ids:
   for rec in db.scalars(select(SourceOpportunity).where(SourceOpportunity.master_opportunity_id.in_(ids))): src_ids.add(rec.source_id)
  srcs=[db.get(Source,sid) for sid in sorted(src_ids)]
  names=sorted({s.source_name_ar for s in srcs if s and s.source_name_ar})
  primary=r.get("source") or (names[0] if names else "غير محدد")
  candidates.append({"review_id":r['id'],"priority":r.get("priority") or "P4","type":r.get("domain"),"subtype":r.get("field") or r.get("reason_key"),"master_ids":ids,"master_reference":" / ".join(refs) if refs else " / ".join(f"Master {x}" for x in ids),"title":r.get("title") or "مراجعة دون عنوان","source_names":names or ([r['source']] if r.get('source') else []),"primary_source":primary,"disposition":r.get("disposition"),"evidence_status":r.get("evidence_status"),"reason_label":r.get("reason_label"),"guarded_standardization":(r.get("evidence") or {}).get("guarded_standardization"),"created_at":r.get("created_at")})

# Freeze a stratified sample. Priorities absent from the live actionable inventory cannot be fabricated.
target_priority={"P2":28,"P3":8,"P4":4,"P1":0}
target_type={"duplicate":6,"location":5,"taxonomy_conflict":6,"field_conflict":23}
required_subtypes=[("field_conflict","opportunity_owner"),("field_conflict","status"),("field_conflict","land_area_sqm"),("field_conflict","investment_value"),("field_conflict","contract_duration_years"),("field_conflict","title_ar"),("field_conflict","normalized_title"),("field_conflict","short_description"),("field_conflict","full_description"),("field_conflict","location_description"),("field_conflict","sector"),("field_conflict","opportunity_type"),("taxonomy_conflict","sector"),("taxonomy_conflict","activity"),("taxonomy_conflict","sub_activity"),("taxonomy_conflict","investment_model"),("duplicate","DUPLICATE_IDENTITY_AMBIGUITY"),("location","LOCATION_EVIDENCE_AMBIGUITY")]
source_pop=Counter(c['primary_source'] for c in candidates)
selected=[]; used=set(); byp=Counter(); byt=Counter(); bys=Counter()
def score(c):
 p=c['priority']; ty=c['type']; src=c['primary_source']
 pd=max(0,target_priority.get(p,0)-byp[p]); td=max(0,target_type.get(ty,0)-byt[ty])
 return (3*(pd/max(1,target_priority.get(p,1))) + 3*(td/max(1,target_type.get(ty,1))) + (1/(1+bys[src])) + (0.8 if c.get('evidence_status')=='EVIDENCE_LIMITED' else 0) + (0.25 if c.get('guarded_standardization') else 0) + min(source_pop[src],100)/10000)
def add_best(pool):
 pool=[c for c in pool if c['review_id'] not in used]
 if not pool:return False
 c=max(pool,key=lambda x:(score(x),-x['review_id']))
 selected.append(c);used.add(c['review_id']);byp[c['priority']]+=1;byt[c['type']]+=1;bys[c['primary_source']]+=1
 return True
for subtype in required_subtypes:
 pool=[c for c in candidates if (c['type'],c['subtype'])==subtype]
 add_best(pool)
# Add until the 40-case type and priority balance is met, then prefer sparse sources and limited evidence.
while len(selected)<40:
 pool=[c for c in candidates if c['review_id'] not in used]
 if not add_best(pool):break
selected.sort(key=lambda c:(int(c['priority'][1:]),c['type'],str(c['subtype']),c['review_id']))
for idx,c in enumerate(selected,1): c['pilot_sequence']=idx; c['phase']='A' if idx<=20 else 'B'; c['review_id_key']=f"{c['type']}:{c['review_id']}"; c['source_recheck_excluded']=c['disposition']=='SOURCE_RECHECK_REQUIRED'
with SessionLocal() as db: jobrows=db.execute(select(SyncJob.id,SyncJob.trigger_type).order_by(SyncJob.id.desc()).limit(1)).first()
result={"captured_at":datetime.now(timezone.utc).isoformat(),"frozen_before_analyst_decisions":True,"selection_method":"Deterministic stratified coverage of rare active subtypes, then priority/type balance with source diversity and inclusion of limited-evidence/guarded cases.","open_reviews_total":len(open_rows),"human_review_required":len(actionable),"source_recheck_required":len(open_rows)-len(actionable),"open_by_type":dict(Counter(r.get('domain') for r in open_rows)),"open_by_subtype":[{"type":k.split('|',1)[0],"subtype":k.split('|',1)[1],"count":v} for k,v in sorted(Counter(f"{r.get('domain')}|{r.get('field') or r.get('reason_key')}" for r in open_rows).items())],"open_by_priority":dict(Counter(r.get('priority') for r in open_rows)),"open_by_source":dict(Counter(c['primary_source'] for c in candidates)),"sync_jobs_current":int(total_jobs),"sync_jobs_max_id":int(max_job or 0),"sample_size":len(selected),"pilot_by_type":dict(Counter(c['type'] for c in selected)),"pilot_by_priority":dict(Counter(c['priority'] for c in selected)),"pilot_by_source":dict(Counter(c['primary_source'] for c in selected)),"pilot_by_subtype":dict(Counter(c['subtype'] for c in selected)),"source_recheck_in_pilot":sum(c['source_recheck_excluded'] for c in selected),"priorities_unavailable":[p for p,n in target_priority.items() if n and not any(c['priority']==p for c in candidates)],"subtypes_unavailable":[f"{t}|{s}" for t,s in required_subtypes if not any(c['type']==t and c['subtype']==s for c in candidates)],"cases":selected}
print(json.dumps(result,ensure_ascii=False,separators=(",",":"),default=str))

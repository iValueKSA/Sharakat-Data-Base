import asyncio,csv,io,json
from collections import Counter
from datetime import datetime,timezone
from sqlalchemy import select,func,event,text
from app.database import SessionLocal,engine
from app.models import Opportunity,SourceOpportunity,SourceObservation,DuplicateCandidate,LocationReview,QualificationReview,OpportunityConflict,AuditEvent,MergeAudit,SyncJob,Source
@event.listens_for(engine,'connect')
def readonly(dbapi_connection,connection_record):
    cur=dbapi_connection.cursor(); cur.execute('SET default_transaction_read_only=on'); cur.close()
from app.data_quality import evaluate_data_quality
from app import main as api
now=datetime.now(timezone.utc)
def iso(v): return v.isoformat() if hasattr(v,'isoformat') else v
def norm_dt(v):
    if not v:return None
    if v.tzinfo is None:return v.replace(tzinfo=timezone.utc)
    return v.astimezone(timezone.utc)
with SessionLocal() as db:
    counts={'current_masters':db.scalar(select(func.count(Opportunity.id)).where(Opportunity.merged_into_id.is_(None))) or 0,'total_masters':db.scalar(select(func.count(Opportunity.id))) or 0,'merged_masters':db.scalar(select(func.count(Opportunity.id)).where(Opportunity.merged_into_id.is_not(None))) or 0,'source_opportunities':db.scalar(select(func.count(SourceOpportunity.id))) or 0,'observations':db.scalar(select(func.count(SourceObservation.id))) or 0}
    models=[(DuplicateCandidate,'duplicate_candidate',{'PENDING','OPEN'}),(LocationReview,'location_review',{'PENDING','OPEN'}),(QualificationReview,'qualification_review',{'PENDING','OPEN'}),(OpportunityConflict,'opportunity_conflict',{'PENDING','OPEN'})]
    review_counts={}; resolved_rows=[]
    for model,kind,opens in models:
      grouped=db.execute(select(model.status,func.count(model.id)).group_by(model.status)).all(); review_counts[model.__tablename__]={str(s):n for s,n in grouped}
      resolved_rows += [(model,kind,row) for row in db.scalars(select(model).where(model.status.not_in(opens))).all()]
    total_reviews=sum(sum(x.values()) for x in review_counts.values())
    open_reviews=sum(v for x in review_counts.values() for s,v in x.items() if s in ('OPEN','PENDING'))
    superseded=sum(v for x in review_counts.values() for s,v in x.items() if s in ('SUPERSEDED','STALE','OBSOLETE'))
    all_events=db.scalars(select(AuditEvent).where(AuditEvent.event_type.like('REVIEW_%')).order_by(AuditEvent.id)).all()
    decision_events=[e for e in all_events if isinstance(e.after_json,dict) and ((e.after_json.get('decision')) or e.event_type=='REVIEW_REOPENED')]
    audit_keys={(e.entity_type,e.entity_id) for e in decision_events if e.entity_type and e.entity_id and e.entity_type!='review_evidence'}
    versioned=[norm_dt(e.created_at) for e in decision_events if (e.request_metadata or {}).get('review_audit_version') in ('1','2') and e.created_at]
    boundary=min(versioned) if versioned else None
    merge_audits=db.scalars(select(MergeAudit).where(MergeAudit.undone_at.is_(None)).order_by(MergeAudit.id)).all()
    merge_pairs={frozenset((m.merged_opportunity_id,m.target_opportunity_id)):m for m in merge_audits}
    historical=[]; current_missing=[]; all_original=[]
    for model,kind,row in resolved_rows:
      rid=str(row.id); linked=[e for e in decision_events if e.entity_type==kind and e.entity_id==rid]
      merge=None
      if kind=='duplicate_candidate' and row.status=='MERGED': merge=merge_pairs.get(frozenset((row.left_opportunity_id,row.right_opportunity_id)))
      if linked: continue
      item_fields={c.name:getattr(row,c.name) for c in row.__table__.columns}
      explanation=item_fields.get('explanation_json') if isinstance(item_fields.get('explanation_json'),dict) else {}
      ident=explanation.get('identity_review_decision') if isinstance(explanation.get('identity_review_decision'),dict) else {}
      reviewed_at=ident.get('reviewed_at')
      reviewed_time=None
      if isinstance(reviewed_at,str):
        try: reviewed_time=norm_dt(datetime.fromisoformat(reviewed_at.replace('Z','+00:00')))
        except ValueError: pass
      resolution_time=norm_dt(item_fields.get('resolved_at') or item_fields.get('updated_at'))
      if merge:
        cls='D_AUDIT_EXISTS_BUT_GATE_FAILED_TO_LINK_IT'
      elif kind=='duplicate_candidate' and row.status=='REJECTED' and reviewed_time and boundary and reviewed_time>=boundary:
        cls='A_CURRENT_DECISION_MISSING_REQUIRED_AUDIT'; current_missing.append(f'{kind}:{rid}')
      elif resolution_time and boundary and resolution_time>=boundary:
        cls='A_CURRENT_DECISION_MISSING_REQUIRED_AUDIT'; current_missing.append(f'{kind}:{rid}')
      elif kind=='duplicate_candidate' and row.status=='REJECTED' and reviewed_time:
        cls='B_HISTORICAL_PRE_AUDIT_GOVERNANCE'
      else:
        cls='E_INCOMPLETE_HISTORICAL_METADATA'
      ent_valid=None
      if kind=='duplicate_candidate':
        left=db.get(Opportunity,row.left_opportunity_id); right=db.get(Opportunity,row.right_opportunity_id); ent_valid=bool(left and right)
      elif kind=='opportunity_conflict':
        ent_valid=bool(db.get(Opportunity,row.opportunity_id) and db.get(SourceOpportunity,row.source_record_id) and db.get(Source,row.source_id))
      elif kind=='location_review':
        ent_valid=bool(db.get(Source,row.source_id) and (row.source_record_id is None or db.get(SourceOpportunity,row.source_record_id)))
      elif kind=='qualification_review':
        ent_valid=bool(db.get(Source,row.source_id) and db.get(SourceOpportunity,row.source_record_id))
      review_created=item_fields.get('created_at') or item_fields.get('detected_at')
      resolved_by=(merge.performed_by if merge else None)
      action=(item_fields.get('resolution_action') or item_fields.get('decision') or item_fields.get('action') or explanation.get('decision') or ident.get('decision'))
      if linked:
        resolved_by=(linked[-1].request_metadata or {}).get('actor') or linked[-1].user_id
        action=(linked[-1].after_json or {}).get('decision')
      item={'review_id':row.id,'review_type':kind,'status':row.status,'created_at':iso(review_created),'resolved_at':iso(item_fields.get('resolved_at') or item_fields.get('updated_at') or (reviewed_time if reviewed_time else None) or (merge.merged_at if merge else None)),'resolved_by':resolved_by or 'UNKNOWN_NOT_STORED','resolution_action':action or 'UNKNOWN_NOT_STORED','audit_event_exists':bool(linked),'audit_event_ids':[e.id for e in linked],'merge_audit_exists':bool(merge),'merge_audit_id':merge.id if merge else None,'review_age_days':round((now-norm_dt(review_created)).total_seconds()/86400,2) if review_created else None,'governance_version_at_resolution':(linked[-1].request_metadata or {}).get('review_audit_version') if linked else ('PRE_VERSIONED' if reviewed_time and boundary and reviewed_time<boundary else ('NOT_VERSIONED_IN_MERGE_AUDIT' if merge else 'UNKNOWN')),'current_entity_valid':ent_valid,'classification':cls}
      all_original.append(item)
      if cls in ('B_HISTORICAL_PRE_AUDIT_GOVERNANCE','E_INCOMPLETE_HISTORICAL_METADATA'): historical.append(item)
    # invalid action records and current logic classification
    allowed={'FIELD_KEEP','FIELD_USE_SOURCE','SECTOR_INFERENCE_ACCEPTED','DUPLICATE_MERGED','DUPLICATE_REJECTED','DUPLICATE_UNDONE','LOCATION_ACCEPTED','LOCATION_REJECTED','QUALIFICATION_ACCEPTED','QUALIFICATION_REJECTED'}
    invalid=[]; ignored_lifecycle=[]
    for e in all_events:
      after=e.after_json if isinstance(e.after_json,dict) else {}; meta=e.request_metadata if isinstance(e.request_metadata,dict) else {}; decision=after.get('decision')
      if not isinstance(decision,str) or decision in allowed: continue
      before=e.before_json if isinstance(e.before_json,dict) else {}
      lifecycle=e.event_type.endswith('_SUPERSEDED') and before.get('status') in ('OPEN','PENDING') and after.get('status')=='SUPERSEDED' and decision.endswith('_SUPERSEDED')
      sys=(str(meta.get('actor') or '').strip().upper()=='SYSTEM')
      rec={'event_id':e.id,'review_id':e.entity_id,'review_type':e.entity_type,'review_subtype':e.event_type.removeprefix('REVIEW_').removesuffix('_SUPERSEDED'),'status_before':before.get('status'),'status_after':after.get('status'),'stored_action':decision,'current_allowed_actions':sorted(allowed),'action_valid_at_time':'SYSTEM_LIFECYCLE' if meta.get('decision_kind')=='SYSTEM_LIFECYCLE' or lifecycle or (sys and meta.get('decision_kind')!='HUMAN') else 'UNPROVEN_LEGACY_OR_INVALID','created_at':iso(e.created_at),'resolved_at':iso(e.created_at) if lifecycle else None,'actor':meta.get('actor') or (str(e.user_id) if e.user_id is not None else None),'audit_event':True,'business_state':None,'decision_kind':meta.get('decision_kind'),'review_audit_version':meta.get('review_audit_version')}
      model={'duplicate_candidate':DuplicateCandidate,'location_review':LocationReview,'qualification_review':QualificationReview,'opportunity_conflict':OpportunityConflict}.get(e.entity_type)
      if model:
        r=db.get(model,int(e.entity_id))
        rec['business_state']=getattr(r,'status',None) if r else 'ENTITY_MISSING'
      if lifecycle or meta.get('decision_kind')=='SYSTEM_LIFECYCLE' or (sys and meta.get('decision_kind')!='HUMAN'): ignored_lifecycle.append(rec)
      else: invalid.append(rec)
    dq=evaluate_data_quality(db,scope='full',trigger='focused_dq_failure_closeout_current',persist=False)
    relevant={g['gate_key']:g for g in dq['gates'] if g['gate_key'] in ('HUMAN_DECISION_WITHOUT_AUDIT','HISTORICAL_REVIEW_AUDIT_INCOMPLETE','REVIEW_DECISION_WITH_INVALID_ACTION','CURRENT_LIST_DUPLICATE_MASTER_ROWS','API_DASHBOARD_EXPORT_RECONCILIATION')}
    # direct endpoint pagination and diverse filters
    api_total=api.opportunities(limit=1,offset=0)['total']; pages=[api.opportunities(limit=100,offset=o)['items'] for o in range(0,api_total,100)]; ids=[x['id'] for page in pages for x in page]; dupe_ids=sorted({i for i in ids if ids.count(i)>1})
    db_ids=set(db.scalars(select(Opportunity.id).where(Opportunity.merged_into_id.is_(None))).all())
    filter_specs={}
    for key,kw in [('sector',{'sector':'COMMERCIAL'}),('status',{'status':'ACTIVE'}),('source',{'source':'furas'}),('location',{'location':'الهفوف'}),('search',{'q':'فرصة'})]:
      try:
        r=api.opportunities(limit=1000,offset=0,**kw); got=[x['id'] for x in r['items']]; filter_specs[key]={'total':r['total'],'rows':len(got),'unique_ids':len(set(got)),'duplicate_ids':sorted({x for x in got if got.count(x)>1})}
      except Exception as e: filter_specs[key]={'error':str(e)}
    csv_resp=api.export_csv(); csv_body=asyncio.run((lambda response: _body(response))(csv_resp)) if False else None
    async def body(resp):
      parts=[]
      async for part in resp.body_iterator: parts.append(part if isinstance(part,bytes) else str(part).encode())
      return b''.join(parts)
    csv_body=asyncio.run(body(api.export_csv())); csv_rows=max(0,sum(1 for _ in csv.reader(io.StringIO(csv_body.decode('utf-8-sig'))))-1)
    xresp=api.export_xlsx(); from openpyxl import load_workbook
    wb=load_workbook(io.BytesIO(xresp.body),read_only=True,data_only=True); xsheet=wb['الفرص الاستثمارية']; xlsx_rows=max(0,xsheet.max_row-6); wb.close()
    sync_total=db.scalar(select(func.count(SyncJob.id))) or 0; sync_max=db.scalar(select(func.max(SyncJob.id))) or 0
    jobs=db.execute(select(SyncJob,Source.source_key).join(Source,Source.id==SyncJob.source_id).order_by(SyncJob.id.desc()).limit(5)).all()
    recent_jobs=[{'job_id':j.id,'source':src,'status':j.status,'trigger':j.trigger_type,'started_at':iso(j.started_at),'finished_at':iso(j.finished_at),'masters_delta':j.new_count+j.update_count,'new':j.new_count,'updated':j.update_count,'unchanged':j.unchanged_count,'removed':j.removed_records_count,'observations_delta':None,'reviews_delta':None} for j,src in jobs]
    master112=db.get(Opportunity,112)
    master112_sources=db.execute(select(Source.source_key,SourceOpportunity.id,SourceOpportunity.source_opportunity_id).join(SourceOpportunity,SourceOpportunity.source_id==Source.id).where(SourceOpportunity.master_opportunity_id==112).order_by(SourceOpportunity.id)).all() if master112 else []
    tie_count=db.scalar(select(func.count(Opportunity.id)).where(Opportunity.last_updated_at==master112.last_updated_at,Opportunity.merged_into_id.is_(None))) if master112 else 0
    print(json.dumps({'captured_at':now.isoformat(),'read_only':True,'counts':counts,'review_counts_by_status':review_counts,'reviews':{'total':total_reviews,'open':open_reviews,'superseded':superseded,'resolved':total_reviews-open_reviews-superseded},'review_audit_boundary':iso(boundary),'original_unlinked_resolved_records':{'count':len(all_original),'classifications':dict(Counter(x['classification'] for x in all_original)),'records':all_original},'current_missing_human_decisions':current_missing,'invalid_action_events':invalid,'excluded_lifecycle_action_events':ignored_lifecycle,'dq':{'total':dq['gates_evaluated'],'counts':dq['counts'],'gates':relevant,'all_gates':dq['gates']},'list':{'total':api_total,'rows':len(ids),'unique_ids':len(set(ids)),'duplicates':dupe_ids,'missing_db_ids':sorted(db_ids-set(ids)),'unexpected_ids':sorted(set(ids)-db_ids),'page_sizes':[len(x) for x in pages],'filters':filter_specs,'csv_rows':csv_rows,'xlsx_rows':xlsx_rows,'original_duplicate_sample_112':{'master_id':112,'title':master112.title_ar if master112 else None,'reference':master112.reference_number if master112 else None,'last_updated_at':iso(master112.last_updated_at) if master112 else None,'same_timestamp_current_masters':tie_count,'source_rows':[{'source':r[0],'source_record_id':r[1],'external_id':r[2]} for r in master112_sources]}},'sync':{'total':sync_total,'max_id':sync_max,'recent_jobs':recent_jobs}},ensure_ascii=False,default=str))

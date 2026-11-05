import sys,json,hashlib
sys.path.insert(0,"/app")
from datetime import datetime,timezone
from collections import defaultdict
from sqlalchemy import select,func
from app.database import SessionLocal
from app.models import Opportunity,SourceOpportunity,Source,SourceObservation,ChangeHistory
from app.standardization import STANDARDIZATION_VERSION

def digest(s): return hashlib.sha256(s.encode()).hexdigest()
with open('/tmp/pre-correction-snapshot.json',encoding='utf-8-sig') as f: before=json.load(f)
with SessionLocal() as db:
 now=db.execute(select(func.now())).scalar()
 masters=db.scalars(select(Opportunity).order_by(Opportunity.id)).all()
 links=db.scalars(select(SourceOpportunity).order_by(SourceOpportunity.id)).all()
 furas=[r for r in links if r.source and r.source.source_key=='furas']
 observations=db.execute(select(func.count(SourceObservation.id),func.max(SourceObservation.id))).one()
 ident=digest('|'.join(f'{m.id}:{m.canonical_id}:{m.merged_into_id}' for m in masters))
 linkhash=digest('|'.join(f'{r.id}:{r.source_id}:{r.master_opportunity_id}:{r.source_opportunity_id}:{r.source_url}' for r in links))
 rawhash=digest('|'.join(f'{r.id}:{digest(json.dumps(r.raw_data_json or {},sort_keys=True,ensure_ascii=False,default=str))}' for r in furas))
 assert ident==before['fingerprints']['master_identity'], 'Master identities changed since baseline'
 assert linkhash==before['fingerprints']['source_links'], 'Source links changed since baseline'
 assert rawhash==before['fingerprints']['furas_raw_payloads'], 'Raw Furas payload changed since baseline'
 assert len(masters)==before['total_master_rows'] and sum(m.merged_into_id is None for m in masters)==before['nonmerged_masters']
 assert len(links)==before['source_opportunities'] and observations[0]==before['observations'] and observations[1]==before['observation_max_id'], 'Database changed since baseline'
 assert len(furas)==177 and len(before['furas_deadline_correction_ids'])==171 and len(before['furas_publication_correction_ids'])==177
 ids_dead=set(before['furas_deadline_correction_ids']); ids_pub=set(before['furas_publication_correction_ids'])
 masters_by_id={m.id:m for m in masters}; source_by_id={r.id:r for r in links}
 # Validate one source record and current unverified raw mapping per correction target.
 for mid in ids_dead:
  m=masters_by_id[mid]; assert m.submission_deadline, f'missing expected deadline on {mid}'
 for mid in ids_pub:
  m=masters_by_id[mid]; assert m.publication_date, f'missing expected publication date on {mid}'
 for row in furas:
  attrs=((row.raw_data_json or {}).get('attributes') or {})
  row.raw_dates={'deadline':None}
  meta=row.standardized_data_json if isinstance(row.standardized_data_json,dict) else {}
  fields=meta.setdefault('fields',{})
  fields['submission_deadline']={'raw':{'STARTDATE':attrs.get('STARTDATE'),'ENDDATE':attrs.get('ENDDATE'),'LASTRFPSELLDATE':attrs.get('LASTRFPSELLDATE'),'LASTBIDATE':attrs.get('LASTBIDATE')},'canonical_id':None,'canonical_label':None,'mapping_status':'UNVERIFIED','rule':'furas_dates_raw_only_v1','review_flags':['UNVERIFIED_DATE_FIELD_SEMANTICS']}
  fields['publication_date']={'raw':attrs.get('STARTDATE'),'canonical_id':None,'canonical_label':None,'mapping_status':'UNVERIFIED','rule':'furas_dates_raw_only_v1','review_flags':['UNVERIFIED_DATE_FIELD_SEMANTICS']}
  row.standardized_data_json=meta; row.standardization_version=STANDARDIZATION_VERSION
 for mid in ids_dead: masters_by_id[mid].submission_deadline=None
 for mid in ids_pub: masters_by_id[mid].publication_date=None
 # Data-level safeguards: no Furas-only canonical dates remain and all protected links/state stay intact.
 db.flush()
 assert sum(bool(m.submission_deadline) for m in masters if m.merged_into_id is None)==before['deadlines_populated']-len(ids_dead)
 assert sum(bool(m.publication_date) for m in masters if m.merged_into_id is None)==before['publication_populated']-len(ids_pub)
 assert all((r.raw_dates or {}).get('deadline') is None for r in furas)
 assert all(r.standardization_version==STANDARDIZATION_VERSION for r in furas)
 # Keep all changes in this single transaction; no status, identity, source link, payload, or observation writes.
 db.commit()
 print(json.dumps({'status':'COMMITTED','snapshot_utc':now.isoformat(),'version':STANDARDIZATION_VERSION,'deadline_corrections':len(ids_dead),'publication_corrections':len(ids_pub),'furas_projection_rows_updated':len(furas),'deadline_populated_after':sum(bool(m.submission_deadline) for m in masters if m.merged_into_id is None),'publication_populated_after':sum(bool(m.publication_date) for m in masters if m.merged_into_id is None),'masters':len(masters),'nonmerged':sum(m.merged_into_id is None for m in masters),'source_links':len(links),'observations':observations[0],'observation_max_id':observations[1],'identity_fingerprint_preserved':ident==before['fingerprints']['master_identity'],'source_link_fingerprint_preserved':linkhash==before['fingerprints']['source_links'],'raw_payload_fingerprint_preserved':rawhash==before['fingerprints']['furas_raw_payloads']},ensure_ascii=False))

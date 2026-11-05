import json,difflib
from types import SimpleNamespace
from sqlalchemy import select,func
from sqlalchemy.orm import joinedload
from app.database import SessionLocal
from app.models import Opportunity,Source,SourceOpportunity
from app.entity_resolution import compare_source_records
from app.normalization import normalize_arabic
snapshot=json.load(open('/tmp/rcjy_live_snapshot.json',encoding='utf-8'))
keys={'furas','modon','invest-saudi','ncp','nhc','pif','mwan'}
with SessionLocal() as db:
 all_rows=db.scalars(select(SourceOpportunity).options(joinedload(SourceOpportunity.source))).all()
 target_rows=[r for r in all_rows if r.source and r.source.source_key in keys]
 masters=db.scalars(select(Opportunity).where(Opportunity.merged_into_id.is_(None))).all()
 result={'current_master_count':len(masters),'current_source_opportunity_count':len(all_rows)-sum(1 for r in all_rows if r.source and r.source.source_key=='rcjy-investment-opportunities'),'cross_source_record_counts':{k:sum(1 for r in target_rows if r.source.source_key==k) for k in sorted(keys)},'records':[]}
 for r in snapshot['records']:
  incoming=SimpleNamespace(source=SimpleNamespace(source_key='rcjy-investment-opportunities'),source_opportunity_id=r['external_id'],source_reference_number=None,source_title=r['title'],raw_location=r['location'],raw_area=None,raw_dates={},raw_status=r['status'],raw_data_json=r['raw'],source_url=r['raw']['source_url'],source_owner=None)
  needle=normalize_arabic(r['title']); strong=[]; nearest=[]
  for other in target_rows:
   title_similarity=difflib.SequenceMatcher(None,needle,normalize_arabic(other.source_title or '')).ratio()
   if title_similarity < .38: continue
   c=compare_source_records(incoming,other)
   evidence={'source_key':other.source.source_key,'provider_id':other.source_opportunity_id,'title':other.source_title,'location':other.raw_location,'master_id':other.master_opportunity_id,'title_similarity':c['title_similarity'],'score':c['current_duplicate_score'],'exact_reference_match':c['exact_identifier_match'],'trusted_reference_match':c['trusted_official_reference_match'],'plot_match':c['plot_match'],'plan_match':c['plan_match'],'auto_merge_safe':c['auto_merge_safe'],'positive_evidence':c['positive_evidence'],'contradictions':c['contradicting_evidence']}
   if c['exact_identifier_match'] or c['trusted_official_reference_match'] or c['plot_match'] or c['plan_match'] or c['auto_merge_safe'] or c['current_duplicate_score']>=.75:
    strong.append(evidence)
   elif c['title_similarity']>=.50:
    nearest.append(evidence)
  nearest.sort(key=lambda x:(x['title_similarity'],x['score']),reverse=True)
  result['records'].append({'provider_id':r['external_id'],'strong_matches':strong,'title_only_or_weak_nearest':nearest[:5]})
 print(json.dumps(result,ensure_ascii=False))

import json,hashlib
from pathlib import Path
b=json.loads(Path('/tmp/master_identity_snapshot_start.json').read_text(encoding='utf8'))
pairs=[(155,156),(155,159),(156,159),(157,160),(158,161),(163,254),(197,198),(263,264)]
masters={x['id']:x for x in b['masters']}; sources={x['id']:x for x in b['sources']}; bym={}
for r in b['source_opportunities']:
 if r.get('master_opportunity_id') is not None:bym.setdefault(r['master_opportunity_id'],[]).append(r)
for a,c in pairs:
 ra=bym[a][0];rc=bym[c][0]
 def summary(r):
  raw=r.get('raw_data_json') or {}
  return {'record_id':r['id'],'master_id':r['master_opportunity_id'],'external_id':r['source_opportunity_id'],'reference':r.get('source_reference_number'),'title':r['source_title'],'url':r['source_url'],'owner':r.get('source_owner'),'location':r.get('raw_location'),'area':r.get('raw_area'),'status':r.get('raw_status'),'first_seen':r.get('first_seen_at'),'last_seen':r.get('last_seen_at'),'hash':r.get('content_hash'),'payload_keys':sorted(raw.keys()),'payload':raw}
 print(json.dumps({'pair':[a,c],'master_a':{'id':a,'created':masters[a]['created_at'],'merged_into':masters[a]['merged_into_id']},'master_b':{'id':c,'created':masters[c]['created_at'],'merged_into':masters[c]['merged_into_id']},'a':summary(ra),'b':summary(rc)},ensure_ascii=False,separators=(',',':')))

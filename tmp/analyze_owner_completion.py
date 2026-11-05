import json,re
from collections import Counter,defaultdict
from pathlib import Path
p=Path('/tmp/owner-completion-targets.jsonl')
rows=[json.loads(x) for x in p.read_text(encoding='utf-8-sig').splitlines() if x.strip()]
key_rx=re.compile(r'(owner|agency|entit|organi[sz]|responsible|issuing|grantor|authority|municipality|ministry|company|institution|developer|project.?owner|investment.?entity|department|issuer|backed.?by|المالك|الجهة|المسؤول|المسؤولة|وزارة|أمانة|بلدية|هيئة|شركة|جامعة|صندوق|جهة|منشئ)',re.I)
text_rx=re.compile(r'(owner|owned by|responsible (?:entity|authority)|project owner|grantor|issuer|issued by|managed by|operated by|طرح(?:ت|تـ)?\s+(?:ال)?(?:أمانة|وزارة|هيئة|شركة)|الجهة (?:المالكة|المسؤولة|المختصة)|صاحب المشروع|تطرح|تعلن|تقديم من قبل|وزارة|أمانة|هيئة|بلدية|جامعة|شركة|صندوق)',re.I)
def walk(obj,path=''):
 if isinstance(obj,dict):
  for k,v in obj.items():
   q=f'{path}.{k}' if path else k
   if key_rx.search(k): yield q,v
   yield from walk(v,q)
 elif isinstance(obj,list):
  for i,v in enumerate(obj): yield from walk(v,f'{path}[{i}]')
source_counts=Counter(); master_ids=defaultdict(list); source_keys=defaultdict(Counter); top_keys=defaultdict(Counter); field_rows=[]
for m in rows:
 for s in m.get('sources') or []:
  sk=s['source_key'];source_counts[sk]+=1;master_ids[sk].append(m['master_id'])
  raw=s.get('raw_data_json') or {};top_keys[sk].update(raw.keys())
  owner_fields=[]
  for path,val in walk(raw):
   owner_fields.append({'path':path,'value':val})
  text_matches=[]
  for key in ['source_title','title','description','raw_text','extracted_description','full_description','short_description']:
   val=raw.get(key) if key in raw else (s.get(key) if key in s else (m.get(key) if key in m else None))
   if isinstance(val,str):
    for mt in text_rx.finditer(val):
     text_matches.append({'field':key,'snippet':val[max(0,mt.start()-90):min(len(val),mt.end()+180)].replace('\n',' ')})
  field_rows.append({'master_id':m['master_id'],'canonical_id':m['canonical_id'],'title':m['title'],'source_record_id':s['source_record_id'],'source_key':sk,'source_name':s['source_name'],'source_owner_projection_not_evidence':s.get('source_owner'),'raw_top_level_keys':list(raw.keys()),'raw_owner_like_fields':owner_fields,'owner_role_text_snippets':text_matches,'platform':m.get('platform'),'source_url':s.get('source_url')})
print(json.dumps({'target_count':len(rows),'source_record_count':sum(source_counts.values()),'source_distribution':{k:{'records':source_counts[k],'masters':master_ids[k]} for k in sorted(source_counts)},'raw_top_level_key_counts':{k:dict(sorted(c.items())) for k,c in sorted(top_keys.items())}},ensure_ascii=False))
Path('/tmp/owner-completion-field-findings.jsonl').write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in field_rows),encoding='utf-8')

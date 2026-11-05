import json,re,unicodedata,difflib
from pathlib import Path
portal=json.loads(Path('/tmp/ncp-portal-basic.json').read_text(encoding='utf-8-sig'))
base=json.loads(Path('/tmp/ncp-all-source-evidence.json').read_text(encoding='utf-8-sig'))
rows=[r for r in base['ncp_source_rows'] if r['source_key']=='ncp']
stop=set('project opportunity privatization privatise privatized privatization and the of for in at from with development develop operation operating launch launching phase request expression interest eoi rfq rfp announcement ncp ppp authority center national'.split())
def norm(s):
 s=(s or '').casefold();s=''.join(c for c in unicodedata.normalize('NFKD',s) if not unicodedata.combining(c));toks=re.findall(r'[a-z0-9]{3,}|[\u0600-\u06ff]{3,}',s);return [t for t in toks if t not in stop]
def sim(a,b):
 aa=' '.join(norm(a));bb=' '.join(norm(b));return difflib.SequenceMatcher(None,aa,bb).ratio(),len(set(norm(a))&set(norm(b)))/max(1,len(set(norm(a))|set(norm(b))))
results=[]
for p in portal:
 cand=[]
 for r in rows:
  vals=[sim(p['title_en'],r['title']),sim(p['title_ar'],r['title']),sim(p['title_en'],r.get('master_title_en')),sim(p['title_ar'],r.get('master_title_ar'))]
  s,j=max(vals,key=lambda x:x[0]+x[1])
  if s>=.25 or j>=.15:cand.append({'id':r['id'],'external_id':r['external_id'],'master_id':r['master_id'],'title':r['title'],'url':r['url'],'location':r['location'],'stage':r['stage'],'s':round(s,3),'j':round(j,3),'description':r['description'][:700]})
 cand.sort(key=lambda x:(x['s'],x['j']),reverse=True)
 results.append({'provider_id':p['provider_id'],'title_en':p['title_en'],'title_ar':p['title_ar'],'location_en':p['location_en'],'sector_en':p['sector_en'],'stage_en':p['sub_stage_en'],'candidates':cand[:5]})
print('portal',len(portal),'NCP rows',len(rows),'candidate portal rows',sum(bool(x['candidates']) for x in results),'candidate pairs',sum(len(x['candidates']) for x in results))
for x in sorted(results,key=lambda x:x['candidates'][0]['s'] if x['candidates'] else 0,reverse=True)[:40]:
 if x['candidates']:
  c=x['candidates'][0];print(x['provider_id'],x['title_en'][:72],'->',c['id'],c['title'][:96],c['s'],c['j'],c['location'])
Path('/tmp/ncp-ncp-title-candidates.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')

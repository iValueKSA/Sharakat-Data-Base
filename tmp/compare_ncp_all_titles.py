import json,re,unicodedata,difflib,collections
from pathlib import Path
portal=json.loads(Path('/tmp/ncp-portal-basic.json').read_text(encoding='utf-8-sig'))
base=json.loads(Path('/tmp/ncp-all-source-evidence.json').read_text(encoding='utf-8-sig'))
rows=base['ncp_source_rows']
stop=set('project opportunity privatization privatise privatized development develop operation operating launch launching phase request expression interest eoi rfq rfp announcement ncp ppp authority national and the of for in at from with'.split())
def tok(s):
 s=(s or '').casefold();s=''.join(c for c in unicodedata.normalize('NFKD',s) if not unicodedata.combining(c));return set(t for t in re.findall(r'[a-z0-9]{3,}|[\u0600-\u06ff]{3,}',s) if t not in stop)
def sim(a,b):
 aa=' '.join(sorted(tok(a)));bb=' '.join(sorted(tok(b)));return difflib.SequenceMatcher(None,aa,bb).ratio(),len(tok(a)&tok(b))/max(1,len(tok(a)|tok(b)))
post=collections.defaultdict(set)
for i,r in enumerate(rows):
 for t in tok(r['title'])|tok(r.get('master_title_ar'))|tok(r.get('master_title_en')):post[t].add(i)
results=[]
for p in portal:
 pt=tok(p.get('title_en'))|tok(p.get('title_ar'))
 inds=set().union(*(post[t] for t in pt if t in post)) if pt else set()
 cand=[]
 for i in inds:
  r=rows[i]
  opts=[sim(p.get('title_en'),r.get('title')),sim(p.get('title_ar'),r.get('title')),sim(p.get('title_en'),r.get('master_title_en')),sim(p.get('title_ar'),r.get('master_title_ar'))]
  s,j=max(opts,key=lambda x:x[0]+x[1])
  # retain candidate evidence only at meaningful shared project naming
  if (s>=.43 and j>=.25) or (j>=.45 and len(pt)>=3):
   cand.append({'source_key':r['source_key'],'source_opportunity_id':r['id'],'external_id':r['external_id'],'master_id':r['master_id'],'title':r['title'],'master_title_en':r['master_title_en'],'url':r['url'],'owner':r['owner'],'location':r['location'],'sector':r['sector'],'stage':r['stage'],'sequence_ratio':round(s,3),'token_jaccard':round(j,3),'description':r['description'][:600]})
 cand.sort(key=lambda x:(x['token_jaccard'],x['sequence_ratio']),reverse=True)
 results.append({'provider_id':p['provider_id'],'title_en':p['title_en'],'title_ar':p['title_ar'],'location_en':p['location_en'],'sector_en':p['sector_en'],'sub_stage_en':p['sub_stage_en'],'candidate_count':len(cand),'candidates':cand[:10]})
Path('/tmp/ncp-all-candidates.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
print('portal items',len(portal),'all-source candidate portal records',sum(bool(x['candidate_count']) for x in results),'candidate pairs',sum(x['candidate_count'] for x in results))
for x in sorted(results,key=lambda x:x['candidates'][0]['token_jaccard'] if x['candidate_count'] else 0,reverse=True)[:60]:
 if x['candidate_count']:
  c=x['candidates'][0]; print(x['provider_id'],x['title_en'][:69],'->',c['source_key'],c['source_opportunity_id'],(c.get('master_id')),c['title'][:80],c['token_jaccard'],c['sequence_ratio'])

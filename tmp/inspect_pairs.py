import json
p='docs/validation/data/master-identity-duplicate-matching/'
d=json.load(open(p+'snapshot-pre-correction-live.json',encoding='utf-8'))
ms={m['id']:m for m in d['masters']}
ss={s['id']:s for s in d['sources']}
links={}
for x in d['source_opportunities']:
    if x.get('master_opportunity_id'):
        links.setdefault(x['master_opportunity_id'],[]).append(x)
a=json.load(open(p+'identity-analysis-pre.json',encoding='utf-8'))
xs=[x for x in a['candidate_pairs'] if any(e.get('same_source') is False for e in x.get('evidence',[]))]
for x in xs:
    if x['master_a'] in [107,193,234,235,237,238,239,240,241,242,246,253,255] or x['master_b'] in [186,187,194,236,238,252,255,247,243,244,269,270,261,276]:
        print('PAIR',x['master_a'],x['master_b'])
        for mid in (x['master_a'],x['master_b']):
            m=ms[mid]
            print('M',mid,'title=',m.get('title_ar'),'owner=',m.get('opportunity_owner'),'area=',m.get('land_area_sqm'),'loc=',m.get('location_description'),'plot=',m.get('plot_number'),'ref=',m.get('reference_number'))
            for z in links.get(mid,[]):
                print(' S',z['id'],ss.get(z['source_id'],{}).get('name'),z.get('source_opportunity_id'),'ref=',z.get('source_reference_number'),'owner=',z.get('source_owner'),'area=',z.get('raw_area'),'title=',z.get('source_title'),'url=',z.get('source_url'))

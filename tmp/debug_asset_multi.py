import csv,io,json,httpx
c=httpx.Client(base_url='http://frontend:8080'); allr=c.get('/api/opportunities?limit=500').json(); multis=[r for r in allr['items'] if len(r.get('asset_facility_types',[]))>1]; out=[]
for r in multis:
 identity=r['asset_facility_types'][0]['id']; res=c.get('/api/export.csv',params={'asset_facility_type':identity}); print('http',res.status_code); rows=list(csv.DictReader(io.StringIO(res.content.decode('utf-8-sig')))) if res.status_code==200 else []; found=[x for x in rows if r['title'] in x.get('اسم الفرصة','')]; out.append({'id':r['id'],'title':r['title'],'labels':r['asset_facility_types'],'count':len(found),'matches':found[:3]})
print(json.dumps(out,ensure_ascii=False,indent=2))
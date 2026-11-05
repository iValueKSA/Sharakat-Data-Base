import asyncio,json,hashlib
from pathlib import Path
import httpx
items=json.loads(Path('/tmp/ncp-portal-basic.json').read_text(encoding='utf-8-sig'))
base='https://investors.ncp.gov.sa/api/v1/projects/'
sem=asyncio.Semaphore(8)
headers={'Accept':'application/json','Referer':'https://investors.ncp.gov.sa/projects'}
async def one(client,item):
 async with sem:
  r=await client.get(base+item['provider_id'],headers=headers)
  r.raise_for_status();p=r.json()
  if not p.get('success') or not isinstance(p.get('data'),dict):raise RuntimeError('unexpected detail response '+item['provider_id'])
  d=p['data'];clean={}
  for k,v in d.items():
   if k in ('projectBackground','stageBackground','sectorLogo') and isinstance(v,str):
    clean[k+'_sha256']=hashlib.sha256(v.encode()).hexdigest();clean[k+'_base64_length']=len(v)
   else:clean[k]=v
  return item['provider_id'],clean,len(r.content)
async def main():
 timeout=httpx.Timeout(60,connect=15)
 async with httpx.AsyncClient(timeout=timeout,follow_redirects=True) as client:
  out=await asyncio.gather(*(one(client,i) for i in items),return_exceptions=True)
 details={};errs=[];total=0
 for x in out:
  if isinstance(x,Exception):errs.append(str(x));continue
  ident,d,n=x;details[ident]=d;total+=n
 Path('/tmp/ncp-portal-detail-metadata.json').write_text(json.dumps(details,ensure_ascii=False),encoding='utf-8')
 print(json.dumps({'requested':len(items),'received':len(details),'errors':errs[:10],'bytes_received':total,'metadata_output_bytes':Path('/tmp/ncp-portal-detail-metadata.json').stat().st_size}))
 print('closed counts',json.dumps({str(k):v for k,v in __import__('collections').Counter(str(d.get('isClosed')) for d in details.values()).items()}))
 print('attachments rows',sum(bool(d.get('projectAttachments')) for d in details.values()),'attachment total',sum(len(d.get('projectAttachments') or []) for d in details.values()))
asyncio.run(main())

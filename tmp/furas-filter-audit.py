import asyncio,json,ssl,httpx,sys
from datetime import date
URL='https://gisapps.balady.gov.sa/opportunities/assets/config.json'
CITIES=('1949','1945','1950','005011001','9','1264','1315','1299','1298','104','005020001')
async def main():
 async with httpx.AsyncClient(timeout=httpx.Timeout(25,connect=12),verify=ssl.create_default_context(),follow_redirects=True) as c:
  cfg=(await c.get(URL)).json();layer=cfg['gisLayerUrl']['investmentMapServerInvestmentP']+'/'+str(cfg['gisLayerIndex']['investmentMapServerInvestmentP'])
  base="CITY_ID IN ("+','.join("'"+x+"'" for x in CITIES)+") AND LASTRFPSELLDATE >= DATE '"+date.today().isoformat()+"' AND OPPORTUNITYACTIVESTATUS='Announced'"
  clauses={'accepted_current':base+' AND QualifyingOpportunity=0','with_qualifying':base,'qualification_required':base+' AND QualifyingOpportunity=1','no_deadline_filter':"CITY_ID IN ("+','.join("'"+x+"'" for x in CITIES)+") AND OPPORTUNITYACTIVESTATUS='Announced' AND QualifyingOpportunity=0",'city_only_all_lifecycle':"CITY_ID IN ("+','.join("'"+x+"'" for x in CITIES)+")"}
  out={'layer':layer,'date':date.today().isoformat(),'counts':{},'fields':[]}
  for name,where in clauses.items():
   p={'f':'json','where':where,'returnCountOnly':'true'};r=await c.get(layer+'/query',params=p);r.raise_for_status();j=r.json();out['counts'][name]={'http':r.status_code,'count':j.get('count'),'where':where,'error':j.get('error')}
  f=await c.get(layer,params={'f':'json'});f.raise_for_status();out['fields']=[{'name':x.get('name'),'alias':x.get('alias'),'type':x.get('type')} for x in f.json().get('fields',[]) if 'QualifyingOpportunity' in x.get('name','') or 'QualifyingOpportunity' in x.get('alias','') or 'RFPSELL' in x.get('name','') or 'ACTIVE' in x.get('name','')]
  print(json.dumps(out,ensure_ascii=False,separators=(',',':')))
asyncio.run(main())

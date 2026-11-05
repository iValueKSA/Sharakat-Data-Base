import httpx,re,json,time
from urllib.parse import urljoin
base='https://invest.rcjy.gov.sa/InvestmentPortal/'
with httpx.Client(follow_redirects=True,timeout=30) as c:
 r=c.get(urljoin(base,'InvestmentOpportunities')); print('page',r.status_code,list(c.cookies.keys()))
 m=re.search(r'OSManifestLoader.indexVersionToken\s*=\s*"([^"]+)"',r.text); print('index_token',bool(m))
 v=c.get(urljoin(base,'moduleservices/moduleversioninfo?'+str(int(time.time()*1000)))); print('version_response',v.status_code,v.text[:300]); version=v.json().get('versionToken')
 body={'versionInfo':{'moduleVersion':version,'apiVersion':'2J20VkfrAS52NRQeFOwQxg'},'viewName':'MainFlow.InvestmentOpportunities','screenData':{'variables':{'SectorId':0,'SubSectorId':0,'StartIndex':0,'MaxRecords':12,'TableSort':'InvestmentOpportunity.Id DESC','IsOpenSidebar':False,'IsInvestor':False,'InvesmentOpportunityListFilter':'','IsOpenSidebarMobile':False,'CityId':0,'_cityIdInDataFetchStatus':1}},'inputParameters':{'StartIndex':0,'MaxRecords':12}}
 h={'outsystems-locale':'en-US','referer':str(r.url),'accept':'application/json','content-type':'application/json; charset=UTF-8','user-agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130 Safari/537.36','outsystems-request-token':str(int(time.time()*1000))}
 x=c.post(urljoin(base,'screenservices/InvestmentPortal/MainFlow/InvestmentOpportunities/ScreenDataSetGetInvestmentOpportunitiesBySearchConditions'),json=body,headers=h); print('api',x.status_code,x.text[:500]);


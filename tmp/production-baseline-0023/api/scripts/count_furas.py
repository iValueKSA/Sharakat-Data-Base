import httpx, time
config=httpx.get("https://gisapps.balady.gov.sa/opportunities/assets/config.json",timeout=15).json()
layer=config["gisLayerUrl"]["investmentMapServerInvestmentP"]+"/"+str(config["gisLayerIndex"]["investmentMapServerInvestmentP"])
city_ids=("1949","1945","1950","005011001","9","1264","1315","1299","1298","104","005020001")
where="CITY_ID IN ("+",".join("'"+x+"'" for x in city_ids)+")"
url="https://gisapps.balady.gov.sa/opportunities/proxy/proxy.ashx?"+layer+"/query?"+str(httpx.QueryParams({"f":"json","where":where,"returnIdsOnly":"true"}))
start=time.time();response=httpx.get(url,timeout=20);payload=response.json()
print("status",response.status_code,"seconds",round(time.time()-start,2),"id_count",len(payload.get("objectIds",[])),"error",payload.get("error"))
ids=payload.get("objectIds",[])[:100]
params={"f":"json","where":"OBJECTID IN ("+",".join(map(str,ids))+")","outFields":"OPPORTUNITYID,OPPORTUNITYDESCRIPTION,CITY_ID,CITYNAME,TOTALSPACEINMETERS","returnGeometry":"false","orderByFields":"OBJECTID"}
start=time.time();response=httpx.get("https://gisapps.balady.gov.sa/opportunities/proxy/proxy.ashx?"+layer+"/query?"+str(httpx.QueryParams(params)),timeout=20)
print("batch status",response.status_code,"seconds",round(time.time()-start,2),"bytes",len(response.text),"body",response.text[:250])
from datetime import date
for sql in (f"{where} AND LASTRFPSELLDATE >= DATE '{date.today().isoformat()}'",f"{where} AND (LASTRFPSELLDATE IS NULL OR LASTRFPSELLDATE >= DATE '{date.today().isoformat()}')"):
    url="https://gisapps.balady.gov.sa/opportunities/proxy/proxy.ashx?"+layer+"/query?"+str(httpx.QueryParams({"f":"json","where":sql,"returnCountOnly":"true"}))
    start=time.time();r=httpx.get(url,timeout=20);print("count filter",sql,"status",r.status_code,"seconds",round(time.time()-start,2),r.text[:200])

"""Print small code excerpts used during Furas endpoint research."""
import httpx

script = httpx.get("https://gisapps.balady.gov.sa/opportunities/main.js", timeout=20).text
for key in ("init_PAGINATION", "PAGE_SIZE=", "FeatureServer", "OPPORTUNITYID =", "drupalDetailPage:", "ph=", "ph =", "var ph", "api:"):
    pos = script.find(key)
    print(f"\n--- {key!r} at {pos} ---")
    if pos >= 0:
        print(script[max(0, pos - 350):pos + 2200])

config=httpx.get("https://gisapps.balady.gov.sa/opportunities/assets/config.json",timeout=20).json()
layer=config["gisLayerUrl"]["investmentMapServerInvestmentP"]+"/"+str(config["gisLayerIndex"]["investmentMapServerInvestmentP"])
proxy="https://gisapps.balady.gov.sa/opportunities/proxy/proxy.ashx?"+layer+"?f=json"
metadata=httpx.get(proxy,timeout=20).json()
print("\n--- Public Furas investment layer ---")
print("service layer:",layer)
print("record limit:",metadata.get("maxRecordCount"))
print("fields:",[(field.get("name"),field.get("alias"),field.get("type")) for field in metadata.get("fields",[])])
print("supports pagination:",metadata.get("advancedQueryCapabilities"))
for expression,fields in (("CITYNAME LIKE '%الاحساء%'","CITY_ID,CITYNAME"),("1=1","CITY_ID,CITYNAME")):
    target=layer+"/query?f=json&where="+httpx.QueryParams({"where":expression})["where"]+"&outFields="+fields+"&returnGeometry=false&returnDistinctValues=true&returnExceededLimitFeatures=true"
    payload=httpx.get("https://gisapps.balady.gov.sa/opportunities/proxy/proxy.ashx?"+target,timeout=30).json()
    print("query:",expression,"error:",payload.get("error"),"values:",[(feature.get("attributes",{}).get("CITY_ID"),feature.get("attributes",{}).get("CITYNAME")) for feature in payload.get("features",[])[:100]])
target=layer+"/query?"+str(httpx.QueryParams({"f":"json","where":"CITY_ID = '1949'","outFields":"*","returnGeometry":"true","resultRecordCount":"5","orderByFields":"LASTRFPSELLDATE DESC"}))
payload=httpx.get("https://gisapps.balady.gov.sa/opportunities/proxy/proxy.ashx?"+target,timeout=30).json()
print("\n--- Sample Al-Ahsa CITY_ID=1949 records ---")
print("error:",payload.get("error"),"features:",len(payload.get("features",[])))
for feature in payload.get("features",[]): print(feature.get("attributes"),feature.get("geometry"))
for expression in ("OPPORTUNITYID = '06-26-189921-64005'","CITY_ID = '1949' AND LASTRFPSELLDATE >= CURRENT_TIMESTAMP"):
    target=layer+"/query?"+str(httpx.QueryParams({"f":"json","where":expression,"outFields":"*","returnGeometry":"true","returnCountOnly":"true"}))
    payload=httpx.get("https://gisapps.balady.gov.sa/opportunities/proxy/proxy.ashx?"+target,timeout=30).json()
    print("where:",expression,"count:",payload.get("count"),"error:",payload.get("error"))
target=layer+"/query?"+str(httpx.QueryParams({"f":"json","where":"OPPORTUNITYID = '06-26-189921-64005'","outFields":"*","returnGeometry":"true"}))
payload=httpx.get("https://gisapps.balady.gov.sa/opportunities/proxy/proxy.ashx?"+target,timeout=30).json()
print("\n--- User-specified Furas record ---")
for feature in payload.get("features",[]):print(feature.get("attributes"),feature.get("geometry"))
localities=("الاحساء","الأحساء","العيون","العمران","الجفر","العقير","سلوى","الهفوف","المبرز","جواثا","الغوار","عريعرة")
where=" OR ".join([f"CITYNAME LIKE '%{name}%'" for name in localities])
target=layer+"/query?"+str(httpx.QueryParams({"f":"json","where":where,"outFields":"CITY_ID,CITYNAME","returnGeometry":"false","returnDistinctValues":"true","returnExceededLimitFeatures":"true"}))
payload=httpx.get("https://gisapps.balady.gov.sa/opportunities/proxy/proxy.ashx?"+target,timeout=30).json()
print("\n--- Confirmed local city names and IDs ---")
print([(f.get("attributes",{}).get("CITY_ID"),f.get("attributes",{}).get("CITYNAME")) for f in payload.get("features",[])])

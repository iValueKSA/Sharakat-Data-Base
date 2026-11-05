import csv, io, json
from datetime import datetime, timezone
import httpx
from openpyxl import load_workbook
BASE="http://frontend:8080"
report={"validated_at_utc":datetime.now(timezone.utc).isoformat(),"base_url":BASE,"investment_models":{},"opportunity_types":{},"sub_activity_general_trade":{},"asset_multi_value":{}}
def get(client,path,params=None):
 r=client.get(path,params=params); r.raise_for_status(); return r
with httpx.Client(base_url=BASE,timeout=45) as c:
 filters=get(c,"/api/filters").json(); dash=get(c,"/api/data-dashboard").json()
 assert dash["global_total"]==291
 expected_models={"investment_model:lease":("التأجير",4),"investment_model:eomt":("التجهيز والتشغيل والصيانة والنقل",1),"investment_model:missing":("غير محدد",286)}
 md={r["canonical_id"]:r["count"] for r in dash["by_investment_model"]}
 for identity,(label,count) in expected_models.items():
  assert filters["option_ids"]["investment_models"][label]==identity and filters["option_counts"]["investment_models"][label]==count
  listing=get(c,"/api/opportunities",{"investment_model":identity,"limit":500}).json(); filtered=get(c,"/api/data-dashboard",{"investment_model":identity}).json()
  csvrows=list(csv.DictReader(io.StringIO(get(c,"/api/export.csv",{"investment_model":identity}).content.decode("utf-8-sig"))))
  wb=load_workbook(io.BytesIO(get(c,"/api/export.xlsx",{"investment_model":identity}).content),read_only=True,data_only=True); sh=wb["الفرص الاستثمارية"]; headers=[x.value for x in next(sh.iter_rows(min_row=6,max_row=6))]; rows=list(sh.iter_rows(min_row=7,values_only=True)); col=headers.index("نموذج الاستثمار"); wb.close()
  assert listing["total"]==filtered["kpis"]["total"]==count and len(listing["items"])==len(csvrows)==len(rows)==count
  assert all(x["investment_model"]==label for x in listing["items"]) and all(x["نموذج الاستثمار"]==label for x in csvrows) and all(x[col]==label for x in rows)
  assert md[identity]==count
  report["investment_models"][identity]={"label":label,"filter":filters["option_counts"]["investment_models"][label],"list":listing["total"],"dashboard":filtered["kpis"]["total"],"csv":len(csvrows),"xlsx":len(rows)}
 assert sum(md.values())==291
 expected_types={"opportunity_type:temporary_rental":("تأجير مؤقت",129),"opportunity_type:missing":("غير محدد",162)}
 for identity,(label,count) in expected_types.items():
  assert filters["option_ids"]["types"][label]==identity and filters["option_counts"]["types"][label]==count
  listing=get(c,"/api/opportunities",{"opportunity_type":identity,"limit":500}).json()
  csvrows=list(csv.DictReader(io.StringIO(get(c,"/api/export.csv",{"opportunity_type":identity}).content.decode("utf-8-sig"))))
  wb=load_workbook(io.BytesIO(get(c,"/api/export.xlsx",{"opportunity_type":identity}).content),read_only=True,data_only=True); sh=wb["الفرص الاستثمارية"]; headers=[x.value for x in next(sh.iter_rows(min_row=6,max_row=6))]; rows=list(sh.iter_rows(min_row=7,values_only=True)); col=headers.index("نوع الفرصة"); wb.close()
  assert listing["total"]==len(csvrows)==len(rows)==count and all(x["نوع الفرصة"]==label for x in csvrows) and all(x[col]==label for x in rows)
  report["opportunity_types"][identity]={"label":label,"list":listing["total"],"csv":len(csvrows),"xlsx":len(rows)}
 trade_id=filters["option_ids"]["sub_activities"]["أنشطة التجارة العامة"]
 trade=get(c,"/api/opportunities",{"sub_activity":trade_id,"limit":500}).json(); csvrows=list(csv.DictReader(io.StringIO(get(c,"/api/export.csv",{"sub_activity":trade_id}).content.decode("utf-8-sig"))))
 wb=load_workbook(io.BytesIO(get(c,"/api/export.xlsx",{"sub_activity":trade_id}).content),read_only=True,data_only=True); sh=wb["الفرص الاستثمارية"]; headers=[x.value for x in next(sh.iter_rows(min_row=6,max_row=6))]; rows=list(sh.iter_rows(min_row=7,values_only=True)); col=headers.index("النشاط الفرعي"); wb.close()
 assert trade["total"]==len(csvrows)==len(rows)==8 and all(x["النشاط الفرعي"]=="أنشطة التجارة العامة" for x in csvrows) and all(x[col]=="أنشطة التجارة العامة" for x in rows)
 report["sub_activity_general_trade"]={"id":trade_id,"list":trade["total"],"csv":len(csvrows),"xlsx":len(rows)}
 allrows=get(c,"/api/opportunities",{"limit":500}).json(); assert allrows["total"]==291 and len(allrows["items"])==291 and len({x["id"] for x in allrows["items"]})==291
 multi=[row for row in allrows["items"] if len(row.get("asset_facility_types",[]))>1]
 assert len(multi)==2
 asset_rows=[]
 for master in multi:
  labels={x["label"] for x in master["asset_facility_types"]}; assert len(labels)==2
  info={"id":master["id"],"title":master["title"],"reference":master["reference"],"labels":sorted(labels),"filter_results":{},"exports":{}}
  for entry in master["asset_facility_types"]:
   identity=entry["id"]; label=entry["label"]
   listing=get(c,"/api/opportunities",{"asset_facility_type":identity,"limit":500}).json()
   hits=[x for x in listing["items"] if x["id"]==master["id"]]
   assert len(hits)==1
   csvrows=list(csv.DictReader(io.StringIO(get(c,"/api/export.csv",{"asset_facility_type":identity}).content.decode("utf-8-sig"))))
   matching=[x for x in csvrows if x["الرقم المرجعي"]==master["reference"]]
   assert len(matching)==1 and set(matching[0]["نوع الأصل أو الموقع"].split(" | "))==labels
   wb=load_workbook(io.BytesIO(get(c,"/api/export.xlsx",{"asset_facility_type":identity}).content),read_only=True,data_only=True); sh=wb["الفرص الاستثمارية"]; headers=[x.value for x in next(sh.iter_rows(min_row=6,max_row=6))]; rows=list(sh.iter_rows(min_row=7,values_only=True)); ai=headers.index("نوع الأصل أو الموقع"); ti=headers.index("الرقم المرجعي"); matching=[row for row in rows if row[ti]==master["reference"]]; assert len(matching)==1 and set(matching[0][ai].split(" | "))==labels; wb.close()
   info["filter_results"][identity]={"total_unique_masters":listing["total"],"master_occurrences":len(hits)}; info["exports"][identity]={"csv_rows":len(csvrows),"xlsx_rows":len(rows),"multi_type_format":" | ","values_preserved":True}
  asset_rows.append(info)
 report["asset_multi_value"]={"unfiltered_rows":len(allrows["items"]),"unique_master_rows":len({x["id"] for x in allrows["items"]}),"multi_type_master_count":len(multi),"masters":asset_rows,"one_row_per_master":True}
print(json.dumps(report,ensure_ascii=False,indent=2))

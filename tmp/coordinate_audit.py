import sys,json
sys.path.insert(0,"/app")
from sqlalchemy import select,func
from app.database import SessionLocal
from app.models import Opportunity,Source,SourceOpportunity
with SessionLocal() as db:
 f=db.scalar(select(Source).where(Source.source_key=='furas'))
 rows=db.execute(select(SourceOpportunity.id,SourceOpportunity.source_opportunity_id,SourceOpportunity.source_url,SourceOpportunity.raw_data_json,SourceOpportunity.standardized_data_json,Opportunity.id,Opportunity.latitude,Opportunity.longitude).join(Opportunity,Opportunity.id==SourceOpportunity.master_opportunity_id).where(SourceOpportunity.source_id==f.id,Opportunity.merged_into_id.is_(None))).all()
 counts={'linked_source_rows':len(rows),'unique_masters':len({r[5] for r in rows}),'master_coordinates':0,'direct_source_geometry':0,'master_matches_source':0,'missing_geometry':0,'invalid_ranges':0,'masters_with_multiple_direct_coords':0}
 points={};labels={};samples=[]
 for r in rows:
  sid,external,url,raw,std,mid,mlat,mlon=r
  if mlat is not None and mlon is not None:counts['master_coordinates']+=1
  raw=raw or {};g=raw.get('geometry') or {};a=raw.get('attributes') or {}
  for k in ('REGIONNAME','CITYNAME','AMANA','BALADYA','DISTRICT'):
   v=a.get(k)
   if v:labels.setdefault(k,{}).setdefault(str(v),0);labels[k][str(v)]+=1
  if not isinstance(g,dict) or g.get('x') is None or g.get('y') is None:counts['missing_geometry']+=1;continue
  lon=float(g['x']);lat=float(g['y']);counts['direct_source_geometry']+=1
  if not(-90<=lat<=90 and -180<=lon<=180):counts['invalid_ranges']+=1;continue
  if mlat is None or mlon is None or abs(float(mlat)-lat)>1e-7 or abs(float(mlon)-lon)>1e-7:continue
  counts['master_matches_source']+=1;points.setdefault(mid,set()).add((lat,lon))
  if len(samples)<5:samples.append({'master_id':mid,'source_record_id':sid,'external_id':external,'latitude':lat,'longitude':lon,'REGIONNAME':a.get('REGIONNAME'),'REGION_ID':a.get('REGION_ID'),'CITYNAME':a.get('CITYNAME'),'CITY_ID':a.get('CITY_ID'),'AMANA':a.get('AMANA'),'url':url,'master_scope':None})
 counts['masters_with_multiple_direct_coords']=sum(len(x)>1 for x in points.values())
 counts['masters_with_one_direct_coord']=sum(len(x)==1 for x in points.values())
 print(json.dumps({'counts':counts,'samples':samples,'location_labels':{k:sorted(v.items(),key=lambda x:-x[1])[:40] for k,v in labels.items()}},ensure_ascii=False,default=str))
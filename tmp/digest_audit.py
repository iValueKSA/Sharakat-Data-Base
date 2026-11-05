import sys,json
sys.path.insert(0,"/app")
from app.database import SessionLocal
from app.models import GeographicReferenceDataset,GeographicReferenceUnit
from app.geographic_references import canonical_dataset_digest
from sqlalchemy import select
payload=json.load(open('/tmp/saudi-reference.json',encoding='utf8'))
with SessionLocal() as db:
 d=db.scalar(select(GeographicReferenceDataset).where(GeographicReferenceDataset.is_current.is_(True)))
 us=db.scalars(select(GeographicReferenceUnit).where(GeographicReferenceUnit.dataset_id==d.id).order_by(GeographicReferenceUnit.level,GeographicReferenceUnit.external_id)).all()
 rows=[]
 for u in us:
  row={'level':u.level,'external_id':u.external_id,'parent_external_id':u.parent_external_id,'name_ar':u.name_ar,'source_record':u.source_record_json}
  if u.name_en is not None:row['name_en']=u.name_en
  if u.aliases_json:row['aliases']=u.aliases_json
  if u.geometry_json is not None:row['geometry']=u.geometry_json
  rows.append(row)
 print(json.dumps({'stored_digest':d.content_sha256,'payload_digest':canonical_dataset_digest(payload['units']),'db_digest':canonical_dataset_digest(rows),'counts':len(rows)},ensure_ascii=False))
 for a,b in zip(payload['units'],rows):
  if json.dumps(a,ensure_ascii=False,sort_keys=True,separators=(',',':'),default=str)!=json.dumps(b,ensure_ascii=False,sort_keys=True,separators=(',',':'),default=str):
   print('DIFF',a['level'],a['external_id'],json.dumps(a,ensure_ascii=False,sort_keys=True)[:400],json.dumps(b,ensure_ascii=False,sort_keys=True)[:400]);break
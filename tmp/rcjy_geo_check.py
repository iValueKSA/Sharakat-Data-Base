from sqlalchemy import select
from app.database import SessionLocal
from app.models import GeographicReferenceUnit,GeographicReferenceDataset
with SessionLocal() as db:
 d=db.scalar(select(GeographicReferenceDataset).where(GeographicReferenceDataset.is_current.is_(True)))
 print('dataset',d.dataset_key,d.version,d.coverage_json)
 for u in db.scalars(select(GeographicReferenceUnit).where(GeographicReferenceUnit.dataset_id==d.id,GeographicReferenceUnit.name_en.ilike('%Yanbu%'))).all():
  p=db.get(GeographicReferenceUnit,u.parent_id) if u.parent_id else None
  print(u.id,u.level,u.external_id,u.name_ar,u.name_en,u.aliases_json,'parent=',None if p is None else (p.level,p.external_id,p.name_ar,p.name_en))

import json
from pathlib import Path
items=json.loads(Path('docs/validation/data/master-identity-duplicate-matching/invest-saudi-11-evidence.json').read_text(encoding='utf-8'))
for it in items:
 r=it['record'];m=r.get('modalData') or {}
 print(json.dumps({'id':it['source_row_id'],'ext':it['external_id'],'ref':it['official_reference'],'title':r.get('title'),'description':r.get('description'),'location':r.get('location'),'region':r.get('region'),'municipality':r.get('municipality'),'coords':r.get('Coordinates') or (m.get('location') if m else None),'location_method':r.get('location_detection_method'),'qualified':r.get('qualified_location'),'pdf':r.get('pdf_url') or r.get('pdf_file'),'link':r.get('link'),'owner':r.get('backed_by'),'site_metadata':{k:m.get(k) for k in ['opportunityNumber','siteArea','descriptionSections','furas_link','downloadPdfLink','location'] if k in m}},ensure_ascii=False)[:3500])

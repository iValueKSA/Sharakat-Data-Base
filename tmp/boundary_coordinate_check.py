import sys,json
sys.path.insert(0,"/app")
from sqlalchemy import select
from app.database import SessionLocal
from app.models import Opportunity,Source,SourceOpportunity,GeographicReferenceDataset,GeographicReferenceUnit

def polygons(g):
 t=g.get('type');c=g.get('coordinates') or []
 if t=='Polygon':return [c]
 if t=='MultiPolygon':return c
 return []
def bbox(coords):
 pts=[pt for ring in coords for pt in ring]
 return (min(p[0] for p in pts),min(p[1] for p in pts),max(p[0] for p in pts),max(p[1] for p in pts))
def inside_ring(x,y,ring):
 inside=False;j=len(ring)-1
 for i,(xi,yi) in enumerate(ring):
  xj,yj=ring[j]
  if ((yi>y)!=(yj>y)) and x<(xj-xi)*(y-yi)/(yj-yi)+xi:inside=not inside
  j=i
 return inside
def inside_poly(x,y,poly):
 if not poly or not inside_ring(x,y,poly[0]):return False
 return not any(inside_ring(x,y,hole) for hole in poly[1:])
with SessionLocal() as db:
 f=db.scalar(select(Source).where(Source.source_key=='furas')); ds=db.scalar(select(GeographicReferenceDataset).where(GeographicReferenceDataset.is_current.is_(True)))
 regions=[]
 for u in db.scalars(select(GeographicReferenceUnit).where(GeographicReferenceUnit.dataset_id==ds.id,GeographicReferenceUnit.level=='region')):
  ps=polygons(u.geometry_json);regions.append((u.external_id,[(bbox(p),p) for p in ps]))
 rows=db.execute(select(SourceOpportunity.raw_data_json).join(Opportunity,Opportunity.id==SourceOpportunity.master_opportunity_id).where(SourceOpportunity.source_id==f.id,Opportunity.merged_into_id.is_(None))).all()
 points=set();invalid=0
 for (raw,) in rows:
  g=(raw or {}).get('geometry') or {}
  if g.get('x') is None or g.get('y') is None:invalid+=1;continue
  points.add((float(g['x']),float(g['y'])))
 hits={}; outside=[]
 for x,y in points:
  found=[]
  for code,polys in regions:
   for (xmin,ymin,xmax,ymax),poly in polys:
    if xmin<=x<=xmax and ymin<=y<=ymax and inside_poly(x,y,poly):found.append(code);break
  if found:hits[x,y]=found
  else:outside.append((x,y))
 print(json.dumps({'linked_rows':len(rows),'unique_points':len(points),'invalid_geometry':invalid,'points_inside_saudi':len(hits),'points_outside_saudi':len(outside),'outside_sample':outside[:20],'multi_region_hits':sum(len(v)>1 for v in hits.values()),'coordinate_duplicates':len(rows)-len(points)},ensure_ascii=False))
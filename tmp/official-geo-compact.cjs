const fs=require('fs'); const root='C:/Users/QusaiAbdElhalim/OneDrive - iValue/Desktop/الشراكات - الأحساء/Sharakat-Data-Base';
const read=p=>JSON.parse(fs.readFileSync(root+'/'+p,'utf8'));
const cur=read('tmp/alahsa-current-record-evidence.json'), ids=read('tmp/alahsa-record-audit-ids.json');
const g=read('docs/validation/deployment/nationwide-geographic-expansion/evidence/taadeen-governorates-20261102.geojson');
const rg=read('docs/validation/deployment/nationwide-geographic-expansion/evidence/taadeen-regions-20261102.geojson');
const f=g.features.find(x=>String(x.properties.Governorate_Code)==='501'); const fr=rg.features.find(x=>String(x.properties.Emirate_Code)==='5');
function ring(p,r){let z=false;for(let i=0,j=r.length-1;i<r.length;j=i++){const [x,y]=r[i],[X,Y]=r[j];if((y>p[1])!==(Y>p[1])&&p[0]<(X-x)*(p[1]-y)/(Y-y)+x)z=!z;}return z}
function poly(p,rings){return ring(p,rings[0])&&!rings.slice(1).some(r=>ring(p,r))}
function geom(p,g){if(!g)return false;if(g.type==='Polygon')return poly(p,g.coordinates);if(g.type==='MultiPolygon')return g.coordinates.some(r=>poly(p,r));return false}
function inG(pt,f){return geom(pt,f.geometry)}
const mapSet=new Set(ids.eligible_ids.map(Number)), exc=new Set(ids.excluded_ids.map(Number)); const groups={}; const perRecord=[]; const regionFeatures=rg.features;
for(const o of cur){const pt=[Number(o.master_longitude),Number(o.master_latitude)], prov=o.coordinate_provenance||{}, b=prov.boundary_validation||{};const category=mapSet.has(+o.master_id)?'MAP_ELIGIBLE':b.status==='SOURCE_COORDINATE_OUTSIDE_SAUDI_REVIEW'?'OUTSIDE_REVIEW':'VERIFIED_UNSPECIFIED';const members=regionFeatures.filter(x=>inG(pt,x)).map(x=>String(x.properties.Emirate_Code)); const key=category+'|gov501='+inG(pt,f)+'|region5='+inG(pt,fr)+'|regions='+members.join(',');groups[key]=(groups[key]||0)+1; perRecord.push({id:o.master_id,category,gov501:inG(pt,f),region5:inG(pt,fr),regions:members,lat:pt[1],lon:pt[0]});}
console.log(JSON.stringify({gov501:f&&{properties:{Governorate_Code:f.properties.Governorate_Code,Governorate_Name:f.properties.Governorate_Name,Parent_Name:f.properties.Parent_Name,source:f.properties.source},type:f.geometry.type},region5:fr&&{properties:{Emirate_Code:fr.properties.Emirate_Code,Emirate_Name:fr.properties.Emirate_Name,source:fr.properties.source},type:fr.geometry.type},groups,perRecord},null,2));


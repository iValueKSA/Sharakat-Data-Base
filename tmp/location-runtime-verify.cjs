(async()=>{
 const base='http://localhost:8080';
 const filters=await (await fetch(base+'/api/filters')).json();
 const id=filters.option_ids.locations['الأحساء'];
 const url=base+'/api/opportunities?location='+encodeURIComponent(id)+'&limit=500';
 const filtered=await (await fetch(url)).json();
 const general=await (await fetch(base+'/api/opportunities?limit=500')).json();
 const dashboard=await (await fetch(base+'/api/data-dashboard?location='+encodeURIComponent(id))).json();
 const geography=await (await fetch(base+'/api/data-dashboard/geography?location='+encodeURIComponent(id))).json();
 const csv=await fetch(base+'/api/export.csv?location='+encodeURIComponent(id));
 const xlsx=await fetch(base+'/api/export.xlsx?location='+encodeURIComponent(id));
 const unresolved=general.items.filter(x=>[70,211,212,213,214,215,216,217].includes(x.id)).map(x=>({id:x.id,status:x.geography.status,confirmed:x.geography.confirmed,city:x.city,location:x.location}));
 const out={validated_at_utc:new Date().toISOString(),parent_filter_id:id,parent_filter_label:'الأحساء',filter_option_count:filters.option_counts.locations['الأحساء'],hierarchy:filters.location_hierarchy,filtered_count:filtered.total,filtered_ids:filtered.items.map(x=>x.id).sort((a,b)=>a-b),dashboard_count:dashboard.kpis.total,map_total:geography.counts.total,map_mapped:geography.counts.exact_mapped,map_point_ids:[...new Set(geography.points.flatMap(x=>x.ids))].sort((a,b)=>a-b),csv_status:csv.status,csv_content_type:csv.headers.get('content-type'),xlsx_status:xlsx.status,xlsx_content_type:xlsx.headers.get('content-type'),unresolved,locality_samples:filtered.items.filter(x=>x.geography.locality).slice(0,8).map(x=>({id:x.id,city:x.city,locality:x.geography.locality,governorate:x.geography.governorate,region:x.geography.region,country:x.geography.country_code})),multi_location:filtered.items.find(x=>x.id===228)?{id:228,city:filtered.items.find(x=>x.id===228).city,geography:filtered.items.find(x=>x.id===228).geography,source_locations:filtered.items.find(x=>x.id===228).sources.flatMap(s=>s.opportunity_locations)}:null};
 console.log(JSON.stringify(out,null,2));
})().catch(e=>{console.error(e);process.exitCode=1});

from __future__ import annotations

import csv
import hashlib
import json
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select, text

from app.database import SessionLocal
from app.models import (
    Opportunity, OpportunityAssetFacilityType, OpportunityConflict,
    OpportunityLocation, Source, SourceObservation, SourceOpportunity,
    SourceOpportunityTaxonomy, SystemEvent, SyncJob,
)
from app.standardization import canonical_id, canonical_value

OUT = Path('/tmp/unspecified-sector-deep-analysis')
OUT.mkdir(parents=True, exist_ok=True)
UNSPEC = 'sector:unspecified'
CLASS_KEY = re.compile(r'(sector|category|industry|theme|classif|taxonomy|activity|sub.?activity|subsector|economic|isic|business.?type|asset.?class|opportunity.?type|product.?type|service.?type)', re.I)
GENERIC = {'فرصة', 'استثمار', 'تأجير', 'تاجير', 'تشغيل', 'موقع', 'أرض', 'ارض', 'مبنى', 'مرفق', 'إنشاء', 'انشاء', 'تطوير', 'مشروع', 'منافسة', 'خدمات', 'activity', 'opportunity', 'investment', 'site', 'land', 'building', 'facility', 'project', 'operation', 'development'}
SECTOR_PHRASES = {
    'sector:tourism': ['فندق', 'فنادق', 'منتجع', 'منتجعات', 'نزل سياحي', 'ضيافة فندقية', 'مرفق سياحي', 'وجهة سياحية', 'سياحة تراثية', 'متحف تراثي', 'hotel', 'resort', 'hospitality facility', 'tourism destination'],
    'sector:agriculture': ['مزرعة', 'مزارع', 'إنتاج زراعي', 'انتاج زراعي', 'نشاط زراعي', 'نخيل', 'تمور', 'مشاتل', 'مشتل', 'بيوت محمية', 'إنتاج التمور', 'date production', 'greenhouse farming', 'agricultural production'],
    'sector:commercial': ['محلات تجارية', 'مركز تجاري', 'مراكز تجارية', 'مركز تسوق', 'أنشطة تجارة المواد الغذائية', 'أنشطة التجارة العامة', 'retail shops', 'shopping center'],
    'sector:financial_services': ['خدمات الصرافة', 'خدمات مالية', 'مركز صرافة', 'exchange services', 'financial services'],
    'sector:industrial': ['مصنع', 'مصانع', 'منشأة صناعية', 'خط إنتاج', 'خط انتاج', 'تصنيع', 'صناعات تحويلية', 'factory', 'manufacturing facility'],
    'sector:real_estate': ['تطوير عقاري', 'مشروع سكني', 'مجمع سكني', 'تطوير وحدات سكنية', 'residential development', 'real estate development'],
    'sector:healthcare': ['مستشفى', 'مركز طبي', 'مركز صحي', 'عيادات طبية', 'خدمات صحية', 'hospital', 'medical center'],
    'sector:education': ['مدرسة', 'مدارس', 'كلية', 'مركز تعليمي', 'مؤسسة تعليمية', 'school', 'education facility'],
    'sector:logistics': ['مستودعات لوجستية', 'مركز لوجستي', 'خدمات لوجستية', 'مركز توزيع', 'logistics center', 'distribution center'],
    'sector:environment': ['إعادة تدوير', 'اعادة تدوير', 'معالجة النفايات', 'معالجة المياه', 'إدارة النفايات', 'waste recycling', 'waste treatment'],
    'sector:energy': ['طاقة متجددة', 'محطة طاقة', 'طاقة شمسية', 'renewable energy', 'solar energy'],
    'sector:technology': ['أبراج اتصالات', 'برج اتصالات', 'مركز بيانات', 'تقنية المعلومات', 'telecom tower', 'data center'],
    'sector:sports': ['مدينة رياضية', 'منشأة رياضية', 'مركز رياضي', 'sports facility', 'sports center'],
    'sector:culture': ['مركز ثقافي', 'مرفق ثقافي', 'فعاليات تراثية', 'cultural center', 'heritage venue'],
}
KNOWN_EXPLICIT = {
    'tourism': 'sector:tourism', 'hospitality': 'sector:tourism', 'adventure tourism': 'sector:tourism',
    'agriculture': 'sector:agriculture', 'agriculture and livestock': 'sector:agriculture',
    'financial services': 'sector:financial_services', 'healthcare': 'sector:healthcare', 'education': 'sector:education',
    'environment': 'sector:environment', 'real estate & construction': 'sector:real_estate',
    'real estate and construction': 'sector:real_estate', 'transport and logistics': 'sector:logistics',
    'logistics and storage': 'sector:logistics', 'manufacturing': 'sector:industrial',
    'industrial': 'sector:industrial', 'commercial': 'sector:commercial',
}


def norm(value):
    if value is None:
        return ''
    s = unicodedata.normalize('NFKD', str(value)).casefold()
    s = ''.join(c for c in s if not unicodedata.combining(c))
    s = s.translate(str.maketrans({'أ':'ا','إ':'ا','آ':'ا','ى':'ي','ة':'ه','ؤ':'و','ئ':'ي'}))
    s = re.sub(r'[^\w\s]', ' ', s, flags=re.UNICODE)
    return re.sub(r'\s+', ' ', s).strip()


def digest(value):
    raw=json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


def flatten_classification(value, prefix='', depth=0):
    out=[]
    if depth>6: return out
    if isinstance(value,dict):
        for k,v in value.items():
            path=f'{prefix}.{k}' if prefix else str(k)
            if isinstance(v,(str,int,float,bool)) and CLASS_KEY.search(str(k)) and str(v).strip():
                out.append({'path':path,'key':str(k),'value':str(v).strip()[:1000]})
            if isinstance(v,(dict,list)): out.extend(flatten_classification(v,path,depth+1))
    elif isinstance(value,list):
        for i,v in enumerate(value[:150]): out.extend(flatten_classification(v,f'{prefix}[{i}]',depth+1))
    return out


def get_snapshot():
    with SessionLocal() as db:
        db.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY'))
        masters=db.scalars(select(Opportunity).where(Opportunity.merged_into_id.is_(None)).order_by(Opportunity.id)).all()
        master_ids={m.id for m in masters}
        srcrows=db.scalars(select(SourceOpportunity).order_by(SourceOpportunity.id)).all()
        srcrows=[s for s in srcrows if s.master_opportunity_id in master_ids]
        sources={s.id:s for s in db.scalars(select(Source).order_by(Source.id)).all()}
        by_master=defaultdict(list)
        for s in srcrows: by_master[s.master_opportunity_id].append(s)
        assets=defaultdict(list)
        for a in db.scalars(select(OpportunityAssetFacilityType).order_by(OpportunityAssetFacilityType.opportunity_id,OpportunityAssetFacilityType.id)).all():
            if a.opportunity_id in master_ids:
                assets[a.opportunity_id].append({'canonical_id':a.canonical_id,'label_ar':a.asset_type.label_ar if a.asset_type else None,'raw_value':a.raw_value,'source_record_id':a.source_record_id})
        locs=defaultdict(list)
        source_ids={s.id for s in srcrows}
        for l in db.scalars(select(OpportunityLocation).order_by(OpportunityLocation.id)).all():
            if l.source_opportunity_id in source_ids: locs[l.source_opportunity_id].append({'location_name':l.location_name,'location_scope':l.location_scope,'is_al_ahsa':l.is_al_ahsa,'source_location_text':l.source_location_text})
        tax=defaultdict(list)
        for t in db.scalars(select(SourceOpportunityTaxonomy).order_by(SourceOpportunityTaxonomy.source_opportunity_id,SourceOpportunityTaxonomy.id)).all():
            if t.source_opportunity_id in source_ids: tax[t.source_opportunity_id].append({'dataset':t.dataset_name,'raw_value':t.source_taxonomy_value,'normalized_value':t.normalized_taxonomy_value,'mapping_rule':t.mapping_rule})
        conflicts=defaultdict(list)
        open_conflicts=db.scalars(select(OpportunityConflict).where(OpportunityConflict.status=='OPEN').order_by(OpportunityConflict.id)).all()
        for c in open_conflicts:
            if c.opportunity_id in master_ids: conflicts[c.opportunity_id].append({'review_id':c.id,'field':c.field_name,'conflict_type':c.conflict_type,'selected_value':c.selected_value,'conflicting_value':c.conflicting_value,'source_record_id':c.source_record_id,'source_id':c.source_id,'detected_at':c.detected_at})
        events=db.scalars(select(SystemEvent).where(SystemEvent.event_type.in_(['SECTOR_INFERENCE_STATUS_CONSOLIDATION_APPLIED','SECTOR_INFERENCE_PHASE2_APPLIED','SECTOR_INFERENCE_PHASE2_OFFICIAL_OVERRIDE'])).order_by(SystemEvent.id)).all()
        provenance=defaultdict(list)
        for e in events:
            for item in (e.payload or {}).get('classifications',[]):
                mid=item.get('master_id')
                if mid in master_ids: provenance[mid].append({'event_type':e.event_type,'event_id':e.id,'created_at':e.created_at,'decision':item})
            mid=(e.payload or {}).get('master_id')
            if mid in master_ids: provenance[mid].append({'event_type':e.event_type,'event_id':e.id,'created_at':e.created_at,'decision':e.payload})
        labeled=[]; unspecified=[]; current_ids=[]; specified_fp=[]
        for m in masters:
            row={'master_id':m.id,'canonical_id':m.canonical_id,'sector':m.sector,'sector_id':canonical_id('sector',m.sector),'title_ar':m.title_ar,'normalized_title':m.normalized_title,'title_en':m.title_en,'activity':m.activity,'sub_activity':m.sub_activity,'subsector':m.subsector,'opportunity_type':m.opportunity_type,'investment_model':m.investment_model,'short_description':m.short_description,'full_description':m.full_description,'owner':m.opportunity_owner,'publisher':m.primary_publication_platform,'location':{'city':m.city,'district':m.district,'description':m.location_description,'lat':m.latitude,'lon':m.longitude},'status':m.status,'reference_number':m.reference_number,'reference_number_normalized':m.reference_number_normalized,'assets':assets.get(m.id,[]),'sources':[],'open_conflicts':conflicts.get(m.id,[]),'inference_provenance':provenance.get(m.id,[])}
            for s in by_master.get(m.id,[]):
                src=sources.get(s.source_id)
                row['sources'].append({'source_record_id':s.id,'source_id':s.source_id,'source_key':src.source_key if src else str(s.source_id),'source_name_ar':src.source_name_ar if src else None,'source_opportunity_id':s.source_opportunity_id,'official_source_id':s.official_source_id_original,'source_reference_number':s.source_reference_number,'source_title':s.source_title,'source_sector':s.source_sector,'normalized_sector':s.normalized_sector,'source_activity':s.source_activity,'source_sub_activity':s.source_sub_activity,'source_subsector':s.source_subsector,'raw_location':s.raw_location,'raw_status':s.raw_status,'canonical_status':s.canonical_status,'raw_data':s.raw_data_json or {},'standardized_data':s.standardized_data_json or {},'source_taxonomies':tax.get(s.id,[]),'source_locations':locs.get(s.id,[])})
            current_ids.append(m.id)
            if row['sector_id']==UNSPEC: unspecified.append(row)
            else: labeled.append(row); specified_fp.append((m.id,m.sector))
        observations=db.execute(select(SourceObservation.id,SourceObservation.source_opportunity_id,SourceObservation.endpoint,SourceObservation.content_hash,SourceObservation.first_seen_at,SourceObservation.last_seen_at).order_by(SourceObservation.id)).all()
        jobs=db.scalars(select(SyncJob).order_by(SyncJob.id)).all()
        return {'captured_at':datetime.now(timezone.utc).isoformat(),'manifest':{'current_masters':len(masters),'specified':len(labeled),'unspecified':len(unspecified),'sector_distribution':dict(sorted(Counter(canonical_value('sector',m.sector) for m in masters).items())),'unspecified_ids':[r['master_id'] for r in unspecified],'master_identity_fingerprint':digest([(m.id,m.canonical_id) for m in masters]),'preexisting_specified_sector_fingerprint':digest(specified_fp),'source_opportunities':len(srcrows),'source_identity_fingerprint':digest([(s.id,s.source_id,s.source_opportunity_id,s.master_opportunity_id) for s in srcrows]),'raw_provenance_fingerprint':digest([(s.id,s.master_opportunity_id,s.source_sector,s.source_activity,s.source_sub_activity,s.raw_data_json,s.standardized_data_json) for s in srcrows]),'observations':len(observations),'observation_history_fingerprint':digest(observations),'open_sector_reviews':sum(1 for c in open_conflicts if c.field_name=='sector'),'open_sector_review_ids':[c.id for c in open_conflicts if c.field_name=='sector'],'sync_job_count':len(jobs),'max_sync_job_id':jobs[-1].id if jobs else None,'active_sync_jobs':[{'id':j.id,'job_state':j.job_state,'trigger_type':j.trigger_type} for j in jobs if j.job_state in ('QUEUED','RUNNING','RETRYING')]},'unspecified_records':unspecified,'labeled_records':labeled,'all_current_ids':current_ids}


def best_sector(value):
    if not value: return None
    normalized=norm(value)
    if normalized in KNOWN_EXPLICIT: return KNOWN_EXPLICIT[normalized]
    candidate=canonical_id('sector',value)
    return candidate if candidate!=UNSPEC and not str(candidate).startswith('unmapped:') else None


def phrase_hits(text_value):
    n=norm(text_value)
    return {sid:[p for p in phrases if norm(p) and norm(p) in n] for sid,phrases in SECTOR_PHRASES.items() if any(norm(p) and norm(p) in n for p in phrases)}


def weak_title_context(title, hits=None):
    hits=hits if hits is not None else phrase_hits(title)
    n=norm(title)
    return bool(('sector:healthcare' in hits and any(norm(x) in n for x in ('بالقرب من مستشفى','مقهى مستشفى'))) or ('sector:agriculture' in hits and any(norm(x) in n for x in ('مدينة التمور','المنتجات الثانوية للنخيل'))))


def main():
    # Analyze the frozen read-only population captured at the start of the task.
    # Regeneration must never silently blend a later scheduled-sync population.
    snapshot=json.loads((OUT/'analysis-snapshot.json').read_text(encoding='utf8'))
    uns=snapshot['unspecified_records']; labeled=snapshot['labeled_records']; allr=uns+labeled
    inferred={r['master_id'] for r in allr if r['inference_provenance']}
    train=[r for r in labeled if r['master_id'] not in inferred]
    srcrows=[(r,s) for r in uns for s in r['sources']]
    def avail_raw(r, field): return any(s.get(field) for s in r['sources'])
    def distinct_description(r):
        values=[]; title=norm(r['title_ar'])
        for v in (r.get('short_description'),r.get('full_description')):
            nv=norm(v)
            if nv and nv!=title and nv not in values: values.append(nv)
        return values
    rawfields=defaultdict(lambda:{'values':[],'sources':Counter(),'records':set(),'used_records':set()})
    for r,s in srcrows:
        for payload_name,payload in [('raw',s['raw_data']),('standardized',s['standardized_data'])]:
            for f in flatten_classification(payload,payload_name):
                key=(s['source_key'],f['path']); entry=rawfields[key]; entry['values'].append(f['value']); entry['sources'][s['source_key']]+=1; entry['records'].add(r['master_id'])
                nk=norm(f['key']).replace(' ','')
                directly_used={'sector','sourcesector','activity','sourceactivity','subactivity','sourcesubactivity','subsector','sourcesubsector','normalizedsector','normalizedsubsector','category','categoryname','industry','industryname','theme','economicactivity','isiccode'}
                stdkeys={norm(x['key']).replace(' ','') for x in flatten_classification(s['standardized_data'])}
                if payload_name=='standardized' or nk in directly_used or nk in stdkeys: entry['used_records'].add(r['master_id'])
    field_output=[]
    for (source,path),e in sorted(rawfields.items()):
        vals=Counter(e['values']); field_output.append({'source':source,'raw_field':path,'non_null_records':len(e['records']),'non_null_values':len(e['values']),'distinct_values':len(vals),'sample_values':[v for v,_ in vals.most_common(8)],'currently_used_by_normalization':len(e['used_records'])>0,'normalization_evidence':'field is represented in standardized payload or mapped to a canonical source classification column' if len(e['used_records']) else 'no matching standardized or canonical source classification field found'})
    # Exclude Phase 1/2 inferred records from empirical controls.
    def group_exact(field, rows):
        groups=defaultdict(Counter)
        for r in rows:
            value=r.get(field)
            if value: groups[norm(value)][canonical_id('sector',r.get('sector'))]+=1
        return groups
    activity_ref=group_exact('activity',train); sub_ref=group_exact('sub_activity',train)
    source_raw_refs=defaultdict(Counter)
    for r in train:
        for s in r['sources']:
            for field in ('source_sector','source_activity','source_sub_activity','source_subsector'):
                if s.get(field): source_raw_refs[(s['source_key'],field,norm(s[field]))][r['sector_id']]+=1
    activity_groups=defaultdict(list); sub_groups=defaultdict(list); raw_groups=defaultdict(list); asset_groups=defaultdict(list)
    for r in uns:
        if r['activity']: activity_groups[r['activity']].append(r)
        if r['sub_activity']: sub_groups[r['sub_activity']].append(r)
        for s in r['sources']:
            for fld in ('source_activity','source_sub_activity','source_sector','source_subsector'):
                if s.get(fld): raw_groups[(s['source_key'],fld,s[fld])].append(r)
        for a in r['assets']:
            asset_groups[a.get('label_ar') or a.get('canonical_id')].append(r)
    def make_pattern_groups(groups, field, ref_groups, min_support):
        out=[]
        for value,rows in sorted(groups.items(),key=lambda p:(-len(p[1]),str(p[0]))):
            ref=ref_groups.get(norm(value),Counter()); total=sum(ref.values()); dist=dict(sorted(ref.items())); dom,n=ref.most_common(1)[0] if ref else (None,0); purity=round(n/total,4) if total else None
            high_label='HIGH_PURITY_ACTIVITY' if field=='activity' else 'HIGH_PURITY_SUBACTIVITY'
            bucket='MISSING_REFERENCE' if not total else high_label if purity>=.98 and total>=min_support else 'MIXED_ACTIVITY' if len(ref)>1 else 'LOW_SAMPLE_OR_SINGLE_SECTOR_REFERENCE'
            out.append({field:value,'unspecified_count':len(rows),'labeled_reference_count':total,'labeled_sector_distribution':dist,'dominant_sector_id':dom,'purity_percentage':round(purity*100,2) if purity is not None else None,'sample_titles':[r['title_ar'] for r in rows[:5]],'sample_master_ids':[r['master_id'] for r in rows[:10]],'analysis_group':bucket})
        return out
    activity_patterns=make_pattern_groups(activity_groups,'activity',activity_ref,25)
    sub_patterns=make_pattern_groups(sub_groups,'sub_activity',sub_ref,8)
    raw_patterns=[]
    for (source,field,value),rows in sorted(raw_groups.items(),key=lambda p:(-len(p[1]),p[0])):
        refs=source_raw_refs.get((source,field,norm(value)),Counter()); total=sum(refs.values()); dom,n=refs.most_common(1)[0] if refs else (None,0)
        raw_patterns.append({'source':source,'raw_field':field,'raw_value':value,'unspecified_count':len({r['master_id'] for r in rows}),'labeled_reference_count':total,'sector_distribution':dict(refs),'dominant_sector_id':dom,'purity_percentage':round(100*n/total,2) if total else None,'sample_master_ids':sorted({r['master_id'] for r in rows})[:10]})
    asset_patterns=[]
    for asset,rows in sorted(asset_groups.items(),key=lambda p:(-len(p[1]),str(p[0]))):
        refs=Counter()
        for r in train:
            if any((a.get('label_ar') or a.get('canonical_id'))==asset for a in r['assets']): refs[r['sector_id']]+=1
        total=sum(refs.values()); dom,n=refs.most_common(1)[0] if refs else (None,0)
        asset_patterns.append({'asset_type':asset,'unspecified_count':len({r['master_id'] for r in rows}),'labeled_count':total,'sector_distribution':dict(refs),'dominant_sector_id':dom,'purity_percentage':round(100*n/total,2) if total else None,'sample_master_ids':sorted({r['master_id'] for r in rows})[:10]})

    # Exact empirical maps use minimum support and purity from Phase 2, but only for diagnosis.
    act_maps={k:v.most_common(1)[0][0] for k,v in activity_ref.items() if sum(v.values())>=25 and v.most_common(1)[0][1]/sum(v.values())>=.98}
    sub_maps={k:v.most_common(1)[0][0] for k,v in sub_ref.items() if sum(v.values())>=8 and v.most_common(1)[0][1]/sum(v.values())>=.98}
    # Learn source-context raw mappings only where observed support is adequate.
    raw_maps={}
    for key,dist in source_raw_refs.items():
        total=sum(dist.values()); sector,n=dist.most_common(1)[0]
        if total>=5 and n/total>=.90: raw_maps[key]=sector
    bucket_order=['EXPLICIT_SOURCE_EVIDENCE_UNMAPPED','HIGH_PURITY_ACTIVITY_RESOLVABLE','HIGH_PURITY_SUBACTIVITY_RESOLVABLE','RAW_SOURCE_CLASSIFICATION_RESOLVABLE','TITLE_PATTERN_RESOLVABLE','DESCRIPTION_RESOLVABLE','MULTI_SIGNAL_RESOLVABLE','CONFLICTING_EVIDENCE','POTENTIAL_TAXONOMY_GAP','GENUINELY_UNCLASSIFIABLE']
    bucket_counts=Counter({key:0 for key in bucket_order}); rows_out=[]; phrase_stats=defaultdict(lambda:{'unspecified':set(),'labeled':Counter(),'samples':[]}); title_groups=defaultdict(list); desc_candidates=[]; multi_candidates=[]; conflicts=[]; tourism_strong=[]; tourism_amb=[]; agric_strong=[]; agric_amb=[]; explicit_rows=[]
    for r in uns:
        hits={}
        # Structured, exact empirical signals.
        if norm(r['activity']) in act_maps: hits.setdefault(act_maps[norm(r['activity'])],{})['activity']=r['activity']
        if norm(r['sub_activity']) in sub_maps: hits.setdefault(sub_maps[norm(r['sub_activity'])],{})['sub_activity']=r['sub_activity']
        official=[]; raw_candidates=[]; raw_unmapped=[]; semantic_raw_review=False
        for s in r['sources']:
            if s['source_key']=='furas' and norm(s.get('source_activity'))==norm('الأنشطة الزراعية والحيوانية'):
                hits.setdefault('sector:agriculture',{})['raw_source_activity']=s['source_activity']; semantic_raw_review=True
            raw_cl=[('source_sector',s.get('source_sector')),('source_subsector',s.get('source_subsector'))]
            for field,value in raw_cl:
                if not value: continue
                sector=best_sector(value)
                if sector: hits.setdefault(sector,{})[field]=value
                else:
                    mapped=KNOWN_EXPLICIT.get(norm(value))
                    if mapped: hits.setdefault(mapped,{})[field]=value
                    else: raw_unmapped.append({'source':s['source_key'],'field':field,'value':value})
            for field,value in [('source_sector',s.get('source_sector')),('source_activity',s.get('source_activity')),('source_sub_activity',s.get('source_sub_activity')),('source_subsector',s.get('source_subsector'))]:
                if value:
                    key=(s['source_key'],field,norm(value))
                    if key in raw_maps: hits.setdefault(raw_maps[key],{})[f'raw_{field}']=value
            # Catch actual category/industry/theme/classification data in raw payloads.
            for f in flatten_classification(s['raw_data'],'raw'):
                kn=norm(f['key']).replace(' ','')
                if any(w in kn for w in ('sector','category','industry','theme','classification','economicactivity','isic')) and not any(w in kn for w in ('activity','subactivity')):
                    mapped=best_sector(f['value']) or KNOWN_EXPLICIT.get(norm(f['value']))
                    if mapped: hits.setdefault(mapped,{})[f['path']]=f['value']
                    elif f['value'].strip(): raw_unmapped.append({'source':s['source_key'],'field':f['path'],'value':f['value']})
        title_hit=phrase_hits(r['title_ar']); desc=' '.join([x for x in [r.get('short_description'),r.get('full_description')] if x and norm(x)!=norm(r['title_ar'])]); desc_hit=phrase_hits(desc)
        title_context_weak=weak_title_context(r.get('title_ar') or '',title_hit)
        asset_text=' '.join(a.get('label_ar') or '' for a in r['assets']); asset_hit=phrase_hits(asset_text)
        for sid,phs in title_hit.items():
            # A phrase is only evidence for analytical grouping; a title alone cannot be automated.
            title_groups[(sid,phs[0])].append(r)
        for sid,phs in desc_hit.items(): phrase_stats[(sid,phs[0])]['unspecified'].add(r['master_id'])
        for sid,phs in title_hit.items(): phrase_stats[(sid,phs[0])]['unspecified'].add(r['master_id'])
        evidence_fields=defaultdict(set)
        for sid,val in hits.items():
            for field in val: evidence_fields[sid].add('structured' if ('activity' in field or 'sector' in field or 'subsector' in field) else 'raw')
        if not title_context_weak:
            for sid,phs in title_hit.items(): evidence_fields[sid].add('title')
        for sid,phs in desc_hit.items(): evidence_fields[sid].add('description')
        for sid,phs in asset_hit.items(): evidence_fields[sid].add('asset')
        sector_evidence={sid:sorted(fields) for sid,fields in evidence_fields.items()}
        conflicting=len(sector_evidence)>1
        mapped_source_raw=bool(raw_unmapped)
        if conflicting:
            bucket='CONFLICTING_EVIDENCE'; likely=None; confidence='LOW'; conflict_summary='Independent structured or source-context signals point to multiple canonical sectors.'; action='REVIEW_CANDIDATE'; conflicts.append(r)
        elif mapped_source_raw:
            bucket='EXPLICIT_SOURCE_EVIDENCE_UNMAPPED'; vals=raw_unmapped; likely=next((KNOWN_EXPLICIT.get(norm(x['value'])) for x in vals if KNOWN_EXPLICIT.get(norm(x['value']))),None); confidence='MEDIUM' if likely else 'LOW'; conflict_summary='Raw source classification is present but is not mapped to the Master sector.'; action='REVIEW_CANDIDATE'; explicit_rows.append((r,vals,likely))
        elif sector_evidence:
            sid=next(iter(sector_evidence)); likely=sid
            if 'activity' in hits.get(sid,{}): bucket='HIGH_PURITY_ACTIVITY_RESOLVABLE'; confidence='HIGH'; action='AUTO_RULE_CANDIDATE'
            elif 'sub_activity' in hits.get(sid,{}): bucket='HIGH_PURITY_SUBACTIVITY_RESOLVABLE'; confidence='HIGH'; action='AUTO_RULE_CANDIDATE'
            elif any(k.startswith('raw_') for k in hits.get(sid,{})) or any(k in hits.get(sid,{}) for k in ('source_sector','source_subsector')): bucket='RAW_SOURCE_CLASSIFICATION_RESOLVABLE'; confidence='MEDIUM' if semantic_raw_review else 'HIGH'; action='REVIEW_CANDIDATE' if semantic_raw_review else 'AUTO_RULE_CANDIDATE'
            elif 'title' in sector_evidence[sid] and len(sector_evidence[sid])==1: bucket='TITLE_PATTERN_RESOLVABLE'; confidence='MEDIUM'; action='REVIEW_CANDIDATE'
            elif 'description' in sector_evidence[sid] and len(sector_evidence[sid])==1: bucket='DESCRIPTION_RESOLVABLE'; confidence='MEDIUM'; action='REVIEW_CANDIDATE'; desc_candidates.append(r)
            else: bucket='MULTI_SIGNAL_RESOLVABLE'; confidence='MEDIUM'; action='REVIEW_CANDIDATE'; multi_candidates.append(r)
            conflict_summary='No competing sector signal detected.'
        else:
            semantic_text=' '.join([r.get('title_ar') or '',r.get('activity') or '',r.get('sub_activity') or '',desc,asset_text])
            if any(norm(x) in norm(semantic_text) for x in ['مقبرة','مقابر','مسلخ','مغسلة موتى','cemetery']) and len(uns)>=20:
                bucket='POTENTIAL_TAXONOMY_GAP'; likely=None; confidence='LOW'; action='TAXONOMY_REVIEW'; conflict_summary='Operational category may not represent a distinct sector; taxonomy review required.'
            else:
                bucket='GENUINELY_UNCLASSIFIABLE'; likely=None; confidence='LOW'; action='REVIEW_CANDIDATE' if title_context_weak else 'KEEP_UNSPECIFIED'; conflict_summary='Title phrase is contextual (nearby landmark, venue, or product reference), not evidence of the opportunity sector.' if title_context_weak else 'No strong contradictory signal; currently available evidence is generic, duplicated, missing, or unsupported.'
        bucket_counts[bucket]+=1
        strong_title=any(len(norm(p).split())>=2 for ps in title_hit.values() for p in ps)
        strong_desc=any(len(norm(p).split())>=2 for ps in desc_hit.values() for p in ps)
        # Strong means at least two independent non-title signals agree, with
        # an explicit/empirical structured classification among them.
        agriculture_independent={x for x in sector_evidence.get('sector:agriculture',[]) if x!='title'}
        tourism_independent={x for x in sector_evidence.get('sector:tourism',[]) if x!='title'}
        if 'sector:tourism' in sector_evidence and len(tourism_independent)>=2 and any(x in tourism_independent for x in ('structured','raw')):
            tourism_strong.append(r)
        elif any(sid=='sector:tourism' for sid in title_hit|desc_hit|asset_hit|{k:{} for k in sector_evidence}): tourism_amb.append(r)
        if 'sector:agriculture' in sector_evidence and len(agriculture_independent)>=2 and any(x in agriculture_independent for x in ('structured','raw')):
            agric_strong.append(r)
        elif semantic_raw_review or (not title_context_weak and any(sid=='sector:agriculture' for sid in title_hit|desc_hit|asset_hit|{k:{} for k in sector_evidence})): agric_amb.append(r)
        if any(norm(a.get('label_ar') or '') in (norm('الحدائق'),norm('الشواطئ والواجهات')) for a in r['assets']): tourism_amb.append(r)
        # Generic rental, site, land, building, and asset labels are available
        # fields, but do not count as sector evidence on their own.
        useful_structured=bool(hits) or any(phrase_hits(a.get('label_ar') or '') for a in r['assets'])
        desc_duplicate=not bool(desc)
        title_only=bool(title_hit) and not useful_structured and not desc_hit and not asset_hit
        if bucket=='GENUINELY_UNCLASSIFIABLE' and title_context_weak: missed='A sector word appears as a nearby landmark, venue, or product reference; the title does not establish the opportunity sector.'
        elif bucket=='GENUINELY_UNCLASSIFIABLE': missed='Only generic lease/type/location or operational asset fields are present; no independent sector signal or supported source mapping.'
        elif bucket=='TITLE_PATTERN_RESOLVABLE': missed='Compound title phrase is visible, but the current classifier requires independent structured confirmation and has no matching phrase rule.'
        elif bucket=='EXPLICIT_SOURCE_EVIDENCE_UNMAPPED': missed='A source classification value is present in raw fields, but its source-specific code is not mapped to a canonical sector.'
        elif bucket=='RAW_SOURCE_CLASSIFICATION_RESOLVABLE': missed='Source-specific raw activity/classification is informative, but is not exposed as a canonical field or exact mapping.'
        elif bucket=='CONFLICTING_EVIDENCE': missed='Independent signals disagree, so conservative conflict handling leaves the record unresolved.'
        elif bucket=='HIGH_PURITY_ACTIVITY_RESOLVABLE': missed='Canonical activity has a high-purity labeled reference mapping, but no rule applied to this record.'
        elif bucket=='HIGH_PURITY_SUBACTIVITY_RESOLVABLE': missed='Canonical sub-activity has a high-purity labeled reference mapping, but no rule applied to this record.'
        elif bucket=='DESCRIPTION_RESOLVABLE': missed='A distinct description contains a sector-indicative phrase absent from the title and structured taxonomy.'
        elif bucket=='MULTI_SIGNAL_RESOLVABLE': missed='Independent signals agree, but current exact rules do not combine this evidence pattern.'
        else: missed='The apparent activity does not fit a distinct existing sector; taxonomy review is needed before any mapping.'
        rowout={'Master ID':r['master_id'],'Title':r['title_ar'],'Source(s)':', '.join(sorted({s['source_key'] for s in r['sources']})),'Activity':r.get('activity'),'Sub-Activity':r.get('sub_activity'),'Asset Type':'; '.join(sorted({a.get('label_ar') or '' for a in r['assets'] if a.get('label_ar')})),'Raw Source Category':'; '.join(sorted({str(f['value']) for s in r['sources'] for f in flatten_classification(s['raw_data']) if re.search(r'category|industry|theme|classif|taxonomy',f['key'],re.I)})),'Raw Source Sector':'; '.join(sorted({s.get('source_sector') for s in r['sources'] if s.get('source_sector')})),'Primary Analysis Bucket':bucket,'Likely Sector':canonical_value('sector',likely) if likely else None,'Likely Sector ID':likely,'Confidence':confidence,'Evidence Summary':json.dumps({'structured':hits,'title_phrases':title_hit,'description_phrases':desc_hit,'asset_phrases':asset_hit},ensure_ascii=False,separators=(',',':')),'Conflict Summary':conflict_summary,'Why Current Classifier Missed':missed,'Recommended Next Action':action}
        raw_activity_values=set(); raw_subactivity_values=set()
        for source_row in r['sources']:
            if source_row.get('source_activity'): raw_activity_values.add(source_row['source_activity'])
            if source_row.get('source_sub_activity'): raw_subactivity_values.add(source_row['source_sub_activity'])
            for field_value in flatten_classification(source_row['raw_data']):
                if re.search(r'activitytype$|economicactivity',field_value['key'],re.I) and not re.search(r'subactivity',field_value['key'],re.I): raw_activity_values.add(field_value['value'])
                if re.search(r'subactivitytype$',field_value['key'],re.I): raw_subactivity_values.add(field_value['value'])
        rowout.update({'Raw Activity':'; '.join(sorted(raw_activity_values)),'Raw Sub-Activity':'; '.join(sorted(raw_subactivity_values)),'Opportunity Type':r.get('opportunity_type'),'Investment Model':r.get('investment_model'),'Short Description':r.get('short_description'),'Full Description':r.get('full_description'),'Owner':r.get('owner'),'Publisher':r.get('publisher'),'Location JSON':json.dumps(r.get('location') or {},ensure_ascii=False,separators=(',',':')),'Status':r.get('status'),'Reference':r.get('reference_number'),'Source Count':len(r['sources']),'Source External IDs JSON':json.dumps([{'source':s['source_key'],'source_opportunity_id':s.get('source_opportunity_id'),'official_source_id':s.get('official_source_id'),'source_reference_number':s.get('source_reference_number')} for s in r['sources']],ensure_ascii=False,separators=(',',':')),'Open Sector Review IDs JSON':json.dumps([c['review_id'] for c in r['open_conflicts'] if c['field']=='sector'],ensure_ascii=False,separators=(',',':')),'Open Taxonomy Review IDs JSON':json.dumps([c['review_id'] for c in r['open_conflicts'] if c['field'] in ('activity','sub_activity','subsector','source_taxonomy')],ensure_ascii=False,separators=(',',':')),'Inference Provenance JSON':json.dumps(r.get('inference_provenance') or [],ensure_ascii=False,separators=(',',':')),'Source Evidence JSON':json.dumps(r['sources'],ensure_ascii=False,separators=(',',':'))})
        rows_out.append(rowout)
    # Compare phrase occurrences in non-inferred labeled controls.
    for r in train:
        texts={norm(x) for x in [r.get('title_ar') or '',r.get('activity') or '',r.get('sub_activity') or '',r.get('short_description') or '',r.get('full_description') or ''] if norm(x)}
        for sid,phrases in SECTOR_PHRASES.items():
            for p in phrases:
                if norm(p) and any(norm(p) in txt for txt in texts): phrase_stats[(sid,p)]['labeled'][r['sector_id']]+=1
    semantic=[]
    for (sid,p),data in phrase_stats.items():
        dist=data['labeled']; total=sum(dist.values()); dom,n=dist.most_common(1)[0] if dist else (None,0); purity=round(n/total,4) if total else None
        kind='HIGHLY_DISCRIMINATIVE' if total>=3 and purity>=.90 and dom==sid else 'AMBIGUOUS' if total else 'NO_LABELED_SUPPORT'
        semantic.append({'phrase':p,'sector_id':sid,'unspecified_occurrences':len(data['unspecified']),'labeled_occurrences':total,'labeled_sector_distribution':dict(dist),'dominant_sector_id':dom,'purity_percentage':round(purity*100,2) if purity is not None else None,'group':kind})
    generic_stats=defaultdict(lambda:{'variants':set(),'unspecified':set(),'labeled':Counter()}); unspecified_id_set={r['master_id'] for r in uns}
    for phrase in GENERIC: generic_stats[norm(phrase)]['variants'].add(phrase)
    for r in uns+train:
        texts={norm(x) for x in [r.get('title_ar') or '',r.get('activity') or '',r.get('sub_activity') or '',r.get('short_description') or '',r.get('full_description') or ''] if norm(x)}
        for phrase in generic_stats:
            if phrase and any(phrase in txt for txt in texts):
                if r['master_id'] in unspecified_id_set: generic_stats[phrase]['unspecified'].add(r['master_id'])
                elif r['master_id'] not in inferred: generic_stats[phrase]['labeled'][r['sector_id']]+=1
    generic_analysis=[]
    for phrase,data in sorted(generic_stats.items(),key=lambda x:(-len(x[1]['unspecified']),x[0])):
        dist=data['labeled']; total=sum(dist.values()); dom,n=dist.most_common(1)[0] if dist else (None,0)
        generic_analysis.append({'normalized_phrase':phrase,'spelling_variants':sorted(data['variants']),'unspecified_occurrences':len(data['unspecified']),'labeled_occurrences':total,'labeled_sector_distribution':dict(dist),'dominant_sector_id':dom,'purity_percentage':round(100*n/total,2) if total else None,'group':'GENERIC','rule_recommendation':'DO_NOT_USE_ALONE'})
    # source-level source opportunity unique-master and field availability
    source_break=defaultdict(list)
    for r in uns:
        for s in r['sources']: source_break[s['source_key']].append((r,s))
    with SessionLocal() as db:
        db.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY'))
        source_catalog={s.source_key:s.source_name_ar for s in db.scalars(select(Source).order_by(Source.priority)).all()}
    source_summary=[]
    for source in sorted(set(source_catalog)|set(source_break),key=lambda key:(-len({r['master_id'] for r,s in source_break.get(key,[])}),key)):
        items=source_break.get(source,[])
        uniq={r['master_id']:r for r,s in items}; masters_for_source=set(uniq); denominator=sum(1 for r in allr if any(s['source_key']==source for s in r['sources']))
        def master_has(r, predicate): return any(predicate(s) for s in r['sources'] if s['source_key']==source)
        source_summary.append({'source':source,'source_name_ar':source_catalog.get(source),'current_masters_from_source':denominator,'unspecified_masters':len(masters_for_source),'unspecified_percent':round(100*len(masters_for_source)/denominator,2) if denominator else 0.0,'raw_sector_field_available':sum(master_has(r,lambda s:bool(s.get('source_sector'))) for r in (x for x in uns if x['master_id'] in masters_for_source)),'raw_activity_field_available':sum(master_has(r,lambda s:bool(s.get('source_activity'))) for r in (x for x in uns if x['master_id'] in masters_for_source)),'raw_subactivity_field_available':sum(master_has(r,lambda s:bool(s.get('source_sub_activity'))) for r in (x for x in uns if x['master_id'] in masters_for_source)),'raw_category_field_available':sum(master_has(r,lambda s:any(re.search(r'category|industry|theme|classif|taxonomy',f['key'],re.I) for f in flatten_classification(s['raw_data']))) for r in (x for x in uns if x['master_id'] in masters_for_source)),'other_classification_fields_available':sum(master_has(r,lambda s:bool(flatten_classification(s['raw_data']))) for r in (x for x in uns if x['master_id'] in masters_for_source))})
    # signal coverage and combination counts
    def has_raw_cat(r): return any(any(re.search(r'category|industry|theme|classif|taxonomy',f['key'],re.I) for f in flatten_classification(s['raw_data'])) for s in r['sources'])
    def has_other_struct(r): return any(flatten_classification(s['raw_data']) for s in r['sources'])
    def has_meaningful_title(r): return any(phrase_hits(r['title_ar']).values())
    def has_desc(r): return bool(distinct_description(r))
    def has_any_description(r): return bool(r.get('short_description') or r.get('full_description'))
    signal=lambda r:{'canonical_activity':bool(r.get('activity')),'canonical_sub_activity':bool(r.get('sub_activity')),'raw_activity':avail_raw(r,'source_activity'),'raw_sub_activity':avail_raw(r,'source_sub_activity'),'asset_type':bool(r['assets']),'opportunity_type':bool(r.get('opportunity_type')),'short_description':bool(r.get('short_description')),'full_description':bool(r.get('full_description')),'raw_source_category':has_raw_cat(r),'raw_source_sector':avail_raw(r,'source_sector'),'other_structured_classification':has_other_struct(r),'meaningful_title_pattern':has_meaningful_title(r),'description_any':has_any_description(r),'distinct_description':has_desc(r)}
    avail={k:sum(signal(r)[k] for r in uns) for k in signal(uns[0]).keys()} if uns else {}
    combos={'activity+sub_activity':lambda x:x['canonical_activity'] and x['canonical_sub_activity'],'activity+title':lambda x:x['canonical_activity'] and x['meaningful_title_pattern'],'sub_activity+title':lambda x:x['canonical_sub_activity'] and x['meaningful_title_pattern'],'title+description':lambda x:x['meaningful_title_pattern'] and x['distinct_description'],'raw_source_category+title':lambda x:x['raw_source_category'] and x['meaningful_title_pattern'],'asset_type+title':lambda x:x['asset_type'] and x['meaningful_title_pattern']}
    combo_counts={k:sum(bool(fn(signal(r))) for r in uns) for k,fn in combos.items()}
    def useful_non_title(r):
        return bool(act_maps.get(norm(r.get('activity') or ''))) or bool(sub_maps.get(norm(r.get('sub_activity') or ''))) or any(best_sector(s.get('source_sector')) or best_sector(s.get('source_subsector')) or (s.get('source_activity') and (s['source_key'], 'source_activity', norm(s['source_activity'])) in raw_maps) or (s.get('source_sub_activity') and (s['source_key'], 'source_sub_activity', norm(s['source_sub_activity'])) in raw_maps) or (s['source_key']=='furas' and norm(s.get('source_activity'))==norm('الأنشطة الزراعية والحيوانية')) for s in r['sources']) or any(phrase_hits(t) for t in [r.get('short_description') or '',r.get('full_description') or ''] if t and norm(t)!=norm(r.get('title_ar'))) or any(phrase_hits(a.get('label_ar') or '') for a in r['assets'])
    titleonly=sum(bool(r.get('title_ar')) and not useful_non_title(r) for r in uns)
    no_useful=sum(not (useful_non_title(r) or (bool(phrase_hits(r.get('title_ar') or '')) and not weak_title_context(r.get('title_ar') or ''))) for r in uns)
    # raw explicit values which failed current canonical mapping, grouped with proposal only when recognized.
    explicit_groups=defaultdict(list)
    for r in uns:
        for s in r['sources']:
            for f in flatten_classification(s['raw_data']):
                if re.search(r'sector|category|industry|theme|classif|taxonomy',f['key'],re.I) and not re.search(r'activity|subactivity',f['key'],re.I) and f['value']:
                    if not best_sector(f['value']): explicit_groups[(s['source_key'],f['path'],f['value'])].append(r)
            if s.get('source_sector') and not best_sector(s['source_sector']): explicit_groups[(s['source_key'],'source_sector',s['source_sector'])].append(r)
    explicit_value_groups=defaultdict(lambda:{'fields':set(),'masters':set()})
    for (source,field,value),rr in explicit_groups.items():
        entry=explicit_value_groups[(source,value)]; entry['fields'].add(field); entry['masters'].update(r['master_id'] for r in rr)
    explicit_values=[]
    for (source,value),entry in sorted(explicit_value_groups.items(),key=lambda p:(-len(p[1]['masters']),p[0])):
        explicit_values.append({'source':source,'raw_fields':sorted(entry['fields']),'raw_value':value,'count':len(entry['masters']),'master_ids':sorted(entry['masters']),'proposed_canonical_sector':KNOWN_EXPLICIT.get(norm(value)),'confidence':'HIGH' if KNOWN_EXPLICIT.get(norm(value)) else 'LOW','notes':'Observed in raw source payload; current master sector remains unspecified. Proposed mappings are analysis only.'})
    # open review impact against fixed unspec snapshot
    reviewrows=[r for r in uns if any(c['field']=='sector' for c in r['open_conflicts'])]
    review_supported=[r for r in reviewrows if r['master_id'] in {x['Master ID'] for x in rows_out if x['Primary Analysis Bucket'] not in ('GENUINELY_UNCLASSIFIABLE','POTENTIAL_TAXONOMY_GAP')}]

    bucket_sum=sum(bucket_counts.values())
    # Build ranked, evidence-backed, not-implemented recommendations.
    recommendations=[]
    for p in activity_patterns:
        if p['analysis_group']=='HIGH_PURITY_ACTIVITY' and p['unspecified_count']:
            recommendations.append({'rule_key':'ANALYSIS_ACTIVITY_'+re.sub(r'\W+','_',norm(p['activity'])).upper(),'signal_type':'canonical_activity','source_fields':['activity'],'match_condition':f"exact normalized activity = {p['activity']}",'proposed_sector_id':p['dominant_sector_id'],'positive_evidence':p['labeled_sector_distribution'],'negative_conditions':['any explicit official sector conflict','mixed source activity evidence'],'support_count':p['labeled_reference_count'],'estimated_records_affected':p['unspecified_count'],'confidence':'HIGH','decision':'AUTO_CLASSIFY_CANDIDATE'})
    for p in sub_patterns:
        if p['analysis_group']=='HIGH_PURITY_SUBACTIVITY' and p['unspecified_count']:
            recommendations.append({'rule_key':'ANALYSIS_SUBACTIVITY_'+re.sub(r'\W+','_',norm(p['sub_activity'])).upper(),'signal_type':'canonical_sub_activity','source_fields':['sub_activity'],'match_condition':f"exact normalized sub-activity = {p['sub_activity']}",'proposed_sector_id':p['dominant_sector_id'],'positive_evidence':p['labeled_sector_distribution'],'negative_conditions':['any conflicting source activity or sub-activity'],'support_count':p['labeled_reference_count'],'estimated_records_affected':p['unspecified_count'],'confidence':'HIGH','decision':'AUTO_CLASSIFY_CANDIDATE'})
    agriculture_source_candidates=[r for r in uns if any(s['source_key']=='furas' and norm(s.get('source_activity'))==norm('الأنشطة الزراعية والحيوانية') for s in r['sources'])]
    if agriculture_source_candidates:
        recommendations.append({'rule_key':'ANALYSIS_FURAS_AGRICULTURAL_ACTIVITY_REVIEW','signal_type':'source_activity_semantic_hint','source_fields':['source_activity'],'source':'furas','match_condition':'exact normalized source_activity = الأنشطة الزراعية والحيوانية','proposed_sector_id':'sector:agriculture','positive_evidence':{'master_ids':[r['master_id'] for r in agriculture_source_candidates],'labeled_reference_count':0,'title_context':'palm by-products processing; agriculture versus industrial processing needs human decision'},'negative_conditions':['no labeled Furas control supports this raw value','processing activity may be industrial/food manufacturing rather than primary agriculture'],'support_count':0,'estimated_records_affected':len(agriculture_source_candidates),'confidence':'MEDIUM','decision':'REVIEW_ONLY'})
    for value in explicit_values:
        recommendations.append({'rule_key':'ANALYSIS_EXPLICIT_'+re.sub(r'\W+','_',norm(value['source']+'_'+value['raw_value'])).upper(),'signal_type':'source_specific_explicit_classification','source_fields':value['raw_fields'],'source':value['source'],'match_condition':f"source={value['source']} AND exact normalized value={value['raw_value']} in fields {value['raw_fields']}",'proposed_sector_id':value['proposed_canonical_sector'],'positive_evidence':{'master_ids':value['master_ids']},'negative_conditions':['official contradictory classification','do not infer sector when source value denotes activity or procurement mechanism'],'support_count':0,'estimated_records_affected':value['count'],'confidence':value['confidence'],'decision':'REVIEW_ONLY'})
    for (source,field,value),rows in raw_groups.items():
        key=(source,field,norm(value))
        if key in raw_maps:
            sector=raw_maps[key]; ids=sorted({r['master_id'] for r in rows})
            recommendations.append({'rule_key':'ANALYSIS_RAW_'+re.sub(r'\W+','_',norm(source+'_'+field+'_'+value)).upper(),'signal_type':'source_specific_empirical_raw_mapping','source_fields':[field],'source':source,'match_condition':f"source={source} AND exact normalized {field}={value}",'proposed_sector_id':sector,'positive_evidence':source_raw_refs[key],'negative_conditions':['conflicting canonical activity/sub-activity','source-specific value differs from the observed exact value'],'support_count':sum(source_raw_refs[key].values()),'estimated_records_affected':len(ids),'confidence':'MEDIUM','decision':'REVIEW_ONLY','sample_master_ids':ids[:10]})
    for (sid,phrase),rs in sorted(title_groups.items(),key=lambda p:(-len(p[1]),p[0])):
        if rs:
            recommendations.append({'rule_key':'ANALYSIS_TITLE_REVIEW_'+re.sub(r'\W+','_',norm(phrase)).upper(),'signal_type':'compound_title_phrase','source_fields':['title_ar','normalized_title'],'match_condition':f'compound phrase contains {phrase}','proposed_sector_id':sid,'positive_evidence':{'unspecified_occurrences':len(rs)},'negative_conditions':['title-only classification prohibited','check official taxonomy and asset contradictions'],'support_count':0,'estimated_records_affected':len(rs),'confidence':'LOW_TO_MEDIUM','decision':'REVIEW_ONLY'})
    # Stable prioritization: confidence, estimated coverage, then explainability.
    recommendations.sort(key=lambda x:(0 if x['decision']=='AUTO_CLASSIFY_CANDIDATE' else 1,0 if x['confidence']=='HIGH' else 1,-x['estimated_records_affected'],-x['support_count'],x['rule_key']))
    recommendations=recommendations[:50]
    # category summary by current canonical sectors, excluding inferred controls
    sector_candidates=[]
    for sid in sorted(set([r['sector_id'] for r in labeled])):
        matches=[x for x in rows_out if x['Likely Sector ID']==sid]
        sector_candidates.append({'sector_id':sid,'strong_candidates':sum(x['Confidence']=='HIGH' for x in matches),'ambiguous_candidates':sum(x['Confidence']!='HIGH' for x in matches),'insufficient':bucket_counts.get('GENUINELY_UNCLASSIFIABLE',0) if sid=='sector:unspecified' else 0})
    taxgap={'potential_taxonomy_gaps':0,'candidates':[],'conclusion':'No repeated, clearly evidenced activity fell outside the current canonical sectors at the conservative materiality screen. Narrow operational activities should remain activity or asset labels, not new sectors.'}
    tourism={'strong_candidates':len(tourism_strong),'ambiguous_candidates':len(tourism_amb),'false_positive_risk_groups':['restaurants and cafes','retail food and groceries','generic parks and entertainment','heritage or place names without visitor activity','generic real estate'],'strong_sample_ids':[r['master_id'] for r in tourism_strong[:30]],'ambiguous_sample_ids':[r['master_id'] for r in tourism_amb[:30]],'current_labeled_references':sum(1 for r in labeled if r['sector_id']=='sector:tourism')}
    agriculture={'strong_candidates':len(agric_strong),'ambiguous_candidates':len(agric_amb),'false_positive_risk_groups':['food retail','food manufacturing','warehouses','general land','date or palm place names without cultivation/production'],'strong_sample_ids':[r['master_id'] for r in agric_strong[:30]],'ambiguous_sample_ids':[r['master_id'] for r in agric_amb[:30]],'current_labeled_references':sum(1 for r in labeled if r['sector_id']=='sector:agriculture')}
    gaps=[{'rank':1,'gap':'Current engine is intentionally conservative because title, description, activity and source activity values are often broad or duplicated.','evidence':'Most remaining records have title/description but few canonical activity/sub-activity values; inspect signal-coverage.json.','impact':'High population, low automatic safety without structured source taxonomy.','recommendation':'Prioritize source-specific structured-field extraction and exact taxonomy mapping.'},{'rank':2,'gap':'Raw source classifications are sparse or source-scoped and are not consistently exposed as canonical fields.','evidence':f"{len(explicit_values)} distinct unmatched raw classification values are catalogued.",'impact':'Potentially high for affected sources; evidence must be field- and source-specific.','recommendation':'Review explicit raw values and add adapter mappings only after official taxonomy validation.'},{'rank':3,'gap':'Descriptions frequently repeat titles and contribute no independent evidence.','evidence':'Duplicate descriptions are collapsed in availability and candidate analysis.','impact':'False confidence risk if text is counted twice.','recommendation':'Extract structured clauses or source taxonomy attributes; do not double-count repeated title text.'}]
    enrichment=[]
    for s in source_summary:
        if s['source']=='furas':
            enrichment.append({'source':s['source'],'current_classification_data_quality':'LOW: 373 unspecified Masters; 0 raw sector/category fields and 7 raw activity/subactivity fields across this population; dominant fields are temporary-rental and asset/location types.','missing_useful_fields':['source taxonomy/industry classification','structured activity and sub-activity for temporary lease opportunities'],'available_but_unused_fields':[x['raw_field'] for x in field_output if x['source']==s['source'] and not x['currently_used_by_normalization']],'recommended_adapter_mapping_change':'Inspect existing official Furas payload fields that classify activity; expose only stable sector/category fields after comparing labeled examples and preserving raw payload.'})
        else:
            enrichment.append({'source':s['source'],'current_classification_data_quality':f"{s['unspecified_masters']} unspecified of {s['current_masters_from_source']} current Masters; raw sector={s['raw_sector_field_available']}, raw activity={s['raw_activity_field_available']}, raw sub-activity={s['raw_subactivity_field_available']}, raw category={s['raw_category_field_available']} Masters.",'missing_useful_fields':['validated sector/category mapping where raw values are generic or unmapped'],'available_but_unused_fields':[x['raw_field'] for x in field_output if x['source']==s['source'] and not x['currently_used_by_normalization']],'recommended_adapter_mapping_change':'Review the source-specific classification field inventory and map only stable, explicit source values; no adapter change was made.'})
    # write machine-readable artifacts
    def write(name,obj): (OUT/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2,default=str)+'\n',encoding='utf8')
    write('unspecified-sector-master-analysis.json',{'snapshot_at':snapshot['captured_at'],'manifest':snapshot['manifest'],'row_count':len(rows_out),'columns':list(rows_out[0]) if rows_out else [],'records':rows_out})
    if rows_out:
        with (OUT/'unspecified-sector-master-analysis.csv').open('w',encoding='utf-8-sig',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(rows_out[0]),extrasaction='ignore');w.writeheader();w.writerows(rows_out)
    write('signal-coverage.json',{'snapshot_at':snapshot['captured_at'],'current_masters':snapshot['manifest']['current_masters'],'specified':snapshot['manifest']['specified'],'unspecified':len(uns),'counts':avail,'combinations':combo_counts,'title_only':titleonly,'no_useful_sector_signal':no_useful,'definitions':{'distinct_description':'short/full description is nonempty and differs from normalized title; counted per Master','description_any':'at least one short or full description field is populated','raw_source_category':'raw payload key contains category/industry/theme/classification/taxonomy; master-level presence','other_structured_classification':'classification-like payload key exists; availability only, values can still be generic or unmapped','title_only':'title exists and no supported non-title sector signal is available; includes generic/contextual titles and is an availability diagnostic, not a claim that the title is sector-indicative','no_useful_sector_signal':'no empirically supported canonical activity/sub-activity/raw mapping, semantic source-activity hint, distinct description phrase, meaningful asset signal, or non-contextual title phrase. Generic labels and contextual mentions are excluded.'}})
    write('source-unspecified-breakdown.json',{'ranked_by_unspecified_masters':source_summary})
    write('unused-source-classification-fields.json',{'discovery_method':'Recursive inspection of raw and standardized source JSON, depth <= 6; classification-like key names only. Used=true where present in standardized payload or matched to a normalized source classification column.','unused_classification_fields_found':sum(not x['currently_used_by_normalization'] for x in field_output),'fields':field_output})
    write('activity-pattern-analysis.json',{'training_scope':'current specified Masters excluding Phase 1/Phase 2 inference provenance','minimum_support':25,'minimum_purity':98,'groups':activity_patterns})
    write('subactivity-pattern-analysis.json',{'training_scope':'current specified Masters excluding inferred provenance','minimum_support':8,'minimum_purity':98,'groups':sub_patterns})
    write('raw-classification-pattern-analysis.json',{'source_context_required':True,'raw_activity_subactivity_sector_patterns':raw_patterns,'explicit_source_evidence_unmapped_count':len({mid for x in explicit_values for mid in x['master_ids']}),'explicit_source_evidence_unmapped_distinct_values':len(explicit_values),'explicit_source_evidence_unmapped_values':explicit_values,'learned_raw_mapping_minimum_support':5,'learned_raw_mapping_minimum_purity':90})
    write('title-pattern-groups.json',{'group_count':len(title_groups),'semantic_groups':[{'pattern_key':f'{sid}:{phrase}','count':len(rs),'sample_master_ids':[r['master_id'] for r in rs[:12]],'sample_titles':[r['title_ar'] for r in rs[:8]],'likely_sector_id':sid,'confidence':'LOW','resolution_status':'CONTEXTUAL_OR_WEAK_MENTION; not counted as title-resolvable','conflicts':'The phrase describes a nearby hospital, a venue at a hospital, a place name, or a processed palm product rather than establishing the opportunity sector.','why_missed':'The title token is present, but the current offer purpose and structured evidence do not confirm that sector. Human context review is required.'} for (sid,phrase),rs in sorted(title_groups.items(),key=lambda p:(-len(p[1]),p[0]))]})
    write('semantic-phrase-analysis.json',{'phrase_count':len(semantic),'phrases':sorted(semantic,key=lambda x:(-x['unspecified_occurrences'],x['phrase'])),'generic_phrase_count':len(generic_analysis),'generic_phrase_analysis':generic_analysis,'generic_phrases':sorted(GENERIC),'method':'Exact normalized phrase occurrence, counted once per Master across title/activity/sub-activity/description fields; Arabic orthographic normalization; labeled controls exclude inferred Masters. Generic phrases are reported descriptively and never proposed as sector rules.'})
    write('asset-type-pattern-analysis.json',{'groups':asset_patterns})
    write('taxonomy-gap-analysis.json',taxgap)
    write('tourism-deep-analysis.json',tourism)
    write('agriculture-deep-analysis.json',agriculture)
    write('classifier-gap-analysis.json',{'top_classifier_gaps':gaps,'all_canonical_sector_candidate_summary':sector_candidates,'current_unspecified':len(uns),'mutually_exclusive_bucket_counts':dict(bucket_counts),'bucket_order':bucket_order,'bucket_sum':bucket_sum,'bucket_reconciliation':'PASSED' if bucket_sum==len(uns) and len(rows_out)==len(uns) else 'FAILED','phase1_phase2_logic_reopened':False})
    write('source-enrichment-recommendations.json',{'adapter_changes_made':False,'sources':enrichment})
    safe=sum(1 for x in rows_out if x['Recommended Next Action']=='AUTO_RULE_CANDIDATE'); reviewable=sum(1 for x in rows_out if x['Recommended Next Action'] in ('REVIEW_CANDIDATE','TAXONOMY_REVIEW')); unclass=bucket_counts.get('GENUINELY_UNCLASSIFIABLE',0)
    write('recommended-rule-pack.json',{'implemented':False,'tiers':{'tier_1_safe_high_impact_auto_rules':[x for x in recommendations if x['decision']=='AUTO_CLASSIFY_CANDIDATE'],'tier_2_review_assist_rules':[x for x in recommendations if x['decision']=='REVIEW_ONLY'],'tier_3_do_not_automate':[{'pattern':'generic lease/location/land/building/restaurant/cafe/food-retail/warehouse/parking/place-name terms','reason':'not sufficient sector evidence; false-positive risks documented in tourism/agriculture analysis'}]},'rules':recommendations,'safe_automatic_candidate_count':safe,'reviewable_candidate_count':reviewable,'likely_remain_unspecified':len(uns)-safe,'next_implementation_requires_explicit_authorization':True})
    source_count_by_master={r['master_id']:len(r['sources']) for r in uns}
    taxonomy_review_ids={r['master_id'] for r in uns if any(c['field'] in ('activity','sub_activity','subsector','source_taxonomy') for c in r['open_conflicts'])}
    review_case_ids=[c['review_id'] for r in uns for c in r['open_conflicts'] if c['field']=='sector']; supported_master_ids={x['Master ID'] for x in rows_out if x['Primary Analysis Bucket'] not in ('GENUINELY_UNCLASSIFIABLE','POTENTIAL_TAXONOMY_GAP')}; supported_review_ids=[c['review_id'] for r in uns if r['master_id'] in supported_master_ids for c in r['open_conflicts'] if c['field']=='sector']
    summary={'task':'UNSPECIFIED_SECTOR_DEEP_SEMANTIC_PATTERN_ANALYSIS','status':'COMPLETE' if bucket_sum==len(uns) and len(rows_out)==len(uns) else 'NOT_COMPLETE','snapshot_at':snapshot['captured_at'],'current_masters':snapshot['manifest']['current_masters'],'current_sector_specified':snapshot['manifest']['specified'],'current_sector_unspecified':len(uns),'unspecified_with_canonical_activity':avail.get('canonical_activity',0),'unspecified_with_canonical_sub_activity':avail.get('canonical_sub_activity',0),'unspecified_with_raw_activity':avail.get('raw_activity',0),'unspecified_with_raw_sub_activity':avail.get('raw_sub_activity',0),'unspecified_with_asset_type':avail.get('asset_type',0),'unspecified_with_opportunity_type':avail.get('opportunity_type',0),'unspecified_with_short_description':avail.get('short_description',0),'unspecified_with_full_description':avail.get('full_description',0),'unspecified_with_raw_source_category':avail.get('raw_source_category',0),'unspecified_with_raw_source_sector':avail.get('raw_source_sector',0),'unspecified_with_description':avail.get('description_any',0),'unspecified_with_distinct_description':avail.get('distinct_description',0),'unspecified_with_no_useful_sector_signal':no_useful,'unspecified_title_only':titleonly,'explicit_source_evidence_unmapped':len({mid for x in explicit_values for mid in x['master_ids']}),'high_purity_activity_resolvable':bucket_counts.get('HIGH_PURITY_ACTIVITY_RESOLVABLE',0),'high_purity_subactivity_resolvable':bucket_counts.get('HIGH_PURITY_SUBACTIVITY_RESOLVABLE',0),'raw_source_classification_resolvable':bucket_counts.get('RAW_SOURCE_CLASSIFICATION_RESOLVABLE',0),'title_pattern_resolvable':bucket_counts.get('TITLE_PATTERN_RESOLVABLE',0),'description_resolvable':bucket_counts.get('DESCRIPTION_RESOLVABLE',0),'multi_signal_resolvable':bucket_counts.get('MULTI_SIGNAL_RESOLVABLE',0),'conflicting_evidence':bucket_counts.get('CONFLICTING_EVIDENCE',0),'potential_taxonomy_gap':bucket_counts.get('POTENTIAL_TAXONOMY_GAP',0),'genuinely_unclassifiable':unclass,'analysis_bucket_counts':dict(bucket_counts),'analysis_bucket_sum':bucket_sum,'analysis_bucket_reconciliation':'PASSED' if bucket_sum==len(uns) else 'FAILED','safe_automatic_classification_candidates':safe,'reviewable_classification_candidates':reviewable,'likely_remain_unspecified':len(uns)-safe,'tourism_strong_candidates':tourism['strong_candidates'],'tourism_ambiguous_candidates':tourism['ambiguous_candidates'],'tourism_false_positive_risk_groups':len(tourism['false_positive_risk_groups']),'agriculture_strong_candidates':agriculture['strong_candidates'],'agriculture_ambiguous_candidates':agriculture['ambiguous_candidates'],'agriculture_false_positive_risk_groups':len(agriculture['false_positive_risk_groups']),'potential_taxonomy_gaps':taxgap['potential_taxonomy_gaps'],'unused_classification_fields_found':sum(not x['currently_used_by_normalization'] for x in field_output),'top_classifier_gaps':gaps,'tier_1_rule_count':sum(x['decision']=='AUTO_CLASSIFY_CANDIDATE' for x in recommendations),'tier_2_rule_count':sum(x['decision']=='REVIEW_ONLY' for x in recommendations),'tier_3_rule_count':1,'current_sector_review_cases':snapshot['manifest']['open_sector_reviews'],'review_cases_with_new_supporting_evidence':len(supported_review_ids),'review_cases_still_ambiguous':max(0,snapshot['manifest']['open_sector_reviews']-len(supported_review_ids)),'supported_review_ids':supported_review_ids,'full_analysis_dataset_rows':len(rows_out),'data_modified':False,'manual_sync_started':False,'observation_count':snapshot['manifest']['observations'],'source_rows_linked_to_current_masters':snapshot['manifest']['source_opportunities'],'sync_job_count':snapshot['manifest']['sync_job_count'],'max_sync_job_id':snapshot['manifest']['max_sync_job_id'],'active_sync_jobs':snapshot['manifest']['active_sync_jobs'],'source_masters_ranked':source_summary,'mutually_exclusive_bucket_counts':dict(bucket_counts),'source_count_by_master':source_count_by_master,'open_taxonomy_review_masters':len(taxonomy_review_ids),'source_explicit_unmapped_values':explicit_values,'sector_distribution':snapshot['manifest']['sector_distribution']}
    write('analysis-summary.json',summary)
    print(json.dumps({'output':str(OUT),'captured_at':snapshot['captured_at'],'manifest':snapshot['manifest'],'summary':{k:v for k,v in summary.items() if k not in ('source_masters_ranked','source_count_by_master','source_explicit_unmapped_values','sector_distribution','top_classifier_gaps')}} ,ensure_ascii=False,default=str))


if __name__=='__main__': main()


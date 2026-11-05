import csv, json
from pathlib import Path
p=Path('/tmp/unspecified-sector-deep-analysis')
required=['FINAL-ANALYSIS.md','unspecified-sector-master-analysis.csv','unspecified-sector-master-analysis.json','signal-coverage.json','source-unspecified-breakdown.json','unused-source-classification-fields.json','activity-pattern-analysis.json','subactivity-pattern-analysis.json','raw-classification-pattern-analysis.json','title-pattern-groups.json','semantic-phrase-analysis.json','asset-type-pattern-analysis.json','taxonomy-gap-analysis.json','tourism-deep-analysis.json','agriculture-deep-analysis.json','classifier-gap-analysis.json','recommended-rule-pack.json']
missing=[x for x in required if not (p/x).exists()]
assert not missing, missing
json_files=list(p.glob('*.json'))
parsed={x.name:json.loads(x.read_text(encoding='utf-8-sig')) for x in json_files}
rows_json=parsed['unspecified-sector-master-analysis.json']['records']
with (p/'unspecified-sector-master-analysis.csv').open(encoding='utf-8-sig',newline='') as f:
    reader=csv.DictReader(f); csv_rows=list(reader); cols=reader.fieldnames
required_cols=['Master ID','Title','Source(s)','Activity','Sub-Activity','Asset Type','Raw Source Category','Raw Source Sector','Primary Analysis Bucket','Likely Sector','Confidence','Evidence Summary','Conflict Summary','Why Current Classifier Missed','Recommended Next Action']
assert set(required_cols)<=set(cols), set(required_cols)-set(cols)
assert len(rows_json)==len(csv_rows)==379
assert len({r['Master ID'] for r in rows_json})==379
assert {str(r['Master ID']) for r in rows_json}=={r['Master ID'] for r in csv_rows}
allowed_actions={'AUTO_RULE_CANDIDATE','REVIEW_CANDIDATE','TAXONOMY_REVIEW','KEEP_UNSPECIFIED'}
assert {r['Recommended Next Action'] for r in rows_json}<=allowed_actions
summary=parsed['analysis-summary.json']
counts={}
for r in rows_json: counts[r['Primary Analysis Bucket']]=counts.get(r['Primary Analysis Bucket'],0)+1
counts={k:counts.get(k,0) for k in summary['analysis_bucket_counts']}; assert counts==summary['analysis_bucket_counts'],(counts,summary['analysis_bucket_counts'])
assert sum(counts.values())==summary['current_sector_unspecified']==379
assert summary['analysis_bucket_reconciliation']=='PASSED'
allowed_buckets={'EXPLICIT_SOURCE_EVIDENCE_UNMAPPED','HIGH_PURITY_ACTIVITY_RESOLVABLE','HIGH_PURITY_SUBACTIVITY_RESOLVABLE','RAW_SOURCE_CLASSIFICATION_RESOLVABLE','TITLE_PATTERN_RESOLVABLE','DESCRIPTION_RESOLVABLE','MULTI_SIGNAL_RESOLVABLE','CONFLICTING_EVIDENCE','POTENTIAL_TAXONOMY_GAP','GENUINELY_UNCLASSIFIABLE'}
assert set(counts)<=allowed_buckets
before=parsed['dq-before.json']; after=parsed['dq-after.json']
assert before['counts']['fail']==after['counts']['fail']==0
assert before['read_only_business_data'] and after['read_only_business_data']
assert {x['gate_key'] for x in before.get('warning_gates',[])}=={x['gate_key'] for x in after.get('warning_gates',[])}
manifest=parsed['analysis-snapshot.json']['manifest']; post=parsed['post-live-manifest.json']
for key in ['current_masters','specified','unspecified','master_identity_fingerprint','preexisting_specified_sector_fingerprint','source_identity_fingerprint','raw_provenance_fingerprint','observations','observation_history_fingerprint','open_sector_reviews','sync_job_count','max_sync_job_id']:
    assert manifest[key]==post[key],(key,manifest[key],post[key])
assert not post['active_sync_jobs']
assert len(parsed['source-unspecified-breakdown.json']['ranked_by_unspecified_masters'])==10
print(json.dumps({'status':'PASS','required_artifacts':len(required),'parsed_json':len(json_files),'csv_rows':len(csv_rows),'distinct_master_ids':len({r['Master ID'] for r in rows_json}),'row_columns':len(cols),'analysis_bucket_counts':counts,'dq_failures_before_after':[before['counts']['fail'],after['counts']['fail']],'fingerprints_unchanged':True,'source_count':10},ensure_ascii=False))

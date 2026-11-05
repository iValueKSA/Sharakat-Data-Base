import csv,json
from pathlib import Path
p=Path('docs/validation/data/master-identity-duplicate-matching')
d=json.loads((p/'identity-analysis-pre.json').read_text(encoding='utf-8'))
raw={(min(x['master_a'],x['master_b']),max(x['master_a'],x['master_b'])):x for x in d['candidate_pairs']}
pre=json.loads((p/'snapshot-pre-correction-live.json').read_text(encoding='utf-8'))
queued={tuple(sorted((c['left_opportunity_id'],c['right_opportunity_id']))) for c in pre['duplicate_candidates'] if c['status']=='PENDING'}
same=json.loads((p/'same-source-identity-screen.json').read_text(encoding='utf-8'))
review={tuple(sorted((x['master_a'],x['master_b']))) for x in same.get('same_source_review_required',[])}
print('raw',len(raw),'queuepre',len(queued),'queue intersect',len(set(raw)&queued),'same review',len(review),'same review intersect',len(set(raw)&review),'union',len(set(raw)|queued|review))
print('new reviews in raw',[(a,b,(min(a,b),max(a,b)) in raw) for a,b in [(155,156),(155,159),(156,159),(157,160),(158,161),(163,254),(197,198),(263,264),(107,186),(107,187)]])
from collections import Counter
print('raw_pair_true_source',sum(any(e.get('same_source') is True for e in x.get('evidence',[])) for x in d['candidate_pairs']))
print('raw_pair_false_source',sum(any(e.get('same_source') is False for e in x.get('evidence',[])) for x in d['candidate_pairs']))
print('raw_pair_no_source_flag',sum(not x.get('evidence') or all('same_source' not in e for e in x['evidence']) for x in d['candidate_pairs']))


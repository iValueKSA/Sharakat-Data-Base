import json
p='docs/validation/data/master-identity-duplicate-matching/'
d=json.load(open(p+'identity-analysis-pre.json',encoding='utf-8'))
for x in d['candidate_pairs']:
 if not any('same_source' in e for e in x.get('evidence',[])):
  print(x['master_a'],x['master_b'],x['methods'],x['best_pair'].get('source_key_a'),x['best_pair'].get('source_key_b'),x['best_pair']['features'].get('plot_conflict'),x['best_pair']['features'].get('plot_match'),x['best_pair']['features'].get('title_similarity'))

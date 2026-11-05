import json
from collections import Counter
p='docs/validation/data/master-identity-duplicate-matching/'
d=json.load(open(p+'identity-analysis-pre.json',encoding='utf-8'))
c=Counter()
for x in d['candidate_pairs']:
 t=any(e.get('same_source') is True for e in x.get('evidence',[]))
 f=any(e.get('same_source') is False for e in x.get('evidence',[]))
 c[(t,f)]+=1
print(c)

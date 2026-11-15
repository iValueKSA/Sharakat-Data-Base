import json
p=r'C:\Users\QusaiAbdElhalim\OneDrive - iValue\Desktop\الشراكات - الأحساء\Sharakat-Data-Base\docs\validation\deployment\nationwide-geographic-expansion\baseline-20261101T071825Z\prechange-database-baseline.json'
with open(p,encoding='utf-8') as f:d=json.load(f)
print('root',list(d)[:30])
for k,v in d.items():
 if isinstance(v,list): print(k,'list',len(v), 'sample_keys',list(v[0])[:20] if v and isinstance(v[0],dict) else None)
 elif isinstance(v,dict): print(k,'dict',len(v),'sample_keys',list(v)[:20])

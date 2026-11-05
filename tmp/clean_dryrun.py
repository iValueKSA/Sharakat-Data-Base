import json
p='/tmp/rcjy_identity_dryrun.json'
t=open(p,encoding='utf-8').read()
obj,end=json.JSONDecoder().raw_decode(t.lstrip())
open('/tmp/rcjy_identity_dryrun_clean.json','w',encoding='utf-8').write(json.dumps(obj,ensure_ascii=False))
print('parsed_chars',end,'total_chars',len(t.lstrip()))
